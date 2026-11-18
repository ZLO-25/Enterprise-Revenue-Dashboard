"""論點卡：燈號由程式算（只用網站已有的數字），論點文字與門檻是人的判斷。

資料：data/thesis/<代號>.json
  {"code","status":"draft|approved","updated":"YYYY-MM-DD","updatedBy":"Claude 草稿|ZL","oneLiner":"…",
   "type":"compounder|growth|cyclical|turnaround","caveat":"卡片固定加註（選填）",
   "metrics":[{"k":"revYoy","name":"營收年增（近四季）","op":">=|<=","thr":20,"group":"biz|val","note":"現況、近五年中位數、近五年達標季數","by":"draft|ZL|analyst"}],
   "breakWhen":"看到什麼就該重新考慮持有","risks":["…"],"history":[{"q":"3Q26","lights":{"revYoy":"g"}}]}
  **status 不是 approved 的一律不上線**（build.py 只注入 approved；草稿只存在這個檔案，等使用者確認）。
可用的指標 key（來源都是網站已有數字，對應 tools/health.py 與 assets/longterm.js 的定義）：
  revYoy 營收年增（近四季） epsYoy EPS 年增（近四季） gm 毛利率（近四季） om 營業利益率（近四季） fcfRate 自由現金流率（近四季）
  revYoyQ 單季營收年增 gmQchg 單季毛利率減前一季（百分點）
  roic roe buybackTtm（近四季回購金額，單位同公司金額） dilYoy 稀釋股數年增 pe 本益比 fpe 預估本益比 peg fcfY 自由現金流殖利率 evS EV/Sales
燈號：g 綠＝最新一點達標；y 黃＝最新一點沒達標、但前一點有達標（或前一點算不出來）；r 紅＝連續兩點都沒達標（季指標看最近兩季、月指標看最近兩個月）；n 灰＝這個指標目前算不出來（寫原因）。
排程只更新燈號與 history，絕不改論點文字或門檻。

用法：python3 tools/thesis.py             列出所有 approved 論點的目前燈號，紅燈置頂
      python3 tools/thesis.py --record 代號  把最新一季的燈號記進 history（每季快報時做一次）
      python3 tools/thesis.py review        論點卡季度檢查：每個門檻最近 8 個點達標幾次、連續幾次沒達標，標出「可能破功／門檻太緊／門檻太鬆」，
                                            寫 reports/thesis-review/<年-月>.md。只產生報告，絕不改門檻或論點文字（那是 ZL 的判斷）。
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import health as H, pe as PE  # noqa

KEYS = ("revYoyQ", "gmQchg", "revYoy", "epsYoy", "gm", "om", "fcfRate", "roic", "roe", "buybackTtm", "dilYoy", "pe", "fpe", "peg", "fcfY", "evS")
MONTHLY = ("pe", "fpe", "peg", "fcfY", "evS")


def ttm(Q, k):
    out = []
    for i in range(len(Q)):
        v = [Q[j].get(k) for j in range(i - 3, i + 1)] if i >= 3 else None
        out.append(None if v is None or any(x is None for x in v) else sum(v))
    return out


def series(Q, val, health):
    """回傳 {key: [(label, value|None), …]}。"""
    rev, eps, ni = ttm(Q, "rev"), ttm(Q, "eps"), ttm(Q, "ni")
    lab = [q["q"] for q in Q]
    yoy = lambda a: [(lab[i], (a[i] / a[i - 4] - 1) * 100 if i >= 4 and a[i] and a[i - 4] and a[i] > 0 and a[i - 4] > 0 else None) for i in range(len(a))]
    gm = []
    for i in range(len(Q)):
        w = Q[i - 3:i + 1] if i >= 3 else None
        r = sum(q["rev"] for q in w) if w else 0
        gm.append((lab[i], round(sum(q["gm"] * q["rev"] for q in w) / r, 2) if w and r and all(q.get("gm") is not None for q in w) else None))
    om = []
    for i in range(len(Q)):
        w = Q[i - 3:i + 1] if i >= 3 else None
        r = sum(q["rev"] for q in w) if w else 0
        om.append((lab[i], round(sum(q["om"] * q["rev"] for q in w) / r, 2) if w and r and all(q.get("om") is not None for q in w) else None))
    ocf, cap = ttm(Q, "ocf"), ttm(Q, "capex")
    fcfr = [(lab[i], round((ocf[i] - cap[i]) / rev[i] * 100, 2) if None not in (ocf[i], cap[i], rev[i]) and rev[i] else None) for i in range(len(Q))]
    revq = [(lab[i], (Q[i]["rev"] / Q[i - 4]["rev"] - 1) * 100 if i >= 4 and Q[i].get("rev") and Q[i - 4].get("rev") and Q[i]["rev"] > 0 and Q[i - 4]["rev"] > 0 else None) for i in range(len(Q))]
    gmq = [(lab[i], round(Q[i]["gm"] - Q[i - 1]["gm"], 2) if i >= 1 and Q[i].get("gm") is not None and Q[i - 1].get("gm") is not None else None) for i in range(len(Q))]
    S = {"revYoyQ": revq, "gmQchg": gmq, "revYoy": yoy(rev), "epsYoy": yoy(eps), "gm": gm, "om": om, "fcfRate": fcfr}
    if health:
        S["roic"] = [(x["q"], x["roic"]) for x in health["quarterly"]]
        S["roe"] = [(x["q"], x["roe"]) for x in health["quarterly"]]
        S["buybackTtm"] = [(x["q"], x["buybackTtm"]) for x in health["quarterly"]]
        S["dilYoy"] = [(x["q"], x["dilYoy"]) for x in health["quarterly"]]
        S["peg"] = [(x["m"], x["peg"]) for x in health["monthly"]]
        S["fcfY"] = [(x["m"], x["fcfY"]) for x in health["monthly"]]
        S["evS"] = [(x["m"], x["evS"]) for x in health["monthly"]]
    if val:
        S["pe"] = [(x["m"], x["pe"]) for x in val["monthly"]]
        S["fpe"] = [(x["m"], x["fpe"]) for x in val["monthly"]]
    return S


def meets(v, op, thr):
    return v >= thr if op == ">=" else v <= thr


def lights(th, Q, val, health):
    S = series(Q, val, health)
    out = {}
    for m in th.get("metrics", []):
        s = [p for p in S.get(m["k"], [])]
        if m["k"] in ("dilYoy", "buybackTtm", "roe", "roic", "gmQchg", "revYoyQ"):   # 季度指標：最新一季算不出來時，改取最近算得出來的季度（label 會標明季別）
            while len(s) > 1 and s[-1][1] is None:
                s = s[:-1]
        if not s or s[-1][1] is None:
            out[m["k"]] = {"light": "n", "now": None, "label": s[-1][0] if s else None, "why": "最新一點算不出來（欄位待確認、分母不是正數或沒有資料）"}
            continue
        now, prev = s[-1][1], (s[-2][1] if len(s) > 1 else None)
        ok = meets(now, m["op"], m["thr"])
        pok = prev is not None and meets(prev, m["op"], m["thr"])
        out[m["k"]] = {"light": "g" if ok else ("y" if (pok or prev is None) else "r"), "now": now, "label": s[-1][0], "prev": prev}
    return out


def load_all():
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    for c in cfg["companies"]:
        if not c.get("enabled"):
            continue
        p = os.path.join(ROOT, "data", "thesis", c["code"] + ".json")
        if os.path.exists(p):
            yield c, json.load(open(p, encoding="utf8"))


def context(code):
    D = json.load(open(os.path.join(ROOT, "data", code + ".json"), encoding="utf8"))
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    c = next(x for x in cfg["companies"] if x["code"] == code)
    pf = os.path.join(ROOT, "data", "prices", code + ".json")
    prices = json.load(open(pf, encoding="utf8")) if c.get("price") and os.path.exists(pf) else None
    Q = H.normq(D, c.get("schema"))
    val = PE.compute(D["quarters"], prices)
    return D, val, H.compute(Q, val, prices), Q


def review_rows(th, Q, val, health, n=8):
    """每個門檻：最近 n 個有值的點中達標幾次、現值、連續沒達標次數，加旗標。"""
    S = series(Q, val, health)
    out = []
    for m in th.get("metrics", []):
        pts = [p for p in S.get(m["k"], []) if p[1] is not None][-n:]
        if not pts:
            out.append({"k": m["k"], "name": m["name"], "group": m.get("group", "biz"), "op": m["op"], "thr": m["thr"], "now": None, "label": None, "n": 0, "ok": 0, "miss": 0, "flags": ["算不出來"]})
            continue
        oks = [meets(v, m["op"], m["thr"]) for _, v in pts]
        miss = 0
        for o in reversed(oks):
            if o:
                break
            miss += 1
        now = pts[-1][1]
        flags = []
        if len(pts) >= 4:
            if m.get("group", "biz") != "val" and miss >= 2:
                flags.append("可能破功")
            if sum(oks) < 3 and m.get("group", "biz") != "val":   # 估值門檻本來就是「等便宜才買」，很少達標是設計，不算太緊
                flags.append("門檻太緊")
            if all(oks) and len(pts) == n and m["thr"] > 0 and (now >= m["thr"] * 1.5 if m["op"] == ">=" else now <= m["thr"] * 0.5):
                flags.append("門檻太鬆")
        out.append({"k": m["k"], "name": m["name"], "group": m.get("group", "biz"), "op": m["op"], "thr": m["thr"], "now": now, "label": pts[-1][0],
                    "n": len(pts), "ok": sum(oks), "miss": miss, "flags": flags})
    return out


def review(today=None):
    import datetime as dt
    today = today or dt.date.today()
    lines = [f"# 論點卡季度檢查 {today.isoformat()}", "",
             "只是報告，**不會改任何門檻或論點文字**（那是 ZL 的判斷）。每個門檻看最近 8 個點（季指標＝8 季、月指標＝8 個月）。", "",
             "旗標：**可能破功**＝體質指標連續 2 次以上沒達標；**門檻太緊**＝體質指標 8 次裡達標不到 3 次（幾乎一直紅，失去分辨力；估值門檻很少達標是設計，不標）；"
             "**門檻太鬆**＝8 次全達標而且現值超過門檻 50% 以上（永遠綠，失去分辨力）。", ""]
    flagged = []
    body = []
    for c, th in load_all():
        if th.get("status") != "approved":
            continue
        D, val, hl, Q = context(c["code"])
        rows = review_rows(th, Q, val, hl)
        body += ["", f"## {c['code']}（{c.get('name', '')}，{th.get('type', '')}）", "", "| 指標 | 群組 | 門檻 | 現值 | 達標 | 連續沒達標 | 旗標 |", "|---|---|---|---|---|---|---|"]
        for r in rows:
            now = "—" if r["now"] is None else f"{r['now']:.1f}（{r['label']}）"
            body.append(f"| {r['name']} | {'體質' if r['group'] != 'val' else '估值'} | {r['op']} {r['thr']} | {now} | {r['ok']}/{r['n']} | {r['miss']} | {'、'.join(r['flags'])} |")
            if r["flags"] and r["flags"] != ["算不出來"]:
                flagged.append(f"- **{c['code']}**　{r['name']}（{r['op']} {r['thr']}，現值 {r['now'] if r['now'] is None else round(r['now'], 1)}，{r['ok']}/{r['n']} 達標）：{'、'.join(r['flags'])}")
    lines += ["## 要 ZL 看的", ""] + (flagged or ["- 沒有旗標"]) + body
    d = os.path.join(ROOT, "reports", "thesis-review")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, today.strftime("%Y-%m") + ".md")
    open(path, "w", encoding="utf8").write("\n".join(lines) + "\n")
    print(f"旗標 {len(flagged)} 個 → reports/thesis-review/{today.strftime('%Y-%m')}.md")
    for x in flagged:
        print(x)


def main():
    a = sys.argv[1:]
    if a[:1] == ["review"]:
        return review()
    if a[:1] == ["--record"]:
        code = a[1]
        p = os.path.join(ROOT, "data", "thesis", code + ".json")
        th = json.load(open(p, encoding="utf8"))
        D, val, hl, Q = context(code)
        L = lights(th, Q, val, hl)
        q = D["quarters"][-1]["q"]
        th["history"] = [h for h in th.get("history", []) if h["q"] != q] + [{"q": q, "lights": {k: v["light"] for k, v in L.items()}}]
        json.dump(th, open(p, "w", encoding="utf8"), ensure_ascii=False, indent=1)
        open(p, "a").write("\n")
        print(code, q, {k: v["light"] for k, v in L.items()})
        return
    rows, red = [], []
    for c, th in load_all():
        if th.get("status") != "approved":
            rows.append(f"  {c['code']}：草稿（{th.get('updated')}），等使用者確認，不上線")
            continue
        D, val, hl, Q = context(c["code"])
        L = lights(th, Q, val, hl)
        s = " ".join(f"{k}:{v['light']}" for k, v in L.items())
        rows.append(f"  {c['code']}：{s}")
        red += [f"{c['code']}.{k}" for k, v in L.items() if v["light"] == "r"]
    print("紅燈：" + (("、".join(red)) if red else "無"))
    print("\n".join(rows) or "  還沒有論點卡")


if __name__ == "__main__":
    main()
