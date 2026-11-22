"""VIX（恐慌指數）每日收盤 → data/market/vix.json。只由 GitHub Actions（prices-daily）執行，Claude 不手填、不修改。

  python3 tools/vix_update.py                抓一次並寫檔（抓不到就保留舊檔，印原因，不讓整個工作變紅）
  python3 tools/vix_update.py --stale-check  最新一筆是不是太舊（超過 STALE_DAYS 天 → 結束碼 1，prices-daily 晚上那一班用）
  python3 tools/vix_update.py --probe        只試探兩個來源抓不抓得到，印頭尾幾行，不寫檔

來源（依序試，第一個成功的就用，檔案裡記下用了哪一個）：
  ① 芝加哥選擇權交易所（Cboe，VIX 的編製單位）公開的每日歷史檔（CSV，1990 年起）
  ② Yahoo Finance ^VIX 日線收盤（和個股每日收盤價同一個來源）
  兩個都抓：用「最新一筆日期比較新」的那個（一樣新用 ①），檔案裡記下用了哪一個；
  兩邊都有的最近一天互相核對，差超過 1% 就在 xcheck 記「待確認」。只抓到一個就用那一個。
首頁「市場情緒」那一行直接讀這個檔；總經儀表板的 VIX 另外來自 FRED（慢一個交易日左右，用來算方向燈）。
所有數字（比前一天、十年位置、52 週高低、落在哪個區間）都在這裡算好，頁面只畫。
區間門檻（20、30）是常見的經驗分界，頁面標「教學」，不是買賣訊號。
"""
import csv, datetime as dt, io, json, os, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "market", "vix.json")
CBOE_CSV = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
CBOE_PAGE = "https://www.cboe.com/tradable_products/vix/vix_historical_data/"
YAHOO_PAGE = "https://finance.yahoo.com/quote/%5EVIX/history/"
UA = "Mozilla/5.0 (prices-daily; +https://github.com/ZLO-25/Enterprise-Revenue-Dashboard)"
STALE_DAYS = 6          # 連假加週末最長也不會超過這麼多天沒有新的收盤
KEEP = 260              # 檔案裡保留最近幾個交易日（約一年），給首頁的小走勢線用
ZONES = {"calm": 20.0, "tense": 30.0}   # 20 以下平靜、30 以上很緊張（經驗分界，教學用）
LO, HI = 5.0, 150.0     # VIX 歷史上從沒離開過這個範圍；超出就當成資料壞掉，不採用


def log(*a):
    print(*a, flush=True)


def http_get(url, timeout=60):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
        return r.read().decode("utf-8-sig", "replace")


def parse_date(s):
    s = s.strip()
    for f in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, f).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"看不懂的日期：{s!r}")


def parse_cboe(text):
    """Cboe 的 CSV（表頭 DATE,OPEN,HIGH,LOW,CLOSE）→ [(日期, 收盤)]，依日期排序。表頭對不上就丟 ValueError。"""
    rows = list(csv.reader(io.StringIO(text)))
    head = None
    for i, r in enumerate(rows[:5]):
        cols = [c.strip().upper() for c in r]
        if "DATE" in cols and "CLOSE" in cols:
            head = (i, cols.index("DATE"), cols.index("CLOSE"))
            break
    if head is None:
        raise ValueError("Cboe 檔案找不到 DATE／CLOSE 表頭")
    i0, di, ci = head
    out = []
    for r in rows[i0 + 1:]:
        if len(r) <= max(di, ci) or not r[di].strip():
            continue
        out.append((parse_date(r[di]), float(r[ci])))
    return check(sorted(out))


def check(points):
    """基本合理性：至少一年的資料、日期不重複、數值在歷史範圍內。不合理就丟 ValueError（整份不採用）。"""
    if len(points) < 250:
        raise ValueError(f"資料太少（{len(points)} 筆）")
    ds = [d for d, _ in points]
    if len(set(ds)) != len(ds):
        raise ValueError("日期重複")
    bad = [(d, c) for d, c in points if not (LO <= c <= HI)]
    if bad:
        raise ValueError(f"數值超出合理範圍：{bad[:3]}")
    return points


def fetch_cboe():
    return parse_cboe(http_get(CBOE_CSV))


def us_session_open(now=None):
    """美股現貨這一天收盤了沒（VIX 算到美東 16:15）。還沒收盤時，Yahoo 當天那一筆是盤中值，不能當收盤。"""
    from zoneinfo import ZoneInfo
    et = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo("America/New_York"))
    return et.date().isoformat(), (et.weekday() < 5 and (et.hour, et.minute) < (16, 30))


def drop_unfinished(points, now=None):
    """排程常常晚好幾個小時才跑，可能落在美股盤中：把「美東今天」還沒收盤的那一筆拿掉。"""
    today_et, open_now = us_session_open(now)
    return [(d, c) for d, c in points if not (open_now and d >= today_et)]


def fetch_yahoo(now=None):
    import yfinance as yf
    df = yf.Ticker("^VIX").history(period="11y", auto_adjust=False, actions=False)
    out = [(i.date().isoformat(), float(c)) for i, c in df["Close"].items() if c == c]
    return check(drop_unfinished(sorted(out), now))


SOURCES = [
    ("Cboe 每日歷史檔（官方）", CBOE_PAGE, fetch_cboe),
    ("Yahoo Finance ^VIX 日線收盤", YAHOO_PAGE, fetch_yahoo),
]


def zone_of(c, zones=ZONES):
    return "calm" if c < zones["calm"] else ("tense" if c >= zones["tense"] else "mid")


def minus_years(d, n):
    y, m, day = int(d[:4]) - n, int(d[5:7]), int(d[8:10])
    if m == 2 and day == 29:
        day = 28
    return f"{y:04d}-{m:02d}-{day:02d}"


def build(points, source, url, now=None):
    """[(日期, 收盤)]（已排序）→ 要寫進檔案的內容。"""
    now = now or dt.datetime.now(dt.timezone.utc)
    (d1, c1), (d0, c0) = points[-1], points[-2]
    w10 = [c for d, c in points if d > minus_years(d1, 10)]
    w52 = [(d, c) for d, c in points if d > minus_years(d1, 1)]
    hi, lo = max(w52, key=lambda x: x[1]), min(w52, key=lambda x: x[1])
    med = sorted(w10)[len(w10) // 2]
    return {
        "updated": now.strftime("%Y-%m-%d %H:%M UTC"),
        "source": source, "sourceUrl": url,
        "last": {"d": d1, "c": round(c1, 2)}, "prev": {"d": d0, "c": round(c0, 2)},
        "chg": round(c1 - c0, 2),
        "pct10": round(100 * sum(1 for v in w10 if v <= c1) / len(w10)), "n10": len(w10), "since10": minus_years(d1, 10),
        "med10": round(med, 2),
        "hi52": {"d": hi[0], "c": round(hi[1], 2)}, "lo52": {"d": lo[0], "c": round(lo[1], 2)},
        "zone": zone_of(c1), "zones": ZONES,
        "points": [[d, round(c, 2)] for d, c in points[-KEEP:]],
        "note": "VIX 收盤值。十年位置＝最近十年每日收盤裡，小於等於最新值的比例。區間門檻是經驗分界（教學），不是買賣訊號。",
    }


XCHECK_TOL = 0.01       # 兩個來源同一天的收盤差超過 1% → 待確認


def cross_check(a_name, a_pts, b_name, b_pts, tol=XCHECK_TOL):
    """兩個來源都有的最近一天，收盤差多少。"""
    b = dict(b_pts)
    for d, c in reversed(a_pts[-10:]):
        if d in b:
            diff = abs(c - b[d]) / b[d]
            ok = diff <= tol
            return {"d": d, "a": a_name, "ac": round(c, 2), "b": b_name, "bc": round(b[d], 2), "ok": ok,
                    "note": ("兩個來源一致" if ok else f"待確認：{d} 兩個來源的收盤差 {diff * 100:.1f}%")}
    return None


def update(sources=SOURCES, now=None):
    """每個來源都試；用最新一筆日期最新的那個（一樣新取排前面的）。回傳 (內容或 None, 每個來源的結果說明)。"""
    notes, got = [], []
    for name, url, fn in sources:
        try:
            pts = fn()
            notes.append(f"{name}：{len(pts)} 筆，最新 {pts[-1][0]} 收 {pts[-1][1]:.2f}")
            got.append((name, url, pts))
        except Exception as e:  # 任何一種失敗都只是少一個來源
            notes.append(f"{name}：失敗（{type(e).__name__}: {str(e)[:120]}）")
    if not got:
        return None, notes
    best = max(got, key=lambda g: g[2][-1][0])          # max 遇到一樣大的回傳第一個＝官方檔優先
    doc = build(best[2], best[0], best[1], now)
    others = [g for g in got if g is not best]
    if others:
        x = cross_check(best[0], best[2], others[0][0], others[0][2])
        if x:
            doc["xcheck"] = x
            notes.append("核對：" + x["note"])
    return doc, notes


def is_stale(doc, today=None):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    try:
        last = dt.date.fromisoformat(doc["last"]["d"])
    except (KeyError, TypeError, ValueError):
        return True
    return (today - last).days > STALE_DAYS


def jload(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--probe" in argv:
        for name, _, fn in SOURCES:
            try:
                p = fn(); log(f"{name}：{len(p)} 筆；頭 {p[:2]}；尾 {p[-3:]}")
            except Exception as e:
                log(f"{name}：失敗（{type(e).__name__}: {e}）")
        return 0
    prev = jload(OUT)
    if "--stale-check" in argv:
        if is_stale(prev):
            log(f"VIX 落後：最新一筆 {((prev or {}).get('last') or {}).get('d', '沒有資料')}（超過 {STALE_DAYS} 天）")
            return 1
        log(f"VIX 最新一筆 {prev['last']['d']}，沒有落後")
        return 0
    doc, notes = update()
    for n in notes:
        log("  " + n)
    if doc is None:
        log("VIX：這一班兩個來源都抓不到，保留舊檔（晚上的落後檢查會看是不是一直抓不到）")
        return 0
    if prev and prev.get("last") == doc["last"] and prev.get("source") == doc["source"] and (prev.get("xcheck") or {}).get("ok") == (doc.get("xcheck") or {}).get("ok"):
        log(f"VIX：最新仍是 {doc['last']['d']}，不重寫")
        return 0
    if prev and prev.get("last", {}).get("d", "") > doc["last"]["d"]:
        log(f"VIX：抓到的最新日期 {doc['last']['d']} 比現有的 {prev['last']['d']} 舊，保留舊檔")
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    log(f"VIX：{doc['last']['d']} 收 {doc['last']['c']}（{doc['chg']:+.2f}），十年位置第 {doc['pct10']} 百分位，來源 {doc['source']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
