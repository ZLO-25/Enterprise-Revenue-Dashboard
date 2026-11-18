"""每日收盤價＋用公式算出的本益比、市值…（GitHub Actions 執行，不經過 Claude，不花 token）。

做什麼：
  1. 依 companies.json 每家的 price 設定，用 yfinance 抓近 400 天日線 Close（auto_adjust=False：已調整股票分割、不扣股利；
     跟每月本益比 prices-monthly 同一個口徑，才和網站已換算成今天股數的 EPS 對得上）
  2. 「還沒收盤」的當天不收：交易所當地時間還沒過收盤 + 20 分鐘，就把今天那根丟掉（盤中價不是收盤價）
  3. 台股（twse／tpex 設定）：最新一天另對證交所／櫃買中心官方收盤價核對，差超過 0.5% → 那天收盤價改 null、寫待確認，
     頁面退回前一個核對過的交易日；來源連不上 → 照收、標「未核對」
  4. 用 tools/daily_calc.py 的公式算：每日本益比、預估本益比、市值、股價營收比、EV/Sales、FCF 殖利率、距論點卡估值上限
  5. 寫 data/daily/<代號>.json（頁面打開時直接讀這個檔，不必重建網站）
資料誠實規則：價格只來自來源原值，不估計、不內插；算不出來的數字是 null 並寫原因。

用法：
  python3 tools/prices_daily.py                 # 抓價＋計算（Actions 用）
  python3 tools/prices_daily.py --recalc        # 不上網，只用現有收盤價重算（財報季度更新後；push 觸發）
  python3 tools/prices_daily.py --company nvda
  python3 tools/prices_daily.py --stale-check   # 有公司最新收盤價落後超過 4 天（台股、韓股 12 天）→ 結束碼 1（每天最後一班用，紅燈＋GitHub 寄信）
"""
import datetime as dt, json, os, sys, time, urllib.request
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import daily_calc as DC, health as H, pe as PE  # noqa: E402

TOL = 0.005
SOURCE = "Yahoo Finance 日線 Close（已依股票分割調整、不含股利調整）"
# 交易所時區與收盤時間（當地）；Yahoo 代號字尾判斷
EXCH = {".TW": ("Asia/Taipei", 13, 30), ".TWO": ("Asia/Taipei", 13, 30), ".KS": ("Asia/Seoul", 15, 30), ".AS": ("Europe/Amsterdam", 17, 30)}
US = ("America/New_York", 16, 0)


def log(*a):
    print(*a, flush=True)


def jload(path, default=None):
    try:
        return json.load(open(path, encoding="utf8"))
    except FileNotFoundError:
        return default


def dfile(code):
    return os.path.join(ROOT, "data", "daily", code + ".json")


def exch(sym):
    for suf, v in EXCH.items():
        if sym.endswith(suf):
            return v
    return US


def fetch_rows(sym):
    import yfinance as yf
    tz, hh, mm = exch(sym)
    now = dt.datetime.now(ZoneInfo(tz))
    done_today = now.hour * 60 + now.minute >= hh * 60 + mm + 20
    err = None
    for i in range(4):
        try:
            df = yf.Ticker(sym).history(start=(now.date() - dt.timedelta(days=400)).isoformat(), end=(now.date() + dt.timedelta(days=2)).isoformat(), auto_adjust=False, actions=False)   # end 明寫到後天：不寫的話 Yahoo 最新一天可能沒包含
            if df is None or df.empty:
                raise RuntimeError("沒有日線資料")
            tail = [(str(x.date()), round(float(v), 4)) for x, v in df["Close"].tail(3).items()]
            log(f"   {sym} Yahoo 最後三天：{tail}（當地 {now:%Y-%m-%d %H:%M}，今天{'已' if done_today else '未'}收盤）")
            rows = []
            for ts, row in df.iterrows():
                d = ts.date()
                if d > now.date() or (d == now.date() and not done_today):
                    continue                      # 還沒收盤：盤中價不收
                c = row["Close"]
                if c != c:                        # NaN
                    continue
                rows.append([d.isoformat(), round(float(c), 4)])
            if not rows:
                raise RuntimeError("沒有已收盤的日線")
            return rows
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"{sym} 抓取失敗：{err}")


def tw_official(kind, stock, d):
    """證交所／櫃買中心官方收盤價（那一天）；None＝官方沒有那天的資料。連不上會丟例外。"""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import prices_update as PU
    days = (PU.twse_month if kind == "twse" else PU.tpex_month)(stock, d[:7])
    return days.get(d)


def cross_check(pc, rows, old):
    """只核對最新一天；舊的已核對結果沿用（old['check'] 記錄核對過的日期）。回傳 check 說明。"""
    kind = "twse" if pc.get("twse") else ("tpex" if pc.get("tpex") else None)
    if not kind:
        return None
    name = "證交所" if kind == "twse" else "櫃買中心"
    d, c = rows[-1]
    oc = (old or {}).get("check") or {}
    if oc.get("d") == d and oc.get("ok") is not None:
        if oc.get("ok") is False:
            rows[-1][1] = None
        return oc
    try:
        t = tw_official(kind, pc[kind], d)
    except Exception as e:  # noqa: BLE001
        return {"d": d, "ok": None, "src": name, "note": f"未核對：{name}連不上（{type(e).__name__}），先照 Yahoo 收"}
    if t is None:
        return {"d": d, "ok": None, "src": name, "note": f"未核對：{name}還沒有 {d} 的資料"}
    diff = abs(c / t - 1)
    if diff > TOL:
        rows[-1][1] = None
        return {"d": d, "ok": False, "src": name, "note": f"待確認：{d} Yahoo 收盤 {c} 與{name} {t} 差 {diff * 100:.2f}%，這天不採用"}
    return {"d": d, "ok": True, "src": name, "note": f"{d} 收盤價與{name}一致（差 {diff * 100:.2f}%）"}


def calc_for(c, daily):
    D = jload(os.path.join(ROOT, "data", c["code"] + ".json"))
    prices = jload(os.path.join(ROOT, "data", "prices", c["code"] + ".json"))
    th = jload(os.path.join(ROOT, "data", "thesis", c["code"] + ".json"))
    th = th if th and th.get("status") == "approved" else None
    val = PE.compute(D["quarters"], prices) if prices else None
    return DC.compute(H.normq(D, c.get("schema")), D["quarters"], daily, prices, val, th)


def save(code, obj):
    os.makedirs(os.path.dirname(dfile(code)), exist_ok=True)
    with open(dfile(code), "w", encoding="utf8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")


def companies(only=None):
    cfg = jload(os.path.join(ROOT, "companies.json"))
    return [c for c in cfg["companies"] if c.get("enabled") and c.get("price") and (not only or c["code"] == only)]


def main():
    a = sys.argv[1:]
    only = a[a.index("--company") + 1] if "--company" in a else None
    recalc = "--recalc" in a
    if "--stale-check" in a:
        today = dt.datetime.now(ZoneInfo("Asia/Taipei")).date()
        late = []
        for c in companies(only):
            dd = jload(dfile(c["code"]))
            last = dd["rows"][-1][0] if dd and dd.get("rows") else None
            lim = 4 if exch(c["price"]["yahoo"]) in (US, EXCH[".AS"]) else 12   # 台股、韓股有農曆年長假
            if last is None or (today - dt.date.fromisoformat(last)).days > lim:
                late.append(f"{c['code']}（最後 {last}）")
        log("每日收盤價落後（美股／ASML 超過 4 天、台韓股超過 12 天）：" + ("、".join(late) if late else "無"))
        return 1 if late else 0
    rc = 0
    for c in companies(only):
        code, pc = c["code"], c["price"]
        old = jload(dfile(code))
        try:
            if recalc:
                if not old:
                    continue
                daily = {k: old[k] for k in ("symbol", "currency", "source", "fetched", "rows", "check") if k in old}
            else:
                rows = fetch_rows(pc["yahoo"])
                chk = cross_check(pc, rows, old)
                if pc.get("twse") or pc.get("tpex"):
                    time.sleep(3.2)               # 證交所／櫃買中心限速
                daily = {"symbol": pc["yahoo"], "currency": pc["currency"], "source": SOURCE,
                         "fetched": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "rows": rows, "check": chk}
            calc = calc_for(c, daily)
        except Exception as e:  # noqa: BLE001
            log(f"[{code}] 失敗：{e}")
            rc = 1
            continue
        if old and not recalc and old.get("rows") == daily["rows"] and old.get("check") == daily.get("check"):
            daily["fetched"] = old.get("fetched")   # 收盤價沒變（假日、還沒收盤）：不改檔，避免空提交
        out = dict(daily, calc=calc)
        if out == old:
            log(f"[{code}] 沒有變動")
            continue
        save(code, out)
        L = (calc or {}).get("latest") or {}
        log(f"[{code}] {L.get('d')} 收 {L.get('c')}  本益比 {L.get('pe')}  市值 {L.get('mcap')}" + (f"  {daily['check']['note']}" if daily.get("check") else ""))
    return rc


if __name__ == "__main__":
    sys.exit(main())
