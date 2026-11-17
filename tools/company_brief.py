#!/usr/bin/env python3
"""公司分析用的「一頁資料摘要」（給 long-term-company-analysis skill 用；只讀檔）。

    python3 tools/company_brief.py <代號> [--n 8]

為什麼有這支：data/<代號>.json 每份約 5 萬字，整份讀進來很花 token，而分析只用得到
最近幾季的重點數字。這支印出約 3 千字：近 N 季損益與現金流（含年增率）、最新財測、
本益比位置、論點卡與燈號、最新一季摘要、待確認清單。數字全部照抄資料檔，不另外計算來源以外的東西
（年增率、TTM 由資料檔的數字直接相除）。需要更細的欄位時，再用 python3 -c 讀那個欄位。
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))


def jload(*p, default=None):
    path = os.path.join(ROOT, *p)
    return json.load(open(path, encoding="utf8")) if os.path.exists(path) else default


def f(v, d=0):
    if v is None:
        return "—"
    return f"{v:,.{d}f}"


def yoy(Q, i, k):
    if i < 4 or Q[i].get(k) is None or not Q[i - 4].get(k):
        return "—"
    return f"{(Q[i][k] / Q[i - 4][k] - 1) * 100:+.0f}%"


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    code, n = a[0].lower(), 8
    if "--n" in a:
        n = int(a[a.index("--n") + 1])
    cfg = jload("companies.json")
    c = next((x for x in cfg["companies"] if x["code"] == code), None)
    if not c:
        sys.exit(f"找不到 {code}")
    D = jload("data", code + ".json")
    Q = D.get("quarters", [])
    unit = (D.get("company") or {}).get("unit") or "百萬（見 company.unit）"
    print(f"# {c.get('name')}（{code}）　產業 {c.get('sector')}　資料 asOf {D.get('asOf')}　金額單位 {unit}")
    print(f"\n## 近 {n} 季（來源：data/{code}.json；YoY 為與 4 季前相比）")
    print("季度 | 營收 | YoY | 毛利率% | 營益率% | EPS | EPS YoY | 營業現金流 | 資本支出 | FCF | 公布日")
    s = max(0, len(Q) - n)
    for i in range(s, len(Q)):
        q = Q[i]
        print(" | ".join([q["q"], f(q.get("rev")), yoy(Q, i, "rev"), f(q.get("gm"), 1), f(q.get("om"), 1),
                          f(q.get("eps"), 2), yoy(Q, i, "eps"), f(q.get("ocf")), f(q.get("capex")), f(q.get("fcf")),
                          str(q.get("rd"))]))
    if len(Q) >= 8:
        t = lambda k, a_, b_: sum((x.get(k) or 0) for x in Q[a_:b_])  # noqa: E731
        print(f"TTM 營收 {f(t('rev', -4, None))}（前一年 {f(t('rev', -8, -4))}）；TTM FCF {f(t('fcf', -4, None))}（前一年 {f(t('fcf', -8, -4))}）")

    g = D.get("guidance") or {}
    if g:
        print(f"\n## 最新財測（{g.get('issued')}，{g.get('note', '')}）")
        for it in g.get("items", []):
            print(f"- {it.get('label')} {it.get('period')}：{it.get('lo')}～{it.get('hi')} {it.get('unit', '')}　{it.get('note', '')}")

    import thesis as T
    try:
        _, val, hl, Qn = T.context(code)
        st = (val or {}).get("stats", {})
        print(f"\n## 本益比（建置時由 tools/pe.py 算，股價 {st.get('priceM')}）")
        print(f"最新 {st.get('latest')}（{st.get('latestM')}）；5 年中位數 {st.get('med5')}；10 年中位數 {st.get('med10')}；"
              f"10 年百分位 {st.get('pct10')}；預估本益比 {st.get('fpeLatest') or '待確認：無快照'}（分析師預估）")
    except Exception as e:  # noqa: BLE001
        val = hl = Qn = None
        print(f"\n## 本益比：待確認（計算失敗：{type(e).__name__}）")

    th = jload("data", "thesis", code + ".json")
    if th:
        print(f"\n## 論點卡（{th.get('status')}，類型 {th.get('type')}，更新 {th.get('updated')}）")
        print("一句話：" + str(th.get("oneLiner")))
        L = {}
        if val is not None:
            try:
                L = T.lights(th, Qn, val, hl)
            except Exception:  # noqa: BLE001
                L = {}
        for m in th.get("metrics", []):
            k = m.get("key") or m.get("k")
            light = L.get(k, {}).get("light", "?") if L else "?"
            print(f"- [{light}] {m.get('name') or m.get('label') or k}：{m.get('op', '')} {m.get('thr', m.get('value', ''))}　{m.get('note', '')[:80]}")
        if th.get("breakWhen"):
            print("論點破了：" + json.dumps(th["breakWhen"], ensure_ascii=False)[:300])
        if th.get("risks"):
            print("風險：" + json.dumps(th["risks"], ensure_ascii=False)[:400])

    sm = D.get("summary")
    if sm:
        print(f"\n## 最新一季摘要（{sm.get('status')}）")
        print(json.dumps({k: sm.get(k) for k in ("headline", "scorecard", "outlook") if sm.get(k)}, ensure_ascii=False)[:1500])

    un = (D.get("notes") or {}).get("unavailable") or []
    print(f"\n## 待確認（{len(un)} 項，列最近 5 項）")
    for u in un[-5:]:
        print("- " + (u if isinstance(u, str) else json.dumps(u, ensure_ascii=False))[:160])
    ms = D.get("milestones") or []
    if ms:
        print("\n## 最近 5 個里程碑")
        for m in sorted(ms, key=lambda x: str(x.get("date") or x.get("d") or ""))[-5:]:
            print("- " + json.dumps(m, ensure_ascii=False)[:160])


if __name__ == "__main__":
    main()
