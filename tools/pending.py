"""「待確認」項目分級與清單（每家公司 data/<代號>.json 的 notes.unavailable）。

用法：
  python3 tools/daily.py pending        分級統計＋寫 reports/pending.md（也可直接 python3 tools/pending.py）
分級規則（以那一行提到的「最近一季」為準；範圍如 1Q10～3Q27 取較晚的一端）：
  近期    最近一季 ≥ 公司最新季 − 1（這是現在就該處理的）
  近三年  最近一季在最新季往前 12 季內
  歷史    更早（多半是公司當時沒公布或來源已不存在，補不回來也不影響現在的判斷）
  無季度  以「待確認：」開頭但沒寫季度（要人工分類）
  說明    不是以「待確認：」開頭的行（資料範圍、口徑說明，不算待確認）
每月第一個週日由每週排程挑最多 6 項「近期」處理（見 docs/WEEKLY_NEWS_PROMPT.md）。
"""
import datetime as dt
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QRE = re.compile(r"(\d)Q(\d\d)")
CATS = ("recent", "y3", "old", "noq")
NAME = {"recent": "近期", "y3": "近三年", "old": "歷史", "noq": "無季度", "note": "說明"}


def qkey(label):
    m = QRE.fullmatch(label)
    return (2000 + int(m.group(2))) * 4 + int(m.group(1)) if m else None


def classify(line, latest_key):
    """回傳 'note'|'recent'|'y3'|'old'|'noq'。latest_key＝公司最新季的 qkey。"""
    if not isinstance(line, str) or not line.startswith("待確認："):
        return "note"
    keys = [(2000 + int(m.group(2))) * 4 + int(m.group(1)) for m in QRE.finditer(line)]
    if not keys or latest_key is None:
        return "noq"
    k = max(keys)
    if k >= latest_key - 1:
        return "recent"
    if k >= latest_key - 11:
        return "y3"
    return "old"


def scan():
    """回傳 {code: {name, latest, items:{cat:[line]}}}（啟用中的公司）。"""
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    out = {}
    for c in cfg["companies"]:
        if not c.get("enabled"):
            continue
        p = os.path.join(ROOT, "data", c["code"] + ".json")
        if not os.path.exists(p):
            continue
        D = json.load(open(p, encoding="utf8"))
        Q = D.get("quarters") or []
        latest = Q[-1]["q"] if Q else None
        lk = qkey(latest) if latest else None
        notes = D.get("notes")
        lines = (notes.get("unavailable") if isinstance(notes, dict) else None) or []
        items = {k: [] for k in CATS + ("note",)}
        for x in lines:
            items[classify(x, lk)].append(x)
        out[c["code"]] = {"name": c.get("name") or c["code"], "latest": latest, "items": items}
    return out


def counts(S):
    return {code: {k: len(v["items"][k]) for k in CATS} for code, v in S.items()}


def report(S):
    tot = {k: sum(len(v["items"][k]) for v in S.values()) for k in CATS}
    L = ["# 待確認清單", "", f"產生日期：{dt.date.today().isoformat()}（`python3 tools/daily.py pending`）。分級規則見 `tools/pending.py`。", "",
         f"合計：近期 **{tot['recent']}**、近三年 {tot['y3']}、歷史 {tot['old']}、無季度 {tot['noq']}（「說明」行不算待確認）。", "",
         "| 公司 | 最新季 | 近期 | 近三年 | 歷史 | 無季度 |", "|---|---|---|---|---|---|"]
    for code, v in S.items():
        c = {k: len(v["items"][k]) for k in CATS}
        L.append(f"| {code} | {v['latest']} | {c['recent']} | {c['y3']} | {c['old']} | {c['noq']} |")
    for cat in ("recent", "noq"):
        L += ["", f"## {NAME[cat]}（逐項）", ""]
        for code, v in S.items():
            for x in v["items"][cat]:
                L.append(f"- **{code}**：{x[:160]}{'…' if len(x) > 160 else ''}")
    return "\n".join(L) + "\n"


def main():
    S = scan()
    c = counts(S)
    tot = {k: sum(v[k] for v in c.values()) for k in CATS}
    print(f"待確認：近期 {tot['recent']}、近三年 {tot['y3']}、歷史 {tot['old']}、無季度 {tot['noq']}")
    for code, v in c.items():
        if v["recent"]:
            print(f"  {code} 近期 {v['recent']}")
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", "pending.md"), "w", encoding="utf8") as f:
        f.write(report(S))
    print("→ reports/pending.md")


if __name__ == "__main__":
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    main()
