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
    {"code": "ym", "name": "小道瓊", "nameEn": "E-mini Dow ($5)", "yahoo": "YM=F", "stooq": "ym.f", "cme": 318, "exchange": "CBOT YM"},
    {"code": "nq", "name": "小那斯達克", "nameEn": "E-mini Nasdaq-100", "yahoo": "NQ=F", "stooq": "nq.f", "cme": 146, "exchange": "CME NQ"},
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


def us_holidays(y):
    """美股／CME 股價指數期貨沒有日 K 的國定假日（NYSE 規則）。只用來判斷「應該要有哪一天」，避免假日誤報。"""
    def nth(month, weekday, n):  # 第 n 個星期幾；n = -1 代表最後一個
        if n > 0:
            d = dt.date(y, month, 1)
            d += dt.timedelta(days=(weekday - d.weekday()) % 7)
            return d + dt.timedelta(weeks=n - 1)
        d = dt.date(y, month + 1, 1) - dt.timedelta(days=1)
        return d - dt.timedelta(days=(d.weekday() - weekday) % 7)
    def observed(d):
        return d - dt.timedelta(days=1) if d.weekday() == 5 else d + dt.timedelta(days=1) if d.weekday() == 6 else d
    a = y % 19; b, c = divmod(y, 100); d_, e = divmod(b, 4); f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d_ - g + 15) % 30; i, k = divmod(c, 4); l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451; month, day = divmod(h + l - 7 * m + 114, 31)
    easter = dt.date(y, month, day + 1)
    return {observed(dt.date(y, 1, 1)), nth(1, 0, 3), nth(2, 0, 3), easter - dt.timedelta(days=2), nth(5, 0, -1),
            observed(dt.date(y, 6, 19)), observed(dt.date(y, 7, 4)), nth(9, 0, 1), nth(11, 3, 4), observed(dt.date(y, 12, 25))}


def expected_date(now=None):
    """現在應該已經拿得到的最新交易日（已收盤、跳過週末與假日）。"""
    d = last_closed_date(now)
    while d.weekday() >= 5 or d in us_holidays(d.year):
        d -= dt.timedelta(days=1)
    return d.isoformat()


def stored_dates(outdir):
    out = {}
    for s in SYMBOLS:
        p = os.path.join(outdir, s["code"] + ".enc.json")
        out[s["code"]] = json.load(open(p)).get("lastDate", "") if os.path.exists(p) else ""
    return out


def gh_output(**kv):
    p = os.environ.get("GITHUB_OUTPUT")
    if p:
        with open(p, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def check():
    """確認：網站上的資料是否已經到最新交易日。只讀日期，不需要密碼、不抓資料。"""
    exp = expected_date()
    have = stored_dates(os.path.join(ROOT, "data", "futures"))
    behind = [c for c, d in have.items() if d < exp]
    log(f"應有的最新交易日 {exp}；目前資料 {have}；" + ("落後：" + ",".join(behind) if behind else "已是最新"))
    gh_output(stale="true" if behind else "false", expected=exp)
    return behind


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


MON = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}


def front_contract(d):
    """依換月慣例（到期前 8 天換）判斷某交易日的近月合約到期月 (年, 月)。"""
    x = dt.date.fromisoformat(d)
    for y in (x.year, x.year + 1):
        for m in (3, 6, 9, 12):
            if x < third_friday(y, m) - dt.timedelta(days=8):
                return (y, m)


def fetch_cme_settle(pid, d):
    """CME 官網每日結算價（官方）。回傳 {(年,月): (結算價, 成交量)}；被擋或沒資料就丟出錯誤。"""
    x = dt.date.fromisoformat(d)
    url = (f"https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/{pid}/FUT"
           f"?strategy=DEFAULT&tradeDate={x.month:02d}/{x.day:02d}/{x.year}&pageSize=50&isProtected&_t={int(time.time()*1000)}")
    h = dict(UA, **{"Accept": "application/json", "Referer": "https://www.cmegroup.com/"})
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        js = json.loads(r.read())
    out = {}
    for row in js.get("settlements", []):
        try:
            mon, yy = row["month"].split()
            v = float(str(row["settle"]).replace(",", "").rstrip("AB"))
            vol = int(str(row.get("volume") or row.get("estimatedVolume") or "0").replace(",", "") or 0)
            out[(2000 + int(yy), MON[mon])] = (v, vol)
        except Exception:  # noqa: BLE001
            continue
    if not out:
        raise RuntimeError("CME 沒有回傳結算價")
    return out


def check_cme(s, bars, n=5):
    """最近 n 個交易日：Yahoo 收盤 vs CME 官方結算價（近月合約）。只回傳差距，不印價格。"""
    res = []
    for b in bars[-n:]:
        try:
            st = fetch_cme_settle(s["cme"], b[0])
            fc = front_contract(b[0])
            if fc not in st:
                res.append({"date": b[0], "ok": None, "why": "CME 沒有近月合約資料"})
                continue
            settle = st[fc][0]
            r = abs(b[4] - settle) / settle
            res.append({"date": b[0], "ok": r <= TOL, "diffPct": round(r * 100, 3), "contract": f"{fc[0]}-{fc[1]:02d}"})
        except Exception as e:  # noqa: BLE001
            res.append({"date": b[0], "ok": None, "why": str(e)[:100]})
    return res


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
    try:
        cme = check_cme(s, bars)
    except Exception as e:  # noqa: BLE001
        cme = [{"ok": None, "why": str(e)[:100]}]
    log(f"  CME 官方結算價比對：{cme}")
    # Yahoo 最新一根的成交量常常還沒更新（會跟前一天一樣），先標成未知，隔天重抓會補上
    if len(bars) > 1 and bars[-1][5] == bars[-2][5]:
        bars[-1][5] = None
    for b in bars:
        if b[5] == 0:
            b[5] = None
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
        "cross": cross, "cme": cme, "flagged": flagged[-200:], "pending": pending,
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
        log("全部商品都抓取失敗")
    if dev:
        return
    # 確認：寫完之後再檢查一次是不是真的到最新交易日
    behind = check()
    if behind:
        msg = f"還沒更新到 {expected_date()}（{','.join(behind)}）：可能 Yahoo 還沒出資料，或抓取失敗"
        if os.environ.get("FINAL_TRY") == "1":
            sys.exit("✗ 今天最後一次嘗試仍失敗，" + msg)   # 讓 Actions 變紅燈，GitHub 會寄信通知
        log("… " + msg + "；稍後重試")
        sys.exit(75)  # 75 = 稍後重試（workflow 會依這個代碼重跑）


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        main()
