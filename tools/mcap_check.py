#!/usr/bin/env python3
"""市值排名每週檢查（給排程 Claude 跑；只讀檔、不連網、不改檔）

    python3 tools/mcap_check.py      → 印出幾行結果；全部正常 exit 0，有問題 exit 1

  檢查：① 這週六的資料到了沒 ② 三張榜各 30 列、依市值排序、每列有來源
        ③ 待確認／警告有幾筆 ④ 黃金地上存量（config.json goldStock）是否該更新了
  另外印出「名次變動」前幾名，排程回報直接用。
"""
import datetime as dt, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "data", "mcap")
TPE = dt.timezone(dt.timedelta(hours=8))
TITLE = {"global": "全球公司", "us": "美國公司", "assets": "全球資產"}


def main():
    cfg = json.load(open(os.path.join(DIR, "config.json"), encoding="utf8"))
    top, bad, info = cfg["top"], [], []
    p = os.path.join(DIR, "latest.json")
    if not os.path.exists(p):
        print("✗ 沒有 data/mcap/latest.json：mcap-weekly 還沒成功跑過"); return 1
    d = json.load(open(p, encoding="utf8"))
    today = dt.datetime.now(TPE).date()
    sat = today - dt.timedelta(days=(today.weekday() - 5) % 7)
    run = dt.date.fromisoformat(d["runDate"])
    (bad if run < sat else info).append(f"資料抓取 {d['fetchedAt']}" + ("（✗ 比本週六舊：mcap-weekly 這週還沒成功）" if run < sat else ""))
    for k in TITLE:
        rows = d["lists"].get(k) or []
        caps = [r["cap"] for r in rows]
        if len(rows) != top: bad.append(f"{TITLE[k]}只有 {len(rows)} 列（應為 {top}）")
        if caps != sorted(caps, reverse=True): bad.append(f"{TITLE[k]}沒有依市值排序")
        if any(not r.get("src") for r in rows): bad.append(f"{TITLE[k]}有列沒有來源")
        pend = [f"{r['rank']}.{r['name']}" for r in rows if (r.get("flag") or "").startswith("待確認")]
        if pend: info.append(f"{TITLE[k]}待確認 {len(pend)} 筆：" + "、".join(pend))
    for m in d.get("metals") or []:
        if m.get("last") is None: bad.append(f"AI 相關金屬 {m['name']} 這週沒有價格")
    if d.get("metals"):
        info.append("AI 相關金屬（1 週／52 週）：" + "、".join(f"{m['name']} {m.get('w1')}%／{m.get('w52')}%" for m in d["metals"]))
    else:
        bad.append("latest.json 沒有 AI 相關金屬（metals）")
    if d.get("assetsAsOf"): bad.append(f"全球資產榜沿用 {d['assetsAsOf']} 的舊資料")
    for w in d.get("warnings") or []: bad.append(w)
    gs = cfg["goldStock"]
    if (today - dt.date.fromisoformat(gs["asOf"])).days > 135:
        info.append(f"黃金地上存量是 {gs['label']}（{gs['tonnes']:,} 公噸），WGC 可能已公布新一季：查 {gs['url']}")
    # 名次變動（和上一次比）
    prev = d.get("prev") and os.path.join(DIR, "history", d["prev"] + ".json")
    if prev and os.path.exists(prev):
        P = json.load(open(prev, encoding="utf8"))
        for k in TITLE:
            old = {r["name"]: r["rank"] for r in P["lists"].get(k) or []}
            mv = []
            for r in d["lists"].get(k) or []:
                o = old.get(r["name"])
                if o is None: mv.append((99, f"{r['name']} 新進榜第 {r['rank']}"))
                elif o != r["rank"]: mv.append((abs(o - r["rank"]), f"{r['name']} {o}→{r['rank']}"))
            out = [n for n in old if n not in {r["name"] for r in d["lists"].get(k) or []}]
            mv.sort(key=lambda x: -x[0])
            s = "、".join(m for _, m in mv[:5]) or "沒有變動"
            info.append(f"{TITLE[k]}名次變動（vs {d['prev']}）：{s}" + (f"；掉出榜外：{'、'.join(out)}" if out else ""))
    for k in TITLE:
        r = (d["lists"].get(k) or [{}])[:3]
        info.append(f"{TITLE[k]}前三：" + "、".join(f"{x.get('name')} {x.get('cap', 0)/1e12:.2f} 兆" for x in r))
    for s in bad: print("✗", s)
    for s in info: print("·", s)
    print("結果：", "有問題" if bad else "正常")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
