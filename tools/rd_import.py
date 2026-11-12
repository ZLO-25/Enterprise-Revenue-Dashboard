"""把 data/rd-sources/<代號>.txt 的公布日對應到 data/<代號>.json 的 quarters[].rd（一次性匯入與日後核對用）。

來源檔每列：  種類 期末日 日期   或   種類 季度標籤 日期
  Q／K／P  期末日對應：Q＝10-Q 申報日、K＝10-K 申報日（第四季用）、P＝財報新聞稿日  → rdB 為 f（申報日）或 p（新聞稿日）
  C        公司法說會日期（標籤對應）→ rdB c
  T        證交所 BWIBBU「財報年／季」欄位第一次換成該季的日期（標籤對應）→ rdB t
匹配規則：由季度標籤與 fiscalYearEnd 推出名目期末日，來源期末日差 ≤ 8 天；Q／K 申報日必須落在期末後 5～100 天內
（較晚的是後期財報的比較欄，不是原始申報日 → 該季 rd 留 null 並記待確認）。
用法：python3 tools/rd_import.py [代號 …]    加 --dry 只印不寫
"""
import calendar, datetime as dt, json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def nominal_end(label, fye):
    n, yy = int(label[0]), int(label[2:])
    fm, fd = map(int, fye.split("-"))
    y, m = 2000 + yy, fm - (4 - n) * 3
    while m <= 0:
        m += 12
        y -= 1
    return dt.date(y, m, min(fd, calendar.monthrange(y, m)[1]))


def load_src(code):
    ent = {"Q": [], "K": [], "P": [], "C": {}, "T": {}}
    p = os.path.join(ROOT, "data", "rd-sources", code + ".txt")
    if not os.path.exists(p):
        return ent
    for ln in open(p, encoding="utf8"):
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        k, a, b = ln.split()
        if k in ("C", "T"):
            ent[k][a] = b
        else:
            ent[k].append((dt.date.fromisoformat(a), dt.date.fromisoformat(b)))
    return ent


def assign(code, D):
    fye = D.get("company", {}).get("fiscalYearEnd") or "12-31"
    src = load_src(code)
    res = {}
    for q in D["quarters"]:
        lab = q["q"]
        rd = rdB = None
        if lab in src["T"]:
            rd, rdB = src["T"][lab], "t"
        elif lab in src["C"]:
            rd, rdB = src["C"][lab], "c"
        else:
            ne = nominal_end(lab, fye)
            kinds = ("K", "P") if lab[0] == "4" else ("Q", "P")
            for kind in kinds:
                for end, filed in src[kind]:
                    if abs((end - ne).days) <= 8 and 5 <= (filed - end).days <= 100:
                        rd, rdB = filed.isoformat(), "p" if kind == "P" else "f"
        res[lab] = (rd, rdB)
    return res


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    codes = args or [c["code"] for c in cfg["companies"] if c.get("enabled") and c.get("price")]
    for code in codes:
        path = os.path.join(ROOT, "data", code + ".json")
        raw = open(path, encoding="utf8").read()
        D = json.loads(raw)
        res = assign(code, D)
        nulls = [l for l, (r, _) in res.items() if r is None]
        print(f"[{code}] {len(res) - len(nulls)}/{len(res)} 季有公布日；空白：{nulls[:40]}")
        if "--dry" in sys.argv:
            continue
        for q in D["quarters"]:
            r, b = res[q["q"]]
            q["rd"] = r
            if r and b:
                q["rdB"] = b
            else:
                q.pop("rdB", None)
        out = json.dumps(D, ensure_ascii=False, indent=1) + ("\n" if raw.endswith("\n") else "")
        open(path, "w", encoding="utf8").write(out)


if __name__ == "__main__":
    main()
