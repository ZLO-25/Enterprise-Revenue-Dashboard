"""13F 抓完後的檢查（f13-quarterly workflow 在抓完跑；本機只讀 data/13f，不連網）。

  ✗ 開頭：資料對不起來（exit 1）
      - 持股加總（sumValue）對申報檔自己寫的 tableValueTotal，差超過 0.5% 且超過 1 千元
      - 合併前列數對 tableEntryTotal
      - config 的 tracked CUSIP，其 nameOfIssuer 不含任何 issuerKeys
  待確認： 開頭：要 Claude 處理（不影響 exit code，但 workflow 會開 issue）
      - nameOfIssuer 含 issuerKeys，但 CUSIP 不在 tracked 對照表（Claude 確認是同一家後填入 config）
      - 抓取時留下的需處理 notes（修正版缺 amendmentType、找不到原始 13F-HR…）
  ℹ 注意： 開頭：已知的資料事實，頁面上已經標出，不開 issue（不影響 exit code）
      - 保密延後揭露（isConfidentialOmitted）、主申報人與接手申報人都有 13F-HR、13F-NT 持股改由他人申報、申報人改變／上一季不可比較
      - config 的 oddCusips（已知的怪 CUSIP，原文照列、不對應本站公司）
用法：python3 tools/f13_check.py
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "data", "13f")


def key_match(name, key):
    """發行人名稱含 key（大小寫不分；key 前面不能接字母數字，避免 'AXT INC' 吃到 'MAXT INC'）。"""
    return re.search(r"(?<![A-Z0-9])" + re.escape(key.upper()), (name or "").upper()) is not None


def match_codes(name, tracked):
    return [c for c, t in tracked.items() if any(key_match(name, k) for k in t.get("issuerKeys") or [])]


def check_docs(cfg, docs):
    """回傳 (errors, todo, info)。docs: {id: <id>.json 內容}。"""
    err, todo, info = [], [], []
    odd = cfg.get("oddCusips") or {}
    INFO_NOTES = ("以主 CIK",)
    tracked = cfg.get("tracked") or {}
    cusip_code = {c: code for code, t in tracked.items() for c in (t.get("cusips") or [])}
    unmapped = {}   # (cusip, name) -> {"codes": set, "who": {id: 最新季}}
    for m in cfg["managers"]:
        d = docs.get(m["id"])
        if not d:
            todo.append(f"待確認：{m['id']} 沒有資料檔")
            continue
        for q in d["quarters"]:
            tag = f"{m['id']} {q['period']}"
            for n in q.get("notes") or []:
                body = n if n.startswith("待確認") else f"待確認：{tag} {n}"
                if any(k in n for k in INFO_NOTES):
                    info.append("ℹ 注意：" + body.replace("待確認：", "", 1) + f"（{tag}）")
                else:
                    todo.append(body)
            if q.get("chgNote"):
                info.append(f"ℹ 注意：{tag} {q['chgNote']}")
            if not q["holdingsKnown"]:
                by = "、".join(o["name"] for o in (q.get("notice") or {}).get("by") or []) or "未列名"
                info.append(f"ℹ 注意：{tag} 申報的是 {q['form']}，持股改由 {by} 申報，這季沒有持股數字")
                continue
            tot, sm = q.get("totalValue"), q.get("sumValue")
            if tot is not None and sm is not None and abs(sm - tot) > max(tot * 0.005, 1000):
                err.append(f"✗ {tag} 持股加總 {sm:,} 對不上申報檔的 tableValueTotal {tot:,}")
            if q.get("entries") is not None and q.get("rawRows") != q["entries"]:
                err.append(f"✗ {tag} 列數 {q['rawRows']}（合併前）對不上 tableEntryTotal {q['entries']}")
            if q.get("confidential"):
                info.append(f"ℹ 注意：{tag} 申報檔標示有保密延後揭露的持股（isConfidentialOmitted），這季持股不完整")
            for h in q["holdings"]:
                code = cusip_code.get(h["cusip"])
                hit = match_codes(h["name"], tracked)
                if h["cusip"] in odd:
                    info.append(f"ℹ 注意：CUSIP {h['cusip']}：{odd[h['cusip']]}")
                    continue
                if code:
                    keys = tracked[code].get("issuerKeys") or []
                    if keys and not any(key_match(h["name"], k) for k in keys):
                        err.append(f"✗ {tag} CUSIP {h['cusip']} 在對照表是 {code}，但申報的名稱是「{h['name']}」，不含 issuerKeys")
                elif hit:
                    u = unmapped.setdefault((h["cusip"], h["name"]), {"codes": set(), "who": {}})
                    u["codes"].update(hit)
                    u["who"].setdefault(m["id"], q["period"])
    for (cusip, name), u in sorted(unmapped.items()):
        who = "、".join(f"{k}（{v}）" for k, v in sorted(u["who"].items()))
        todo.append(f"待確認：{who} 持有「{name}」CUSIP {cusip}，名稱像 {'/'.join(sorted(u['codes']))}，但不在 data/13f/config.json 的 tracked 對照表")
    info = list(dict.fromkeys(info))
    return err, todo, info


def main():
    with open(os.path.join(DIR, "config.json"), encoding="utf8") as f:
        cfg = json.load(f)
    docs = {}
    for m in cfg["managers"]:
        p = os.path.join(DIR, m["id"] + ".json")
        if os.path.exists(p):
            with open(p, encoding="utf8") as f:
                docs[m["id"]] = json.load(f)
    if not docs:
        print("data/13f 還沒有資料檔（尚未抓取）")
        return 0
    err, todo, info = check_docs(cfg, docs)
    for l in err + todo + info:
        print(l)
    print(f"檢查完成：{len(docs)} 位經理人，✗ {len(err)}、待確認 {len(todo)}、ℹ 注意 {len(info)}")
    return 1 if err else 0


if __name__ == "__main__":
    sys.exit(main())
