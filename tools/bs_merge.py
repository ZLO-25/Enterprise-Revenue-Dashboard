"""把 data/bs-raw/<代號>.json（bs_fetch.py 的提案）合併進 data/<代號>.json 的 quarters[]。

  python3 tools/bs_merge.py <代號>…       合併 8 個欄位後請接著跑 python3 tools/validate.py <代號>
  python3 tools/bs_merge.py --only sbc <代號>…   只寫 sbc（當季股票酬勞）一個欄位，其他欄位與其他「待確認」說明一個字都不動
  python3 tools/bs_merge.py --only sbc --no-source <代號>…   來源不是 SEC XBRL 的公司：sbc 全部 null＋待確認說明（不估計）

規則：提案有值就寫入，沒有值一律 null（不估計、不內插）；每個欄位只要有 null，就在 notes.unavailable 加一行
「待確認：資產負債表欄位 <中文名>（<key>）：<n> 季沒有值（<季度範圍>）：<原因摘要>」。舊的同類行會先移除再重寫，所以可重複執行。
提案產生 8 個欄位以外的鍵一律忽略（預設模式）。
sbc 合理性：負值（年度累計相減得負）或單季 sbc ÷ 單季營收 > 60% → 不用，寫原因。
"""
import collections, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import health as H  # noqa

MARK = "待確認：資產負債表欄位 "


NO_SOURCE = "來源不是 SEC XBRL，尚未從年報讀取"
SBC_MAX_REV = 0.6
# 超過 60% 但已經逐季對過 SEC 申報數字的季度（只有這裡列的才放行；新的超標季度仍然先擋下來，對過才加進來）。
# 對法：GitHub Actions bs-fetch 的 dump 模式列出 ShareBasedCompensation 的原始事實，確認「本期累計 − 上一期累計」和提案一致，
# 而且同一季的稅前虧損規模對得上（2026-11-18 核對）。
SBC_VERIFIED = {
    "pltr": {"3Q20": "前三季累計 1,028.914 − 上半年累計 181.955 ＝ 846.959；同一季申報的稅前虧損是 861.9，規模對得上",
             "4Q20": "全年 1,270.702 − 前三季累計 1,028.914 ＝ 241.788",
             "2Q21": "上半年累計 426.473 − 第一季 193.731 ＝ 232.742"},
    "meta": {"2Q12": "10-Q 的單季值 1,106，也等於上半年累計 1,209 − 第一季 103"},
}
SBC_NOTE = "股票酬勞（sbc）占當季營收超過 60% 但已核對 SEC 申報數字、照實收錄的季度："


def sbc_reject(sb, rev):
    """sbc 合理性：回傳不使用的原因（字串），可以用就回傳 None。"""
    if sb is None:
        return None
    if sb < 0:
        return "年度累計相減得負值（來源口徑前後不一致，不使用）"
    if rev and rev > 0 and sb / rev > SBC_MAX_REV:
        return (f"股票酬勞占當季營收超過 {SBC_MAX_REV:.0%}（可能是上市前後一次認列的真實數字，也可能是單位或口徑有誤；"
                "還沒對過 10-Q 原文，先不使用）")
    return None


def main():
    args = sys.argv[1:]
    only = None
    if "--only" in args:
        i = args.index("--only")
        only = args[i + 1]
        del args[i:i + 2]
        if only != "sbc":
            raise SystemExit("--only 目前只支援 sbc")
    no_source = "--no-source" in args
    args = [a for a in args if a != "--no-source"]
    if no_source and not only:
        raise SystemExit("--no-source 要和 --only sbc 一起用")
    FIELDS = (only,) if only else H.BS8
    mark = MARK + H.NAMES[only] if only else MARK
    for code in args:
        if no_source:
            raw = {"quarters": []}
        else:
            raw = json.load(open(os.path.join(ROOT, "data", "bs-raw", code + ".json"), encoding="utf8"))
        path = os.path.join(ROOT, "data", code + ".json")
        D = json.load(open(path, encoding="utf8"))
        by = {r["q"]: r for r in raw["quarters"]}
        miss = {k: [] for k in FIELDS}
        why = {k: collections.Counter() for k in FIELDS}
        whyq = {k: {} for k in FIELDS}
        verified = []
        for q in D["quarters"]:
            r = by.get(q["q"], {"vals": {}, "why": {"*": "提案沒有這一季"}})
            r = {"vals": dict(r["vals"]), "why": dict(r["why"])}
            if q is D["quarters"][-1] and "*" in r["why"] and not r["vals"]:
                # 最新一季對不上，通常是新聞稿已公布、10-Q 還沒進 SEC XBRL（不是「早於 XBRL」）
                r["why"]["*"] = "SEC XBRL 還沒有這一季的資料（最新一季常要等 10-Q 申報後再抓）"
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
            bad = sbc_reject(r["vals"].get("sbc"), q.get("rev"))
            if bad and "超過" in bad and q["q"] in SBC_VERIFIED.get(code, {}):
                bad = None
                verified.append(q["q"])
            if bad:
                r["vals"]["sbc"] = None
                r["why"]["sbc"] = bad
            for k in ("buyback", "debt", "cash"):
                if (r["vals"].get(k) or 0) < 0:
                    r["vals"][k] = None
                    r["why"][k] = "年度累計相減得負值（來源口徑前後不一致，不使用）"
            for k in FIELDS:
                v = r["vals"].get(k)
                q[k] = v
                if v is None:
                    miss[k].append(q["q"])
                    wk = NO_SOURCE if no_source else (r["why"].get(k) or r["why"].get("*") or "來源沒有這個值")
                    why[k][wk] += 1
                    whyq[k].setdefault(wk, []).append(q["q"])
        notes = D.setdefault("notes", {})
        un = [x for x in notes.get("unavailable", []) if not x.startswith(mark) and not (only and x.startswith(f"待確認：{H.NAMES[only]}（{only}）"))]
        if "sbc" in FIELDS:
            un = [x for x in un if not x.startswith(SBC_NOTE)]
            if verified:
                un.append(SBC_NOTE + "；".join(f"{x}（{SBC_VERIFIED[code][x]}）" for x in verified) + "。單位百萬美元")
        for k in FIELDS:
            if miss[k] and no_source:
                un.append(f"待確認：{H.NAMES[k]}（{k}）：{NO_SOURCE}")
            elif miss[k]:
                # --only 模式（sbc）：季數少的原因把季別列出來，方便之後逐季對 10-Q
                reasons = "；".join(f"{w}（{n} 季" + (("：" + "、".join(whyq[k][w])) if only and n <= 6 else "") + "）" for w, n in why[k].most_common(3))
                un.append(f"{MARK}{H.NAMES[k]}（{k}）：{len(miss[k])} 季沒有值（{miss[k][0]}～{miss[k][-1]}）：{reasons}")
        notes["unavailable"] = un
        with open(path, "w", encoding="utf8") as f:
            json.dump(D, f, ensure_ascii=False, indent=1)
            f.write("\n")
        print(code, {k: len(D["quarters"]) - len(miss[k]) for k in FIELDS}, "有值的季數")


if __name__ == "__main__":
    main()
