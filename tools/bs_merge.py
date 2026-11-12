"""把 data/bs-raw/<代號>.json（bs_fetch.py 的提案）合併進 data/<代號>.json 的 quarters[]。

  python3 tools/bs_merge.py <代號>…       合併後請接著跑 python3 tools/validate.py <代號>

規則：提案有值就寫入，沒有值一律 null（不估計、不內插）；每個欄位只要有 null，就在 notes.unavailable 加一行
「待確認：資產負債表欄位 <中文名>（<key>）：<n> 季沒有值（<季度範圍>）：<原因摘要>」。舊的同類行會先移除再重寫，所以可重複執行。
提案產生 8 個欄位以外的鍵一律忽略。
"""
import collections, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import health as H  # noqa

MARK = "待確認：資產負債表欄位 "


def main():
    for code in sys.argv[1:]:
        raw = json.load(open(os.path.join(ROOT, "data", "bs-raw", code + ".json"), encoding="utf8"))
        path = os.path.join(ROOT, "data", code + ".json")
        D = json.load(open(path, encoding="utf8"))
        by = {r["q"]: r for r in raw["quarters"]}
        miss = {k: [] for k in H.NEW}
        why = {k: collections.Counter() for k in H.NEW}
        for q in D["quarters"]:
            r = by.get(q["q"], {"vals": {}, "why": {"*": "提案沒有這一季"}})
            r = {"vals": dict(r["vals"]), "why": dict(r["why"])}
            ni, eps = q.get("ni"), q.get("eps")
            dil = r["vals"].get("dilSh")
            if dil is not None and ni is not None and eps is not None and abs(eps) >= 0.05 and abs(ni / dil - eps) > max(0.02, abs(eps) * 0.04):
                r["vals"]["dilSh"] = None
                r["why"]["dilSh"] = "淨利÷稀釋股數與 EPS 對不上（SEC 資料單位或分割換算疑似有誤，不使用）"
            ref = (ni / eps) if (ni is not None and eps is not None and abs(eps) >= 0.05 and ni / eps > 0) else (r["vals"].get("dilSh"))
            sh = r["vals"].get("shOut")
            if sh is not None and ref and not (0.2 <= sh / ref <= 5):
                r["vals"]["shOut"] = None
                r["why"]["shOut"] = "期末股數與淨利÷EPS 差一個數量級以上（單位或分割換算疑似有誤，不使用）"
            for k in H.NEW:
                v = r["vals"].get(k)
                q[k] = v
                if v is None:
                    miss[k].append(q["q"])
                    why[k][r["why"].get(k) or r["why"].get("*") or "來源沒有這個值"] += 1
        notes = D.setdefault("notes", {})
        un = [x for x in notes.get("unavailable", []) if not x.startswith(MARK)]
        for k in H.NEW:
            if miss[k]:
                reasons = "；".join(f"{w}（{n} 季）" for w, n in why[k].most_common(3))
                un.append(f"{MARK}{H.NAMES[k]}（{k}）：{len(miss[k])} 季沒有值（{miss[k][0]}～{miss[k][-1]}）：{reasons}")
        notes["unavailable"] = un
        with open(path, "w", encoding="utf8") as f:
            json.dump(D, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(code, {k: len(D["quarters"]) - len(miss[k]) for k in H.NEW}, "有值的季數")


if __name__ == "__main__":
    main()
