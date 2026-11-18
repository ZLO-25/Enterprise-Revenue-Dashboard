"""SEC 收件匣（GitHub Actions 的 daily-prep 跑，不經過 Claude、不花 token）：把每日檢查「快報」「核對」要讀的東西先準備好。

為什麼：快報時 Claude 要自己開網頁找 8-K 附件 99.1、核對時要讀 10-Q 或手動觸發 bs-fetch 再等它跑完，
       每多一次往返就多讀一次整個對話（token 是「回合數 × 對話長度」）。這些都是固定步驟，交給 Actions 先做。

做三件事（只寫 data/inbox/ 與 data/bs-raw/，不改 data/<代號>.json）：
  ① 新聞稿預抓：sec-feed 有比最新一季 rd 更新的 8-K 2.02 → 下載附件 99.1 轉成純文字
     data/inbox/<代號>/pr-<申報日>.txt（第一行 SOURCE 是 SEC 原始網址）。每家只留最近 2 份。
  ② 損益與現金流 XBRL 核對表：狀態是快報／補完（還沒核對完）的公司，
     讀 SEC XBRL 的營收、毛利、營業利益、淨利、稀釋 EPS、營業現金流、資本支出，和我們的最近 3 季比對
     → data/inbox/<代號>/xbrl.json。只是「核對」，不自動寫進公司資料（資料誠實：寫入仍由 Claude 對來源後做）。
  ③ 同一批公司順便重算資產負債表提案 data/bs-raw/<代號>.json 的「最近 3 季」（更早的季度保留舊提案），
     Claude 只要跑 bs_merge.py，不必再觸發 bs-fetch、等待。EPS 依股票分割換算成今天的股數再比。

用法：python3 tools/sec_inbox.py [--company nvda] [--no-bs]
看結果（Claude）：python3 tools/daily.py inbox [代號]
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
UA = "Enterprise-Revenue-Dashboard research contact@example.com"
INBOX = os.path.join(ROOT, "data", "inbox")
KEEP_PR = 2
CHECK_QS = 3

# 損益與現金流的 XBRL 概念（第一個有值的）。kind：q＝單季（第四季＝全年－前九個月）、qonly＝只收單季值、ytd＝年初累計相減
IS_MAP = {
    "rev": ("q", ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"]),
    "gp": ("q", ["GrossProfit"]),
    "opInc": ("q", ["OperatingIncomeLoss"]),
    "ni": ("q", ["NetIncomeLoss"]),
    "eps": ("qonly", ["EarningsPerShareDiluted"]),
    "ocf": ("ytd", ["NetCashProvidedByUsedInOperatingActivities", "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"]),
    "capex": ("ytd", ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"]),
}


# ---------------------------------------------------------------- 純函式（有單元測試）
def pr_due(feed_entry, last_rd, have):
    """回傳要預抓的 8-K（比 last_rd 新、還沒抓過）。have＝已存在的申報日集合。"""
    if not feed_entry or not last_rd:
        return []
    return [e for e in feed_entry.get("earnings8k", []) if e["date"] > last_rd and e["date"] not in have][:1]


def pick_ex99(names):
    """從申報索引的檔名中挑財報新聞稿（附件 99.1 優先）。"""
    docs = [n for n in names if n.lower().endswith((".htm", ".html", ".txt")) and "index" not in n.lower()]
    for pat in (r"ex.?99.?0?1(?!\d)", r"99", r"earning|release|pressrel"):
        hit = [n for n in docs if re.search(pat, n, re.I) and not re.match(r"^\d{10}-\d{2}-\d{6}\.txt$", n)]
        if hit:
            return hit[0]
    return None


def xbrl_due(state):
    """這家公司今天要不要做 XBRL 核對表＋資產負債表提案：只有快報／補完中（還沒核對完）的公司。
    （不能用「10-Q 申報日晚於 rd」判斷：10-Q 本來就在新聞稿之後，核對完的公司也永遠成立，實測 2026-11-19 一次跑了 14 家。）"""
    return state in ("flash", "completed")


def merge_recent(old, new, n=CHECK_QS):
    """資產負債表提案只換最近 n 季，更早的季度保留舊提案（有些公司舊提案是特殊做法產生的，例如 GOOGL 2015 前用 Google Inc. 的 CIK）。"""
    if not old:
        return new
    keep = {r["q"] for r in new["quarters"][-n:]}
    newby = {r["q"]: r for r in new["quarters"]}
    rows = [newby[r["q"]] if r["q"] in keep else r for r in old["quarters"]]
    have = {r["q"] for r in rows}
    rows += [newby[q] for q in [r["q"] for r in new["quarters"][-n:]] if q not in have]
    return dict(old, quarters=rows, fetched=new.get("fetched"), recentOnly=n)


Q4_WHY = "第四季由全年減前九個月推算（10-K 修正過前三季時不準），請以第四季新聞稿單季數字為準"


def derived_q4_unreliable(kind, days, ok):
    """SEC 沒有單季值、是「全年 − 前九個月」推算的第四季，而且對不上：不判不一致。
    原因：10-K 若修正過前三季（例 CRWD FY2026 股票酬勞修正），全年是新口徑、前九個月是 10-Q 的舊口徑，相減會差（實測 2026-11-19）。"""
    return kind == "q" and (days or 0) > 100 and ok is False


def close_enough(field, ours, sec):
    if ours is None or sec is None:
        return None
    if field == "eps":
        return abs(ours - sec) <= 0.011
    return abs(ours - sec) <= max(0.6, abs(sec) * 0.001)


# ---------------------------------------------------------------- HTML → 純文字（同 sec-raw 分支的 tools/sec_raw.py）
class _T(HTMLParser):
    def __init__(s):
        super().__init__(); s.out = []; s.cell = []; s.row = []; s.intable = 0; s.skip = 0

    def handle_starttag(s, t, a):
        if t in ("script", "style"): s.skip += 1
        if t == "table": s.intable += 1
        if t == "tr": s.row = []
        if t in ("td", "th"): s.cell = []
        if t in ("br", "p", "div") and not s.intable: s.out.append("\n")

    def handle_endtag(s, t):
        if t in ("script", "style"): s.skip -= 1
        if t in ("td", "th"):
            c = " ".join("".join(s.cell).split())
            if c: s.row.append(c)
            s.cell = []
        if t == "tr":
            if s.row: s.out.append("\n" + " | ".join(s.row))
            s.row = []
        if t == "table": s.intable -= 1; s.out.append("\n")

    def handle_data(s, d):
        if s.skip: return
        (s.cell if s.intable else s.out).append(d)


def html_text(b):
    p = _T(); p.feed(b.decode("utf-8", "replace")); t = "".join(p.out)
    t = re.sub(r"[ \t\xa0]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip() + "\n"


def get(url, raw=False):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
                b = r.read(); time.sleep(0.15)
                return b if raw else json.loads(b)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (i + 1))
        except Exception as e:  # noqa: BLE001
            print("  重試", url, e); time.sleep(2 * (i + 1))
    return None


# ---------------------------------------------------------------- ① 新聞稿
def fetch_pr(code, cik, e):
    acc = e["acc"].replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}"
    idx = get(base + "/index.json")
    if not idx:
        print(f"  {code}：讀不到申報索引 {e['acc']}"); return None
    ex = pick_ex99([i["name"] for i in idx["directory"]["item"]])
    if not ex:
        print(f"  {code}：{e['acc']} 找不到新聞稿附件"); return None
    b = get(f"{base}/{ex}", raw=True)
    if not b:
        return None
    d = os.path.join(INBOX, code); os.makedirs(d, exist_ok=True)
    fn = os.path.join(d, f"pr-{e['date']}.txt")
    with open(fn, "w", encoding="utf8") as f:
        f.write(f"SOURCE {base}/{ex}\nFILED {e['date']}（8-K Item 2.02，附件 99.1；Actions 預抓，未經 Claude 修改）\n\n" + html_text(b))
    olds = sorted(x for x in os.listdir(d) if x.startswith("pr-"))
    for x in olds[:-KEEP_PR]:
        os.remove(os.path.join(d, x))
    print(f"  {code}：新聞稿已存 data/inbox/{code}/pr-{e['date']}.txt")
    return fn


# ---------------------------------------------------------------- ② 損益 XBRL 核對表
def xbrl_check(code, cik, D, bs_map, c=None):
    import bs_fetch as BF
    splits = BF.splits_for(c["price"]["yahoo"]) if (c and c.get("price")) else []
    Q = D["quarters"]
    fye = (D.get("company") or {}).get("fiscalYearEnd") or "12-31"
    ni_names = (bs_map.get(code) or {}).get("ni") or ["NetIncomeLoss"]
    F = {}
    for _, (_, names) in IS_MAP.items():
        for n in names:
            if n not in F:
                F[n] = BF.concept(cik, n)
    for n in ni_names:
        F.setdefault(n, BF.concept(cik, n))
    ends, _, _ = BF.quarter_ends([f for n in ni_names for f in F[n]], Q, fye)
    out = {"code": code, "fetched": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "quarters": []}
    for i in range(max(0, len(Q) - CHECK_QS), len(Q)):
        q, E = Q[i], ends[i]
        row = {"q": q["q"], "end": E, "rows": {}}
        if not E:
            row["why"] = "SEC XBRL 還沒有這一季（10-Q／10-K 尚未申報，或淨利對不上）"
            out["quarters"].append(row); continue
        prev = ends[i - 1] if i > 0 else None
        for field, (kind, names) in IS_MAP.items():
            got = None
            for n in names:
                f, v = BF.flow(F.get(n, []), E, prev, kind)
                if f:
                    if field == "eps":
                        if splits is None:
                            got = {"ours": q.get(field), "sec": None, "ok": None, "why": "沒有分割資料，EPS 不比"}
                            break
                        sec = round(v / BF.factor(splits, f["filed"]), 4)   # 申報後才分割 → 換算成今天的股數（同 bs_fetch）
                    else:
                        sec = round(v / 1e6, 3)
                    got = {"ours": q.get(field), "sec": sec, "c": n, "acc": f["accn"], "filed": f["filed"], "ok": close_enough(field, q.get(field), sec)}
                    if derived_q4_unreliable(kind, BF.dur(f), got["ok"]):
                        got.update(ok=None, why=Q4_WHY)
                    break
            row["rows"][field] = got or {"ours": q.get(field), "sec": None, "ok": None, "why": "讀不到單季值"}
        out["quarters"].append(row)
    d = os.path.join(INBOX, code); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "xbrl.json"), "w", encoding="utf8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1); f.write("\n")
    bad = sum(1 for r in out["quarters"] for x in r["rows"].values() if x.get("ok") is False)
    print(f"  {code}：XBRL 核對表 {len(out['quarters'])} 季，不一致 {bad} 格")
    return out


# ---------------------------------------------------------------- 給 Claude 看（python3 tools/daily.py inbox [代號]）
LABEL = {"rev": "營收", "gp": "毛利", "opInc": "營業利益", "ni": "淨利", "eps": "稀釋EPS", "ocf": "營業現金流", "capex": "資本支出"}


def report(codes=None):
    if not os.path.isdir(INBOX):
        print("收件匣是空的（data/inbox/ 不存在）"); return 0
    codes = codes or sorted(x for x in os.listdir(INBOX) if os.path.isdir(os.path.join(INBOX, x)))
    for code in codes:
        d = os.path.join(INBOX, code)
        print(f"【{code}】")
        if not os.path.isdir(d):
            print("  收件匣沒有東西（美股之外的公司不會有；美股要等 daily-prep 跑過）"); continue
        prs = sorted(x for x in os.listdir(d) if x.startswith("pr-"))
        for x in prs:
            with open(os.path.join(d, x), encoding="utf8") as f:
                src = f.readline().strip()
            print(f"  新聞稿 data/inbox/{code}/{x}（{os.path.getsize(os.path.join(d, x)) // 1024} KB）{src}")
        if not prs:
            print("  新聞稿：沒有預抓（SEC 還沒有比最新一季更新的財報 8-K）")
        xp = os.path.join(d, "xbrl.json")
        if not os.path.exists(xp):
            print("  XBRL 核對表：沒有（狀態不是快報／補完，SEC 也沒有新的 10-Q／10-K）"); continue
        X = json.load(open(xp, encoding="utf8"))
        print(f"  XBRL 核對表（Actions 讀 SEC，{X['fetched']}）：✓ 一致　✗ 不一致（要對來源）　≈ 第四季推算值不比（看新聞稿）　－ 讀不到")
        for r in X["quarters"]:
            if r.get("why"):
                print(f"    {r['q']}：{r['why']}"); continue
            cells = []
            for k, v in r["rows"].items():
                mark = {True: "✓", False: "✗", None: "－"}[v.get("ok")] if not (v.get("ok") is None and v.get("sec") is not None) else "≈"
                cells.append(f"{LABEL[k]}{mark}" + (f"(我們 {v['ours']}／SEC {v['sec']})" if v.get("ok") is False else ""))
            print(f"    {r['q']}（期末 {r['end']}）：" + "　".join(cells))
    return 0


# ---------------------------------------------------------------- 主程式
def main():
    a = sys.argv[1:]
    only = a[a.index("--company") + 1] if "--company" in a else None
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    feed = json.load(open(os.path.join(ROOT, "data", "sec-feed.json"), encoding="utf8")).get("companies", {})
    cal = json.load(open(os.path.join(ROOT, "data", "calendar.json"), encoding="utf8")).get("companies", {})
    bs_map = json.load(open(os.path.join(ROOT, "tools", "bs_map.json"), encoding="utf8"))
    bs_todo, fails = [], 0
    for c in cfg["companies"]:
        code = c["code"]
        if not (c.get("enabled") and c.get("cik")) or (only and code != only):
            continue
        D = json.load(open(os.path.join(ROOT, "data", code + ".json"), encoding="utf8"))
        Q = D.get("quarters") or []
        last_rd = Q[-1].get("rd") if Q else None
        f = feed.get(code)
        d = os.path.join(INBOX, code)
        have = {x[3:13] for x in os.listdir(d) if x.startswith("pr-")} if os.path.isdir(d) else set()
        try:
            for e in pr_due(f, last_rd, have):
                fetch_pr(code, c["cik"], e)
            xp = os.path.join(d, "xbrl.json")
            if not xbrl_due(cal.get(code, {}).get("state", "waiting")) and os.path.exists(xp):
                os.remove(xp)   # 核對完了：舊核對表不留，免得排程誤讀
            if xbrl_due(cal.get(code, {}).get("state", "waiting")) and Q and (f or {}).get("periodic"):
                xbrl_check(code, c["cik"], D, bs_map, c)
                if code in bs_map:
                    bs_todo.append(code)
        except Exception as e:  # noqa: BLE001  一家失敗不擋其他家
            fails += 1
            print(f"  {code}：失敗 {type(e).__name__} {e}")
    if bs_todo and "--no-bs" not in a:
        import bs_fetch as BF
        for code in bs_todo:
            try:
                rp = os.path.join(ROOT, "data", "bs-raw", code + ".json")
                old = json.load(open(rp, encoding="utf8")) if os.path.exists(rp) else None
                BF.build(cfg, code)
                new = json.load(open(rp, encoding="utf8"))
                with open(rp, "w", encoding="utf8") as fh:
                    json.dump(merge_recent(old, new), fh, ensure_ascii=False, indent=0); fh.write("\n")
            except Exception as e:  # noqa: BLE001
                fails += 1
                print(f"  {code}：資產負債表提案失敗 {type(e).__name__} {e}")
    print(f"收件匣完成：資產負債表提案 {len(bs_todo)} 家，失敗 {fails}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
