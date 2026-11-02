"""小道瓊（YM）、小那斯達克（NQ）期貨日 K 每日更新（GitHub Actions 執行，不經過 Claude）。

流程：
  1. 抓 Yahoo Finance 連續近月合約（YM=F、NQ=F）全部日 K（主來源）
  2. 抓 Stooq（ym.f、nq.f）日 K（備援，只用來交叉核對收盤價）
  3. 核對：OHLC 合理、日期不重複；新的一根收盤價兩來源差 > 0.1% → 先不發佈，列入「待確認」
  4. 壓縮 + AES-256-GCM 加密（金鑰由密碼經 PBKDF2-SHA256 推導），寫入 data/futures/<代號>.enc.json

密碼放在 GitHub Secret FUTURES_PASSWORD，程式從環境變數讀取；沒有密碼就停止，絕不寫出明文。
執行紀錄（公開 repo 的 Actions log 任何人都看得到）只印筆數、日期、核對結果，不印任何價格。

用法：
  FUTURES_PASSWORD=... python3 tools/futures_update.py            # 正式
  python3 tools/futures_update.py --dev-pubkey <PEM 檔>          # 開發檢查用：改用公鑰加密到 data/futures-dev/
資料誠實規則：價格只來自來源原值，不估計、不內插；推算的換月日在頁面上標明是推算。
"""
import base64, datetime as dt, json, os, sys, urllib.request, zlib, csv, io, time
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CT = ZoneInfo("America/Chicago")
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
SYMBOLS = [
    {"code": "ym", "name": "小道瓊", "nameEn": "E-mini Dow ($5)", "yahoo": "YM=F", "stooq": "ym.f", "exchange": "CBOT YM"},
    {"code": "nq", "name": "小那斯達克", "nameEn": "E-mini Nasdaq-100", "yahoo": "NQ=F", "stooq": "nq.f", "exchange": "CME NQ"},
]
TOL = 0.001  # 兩來源收盤價容許差距 0.1%


def log(*a):
    print(*a, flush=True)


def get(url, tries=3):
    err = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{url.split('?')[0]} 抓取失敗：{err}")


def cme_trade_date(ts):
    """Yahoo 的時間戳 → CME 交易日。夜盤 17:00 CT 開始的時間戳屬於隔天交易日。"""
    t = dt.datetime.fromtimestamp(ts, CT)
    d = t.date()
    if t.hour >= 17:
        d += dt.timedelta(days=1)
    return d


def last_closed_date(now=None):
    """已經收盤的最新交易日：CT 16:15 以後才算今天收完。"""
    now = now or dt.datetime.now(CT)
    d = now.date()
    return d if now.time() >= dt.time(16, 15) else d - dt.timedelta(days=1)


def fetch_yahoo(sym):
    """用 yfinance 抓（它會處理 Yahoo 的 cookie／crumb，直接打 API 常被 429 擋）。"""
    import yfinance as yf
    df = None
    for i in range(3):
        try:
            df = yf.Ticker(sym).history(period="max", interval="1d", auto_adjust=False, actions=False, raise_errors=True)
            if len(df):
                break
        except Exception as e:  # noqa: BLE001
            log(f"  Yahoo 第 {i+1} 次失敗：{str(e)[:120]}")
            time.sleep(10 * (i + 1))
    if df is None or not len(df):
        raise RuntimeError(f"Yahoo {sym} 抓不到資料")
    hours, bars = {}, {}
    for idx, r in df.iterrows():
        o, h, l, c, v = (r[k] for k in ("Open", "High", "Low", "Close", "Volume"))
        if any(x != x for x in (o, h, l, c)):  # NaN
            continue
        t = idx.to_pydatetime().astimezone(CT)
        hours[t.hour] = hours.get(t.hour, 0) + 1
        d = cme_trade_date(t.timestamp())
        bars[d.isoformat()] = [d.isoformat(), round(float(o), 4), round(float(h), 4), round(float(l), 4), round(float(c), 4), int(v or 0)]
    log(f"  Yahoo {sym}: {len(bars)} 根，時間戳小時分布(CT) {dict(sorted(hours.items()))}，原始時區 {df.index.tz}")
    return bars


def fetch_stooq(sym):
    raw = get(f"https://stooq.com/q/d/l/?s={sym}&i=d").decode("utf8", "replace")
    rows = list(csv.DictReader(io.StringIO(raw)))
    if not rows or "Close" not in rows[0]:
        raise RuntimeError("Stooq 回傳的不是日 K CSV（可能需要驗證或被擋）：" + raw[:80].replace("\n", " "))
    out = {r["Date"]: float(r["Close"]) for r in rows if r.get("Close") not in (None, "", "N/D")}
    log(f"  Stooq {sym}: {len(out)} 根")
    return out


def third_friday(y, m):
    d = dt.date(y, m, 15)
    return d + dt.timedelta(days=(4 - d.weekday()) % 7)


def roll_dates(first, last):
    """CME 股價指數期貨慣例：到期日（3/6/9/12 月第三個星期五）前 8 天換月。推算值，頁面會標明。"""
    out = []
    for y in range(int(first[:4]), int(last[:4]) + 2):
        for m in (3, 6, 9, 12):
            ex = third_friday(y, m)
            r = ex - dt.timedelta(days=8)
            if first <= r.isoformat() <= last:
                out.append({"date": r.isoformat(), "expiry": ex.isoformat(), "from": "HMUZ"[(m // 3) - 1] + str(y)[-2:]})
    return out


def in_roll_window(d):
    x = dt.date.fromisoformat(d)
    for m in (3, 6, 9, 12):
        for y in (x.year, x.year + 1):
            ex = third_friday(y, m)
            if ex - dt.timedelta(days=10) <= x <= ex:
                return True
    return False


def sane(b):
    _, o, h, l, c, v = b
    return h >= max(o, c) - 1e-9 and l <= min(o, c) + 1e-9 and min(o, h, l, c) > 0 and v >= 0


def build(s, prev):
    cutoff = last_closed_date().isoformat()
    y = fetch_yahoo(s["yahoo"])
    bars = [b for d, b in sorted(y.items()) if d <= cutoff]
    bad = [b[0] for b in bars if not sane(b)]
    bars = [b for b in bars if sane(b)]
    pending = [{"date": d, "reason": "待確認：開高低收不合理（最高價低於開/收盤或最低價高於開/收盤），沒有採用"} for d in bad]
    try:
        st = fetch_stooq(s["stooq"])
        cross = {"source": "Stooq", "ok": True}
    except Exception as e:  # noqa: BLE001
        st, cross = {}, {"source": "Stooq", "ok": False, "error": str(e)[:160]}
        log("  ⚠ Stooq 無法核對：", cross["error"])
    diffs, mism = [], []
    for b in bars:
        c2 = st.get(b[0])
        if c2:
            r = abs(b[4] - c2) / c2
            diffs.append(r)
            if r > TOL:
                mism.append((b[0], r))
    cross.update({"compared": len(diffs), "mismatch": len(mism),
                  "mismatchInRollWindow": sum(1 for d, _ in mism if in_roll_window(d)),
                  "maxDiffPct": round(max(diffs) * 100, 3) if diffs else None})
    # 新增的 K 棒（上次發佈之後的）若兩來源不一致且不在換月期間 → 先不發佈
    # 第一次建檔時，只對最近 7 天嚴格把關；更早的不一致列為「標記」，在頁面上公開說明
    last_pub = prev.get("lastDate") or (dt.date.fromisoformat(cutoff) - dt.timedelta(days=7)).isoformat()
    held = [d for d, r in mism if d > last_pub and not in_roll_window(d)]
    for d, r in mism:
        if d in held:
            pending.append({"date": d, "reason": f"待確認：Yahoo 與 Stooq 收盤價差 {r*100:.2f}%（超過 0.1%），這根 K 棒暫不發佈"})
    bars = [b for b in bars if b[0] not in held]
    if held:
        # 不能跳過中間一天：從第一個被擋的日期之後都先不放
        first = min(held)
        bars = [b for b in bars if b[0] < first]
    flagged = [{"date": d, "diffPct": round(r * 100, 2), "roll": in_roll_window(d)} for d, r in mism if d not in held]
    log(f"  採用 {len(bars)} 根：{bars[0][0]} ~ {bars[-1][0]}；交叉核對 {cross}；暫不發佈 {len(held)} 根")
    return {
        "code": s["code"], "name": s["name"], "nameEn": s["nameEn"], "exchange": s["exchange"],
        "source": {"n": "Yahoo Finance（" + s["yahoo"] + "，連續近月合約，未調整）", "url": f"https://finance.yahoo.com/quote/{s['yahoo']}/history"},
        "check": {"n": "Stooq（" + s["stooq"] + "）", "url": f"https://stooq.com/q/?s={s['stooq']}"},
        "fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "firstDate": bars[0][0], "lastDate": bars[-1][0],
        "cols": ["date", "open", "high", "low", "close", "volume"], "bars": bars,
        "rolls": roll_dates(bars[0][0], bars[-1][0]),
        "cross": cross, "flagged": flagged[-200:], "pending": pending,
    }


def pack(obj):
    return zlib.compress(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf8"), 9)


def encrypt_password(plain, password):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kp = json.load(open(os.path.join(ROOT, "data", "futures", "key.json")))
    salt = base64.b64decode(kp["salt"])
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=kp["iter"]).derive(password.encode("utf8"))
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, plain, None)
    return {"v": 1, "iv": base64.b64encode(iv).decode(), "ct": base64.b64encode(ct).decode()}


def encrypt_pubkey(plain, pem_path):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    pub = serialization.load_pem_public_key(open(pem_path, "rb").read())
    k = AESGCM.generate_key(256)
    iv = os.urandom(12)
    ek = pub.encrypt(k, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return {"ek": base64.b64encode(ek).decode(), "iv": base64.b64encode(iv).decode(), "ct": base64.b64encode(AESGCM(k).encrypt(iv, plain, None)).decode()}


def main():
    dev = sys.argv[sys.argv.index("--dev-pubkey") + 1] if "--dev-pubkey" in sys.argv else None
    pw = os.environ.get("FUTURES_PASSWORD", "")
    if not dev and len(pw) < 12:
        sys.exit("沒有設定 FUTURES_PASSWORD（或少於 12 字），停止：不會寫出未加密的資料。")
    outdir = os.path.join(ROOT, "data", "futures-dev" if dev else "futures")
    os.makedirs(outdir, exist_ok=True)
    failed = []
    for s in SYMBOLS:
        log(f"[{s['code']}] {s['name']}")
        path = os.path.join(outdir, s["code"] + ".enc.json")
        prev = json.load(open(path)) if os.path.exists(path) else {}
        try:
            data = build(s, prev)
        except Exception as e:  # noqa: BLE001
            log(f"  ✗ 失敗：{e}；保留上一版資料")
            failed.append(s["code"])
            continue
        if prev.get("lastDate") == data["lastDate"] and prev.get("pendingCount", 0) == len(data["pending"]):
            log("  沒有新的 K 棒，不更新檔案")
            continue
        body = encrypt_pubkey(pack(data), dev) if dev else encrypt_password(pack(data), pw)
        # 檔案外層只放不含價格的資訊（日期、筆數、待確認數），讓首頁在解鎖前也能顯示新鮮度
        out = {"code": s["code"], "name": s["name"], "lastDate": data["lastDate"], "firstDate": data["firstDate"],
               "bars": len(data["bars"]), "pendingCount": len(data["pending"]), "fetchedAt": data["fetchedAt"], **body}
        with open(path, "w") as f:
            json.dump(out, f, separators=(",", ":"))
        log(f"  ✓ 已寫入 {os.path.relpath(path, ROOT)}（加密）")
    if failed and len(failed) == len(SYMBOLS):
        sys.exit("全部商品都失敗")


if __name__ == "__main__":
    main()
