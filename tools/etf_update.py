"""ETF 追蹤：每日收盤價、報酬、費用率、前十大持股（GitHub Actions 的 prices-daily 一併執行，不經過 Claude，不花 token）。

流程（清單在 data/etf/config.json）：
  1. 每檔 ETF 用 Yahoo 抓上市以來的日線 Close（和個股同一支 tools/prices_daily.py fetch_rows：還沒收盤的當天不收）
     台股 ETF（twse 設定）最新一天對證交所官方收盤價，差超過 0.5% 那天不用（同個股規則）
     → data/etf/daily/<代號>.json（看盤 K 棒的 kbar_update.py 也拿它核對 ETF 的 K 棒）
  2. 用收盤價算價格報酬（1／3 個月、今年以來、1／3／5／10 年、上市以來，3 年以上另算年化）；不含配息
  3. 每 holdingsEveryDays 天抓一次 Yahoo 的基金資料：前十大持股＋權重、費用率、資產規模
     抓不到 → 沿用上次的；從來沒抓到 → 寫「待確認」與原因（例如台股 ETF Yahoo 多半沒有持股資料）
     台股持股名稱用證交所／櫃買中心公開資料的簡稱（data/etf/twnames.json，跟持股一起每週更新）
     kind=commodity（實物黃金、期貨）沒有股票持股 → 顯示 holdingsNote
     持股若是網站有追蹤的公司 → 連到公司頁，並附那家公司自己的 1 年報酬（data/daily）做對照
  4. 寫 data/etf/latest.json（ETF 頁打開時直接讀，不必重建網站）
資料誠實規則：價格、權重、費用率只來自來源原值，不估計、不內插；讀不到就 null＋原因。
Yahoo 的持股與費用率是第三方整理（不是發行商原始檔），頁面標「Yahoo Finance，未對發行商」，並附發行商連結。

用法：
  python3 tools/etf_update.py                 # 抓價＋（到期才）抓持股
  python3 tools/etf_update.py --holdings      # 這次一定重抓持股
  python3 tools/etf_update.py --only etf_soxx
  python3 tools/etf_update.py --recalc        # 不上網：用現有收盤價重算 latest.json
  python3 tools/etf_update.py --stale-check   # 有 ETF 收盤價落後（美股 4 天、台股 12 天）→ 結束碼 1
"""
import datetime as dt, json, os, sys, time
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

EDIR = os.path.join(ROOT, "data", "etf")
SOURCE = "Yahoo Finance 日線 Close（已依分割調整、不含配息）"
FUND_SRC = "Yahoo Finance 基金資料（第三方整理，未對發行商原始檔）"
WINDOWS = [("m1", 0, 1), ("m3", 0, 3), ("y1", 1, 0), ("y3", 3, 0), ("y5", 5, 0), ("y10", 10, 0)]   # (key, 年, 月)
TW_NAMES_SRC = "證交所／櫃買中心公開資料（公司簡稱）"


def log(*a):
    print(*a, flush=True)


def jload(path, default=None):
    try:
        with open(path, encoding="utf8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def jsave(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")


def config(path=None):
    return jload(path or os.path.join(EDIR, "config.json"))


def check_config(cfg):
    """設定檢查（validate 與測試共用）：回傳錯誤字串清單。"""
    err, seen = [], set()
    groups = cfg.get("groups") or []
    for e in cfg.get("etfs") or []:
        c = e.get("code", "")
        if not c.startswith("etf_") or c != c.lower():
            err.append(f"{c}：code 要是小寫、以 etf_ 開頭（避免和公司代號撞名）")
        if c in seen:
            err.append(f"{c}：code 重複")
        seen.add(c)
        for k in ("ticker", "name", "group", "yahoo", "currency", "issuer", "why"):
            if not e.get(k):
                err.append(f"{c}：缺 {k}")
        if e.get("group") not in groups:
            err.append(f"{c}：group「{e.get('group')}」不在 groups 清單")
        if e.get("from") and len(e["from"]) != 7:
            err.append(f"{c}：from 要是 YYYY-MM")
    return err


# ---------- 報酬（純函式） ----------
def _minus(d, years, months):
    y, m = d.year - years, d.month - months
    while m < 1:
        m += 12
        y -= 1
    import calendar
    return dt.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def _base(rows, target):
    """target 當天或之前最後一個有收盤的列；沒有（資料起點晚於 target）→ None。"""
    best = None
    for d, c in rows:
        if d > target:
            break
        if c is not None:
            best = (d, c)
    return best


def returns(rows):
    """rows：[[YYYY-MM-DD, close|None]...]（依日期）。回傳 {last:{d,c}, ret:{key:%}, base:{key:date}}。
    資料不夠長（基準日早於第一筆）→ 那一欄 null，不用較短期間代替。"""
    rows = [(r[0], r[1]) for r in rows or []]
    valid = [r for r in rows if r[1] is not None]
    if not valid:
        return {"last": None, "ret": {}, "base": {}}
    ld, lc = valid[-1]
    last = dt.date.fromisoformat(ld)
    first = valid[0][0]
    ret, base = {}, {}

    def put(k, b, years=None):
        if not b:
            ret[k] = None
            if years and years > 1:
                ret[k + "a"] = None
            return
        r = lc / b[1] - 1
        ret[k] = round(r * 100, 2)
        base[k] = b[0]
        if years and years > 1:
            ret[k + "a"] = round(((1 + r) ** (1 / years) - 1) * 100, 2)

    for k, y, m in WINDOWS:
        tgt = _minus(last, y, m).isoformat()
        if tgt < first:
            ret[k] = None
            if y > 1:
                ret[k + "a"] = None
            continue
        put(k, _base(rows, tgt), y or None)
    ytd = f"{last.year - 1}-12-31"
    put("ytd", _base(rows, ytd) if ytd >= first else None)
    # 上市以來（資料第一天起）；滿 1 年才算年化
    f0 = valid[0]
    yrs = (last - dt.date.fromisoformat(f0[0])).days / 365.25
    ret["all"] = round((lc / f0[1] - 1) * 100, 2)
    base["all"] = f0[0]
    ret["alla"] = round(((lc / f0[1]) ** (1 / yrs) - 1) * 100, 2) if yrs >= 1 else None
    return {"last": {"d": ld, "c": lc}, "ret": ret, "base": base}


# ---------- 持股（純函式） ----------
def symbol_map(companies, aliases):
    m = {}
    for c in companies:
        if c.get("enabled") is False:
            continue
        y = (c.get("price") or {}).get("yahoo")
        for s in filter(None, [y, (y or "").split(".")[0] if y and "." in y and not y.split(".")[0].isdigit() else None, c.get("ticker")]):
            m.setdefault(s.upper(), c["code"])
    for s, code in (aliases or {}).items():
        m[s.upper()] = code
    return m


def tw_code(sym):
    """'2330.TW' / '5274.TWO' → '2330'；不是台股代號 → None。"""
    s = str(sym or "").upper()
    for suf in (".TWO", ".TW"):
        if s.endswith(suf):
            return s[: -len(suf)]
    return None


def parse_holdings(items, smap, cos_by_code, r1y_of, tw_names=None):
    """items：[(symbol, name, weight 0~1)]。回傳 (rows, sum%, flag)。權重怪（負數、>1、合計 >105%）→ flag 待確認。"""
    rows, flag = [], None
    for sym, name, w in items:
        if w is None or w != w:
            continue
        w = float(w)
        if w < 0 or w > 1:
            flag = f"待確認：{sym} 權重 {w} 不在 0～100% 之間"
            continue
        code = smap.get(str(sym or "").upper())
        row = {"sym": sym, "name": name, "w": round(w * 100, 2)}
        zh = (tw_names or {}).get(tw_code(sym))
        if zh:
            row["zh"] = zh
        if code and code in cos_by_code:
            row["code"] = code
            row["href"] = cos_by_code[code]["path"]
            row["co"] = cos_by_code[code]["name"]
            r = r1y_of(code)
            if r:
                row["r1y"], row["r1yD"] = r
        rows.append(row)
    s = round(sum(r["w"] for r in rows), 2)
    if s > 105:
        flag = f"待確認：前十大權重合計 {s}%，超過 100%"
    return rows, s, flag


def expense(fund_ops, info):
    """費用率（%）。fund_ops：Yahoo fund_operations 的 Annual Report Expense Ratio（小數，例如 0.0003）；
    info：netExpenseRatio（已是 %，例如 0.03）。兩個都有且差超過 0.02 個百分點 → 待確認。"""
    a = None if fund_ops is None or fund_ops != fund_ops else round(float(fund_ops) * 100, 4)
    b = None if info is None or info != info else round(float(info), 4)
    v = a if a is not None else b
    out = {"pct": v, "src": FUND_SRC + ("（年報費用率）" if a is not None else "（淨費用率）" if b is not None else "")}
    if v is None:
        out["flag"] = "待確認：Yahoo 沒有這檔的費用率，請看發行商頁面"
    elif not (0 < v < 3):
        out["flag"] = f"待確認：費用率 {v}% 不合理，可能是單位錯，先不採用"
        out["pct"] = None
    elif a is not None and b is not None and abs(a - b) > 0.02:
        out["flag"] = f"待確認：Yahoo 兩個欄位不一致（年報 {a}%、淨 {b}%）"
    return out


def r1y_from_daily(code, ddir=None):
    d = jload(os.path.join(ddir or os.path.join(ROOT, "data", "daily"), code + ".json"))
    if not d or not d.get("rows"):
        return None
    r = returns(d["rows"])
    v = r["ret"].get("y1")
    return None if v is None else (v, r["last"]["d"])


# ---------- 網路（只有這一段上網） ----------
def fetch_fund(sym):
    """回傳 dict(items, er_ops, er_info, aum, aumCur)；任何一段讀不到就是 None。"""
    import yfinance as yf
    t = yf.Ticker(sym)
    out = {"items": None, "er_ops": None, "er_info": None, "aum": None}
    try:
        fd = t.funds_data
        th = fd.top_holdings
        if th is not None and len(th):
            cols = {c.lower(): c for c in th.columns}
            nc, wc = cols.get("name"), cols.get("holding percent")
            if wc:
                out["items"] = [(str(i), str(r[nc]) if nc else "", r[wc]) for i, r in th.iterrows()]
        ops = fd.fund_operations
        if ops is not None and len(ops):
            for idx in ops.index:
                if "expense" in str(idx).lower() and "annual" in str(idx).lower():
                    v = ops.loc[idx].iloc[0]
                    out["er_ops"] = None if v is None else float(v)
    except Exception as e:  # noqa: BLE001
        log(f"   {sym} 基金資料讀取失敗：{type(e).__name__}")
    try:
        info = t.info or {}
        out["er_info"] = info.get("netExpenseRatio")
        out["aum"] = info.get("totalAssets")
    except Exception as e:  # noqa: BLE001
        log(f"   {sym} 報價資訊讀取失敗：{type(e).__name__}")
    return out


def fetch_tw_names():
    """證交所＋櫃買中心公開資料的「代號 → 公司簡稱」（含 ETF）。任一邊失敗就只用另一邊；都失敗回傳 {}。"""
    import urllib.request
    out = {}
    srcs = [("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", "Code", "Name"),
            ("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes", "SecuritiesCompanyCode", "CompanyName")]
    for url, kc, kn in srcs:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Enterprise-Revenue-Dashboard"}), timeout=40) as r:
                rows = json.loads(r.read())
            n = 0
            for x in rows:
                c, nm = str(x.get(kc) or "").strip(), str(x.get(kn) or "").strip()
                if c and nm:
                    out[c] = nm
                    n += 1
            log(f"   台股名稱：{url.split('/')[2]} {n} 筆")
        except Exception as ex:  # noqa: BLE001
            log(f"   台股名稱讀取失敗（{url.split('/')[2]}）：{type(ex).__name__}")
    return out


# ---------- 主流程 ----------
def build_entry(e, daily, fund_prev, fund_new, today, smap, cos_by_code, r1y_of, tw_names=None):
    """組 latest.json 的一檔。fund_new＝這次抓到的基金資料（沒抓就 None），fund_prev＝上次 latest 的那一檔。"""
    R = returns((daily or {}).get("rows"))
    links = {"issuer": e.get("issuerUrl"), "yahoo": ("https://tw.stock.yahoo.com/quote/" + e["yahoo"]) if e.get("twse")
             else "https://finance.yahoo.com/quote/" + e["yahoo"] + "/holdings"}
    if e.get("twse"):
        links["twse"] = "https://www.twse.com.tw/zh/ETFortune/etfInfo/" + e["twse"]
    out = {k: e.get(k) for k in ("code", "ticker", "name", "zh", "group", "currency", "issuer", "index", "why", "from", "kind")}
    out.update(links=links, last=R["last"], ret=R["ret"], base=R["base"], check=(daily or {}).get("check"))
    prev = fund_prev or {}
    if fund_new is not None:
        rows, s, flag = parse_holdings(fund_new.get("items") or [], smap, cos_by_code, r1y_of, tw_names)
        if e.get("kind") == "commodity":
            out["holdings"] = {"asOf": today, "rows": [], "note": e.get("holdingsNote") or "持有實物或期貨，沒有股票持股。"}
        elif rows:
            out["holdings"] = {"asOf": today, "src": FUND_SRC, "rows": rows, "sum": s, "flag": flag}
        elif prev.get("holdings") and prev["holdings"].get("rows"):
            out["holdings"] = dict(prev["holdings"], stale="這次沒抓到，沿用 " + prev["holdings"].get("asOf", "?") + " 的資料")
        else:
            out["holdings"] = {"asOf": today, "src": FUND_SRC, "rows": [], "flag": "待確認：Yahoo 沒有這檔的持股資料，請看發行商／證交所頁面"}
        er = expense(fund_new.get("er_ops"), fund_new.get("er_info"))
        if er["pct"] is None and (prev.get("er") or {}).get("pct") is not None:
            er = dict(prev["er"], stale="這次沒抓到，沿用 " + prev["er"].get("asOf", "?") + " 的資料")
        else:
            er["asOf"] = today
        out["er"] = er
        a = fund_new.get("aum")
        out["aum"] = {"v": a, "asOf": today, "src": FUND_SRC} if a else prev.get("aum")
    else:
        for k in ("holdings", "er", "aum"):
            if prev.get(k) is not None:
                out[k] = prev[k]
        if e.get("kind") == "commodity" and not (out.get("holdings") or {}).get("note"):
            out["holdings"] = {"rows": [], "note": e.get("holdingsNote") or "持有實物或期貨，沒有股票持股。"}
        for r in ((out.get("holdings") or {}).get("rows") or []):     # 中文簡稱：名單更新後也補上
            zh = (tw_names or {}).get(tw_code(r.get("sym")))
            if zh:
                r["zh"] = zh
        # 持股對應本站公司、1 年報酬對照：每天重算（持股名單本身每週才抓；新增公司或代號對應後馬上生效）
        for r in ((out.get("holdings") or {}).get("rows") or []):
            code = smap.get(str(r.get("sym") or "").upper())
            for k in ("code", "href", "co"):
                r.pop(k, None)
            if code and code in cos_by_code:
                r["code"], r["href"], r["co"] = code, cos_by_code[code]["path"], cos_by_code[code]["name"]
            if r.get("code"):
                v = r1y_of(r["code"])
                r.pop("r1y", None), r.pop("r1yD", None)
                if v:
                    r["r1y"], r["r1yD"] = v
    return out


def due(prev_entry, today, every):
    h = (prev_entry or {}).get("holdings") or {}
    if not h.get("asOf") or h.get("stale"):
        return True
    return (dt.date.fromisoformat(today) - dt.date.fromisoformat(h["asOf"])).days >= every


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    cfg = config()
    errs = check_config(cfg)
    if errs:
        log("設定有錯：\n" + "\n".join(errs))
        return 1
    only = a[a.index("--only") + 1] if "--only" in a else None
    etfs = [e for e in cfg["etfs"] if not only or e["code"] == only]
    import prices_daily as PD
    if "--stale-check" in a:
        today = dt.datetime.now(ZoneInfo("Asia/Taipei")).date()
        late = []
        for e in etfs:
            d = jload(os.path.join(EDIR, "daily", e["code"] + ".json"))
            last = d["rows"][-1][0] if d and d.get("rows") else None
            lim = 12 if e.get("twse") else 4
            if last is None or (today - dt.date.fromisoformat(last)).days > lim:
                late.append(f"{e['code']}（最後 {last}）")
        log("ETF 收盤價落後（美股超過 4 天、台股超過 12 天）：" + ("、".join(late) if late else "無"))
        return 1 if late else 0
    recalc, force_h = "--recalc" in a, "--holdings" in a
    today = dt.datetime.now(ZoneInfo("Asia/Taipei")).date().isoformat()
    cos = jload(os.path.join(ROOT, "companies.json"))["companies"]
    smap = symbol_map(cos, cfg.get("aliases"))
    cos_by_code = {c["code"]: c for c in cos if c.get("enabled") is not False}
    latest_path = os.path.join(EDIR, "latest.json")
    old = jload(latest_path, {}) or {}
    prev_by = {x["code"]: x for x in old.get("etfs") or []}
    rc, entries = 0, []
    names_path = os.path.join(EDIR, "twnames.json")
    tw = jload(names_path, {}) or {}
    need_names = not recalc and any(e in etfs and (force_h or due(prev_by.get(e["code"]), today, cfg.get("holdingsEveryDays", 7)))
                                    for e in cfg["etfs"]) or (not recalc and not tw.get("names"))
    if need_names:
        got = fetch_tw_names()
        if len(got) > 500:                      # 抓到完整清單才換（避免只抓到一半就覆蓋）
            tw = {"asOf": today, "src": TW_NAMES_SRC, "names": got}
            jsave(names_path, tw)
    tw_names = tw.get("names") or {}
    for e in cfg["etfs"]:
        code = e["code"]
        dpath = os.path.join(EDIR, "daily", code + ".json")
        daily = jload(dpath)
        if e in etfs and not recalc:
            try:
                rows = PD.fetch_rows(e["yahoo"], e.get("from"), full=True)   # ETF 頁要上市以來的完整歷史
                pc = {"twse": e["twse"]} if e.get("twse") else {}
                chk = PD.cross_check(pc, rows, daily)
                if pc:
                    time.sleep(3.2)                     # 證交所限速
                new = {"symbol": e["yahoo"], "currency": e["currency"], "source": SOURCE,
                       "fetched": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "rows": rows, "check": chk}
                if daily and daily.get("rows") == rows and daily.get("check") == chk:
                    new["fetched"] = daily.get("fetched")
                if new != daily:
                    jsave(dpath, new)
                daily = new
                L = rows[-1]
                log(f"[{code}] {L[0]} 收盤已更新" + (f"；{chk['note']}" if chk else ""))
            except Exception as ex:  # noqa: BLE001
                log(f"[{code}] 收盤價失敗：{str(ex)[:120]}；保留舊檔")
                rc = 1
        fund = None
        if e in etfs and not recalc and (force_h or due(prev_by.get(code), today, cfg.get("holdingsEveryDays", 7))):
            try:
                fund = fetch_fund(e["yahoo"])
                n = len(fund.get("items") or [])
                log(f"[{code}] 基金資料：持股 {n} 筆、費用率{'有' if fund.get('er_ops') is not None or fund.get('er_info') is not None else '沒有'}")
            except Exception as ex:  # noqa: BLE001
                log(f"[{code}] 基金資料失敗：{type(ex).__name__}；沿用上次")
        entries.append(build_entry(e, daily, prev_by.get(code), fund, today, smap, cos_by_code, r1y_from_daily, tw_names))
    out = {"groups": cfg["groups"], "source": SOURCE, "fundSource": FUND_SRC, "twNamesSrc": TW_NAMES_SRC if tw_names else None, "etfs": entries}
    if {k: v for k, v in old.items() if k != "updated"} != out:
        out = dict(out, updated=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"))
        jsave(latest_path, out)
        log("已寫入 data/etf/latest.json")
    else:
        log("data/etf/latest.json 沒有變動")
    return rc


if __name__ == "__main__":
    sys.exit(main())
