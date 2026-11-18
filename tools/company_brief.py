#!/usr/bin/env python3
"""公司分析用的「一頁資料摘要」（給 long-term-company-analysis skill 用；只讀檔）。

    python3 tools/company_brief.py <代號> [--n 8]

為什麼有這支：data/<代號>.json 每份約 5 萬字，整份讀進來很花 token，而分析只用得到
最近幾季的重點數字。這支印出約 3～6 千字：近 N 季損益與現金流（含年增率）、分部營收與營運指標（segments／extra）、最新財測、
本益比位置、論點卡與燈號、最新一季摘要、待確認清單。數字全部照抄資料檔，不另外計算來源以外的東西
（年增率、TTM 由資料檔的數字直接相除）。需要更細的欄位時，再用 python3 -c 讀那個欄位。
"""
import json, os, sys
import pe as PE

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

    for key in ("segments", "extra"):
        blk = D.get(key)
        if not isinstance(blk, dict) or not blk.get("quarters"):
            continue
        ks = blk.get("keys", [])
        print(f"\n## {blk.get('title', key)}（{blk.get('unit', '見各欄')}；近 {min(n, len(blk['quarters']))} 季，來源 data/{code}.json 的 {key}）")
        print("季度 | " + " | ".join(k.get("n", k.get("k")) for k in ks))
        for row in blk["quarters"][-n:]:
            print(row.get("q") + " | " + " | ".join(f(row.get(k["k"]), 1 if isinstance(row.get(k["k"]), float) and row.get(k["k"]) < 100 else 0) for k in ks))

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
        print(f"最新 {PE.pe_text(st.get('latest'))}（{st.get('latestM')}）；5 年中位數 {PE.pe_text(st.get('med5'))}；10 年中位數 {st.get('med10')}；"
              f"10 年百分位 {st.get('pct10')}；預估本益比 {st.get('fpeLatest') or '待確認：無快照'}（分析師預估）")
    except Exception as e:  # noqa: BLE001
        val = hl = Qn = None
        print(f"\n## 本益比：待確認（計算失敗：{type(e).__name__}）")

    try:
        bf = T.buffett_for(c, D, val, hl, jload("data", "thesis", code + ".json")) if val is not None else None
    except Exception as e:  # noqa: BLE001
        bf = None
        print(f"\n## 巴菲特＋蒙格檢查表摘要：待確認（計算失敗：{type(e).__name__}）")
    if bf:
        # 全部是 tools/buffett.py 建置時算好的數字；觀念是意譯，見 docs/BUFFETT_MUNGER.md
        E, S, R, BB, RT, IM, NP, VI = bf["ey"], bf.get("summary"), bf["record"], bf.get("buyback"), bf.get("retained"), bf["implied"], bf["normPe"], bf["vsIndex"]
        WHY = {"missing": "欄位待確認", "neg": "分母不是正數或虧損", "short": "資料不夠長", "noprice": "沒有股價資料", "loss": "虧損或本益比不可用", "noisy": "本益比超過 200 倍",
               "norates": "讀不到公債資料", "nobond": "網站沒有該國公債資料", "noidx": "網站沒有不含股息的同幣別指數資料", "nodps": "本站沒有收錄每股股利", "nosbc": "股票酬勞欄位待確認（來源不是 SEC 申報檔）"}
        w = lambda c: WHY.get(c, c or "沒有資料")  # noqa: E731
        v = lambda x, u="": "算不出來" if x is None else f"{x}{u}"  # noqa: E731
        print("\n## 巴菲特＋蒙格檢查表摘要（tools/buffett.py，建置時算；分析結論要引用這裡的數字）")
        if E.get("ey") is None:
            print(f"- 盈餘殖利率：算不出來（{w(E.get('why'))}）")
        elif E.get("bond"):
            print(f"- 盈餘殖利率 {E['ey']}%（本益比 {E['pe']}，{E['m']}）對 {E['bond']['name']} {E['bond']['v']}%（{E['bond']['d']}）＝ 差 {E['spread']:+.2f} 個百分點")
        else:
            print(f"- 盈餘殖利率 {E['ey']}%；公債：{w(E.get('bondWhy'))}" + (f"；參考 {E['ref']['v']}%（{E['refNote']}）" if E.get("ref") else ""))
        if S:
            print(f"- 十年成績單：ROE 近 20 季達 15% {S['roeOk']['ok']}/{S['roeOk']['n']}、近 40 季 {S['roeOk40']['ok']}/{S['roeOk40']['n']}；EPS 比前一年高 {S['epsUp']['up']}/{S['epsUp']['n']} 年；虧損 {S['lossYears']}/{S['years']} 年；毛利率三年變化 {v(S['gmChg3'], ' 個百分點')}；每股淨值五年年化 {v(S['bvCagr5'], '%')}")
        if BB:
            rows = [r for r in BB["rows"] if r.get("where")]
            cnt = {k: sum(1 for r in rows if r["where"] == k) for k in ("偏貴時買", "接近平常", "偏便宜時買")}
            print(f"- 回購買在：" + "、".join(f"{k} {n} 年" for k, n in cnt.items()) + f"（只算有回購的年度點）；股數五年變化 {v(BB['shChg5'], '%')}；近四季回購占市值 {v(BB['buybackYield'], '%')}")
        if RT and RT.get("ratio") is not None:
            print(f"- 保留盈餘測試：每留 1 元盈餘創造 {RT['ratio']} 元市值（留下 {RT['kept']}，市值增加 {RT['mcapChg']}，{RT['m0']}→{RT['mNow']}）" + (f"；{RT['preDivQ']} 季以前尚未配息，股利當 0" if RT.get("preDivQ") else ""))
        elif RT:
            print(f"- 保留盈餘測試：算不出來（{w(RT.get('why'))}）{RT.get('note') or ''}")
        OW = bf.get("owner")
        if OW:
            if OW.get("sbcRev") is None:
                print(f"- 股票酬勞與業主盈餘（近似）：算不出來（{w((OW.get('why') or {}).get('sbcRev'))}）")
            else:
                oy = "算不出來" if OW.get("oeYield") is None else f"{OW['oeYield']}%" + ("" if OW.get("oeSpread") is None else f"，對公債差 {OW['oeSpread']:+.2f} 個百分點")
                print(f"- 股票酬勞占營收 {OW['sbcRev']}%（近五年中位數 {v(OW.get('sbcRev5med'), '%')}，{OW['q']}）；扣股票酬勞後的自由現金流率 {v(OW.get('fcfSbcRate'), '%')}（未扣 {v(OW.get('fcfRate'), '%')}）；扣酬勞後現金流殖利率 {oy}。業主盈餘的近似：財報沒有拆維持性與成長性資本支出")
        g = IM.get("g") or {}
        print(f"- 價格隱含的成長：" + (f"每年 {g.get('15')}%（十年後 15 倍）／{g.get('20')}%（20 倍）" if g else f"算不出來（{w(IM['why'])}）") + f"（{IM['assume']['text']}）；公司近五年 EPS 年化成長 {v(IM['epsCagr5'], '%')}")
        print(f"- 十年平均獲利本益比：{v(NP['normPe'], ' 倍') if NP['normPe'] is not None else '算不出來（' + w(NP['why']) + '）'}（循環股才是主角）")
        if VI.get("rows"):
            print("- 對指數（" + str(VI["index"]) + "，兩邊都不含股利）：" + "；".join(f"{r['years']} 年 股價 {r['stock']}% 指數 {r['index']}%" for r in VI["rows"] if r["stock"] is not None))
        else:
            print(f"- 對指數：算不出來（{w(VI.get('why'))}）")
        print(f"- 類型資格（穩健複利要十年紀錄）：{R['quarters']} 季；結果 {'算不出來' if R['tenYearOk'] is None else ('通過' if R['tenYearOk'] else '未通過')}" + (f"（{'；'.join(R['why'])}）" if R["why"] else ""))

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
            print(f"- [{light}]{'（輔助）' if m.get('role') == 'aux' else ''} {m.get('name') or m.get('label') or k}：{m.get('op', '')} {m.get('thr', m.get('value', ''))}　{m.get('note', '')[:80]}")
        if th.get("warnWhen"):
            print("季度警示（黃燈，先觀察）：" + json.dumps(th["warnWhen"], ensure_ascii=False)[:300])
        if th.get("breakWhen"):
            print("論點破了（結構性）：" + json.dumps(th["breakWhen"], ensure_ascii=False)[:300])
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
