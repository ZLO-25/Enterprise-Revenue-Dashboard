"""AI 資本支出鏈：把本站已有的財報數字，照「日曆季」加總成一張表（總經儀表板用）。建置時算，不存檔。

  買方（雲端大廠）每季資本支出 ──加總──▶ 四家合計、年增率、占營收比重
        │  （它們的支出，就是下游的營收）
        ▼
  賣方（晶片與代工）每季營收年增率

規則：
  · 數字全部來自 data/<代號>.json（各公司財報），這裡只做加總與年增率，不估計
  · 會計年度不同的公司（例如微軟 6 月結帳）用季末月份對到日曆季；季末不在 3／6／9／12 月的公司不能當買方（對不齊）
  · 某一季只要有一家買方缺資本支出，合計就留空，並在 missing 寫「待確認：」，不用其他家去推
清單在 data/macro/config.json 的 chain。用法：python3 tools/capex_chain.py（印最近 8 季）
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buffett as B
import health as H

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def prev_year(label):
    """'3Q26' → '3Q25'"""
    return f"{label[:2]}{int(label[2:]) - 1:02d}"


def cal_quarter(end_month):
    """季末月份 'YYYY-MM' → '2026Q3'；不是 3／6／9／12 月 → None（和日曆季對不齊）"""
    y, m = int(end_month[:4]), int(end_month[5:7])
    return f"{y}Q{m // 3}" if m % 3 == 0 else None


def yoy(now, before):
    if now is None or before is None or before <= 0:
        return None
    return round((now / before - 1) * 100, 1)


def company_rows(Q, fye):
    """每季：{label, end（季末月份）, capex, rev, revYoy}"""
    by = {q["q"]: q for q in Q}
    out = []
    for q in Q:
        p = by.get(prev_year(q["q"]))
        out.append({"q": q["q"], "end": B.end_month(q["q"], fye), "capex": q.get("capex"), "rev": q.get("rev"),
                    "revYoy": yoy(q.get("rev"), p.get("rev") if p else None)})
    return out


def compute(chain, companies, datasets, since="2015Q1"):
    """chain = {"buyers":[代號…], "suppliers":[代號…]}；companies = companies.json 的公司清單；datasets = {代號: data}。"""
    C = {c["code"]: c for c in companies}
    rows_of, missing = {}, []
    for code in chain["buyers"] + chain["suppliers"]:
        if code not in C or code not in datasets:
            missing.append(f"待確認：{code} 不在網站追蹤清單裡，資本支出鏈沒有算進去")
            continue
        D = datasets[code]
        fye = (D.get("company") or {}).get("fiscalYearEnd") or "12-31"
        rows_of[code] = company_rows(H.normq(D, C[code].get("schema")), fye)
    buyers = [b for b in chain["buyers"] if b in rows_of]
    cq = {}       # 日曆季 → {代號: 那一季的列}
    for b in buyers:
        for r in rows_of[b]:
            k = cal_quarter(r["end"])
            if k is None:
                missing.append(f"待確認：{b} 的季末（{r['end']}）不在 3／6／9／12 月，不能和其他買方加總")
                break
            cq.setdefault(k, {})[b] = r
    rows = []
    for k in sorted(cq):
        if k < since:
            continue
        got = cq[k]
        cap = {b: (got[b]["capex"] if b in got else None) for b in buyers}
        rev = {b: (got[b]["rev"] if b in got else None) for b in buyers}
        full = bool(buyers) and all(v is not None for v in cap.values())
        total = round(sum(cap.values()), 1) if full else None
        trev = sum(rev.values()) if full and all(v is not None for v in rev.values()) else None
        rows.append({"cq": k, "capex": cap, "total": total, "pctRev": round(total / trev * 100, 1) if total is not None and trev else None})
    by = {r["cq"]: r for r in rows}
    for r in rows:
        p = by.get(f"{int(r['cq'][:4]) - 1}{r['cq'][4:]}")
        r["yoy"] = yoy(r["total"], p["total"] if p else None)
    # 最後幾季如果有買方還沒公布：留空並說明（常見：財報季剛開始）
    for r in rows[-2:]:
        if r["total"] is None:
            lack = [C[b]["name"] for b in buyers if r["capex"][b] is None]
            missing.append(f"待確認：{r['cq']} 的合計：{'、'.join(lack)} 這一季的資本支出還沒有（尚未公布或財報沒有這一欄）")
    sup = []
    for s in chain["suppliers"]:
        if s not in rows_of:
            continue
        pts = [{"q": r["q"], "end": r["end"], "rev": r["rev"], "yoy": r["revYoy"]} for r in rows_of[s] if r["end"] >= since[:4] + "-01"]
        sup.append({"code": s, "name": C[s]["name"], "path": C[s]["path"], "currency": C[s].get("currency", ""), "points": pts})
    return {"buyers": [{"code": b, "name": C[b]["name"], "path": C[b]["path"]} for b in buyers], "rows": rows, "suppliers": sup, "missing": missing}


def load():
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    chain = json.load(open(os.path.join(ROOT, "data", "macro", "config.json"), encoding="utf8"))["chain"]
    cos = [c for c in cfg["companies"] if c.get("enabled")]
    data = {}
    for code in chain["buyers"] + chain["suppliers"]:
        p = os.path.join(ROOT, "data", code + ".json")
        if os.path.exists(p) and any(c["code"] == code for c in cos):
            data[code] = json.load(open(p, encoding="utf8"))
    return compute(chain, cos, data)


if __name__ == "__main__":
    out = load()
    names = [b["name"] for b in out["buyers"]]
    print("日曆季   " + "  ".join(f"{n:>8s}" for n in names) + "      合計   年增%  占營收%")
    for r in out["rows"][-8:]:
        print(f"{r['cq']}  " + "  ".join(f"{(r['capex'][b['code']] if r['capex'][b['code']] is not None else float('nan')):>10,.0f}" for b in out["buyers"]) +
              f"  {r['total'] if r['total'] is not None else '—':>9}  {r['yoy'] if r['yoy'] is not None else '—':>6}  {r['pctRev'] if r['pctRev'] is not None else '—':>6}")
    for s in out["suppliers"]:
        p = s["points"][-1]
        print(f"{s['name']}：{p['q']}（季末 {p['end']}）營收年增 {p['yoy']}%")
    for m in out["missing"]:
        print(m)
