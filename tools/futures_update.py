"""小道瓊（YM）、小那斯達克（NQ）、大台指（TX）期貨日 K 每日更新（GitHub Actions 執行，不經過 Claude）。

大台指（TX）另走 build_tx()：資料來自臺灣期貨交易所官方「期貨每日交易行情」下載（一次最多查一個月），
只用「一般交易時段」（日盤 08:45–13:45），每天取近月合約（最早到期的單一月份合約，不含價差、週契約）。
第一次從 1998-07 抓完整歷史；之後解開上一版、只重抓最近約 45 天合併。換月日是實際換約的日子（不是推算）。
台灣假日無法事先算：抓取成功、而且已經過了隔天早上 07:00 仍沒有那一天，就當作休市（記在 checkedFor）。

YM／NQ 流程：
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
    {"code": "tx", "name": "大台指", "nameEn": "TAIEX Futures (TX)", "taifex": "TX", "exchange": "TAIFEX TX", "market": "TW"},
]
TPE = ZoneInfo("Asia/Taipei")
TAIFEX_URL = "https://www.taifex.com.tw/cht/3/futDataDown"
TX_FIRST = dt.date(1998, 7, 21)   # 台指期上市日
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


def tw_expected_date(now=None):
    """台灣：日盤 13:45 收盤，期交所下午公布；台北 16:30 以後才算今天有資料。只跳過週末（台灣假日由 checkedFor 處理）。"""
    now = now or dt.datetime.now(TPE)
    d = now.date() if now.time() >= dt.time(16, 30) else now.date() - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d.isoformat()


def tw_assume_closed(day, now=None):
    """抓取成功但沒有 day 這一天：已經過了隔天台北 07:00 就當作休市（颱風、春節等）；還沒過就稍後重試。"""
    now = now or dt.datetime.now(TPE)
    nxt = dt.datetime.combine(dt.date.fromisoformat(day) + dt.timedelta(days=1), dt.time(7, 0), TPE)
    return now >= nxt


def expected_for(s, now=None):
    if s.get("market") == "TW":
        return tw_expected_date(now.astimezone(TPE) if now else None)
    return expected_date(now.astimezone(CT) if now else None)


def stored_meta(outdir):
    out = {}
    for s in SYMBOLS:
        p = os.path.join(outdir, s["code"] + ".enc.json")
        out[s["code"]] = json.load(open(p)) if os.path.exists(p) else {}
    return out


def stored_dates(outdir):
    return {c: m.get("lastDate", "") for c, m in stored_meta(outdir).items()}


def behind_list(meta, now=None):
    """哪些商品落後：最新 K 棒早於應有日期，而且也還沒確認那天是休市（checkedFor）。"""
    out = []
    for s in SYMBOLS:
        m, exp = meta.get(s["code"], {}), expected_for(s, now)
        if max(m.get("lastDate", ""), m.get("checkedFor", "")) < exp:
            out.append(s["code"])
    return out


def gh_output(**kv):
    p = os.environ.get("GITHUB_OUTPUT")
    if p:
        with open(p, "a") as f:
            for k, v in kv.items():
                f.write(f"{k}={v}\n")


def check():
    """確認：網站上的資料是否已經到最新交易日。只讀日期，不需要密碼、不抓資料。"""
    meta = stored_meta(os.path.join(ROOT, "data", "futures"))
    exp = {s["code"]: expected_for(s) for s in SYMBOLS}
    have = {c: m.get("lastDate", "") for c, m in meta.items()}
    behind = behind_list(meta)
    newimp = [c for c, m in meta.items() if import_sha(c) and m.get("importSha", "") != import_sha(c)]
    log(f"應有的最新交易日 {exp}；目前資料 {have}；" + ("落後：" + ",".join(behind) if behind else "已是最新")
        + (f"；有新的 TradingView 匯入檔：{','.join(newimp)}" if newimp else ""))
    nokey = not (os.path.exists(IMPORT_PUB) and os.path.exists(IMPORT_KEY))
    if nokey:
        log("還沒有 TradingView 匯入用的金鑰，這一班會產生")
    gh_output(stale="true" if behind or newimp or nokey else "false", expected=exp["ym"])
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
    extra = None
    tv = load_import(s["code"])
    if tv:
        bars, extra, filled = merge_tv(bars, tv, bad)
        pending = [p for p in pending if p["date"] not in filled]
        if extra.get("rejected"):
            pending.append({"date": None, "reason": extra["rejected"]})
        log(f"  TradingView 補充：{ {k: v for k, v in extra.items() if k != 'dates'} }")
    log(f"  待確認日期：{[p['date'] for p in pending]}")
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
        "cross": cross, "cme": cme, "flagged": flagged[-200:], "pending": pending, "extra": extra,
    }


# ---------- 大台指（TAIFEX 官方每日行情） ----------
def taifex_csv(a, b, tries=3):
    """期交所「期貨每日交易行情」CSV（a、b 為 date，區間最多一個月）。回傳 list of rows（第一列為欄名）。"""
    import urllib.parse
    form = urllib.parse.urlencode({"down_type": "1", "commodity_id": "TX", "commodity_id2": "",
                                   "queryStartDate": a.strftime("%Y/%m/%d"), "queryEndDate": b.strftime("%Y/%m/%d")}).encode()
    err = None
    for i in range(tries):
        try:
            req = urllib.request.Request(TAIFEX_URL, data=form, headers=dict(UA, **{"Content-Type": "application/x-www-form-urlencoded"}))
            with urllib.request.urlopen(req, timeout=60) as r:
                raw, ct = r.read(), (r.headers.get("Content-Type") or "")
            if "MS950" not in ct.upper() and not raw.startswith("交易日期".encode("cp950")):
                raise RuntimeError("回傳的不是 CSV（可能查詢區間太長或網站維護）")
            return list(csv.reader(io.StringIO(raw.decode("cp950", "replace"))))
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"期交所 {a}~{b} 抓取失敗：{err}")


def num(x):
    x = (x or "").strip().replace(",", "")
    return None if x in ("", "-") else float(x)


def parse_taifex(rows):
    """CSV → {日期: (到期月, [date,o,h,l,c,v])}：只取一般交易時段、單一月份合約中最早到期的（近月）。
    近月那一列沒有成交（開高低收是「-」）→ 放進 missing，不改用別的月份。"""
    import re
    if not rows:
        return {}, []
    h = [x.strip() for x in rows[0]]
    ix = lambda name: next((i for i, x in enumerate(h) if x.startswith(name)), None)
    iD, iM, iO, iH, iL, iC, iV, iS = (ix(n) for n in ("交易日期", "到期月份", "開盤價", "最高價", "最低價", "收盤價", "成交量", "交易時段"))
    if None in (iD, iM, iO, iH, iL, iC, iV):
        raise RuntimeError("期交所 CSV 欄位和預期不同：" + ",".join(h[:12]))
    best = {}
    for r in rows[1:]:
        if len(r) <= max(iD, iM, iC, iV):
            continue
        if iS is not None and len(r) > iS and r[iS].strip() not in ("一般", ""):
            continue
        m = r[iM].strip()
        if not re.fullmatch(r"\d{6}", m):          # 價差（202611/202612）、週契約（202611W4）不要
            continue
        d = r[iD].strip().replace("/", "-")
        if d not in best or m < best[d][0]:
            best[d] = (m, r)
    out, missing = {}, []
    for d, (m, r) in best.items():
        o, hi, lo, c, v = num(r[iO]), num(r[iH]), num(r[iL]), num(r[iC]), num(r[iV])
        if None in (o, hi, lo, c):
            missing.append(d)
            continue
        out[d] = (m, [d, o, hi, lo, c, int(v or 0)])
    return out, missing


def month_ranges(a, b):
    """[a, b] 切成一個月一段（期交所一次最多查一個月）。"""
    cur = a
    while cur <= b:
        nxt = (cur.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        yield cur, min(b, nxt - dt.timedelta(days=1))
        cur = nxt


def tx_rolls(months):
    """實際換月日：近月合約和前一個交易日不同的那天。months = [(date, 到期月)] 依日期排序。"""
    out = []
    for (d0, m0), (d1, m1) in zip(months, months[1:]):
        if m1 != m0:
            out.append({"date": d1, "from": m0, "to": m1})
    return out


def decrypt_password(file, password):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kp = json.load(open(os.path.join(ROOT, "data", "futures", "key.json")))
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(kp["salt"]), iterations=kp["iter"]).derive(password.encode("utf8"))
    return json.loads(zlib.decompress(AESGCM(key).decrypt(base64.b64decode(file["iv"]), base64.b64decode(file["ct"]), None)))


def build_tx(s, prev, pw):
    today = dt.datetime.now(TPE).date()
    old, start, old_pend = {}, TX_FIRST, []
    if prev.get("ct"):
        try:
            p = decrypt_password(prev, pw)
            old = {b[0]: (m, b) for b, m in zip(p["bars"], p["months"])}
            start = dt.date.fromisoformat(p["lastDate"]) - dt.timedelta(days=45)
            old_pend = p.get("pending") or []
        except Exception as e:  # noqa: BLE001
            log(f"  上一版解不開（{str(e)[:60]}），重抓完整歷史")
            old = {}
    got, missing, n = {}, [], 0
    for a, b in month_ranges(start, today):
        part, miss = parse_taifex(taifex_csv(a, b))
        got.update(part); missing += miss; n += 1
        time.sleep(0.4)
    if not got:
        raise RuntimeError("期交所沒有回傳任何近月資料")
    log(f"  期交所：查 {n} 個月，取得 {len(got)} 天（{min(got)} ~ {max(got)}）")
    merged = dict(old); merged.update(got)
    rows = [merged[d] for d in sorted(merged)]
    bad = [b[0] for _, b in rows if not sane(b)]
    keep = [(m, b) for m, b in rows if sane(b)]
    pend_old = [x for x in old_pend if x["date"] < start.isoformat()]
    pending = [{"date": d, "reason": "待確認：開高低收不合理（最高價低於開/收盤或最低價高於開/收盤），沒有採用"} for d in bad]
    pending += [{"date": d, "reason": "待確認：期交所當天近月合約沒有開高低收（顯示「-」），沒有改用其他月份"} for d in sorted(set(missing)) if d not in merged]
    bars = [b for _, b in keep]
    for b in bars:
        if b[5] == 0:
            b[5] = None
    months = [m for m, _ in keep]
    log(f"  採用 {len(bars)} 根：{bars[0][0]} ~ {bars[-1][0]}；待確認 {len(pending)} 根")
    return {
        "code": s["code"], "name": s["name"], "nameEn": s["nameEn"], "exchange": s["exchange"], "market": "TW",
        "session": "日盤 08:45–13:45",
        "source": {"n": "臺灣期貨交易所 期貨每日交易行情（TX 近月合約，官方）", "url": "https://www.taifex.com.tw/cht/3/futDataDown"},
        "fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "firstDate": bars[0][0], "lastDate": bars[-1][0],
        "cols": ["date", "open", "high", "low", "close", "volume"], "bars": bars, "months": months,
        "rolls": tx_rolls(list(zip([b[0] for b in bars], months))),
        "pending": pend_old + pending,
    }, set(got)


# ---------- 匯入 TradingView 資料（補 Yahoo 沒有的早期歷史與缺漏日） ----------
# Claude 用 TradingView MCP 抓到的日 K，用公鑰加密成 data/futures/import/<代號>.tv.enc.json 放進 repo（公開 repo 只看得到密文）。
# 私鑰由 GitHub Actions 自己產生，用 FUTURES_PASSWORD 加密存在 data/futures/import.key.enc.json；只有 Actions 解得開。
# 合併規則（資料誠實）：先用重疊日子比對收盤價；對得上才採用，只補 Yahoo 第一天之前的 K 棒與中間缺漏／不合理的日子，
# 而且缺漏日前後各 3 個交易日兩邊收盤都要一致。對不起來的整份不採用，列入待確認。
IMPORT_DIR = os.path.join(ROOT, "data", "futures", "import")
IMPORT_PUB = os.path.join(ROOT, "data", "futures", "import.pub.pem")
IMPORT_KEY = os.path.join(ROOT, "data", "futures", "import.key.enc.json")
TV_TOL = 0.003  # TradingView 與 Yahoo 收盤價容許差距 0.3%


def ensure_import_key(pw):
    """還沒有匯入用的金鑰就產生一組（只在 Actions 執行，私鑰以密碼加密後才寫入）。"""
    if os.path.exists(IMPORT_PUB) and os.path.exists(IMPORT_KEY):
        return False
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    k = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    priv = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    with open(IMPORT_KEY, "w") as f:
        json.dump(encrypt_password(priv, pw), f)
    with open(IMPORT_PUB, "wb") as f:
        f.write(k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    log("  已產生 TradingView 匯入用的金鑰（公鑰 import.pub.pem；私鑰以密碼加密）")
    return True


def decrypt_password_raw(file, password):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kp = json.load(open(os.path.join(ROOT, "data", "futures", "key.json")))
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(kp["salt"]), iterations=kp["iter"]).derive(password.encode("utf8"))
    return AESGCM(key).decrypt(base64.b64decode(file["iv"]), base64.b64decode(file["ct"]), None)


def decrypt_hybrid(file, priv_pem):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives import serialization, hashes
    from cryptography.hazmat.primitives.asymmetric import padding
    priv = serialization.load_pem_private_key(priv_pem, password=None)
    k = priv.decrypt(base64.b64decode(file["ek"]), padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return AESGCM(k).decrypt(base64.b64decode(file["iv"]), base64.b64decode(file["ct"]), None)


def import_sha(code):
    import hashlib
    p = os.path.join(IMPORT_DIR, code + ".tv.enc.json")
    return hashlib.sha256(open(p, "rb").read()).hexdigest()[:16] if os.path.exists(p) else ""


def load_import(code):
    """解開 TradingView 匯入檔；沒有檔或解不開回傳 None（解不開會在 log 說明，不印內容）。"""
    p = os.path.join(IMPORT_DIR, code + ".tv.enc.json")
    pw = os.environ.get("FUTURES_PASSWORD", "")
    if not os.path.exists(p) or not os.path.exists(IMPORT_KEY) or len(pw) < 12:
        return None
    try:
        priv = decrypt_password_raw(json.load(open(IMPORT_KEY)), pw)
        return json.loads(zlib.decompress(decrypt_hybrid(json.load(open(p)), priv)))
    except Exception as e:  # noqa: BLE001
        log(f"  ⚠ TradingView 匯入檔解不開：{type(e).__name__}")
        return None


def tv_bars(tv, shift):
    """TradingView 欄位格式 → {日期: [date,o,h,l,c,v]}；shift = 時間戳的 UTC 日期要加幾天才是交易日。"""
    out = {}
    for t, o, h, l, c, v in zip(tv["t"], tv["o"], tv["h"], tv["l"], tv["c"], tv["v"]):
        d = (dt.datetime.fromtimestamp(t, dt.timezone.utc).date() + dt.timedelta(days=shift)).isoformat()
        b = [d, float(o), float(h), float(l), float(c), int(v or 0)]
        if sane(b):
            out[d] = b
    return out


def merge_tv(bars, tv, bad=()):
    """把 TradingView 補進 Yahoo 的日 K。回傳 (新 bars, 說明, 補上的日期集合)。"""
    ya = {b[0]: b for b in bars}
    best = None
    for shift in (0, 1, -1):
        tb = tv_bars(tv, shift)
        common = [d for d in ya if d in tb]
        if not common:
            continue
        diffs = sorted(abs(tb[d][4] - ya[d][4]) / ya[d][4] for d in common)
        ok = sum(1 for x in diffs if x <= TV_TOL)
        if best is None or ok > best[0]:
            best = (ok, shift, tb, common, diffs)
    info = {"n": f"TradingView（{tv.get('symbol', '')}）", "url": "https://www.tradingview.com/symbols/" + tv.get("symbol", "").replace(":", "-") + "/",
            "fetched": tv.get("fetched"), "prepended": 0, "filled": 0, "dates": []}
    if not best or len(best[3]) < 20 or best[4][len(best[4]) // 2] > TV_TOL or best[0] < 0.8 * len(best[3]):
        info["rejected"] = (f"待確認：TradingView 匯入資料與 Yahoo 重疊 {len(best[3]) if best else 0} 天，收盤價對不起來（或重疊太少），整份沒有採用")
        return bars, info, set()
    ok, shift, tb, common, diffs = best
    info.update(overlap=len(common), medianDiffPct=round(diffs[len(diffs) // 2] * 100, 3), shift=shift)
    yd = sorted(ya)
    first = yd[0]
    add = {d: b for d, b in tb.items() if d < first}
    agree = lambda d: d in tb and abs(tb[d][4] - ya[d][4]) / ya[d][4] <= TV_TOL
    import bisect
    filled = set()
    for d, b in tb.items():
        if d < first or d > yd[-1] or d in ya:
            continue
        i = bisect.bisect_left(yd, d)
        near = yd[max(0, i - 3):i] + yd[i:i + 3]
        if len(near) == 6 and all(agree(x) for x in near):
            add[d] = b
            filled.add(d)
    info["prepended"] = sum(1 for d in add if d < first)
    info["filled"] = len(filled)
    info["dates"] = sorted(add)
    info["bad"] = sorted(set(bad) & filled)
    merged = sorted(list(ya.values()) + list(add.values()), key=lambda b: b[0])
    return merged, info, filled


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
    if not dev:
        ensure_import_key(pw)
    failed = []
    for s in SYMBOLS:
        log(f"[{s['code']}] {s['name']}")
        path = os.path.join(outdir, s["code"] + ".enc.json")
        prev = json.load(open(path)) if os.path.exists(path) else {}
        checked = prev.get("checkedFor", "")
        try:
            if s.get("market") == "TW":
                if dev:
                    log("  開發模式不抓台指期")
                    continue
                data, seen = build_tx(s, prev, pw)
                exp = tw_expected_date()
                if exp not in seen and data["lastDate"] < exp and tw_assume_closed(exp):
                    checked = exp
                    log(f"  期交所沒有 {exp} 的資料，已過隔天早上，視為休市")
            else:
                data = build(s, prev)
        except Exception as e:  # noqa: BLE001
            log(f"  ✗ 失敗：{e}；保留上一版資料")
            failed.append(s["code"])
            continue
        same_imp = prev.get("importSha", "") == import_sha(s["code"])
        if same_imp and prev.get("lastDate") == data["lastDate"] and prev.get("firstDate") == data["firstDate"] and prev.get("pendingCount", 0) == len(data["pending"]):
            if checked != prev.get("checkedFor", ""):
                prev["checkedFor"] = checked
                with open(path, "w") as f:
                    json.dump(prev, f, separators=(",", ":"))
                log("  沒有新的 K 棒；記下已確認休市的日期")
            else:
                log("  沒有新的 K 棒，不更新檔案")
            continue
        body = encrypt_pubkey(pack(data), dev) if dev else encrypt_password(pack(data), pw)
        # 檔案外層只放不含價格的資訊（日期、筆數、待確認數），讓首頁在解鎖前也能顯示新鮮度
        out = {"code": s["code"], "name": s["name"], "lastDate": data["lastDate"], "firstDate": data["firstDate"],
               "bars": len(data["bars"]), "pendingCount": len(data["pending"]), "fetchedAt": data["fetchedAt"], **body}
        if checked > data["lastDate"]:
            out["checkedFor"] = checked
        if import_sha(s["code"]):
            out["importSha"] = import_sha(s["code"])
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
        msg = f"還沒更新到最新交易日（{','.join(behind)}）：可能來源還沒出資料，或抓取失敗"
        if os.environ.get("FINAL_TRY") == "1":
            sys.exit("✗ 今天最後一次嘗試仍失敗，" + msg)   # 讓 Actions 變紅燈，GitHub 會寄信通知
        log("… " + msg + "；稍後重試")
        sys.exit(75)  # 75 = 稍後重試（workflow 會依這個代碼重跑）


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        main()
