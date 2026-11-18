"""世界趨勢月報的「事實表」：把網站自己的財報資料（書面來源）濃縮成一頁，月報排程先讀這一頁，不必逐家打開 data/<代號>.json。

  python3 tools/daily.py trend-facts      （走 daily.py 是因為排程的權限白名單已允許它）

內容（全部是已公布的財報數字，標「書面」；這裡不做任何預估）：
  ① 每家公司最新一季：日曆季、營收年增、毛利率與一年前比、營業利益率、資本支出年增、最新書面財測第一項
  ② 四大雲端（MSFT、AMZN、GOOGL、META）資本支出合計，依日曆季（只加四家都已公布的季度）
  ③ 記憶體（MU、三星）毛利率最近 5 季
算不出來（缺季、缺欄位）就寫「－」，不補。
"""
import datetime as dt
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
HYPER = ["msft", "amzn", "googl", "meta"]
MEMORY = ["mu", "samsung"]


def jload(*p):
    with open(os.path.join(ROOT, *p), encoding="utf8") as f:
        return json.load(f)


def cal_q(label, fye):
    """公司季度標籤 → 日曆季（例 MSFT 1Q27 → 2026Q3）：用名目期末日落在哪個日曆季。"""
    import rd_import as RDI
    try:
        e = RDI.nominal_end(label, fye)
    except (ValueError, IndexError):
        return None
    mid = e - dt.timedelta(days=45)  # 用季度中點：NVDA 8～10 月、AAPL 52/53 週制期末 10/1 都算第三季
    return f"{mid.year}Q{(mid.month - 1) // 3 + 1}"


def prior_year(label):
    try:
        return f"{label[:2]}{int(label[2:]) - 1:02d}"
    except ValueError:
        return None


def pct(a, b):
    if a is None or b in (None, 0) or b < 0:
        return None
    return (a / b - 1) * 100


def lv(x):
    return "－" if x is None else f"{x:.1f}%"


def f1(x, unit=""):
    return "－" if x is None else f"{x:+.0f}{unit}" if unit == "%" else f"{x:.1f}{unit}"


def company_row(c, D):
    Q = D.get("quarters") or []
    if not Q:
        return None
    fye = (D.get("company") or {}).get("fiscalYearEnd") or "12-31"
    q = Q[-1]
    by = {x["q"]: x for x in Q}
    p = by.get(prior_year(q["q"]) or "", {})
    gm_d = (q["gm"] - p["gm"]) if q.get("gm") is not None and p.get("gm") is not None else None
    g = D.get("guidance") or {}
    gi = (g.get("items") or [None])[0] if isinstance(g, dict) else None
    gtxt = f"{gi['label']} {gi.get('lo')}～{gi.get('hi')} {gi.get('unit', '')}（{gi.get('period', '')}）" if gi else "－"
    return {
        "code": c["code"], "name": c.get("name") or c["code"], "sector": c.get("sector", ""), "q": q["q"], "cq": cal_q(q["q"], fye),
        "revYoY": pct(q.get("rev"), p.get("rev")), "gm": q.get("gm"), "gmD": gm_d, "om": q.get("om"),
        "capexYoY": pct(q.get("capex"), p.get("capex")), "guide": gtxt,
    }


def hyper_capex(datas):
    tot = {}
    for code in HYPER:
        D = datas.get(code)
        if not D:
            continue
        fye = (D.get("company") or {}).get("fiscalYearEnd") or "12-31"
        for q in D["quarters"]:
            k = cal_q(q["q"], fye)
            if k and q.get("capex") is not None:
                tot.setdefault(k, {})[code] = q["capex"]
    rows = [(k, sum(v.values())) for k, v in sorted(tot.items()) if len(v) == len(HYPER)]
    out = []
    for i, (k, s) in enumerate(rows):
        prev = dict(rows).get(f"{int(k[:4]) - 1}{k[4:]}")
        out.append((k, s, pct(s, prev)))
    return out[-5:]


def main():
    cfg = jload("companies.json")
    datas, rows = {}, []
    for c in cfg["companies"]:
        if not c.get("enabled"):
            continue
        try:
            D = jload("data", c["code"] + ".json")
        except FileNotFoundError:
            continue
        datas[c["code"]] = D
        r = company_row(c, D)
        if r:
            rows.append(r)
    print("# 趨勢月報事實表（網站財報資料，全部是「書面」已公布數字；不含預估）\n")
    print("## ① 各公司最新一季")
    print("| 產業 | 公司 | 季度（日曆季） | 營收年增 | 毛利率（比一年前） | 營業利益率 | 資本支出年增 | 最新書面財測第一項 |")
    print("|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: (r["sector"], r["code"])):
        print(f"| {r['sector']} | {r['name']} | {r['q']}（{r['cq'] or '－'}） | {f1(r['revYoY'], '%')} | {lv(r['gm'])}（{'－' if r['gmD'] is None else f"{r['gmD']:+.1f} 點"}） | {lv(r['om'])} | {f1(r['capexYoY'], '%')} | {r['guide']} |")
    print("\n## ② 四大雲端資本支出合計（百萬美元，依日曆季，四家都公布才加）")
    hc = hyper_capex(datas)
    print("\n".join(f"- {k}：{s:,.0f}（年增 {f1(y, '%')}）" for k, s, y in hc) or "- －")
    print("\n## ③ 記憶體毛利率（最近 5 季）")
    for code in MEMORY:
        D = datas.get(code)
        if D:
            print(f"- {code}：" + "、".join(f"{q['q']} {lv(q.get('gm'))}" for q in D["quarters"][-5:]))
    print("\n註：營收年增用同一個公司季度標籤比一年前；幣別依各公司（三星韓元、台股新台幣），百分比可直接比。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
