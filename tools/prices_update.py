"""每月月底收盤價與分析師預估（GitHub Actions 執行，不經過 Claude）。

做什麼：
  1. 依 companies.json 每家的 price 設定，用 yfinance 抓日線 Close（auto_adjust=False：已調整股票分割、不扣股利）
  2. 每月取最後一個有成交的交易日，寫入 data/prices/<代號>.json 的 monthly[]（只收「已經結束」的月份）
  3. 每次重抓全部歷史並與舊檔比對：舊月份改變超過 0.5% ＝ 有分割或資料修正 → 這家不覆寫、印出差異並失敗，
     等 Claude 依 SOURCES.md 同步重編 EPS 後，再用 --accept-restatement <代號> 覆寫
  4. 有 twse 設定的台股：對證交所官方個股日成交資訊（STOCK_DAY）交叉核對，差超過 0.5% 的月份 c 改 null、寫待確認
  5. forward[]：月底後 10 天內，抓 Yahoo 分析師 EPS 預估（今年度、下年度）存一筆當月快照；已寫入的月份不覆寫，不回填
資料誠實規則：價格與預估只來自來源原值，不估計、不內插。

用法：
  python3 tools/prices_update.py --check                 # 是否已到最新（寫 GITHUB_OUTPUT 的 stale=true/false）
  python3 tools/prices_update.py [--company tsmc]        # 正式
  python3 tools/prices_update.py --forward-probe         # 只印 12 家有沒有預估，不寫檔
  python3 tools/prices_update.py --accept-restatement aapl
結束碼：0 成功；75 還沒到最新（可重試）；1 錯誤（含舊月份被改動）。
"""
import datetime as dt, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOL = 0.005
SOURCE = "Yahoo Finance 日線 Close（已依股票分割調整、不含股利調整）"


def log(*a):
    print(*a, flush=True)


def today():
    return dt.datetime.now(dt.timezone.utc).date()


def prev_month(d):
    first = d.replace(day=1)
    last = first - dt.timedelta(days=1)
    return last.strftime("%Y-%m")


def month_end(m):
    y, mo = map(int, m.split("-"))
    nxt = dt.date(y + (mo == 12), mo % 12 + 1, 1)
    return nxt - dt.timedelta(days=1)


def months(a, b):
    y, m = map(int, a.split("-"))
    out = []
    while f"{y:04d}-{m:02d}" <= b:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def cfg_companies(only=None):
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    return [c for c in cfg["companies"] if c.get("enabled") and c.get("price") and (not only or c["code"] == only)]


def pfile(code):
    return os.path.join(ROOT, "data", "prices", code + ".json")


def load_prices(code):
    try:
        return json.load(open(pfile(code), encoding="utf8"))
    except FileNotFoundError:
        return None


def save_prices(code, obj):
    os.makedirs(os.path.dirname(pfile(code)), exist_ok=True)
    with open(pfile(code), "w", encoding="utf8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
        f.write("\n")


def forward_window_open(last_m):
    return (today() - month_end(last_m)).days <= 10


def is_stale(c):
    last = prev_month(today())
    p = load_prices(c["code"])
    if not p or not p["monthly"] or p["monthly"][-1]["m"] < last:
        return True
    if forward_window_open(last) and not any(f["m"] == last for f in p.get("forward", [])):
        return True
    return False


# ---------- Yahoo ----------
def fetch_monthly(pc):
    import yfinance as yf
    t = yf.Ticker(pc["yahoo"])
    df = t.history(start=pc["from"] + "-01", auto_adjust=False, actions=False)
    if df is None or df.empty:
        raise RuntimeError(f"{pc['yahoo']} 沒有任何日線資料")
    last = prev_month(today())
    byM = {}
    for ts, row in df.iterrows():
        d = ts.date()
        m = d.strftime("%Y-%m")
        if m > last or row["Close"] != row["Close"]:   # 未結束的月份、NaN
            continue
        byM[m] = (d.isoformat(), round(float(row["Close"]), 4))
    ms = sorted(byM)
    if not ms:
        raise RuntimeError(f"{pc['yahoo']} 沒有已結束月份的資料")
    out = []
    for m in months(ms[0], last):          # 開頭沒資料的月份＝尚未上市，不列；中間缺漏要標待確認
        if m in byM:
            out.append({"m": m, "d": byM[m][0], "c": byM[m][1]})
        else:
            out.append({"m": m, "d": month_end(m).isoformat(), "c": None, "why": "待確認：Yahoo 無該月成交資料"})
    return out


def merge(old, new, code, accept):
    """舊月份被改動超過 0.5% 就不覆寫。"""
    diffs = []
    oldm = {r["m"]: r for r in (old or {}).get("monthly", [])}
    for r in new:
        o = oldm.get(r["m"])
        if not o or o.get("c") is None or r["c"] is None:
            continue
        if abs(r["c"] / o["c"] - 1) > TOL:
            diffs.append((r["m"], o["c"], r["c"]))
        else:
            r["c"] = o["c"]               # 差異在容許範圍內：保留舊值，避免每月重寫整檔
            r["d"] = o["d"]
        if o.get("x"):
            r["x"] = o["x"]
    if diffs and not accept:
        log(f"[{code}] 舊月份股價與上次不同（共 {len(diffs)} 個月，可能是股票分割或 Yahoo 修正），不覆寫：")
        for m, a, b in diffs[:12]:
            log(f"   {m}: {a} → {b}")
        return None
    if diffs and accept:
        for r in new:
            r.pop("x", None)
    return new


# ---------- 證交所交叉核對 ----------
def twse_month(stock, ym):
    url = f"https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date={ym.replace('-', '')}01&stockNo={stock}"
    for i in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Enterprise-Revenue-Dashboard price check"}), timeout=40) as r:
                j = json.loads(r.read())
            if j.get("stat") != "OK":
                return {}
            out = {}
            for row in j["data"]:
                y, mo, d = row[0].split("/")
                out[f"{int(y) + 1911:04d}-{mo}-{d}"] = float(row[6].replace(",", ""))
            return out
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"證交所 {stock} {ym} 抓取失敗：{err}")


def twse_check(stock, rows):
    bad = 0
    for r in rows:
        if r.get("x") or r["c"] is None:
            continue
        time.sleep(3.2)                         # 證交所限速：約每 5 秒 3 次
        days = twse_month(stock, r["m"])
        t = days.get(r["d"])
        if t is None:
            r["x"] = "twse-no-data"
            continue
        diff = abs(r["c"] / t - 1)
        if diff > TOL:
            bad += 1
            r["why"] = f"待確認：與證交所收盤價差 {diff * 100:.2f}%"
            r["c"] = None
        else:
            r["x"] = "twse"
    return bad


# ---------- 分析師預估 ----------
def fetch_forward(pc, m, cur):
    import yfinance as yf
    t = yf.Ticker(pc["yahoo"])
    base = {"m": m, "asOf": today().isoformat()}
    try:
        e = t.earnings_estimate
        info = t.info
        nfy = info.get("nextFiscalYearEnd")
        if e is None or "0y" not in e.index or "+1y" not in e.index or not nfy:
            return {**base, "why": "待確認：無分析師預估"}
        a, b = e.loc["0y"], e.loc["+1y"]
        if a["avg"] != a["avg"] or b["avg"] != b["avg"]:
            return {**base, "why": "待確認：無分析師預估（今年度或下年度缺）"}
        if str(a.get("currency") or cur) != cur:
            return {**base, "why": f"待確認：預估幣別 {a.get('currency')} 與股價幣別 {cur} 不同"}
        fy1 = dt.datetime.fromtimestamp(nfy, dt.timezone.utc).date()
        if fy1 <= month_end(m):
            return {**base, "why": "待確認：Yahoo 的今年度結束日早於月底（年度剛結束尚未換年）"}
        try:
            fy2 = fy1.replace(year=fy1.year + 1)
        except ValueError:
            fy2 = fy1 + dt.timedelta(days=365)
        return {**base, "fy1End": fy1.isoformat(), "fy2End": fy2.isoformat(), "eps1": round(float(a["avg"]), 4), "eps2": round(float(b["avg"]), 4),
                "n1": int(a["numberOfAnalysts"]) if a["numberOfAnalysts"] == a["numberOfAnalysts"] else None,
                "n2": int(b["numberOfAnalysts"]) if b["numberOfAnalysts"] == b["numberOfAnalysts"] else None}
    except Exception as ex:  # noqa: BLE001  抓不到不算失敗，只記錄
        return {**base, "why": "待確認：無分析師預估（來源讀取失敗）"}


def main():
    args = sys.argv[1:]
    only = args[args.index("--company") + 1] if "--company" in args else None
    accept = args[args.index("--accept-restatement") + 1] if "--accept-restatement" in args else None
    comps = cfg_companies(only or accept)
    last = prev_month(today())
    if "--check" in args:
        stale = any(is_stale(c) for c in comps)
        log(f"最新月份應為 {last}；{'有公司落後，需要更新' if stale else '全部已是最新'}")
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                f.write(f"stale={'true' if stale else 'false'}\n")
        return 0
    if "--forward-probe" in args:
        for c in comps:
            f = fetch_forward(c["price"], last, c["price"]["currency"])
            log(c["code"], "有預估" if not f.get("why") else f["why"], {k: f.get(k) for k in ("fy1End", "eps1", "eps2", "n1", "n2")} if not f.get("why") else "")
        return 0
    rc = 0
    for c in comps:
        pc, code = c["price"], c["code"]
        old = load_prices(code)
        if not (is_stale(c) or accept):
            log(f"[{code}] 已是最新")
            continue
        try:
            new = merge(old, fetch_monthly(pc), code, accept == code)
        except Exception as e:  # noqa: BLE001
            log(f"[{code}] 失敗：{e}")
            rc = 1
            continue
        if new is None:
            rc = 1
            continue
        if pc.get("twse"):
            bad = twse_check(pc["twse"], new)
            log(f"[{code}] 證交所交叉核對完成，{bad} 個月份差超過 0.5%（已標待確認）")
        fwd = list((old or {}).get("forward", []))
        if forward_window_open(last) and not any(f["m"] == last for f in fwd):
            f = fetch_forward(pc, last, pc["currency"])
            fwd.append(f)
            log(f"[{code}] {last} 預估快照：{'已寫入' if not f.get('why') else f['why']}")
        out = {"symbol": pc["yahoo"], "currency": pc["currency"], "source": SOURCE, "fetched": today().isoformat(), "monthly": new, "forward": fwd}
        if pc.get("twse"):
            out["crossCheck"] = "臺灣證券交易所 STOCK_DAY 收盤價（差 0.5% 以內才收）"
        save_prices(code, out)
        log(f"[{code}] {new[0]['m']} ～ {new[-1]['m']}，共 {len(new)} 個月")
    if rc == 0 and os.environ.get("FINAL_TRY") != "1":
        pass
    return rc


if __name__ == "__main__":
    sys.exit(main())
