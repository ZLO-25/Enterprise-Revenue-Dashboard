"""核對各公司資料；任何一項沒過就以非 0 結束（排程看到失敗就不要發佈）。
用法：python3 tools/validate.py [代號 ...]    不給代號＝所有啟用中的公司
新增公司時，在 CHECKS 加一個以 schema 或代號為鍵的函式即可。
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?|-Q[1-4]|-H[12])?$")


def load(code):
    with open(os.path.join(ROOT, "data", code + ".json"), encoding="utf8") as f:
        return json.load(f)


def common(code, D, err):
    """所有公司共通：日期格式、事件與里程碑欄位。"""
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", D.get("asOf", "")):
        err.append("asOf 格式必須是 YYYY-MM-DD")
    for m in D.get("milestones", []):
        if not DATE_RE.match(m.get("d", "")):
            err.append(f"milestones 日期格式錯誤：{m.get('d')}")
        if m.get("st") not in ("p", "f"):
            err.append(f"milestones st 必須是 p 或 f：{m.get('t')}")
        if m.get("unc") and not (m.get("note") or "").startswith("待確定"):
            err.append(f"unc 的項目 note 要以「待確定：」開頭：{m.get('t')}")
        if not m.get("src"):
            err.append(f"milestones 缺 src：{m.get('t')}")
    for f in D.get("fabs", []):
        for e in f["ms"]:
            if not DATE_RE.match(e["d"]):
                err.append(f"fabs 日期格式錯誤：{f['id']} {e['d']}")
    ids = [f["id"] for f in D.get("fabs", [])]
    if len(ids) != len(set(ids)):
        err.append("fabs id 重複")
    for e in D.get("events", []):
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", e["date"]):
            err.append(f"events 日期格式錯誤：{e['date']}")


def tsmc(D, err):
    """每一季 rev 與該季三個月 monthly 加總相差不超過 200（百萬元）。"""
    for q in D["quarters"]:
        qi, yy = int(q["q"][0]), 2000 + int(q["q"][2:])
        ms = D["monthly"].get(str(yy), [])[(qi - 1) * 3:qi * 3]
        if len(ms) == 3 and abs(sum(ms) - q["rev"]) > 200:
            err.append(f"{q['q']} 季營收 {q['rev']} 與月營收加總 {sum(ms)} 差 {abs(sum(ms) - q['rev'])} 超過 200")
    labels = [q["q"] for q in D["quarters"]]
    if len(labels) != len(set(labels)):
        err.append("quarters 季度重複")


def v1_pltr(D, err):
    """政府＋商業＝總營收；四季加總對照 annual；毛利率、淨利率自洽；非 GAAP 對照公司全年公布值。"""
    Q, P = D["quarters"], D["pltr"]["quarters"]
    if [q["q"] for q in Q] != [p["q"] for p in P]:
        err.append("quarters 與 pltr.quarters 的季度不一致")
        return
    for q, p in zip(Q, P):
        if abs(p["gov"] + p["com"] - q["rev"]) > 0.15:
            err.append(f"{q['q']} 政府＋商業 {p['gov'] + p['com']:.1f} ≠ 營收 {q['rev']}")
        if abs(q["gp"] / q["rev"] * 100 - q["gm"]) > 0.15:
            err.append(f"{q['q']} 毛利率與毛利／營收不符")
        if abs(q["opInc"] / q["rev"] * 100 - q["om"]) > 0.15:
            err.append(f"{q['q']} 營業利益率與營業利益／營收不符")
    for y, a in D["annual"].items():
        qs = [i for i, q in enumerate(Q) if q["q"].endswith("Q" + y[2:])]
        if len(qs) != 4 or a.get("gp") is None:
            continue
        pick = lambda key, src: sum((src[i][key] or 0) for i in qs)
        for key, src, akey in [("rev", Q, "rev"), ("gp", Q, "gp"), ("opInc", Q, "opInc"), ("ni", Q, "ni"), ("ocf", Q, "ocf"), ("capex", Q, "capex"),
                               ("adjOpInc", P, "adjOpInc"), ("adjFcf", P, "adjFcf"), ("sbc", P, "sbc")]:
            if abs(pick(key, src) - a[akey]) > 0.6:
                err.append(f"{y} 年 {key} 四季加總 {pick(key, src):.1f} ≠ 全年 {a[akey]}（可能是四捨五入以外的差異）")
    g = D["guidance"]
    if not (g["nextQ"]["revLo"] <= g["nextQ"]["revHi"] and g["year"]["revLo"] <= g["year"]["revHi"]):
        err.append("guidance 區間上下限顛倒")


CHECKS = {"tsmc": tsmc, "pltr": v1_pltr}


def main():
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    codes = sys.argv[1:] or [c["code"] for c in cfg["companies"] if c.get("enabled")]
    failed = False
    for code in codes:
        err = []
        try:
            D = load(code)
            common(code, D, err)
            if code in CHECKS:
                CHECKS[code](D, err)
            else:
                print(f"[{code}] 注意：沒有專屬核對函式（tools/validate.py 的 CHECKS），只做共通檢查")
        except Exception as e:  # noqa
            err.append(f"讀取失敗：{e!r}")
        print(f"[{code}] " + ("通過" if not err else f"{len(err)} 項未通過"))
        for e in err:
            print("   -", e)
        failed |= bool(err)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
