"""核對各公司資料與設定；任何一項沒過就以非 0 結束（排程看到失敗就不要發佈）。

用法：python3 tools/validate.py [代號 ...]    不給代號＝所有啟用中的公司（並一併檢查 companies.json）

檢查分三層，新增公司通常「一行程式都不用加」：
  1. 設定層 companies.json：欄位齊全、代號唯一、path＝代號/、資料檔／模板／SOURCES.md 都存在
  2. 共通層（所有 schema）：asOf、events、milestones、fabs 的日期與欄位格式
  3. 資料層：
     - schema v1 → 通用核對 v1_generic（季度順序、毛利率／營益率自洽、FCF、四季＝全年、segments 加總、waterfall 加總、財測區間）
     - 另外若 CHECKS 有該公司的專屬函式（例：tsmc、pltr）就再多做一層
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?|-Q[1-4]|-H[12])?$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
Q_RE = re.compile(r"^[1-4]Q\d{2}$")
REQUIRED_CFG = ("code", "name", "nameEn", "ticker", "exchange", "currency", "frequency", "path", "schema", "template", "title", "description", "enabled")


def load(code):
    with open(os.path.join(ROOT, "data", code + ".json"), encoding="utf8") as f:
        return json.load(f)


def qkey(q):
    return (int(q[2:]), int(q[0]))


# ---------- 1. 設定層 ----------
def check_config(cfg, err):
    seen = set()
    for c in cfg.get("companies", []):
        tag = c.get("code", "?")
        for k in REQUIRED_CFG:
            if k not in c:
                err.append(f"companies.json [{tag}] 缺欄位 {k}")
        if not re.match(r"^[a-z0-9]+$", tag):
            err.append(f"companies.json [{tag}] code 只能是小寫英數字")
        if tag in seen:
            err.append(f"companies.json code 重複：{tag}")
        seen.add(tag)
        if c.get("path") != tag + "/":
            err.append(f"companies.json [{tag}] path 應為 {tag}/（現在是 {c.get('path')}）")
        if c.get("frequency") not in ("quarterly", "monthly+quarterly"):
            err.append(f"companies.json [{tag}] frequency 只能是 quarterly 或 monthly+quarterly")
        if not c.get("enabled"):
            continue
        for rel in (("data", tag + ".json"), ("templates", c.get("template", "") + ".frag.html"), ("companies", tag, "SOURCES.md")):
            if not os.path.exists(os.path.join(ROOT, *rel)):
                err.append(f"[{tag}] 找不到 {'/'.join(rel)}")
        if not c.get("primarySource", {}).get("url"):
            err.append(f"companies.json [{tag}] 缺 primarySource {{n, url}}（首頁「資料新鮮度與來源」要用）")


# ---------- 2. 共通層 ----------
def common(code, D, err):
    if not DAY_RE.match(D.get("asOf", "")):
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
        if not DAY_RE.match(e.get("date", "")):
            err.append(f"events 日期格式錯誤：{e.get('date')}")
        if not e.get("t"):
            err.append(f"events 缺說明 t：{e.get('date')}")
    labels = [q["q"] for q in D.get("quarters", [])]
    if len(labels) != len(set(labels)):
        err.append("quarters 季度重複")
    bad = [q for q in labels if not Q_RE.match(q)]
    if bad:
        err.append(f"quarters 季度標籤格式應為 nQyy（例 3Q26）：{bad[:3]}")
    if labels and labels != sorted(labels, key=qkey):
        err.append("quarters 沒有依時間排序")


# ---------- 3. 資料層：v1 通用 ----------
def v1_generic(D, err):
    Q = D.get("quarters", [])
    if not Q:
        err.append("quarters 是空的"); return
    for k in ("company", "quarters", "annual", "events", "milestones"):
        if k not in D:
            err.append(f"v1 缺頂層欄位 {k}")
    C = D.get("company", {})
    for k in ("code", "name", "ticker", "exchange", "currency", "unit"):
        if not C.get(k):
            err.append(f"company 缺 {k}")
    for q in Q:
        for k in ("q", "rev", "gm", "om", "eps"):
            if q.get(k) is None:
                err.append(f"{q.get('q')} 缺必要欄位 {k}（共用欄位不能是 null：rev、gm、om、eps）")
        if q.get("rev") in (None, 0):
            continue
        if q.get("gp") is not None and abs(q["gp"] / q["rev"] * 100 - q["gm"]) > 0.15:
            err.append(f"{q['q']} 毛利率 {q['gm']} 與毛利／營收 {q['gp'] / q['rev'] * 100:.1f} 不符")
        if q.get("opInc") is not None and abs(q["opInc"] / q["rev"] * 100 - q["om"]) > 0.15:
            err.append(f"{q['q']} 營業利益率 {q['om']} 與營業利益／營收 {q['opInc'] / q['rev'] * 100:.1f} 不符")
        if q.get("fcf") is not None and q.get("ocf") is not None and q.get("capex") is not None and abs(q["ocf"] - q["capex"] - q["fcf"]) > 0.6:
            err.append(f"{q['q']} fcf {q['fcf']} ≠ ocf − capex {q['ocf'] - q['capex']:.1f}")
        if q.get("capex") is not None and q["capex"] < 0:
            err.append(f"{q['q']} capex 應為正數（現金流出以正數記）")
    # 四季加總 ＝ 全年
    for y, a in (D.get("annual") or {}).items():
        qs = [q for q in Q if q["q"].endswith("Q" + str(y)[2:])]
        if len(qs) != 4:
            continue
        for key in ("rev", "gp", "opInc", "ni", "ocf", "capex"):
            if a.get(key) is None or any(q.get(key) is None for q in qs):
                continue
            s = sum(q[key] for q in qs)
            tol = max(0.6, abs(a[key]) * 0.001)
            if abs(s - a[key]) > tol:
                err.append(f"{y} 年 {key} 四季加總 {s:.1f} ≠ 全年 {a[key]}")
    # 營收拆分
    seg = D.get("segments")
    if seg:
        keys = [k["k"] for k in seg.get("keys", [])]
        byq = {q["q"]: q for q in Q}
        for s in seg.get("quarters", []):
            q = byq.get(s["q"])
            if not q:
                err.append(f"segments 有 quarters 沒有的季度：{s['q']}"); continue
            vals = [s.get(k) for k in keys]
            if all(v is not None for v in vals) and abs(sum(vals) - q["rev"]) > max(0.15, q["rev"] * 0.002):
                err.append(f"{s['q']} 營收拆分加總 {sum(vals):.1f} ≠ 營收 {q['rev']}")
    # 專屬指標季度存在
    ex = D.get("extra")
    if ex:
        byq = {q["q"] for q in Q}
        for s in ex.get("quarters", []):
            if s["q"] not in byq:
                err.append(f"extra 有 quarters 沒有的季度：{s['q']}")
    # waterfall：小計必須等於前一個小計加中間各項
    W = D.get("waterfall")
    if W:
        run = None
        rows = W.get("rows", [])
        if any(r.get("v") is None for r in rows):
            err.append("waterfall 有 null 的數字"); rows = []
        for r in rows:
            if r.get("t"):
                if run is not None and abs(run - r["v"]) > max(0.6, abs(r["v"]) * 0.002):
                    err.append(f"waterfall 「{r['n']}」{r['v']} ≠ 前面累加 {run:.1f}")
                run = r["v"]
            else:
                run = (run or 0) + r["v"]
        if rows and Q and rows[0].get("t") and W.get("q") == Q[-1]["q"]:
            unit_ratio = W["rows"][0]["v"] / Q[-1]["rev"] if Q[-1]["rev"] else 1
            if abs(unit_ratio - 1) > 0.002 and abs(unit_ratio - 0.01) > 0.0001:
                err.append(f"waterfall 營收 {W['rows'][0]['v']} 與 {Q[-1]['q']} rev {Q[-1]['rev']} 不一致（單位要相同或剛好差 100 倍）")
    # 財測
    g = D.get("guidance")
    if g and g.get("items"):
        for it in g["items"]:
            if it.get("lo") is not None and it.get("hi") is not None and it["lo"] > it["hi"]:
                err.append(f"guidance 「{it.get('label')}」區間上下限顛倒")
    if g and g.get("nextQ") and g["nextQ"].get("revLo") is not None and g["nextQ"]["revLo"] > g["nextQ"]["revHi"]:
        err.append("guidance.nextQ 區間上下限顛倒")


# ---------- 3b. 公司專屬 ----------
def tsmc(D, err):
    """每一季 rev 與該季三個月 monthly 加總相差不超過 200（百萬元）。"""
    for q in D["quarters"]:
        qi, yy = int(q["q"][0]), 2000 + int(q["q"][2:])
        ms = D["monthly"].get(str(yy), [])[(qi - 1) * 3:qi * 3]
        if len(ms) == 3 and abs(sum(ms) - q["rev"]) > 200:
            err.append(f"{q['q']} 季營收 {q['rev']} 與月營收加總 {sum(ms)} 差 {abs(sum(ms) - q['rev'])} 超過 200")


def pltr(D, err):
    """政府＋商業＝總營收；非 GAAP 四季加總對照公司全年公布值。"""
    Q, P = D["quarters"], D["pltr"]["quarters"]
    if [q["q"] for q in Q] != [p["q"] for p in P]:
        err.append("quarters 與 pltr.quarters 的季度不一致")
        return
    for q, p in zip(Q, P):
        if abs(p["gov"] + p["com"] - q["rev"]) > 0.15:
            err.append(f"{q['q']} 政府＋商業 {p['gov'] + p['com']:.1f} ≠ 營收 {q['rev']}")
    for y, a in D["annual"].items():
        qs = [i for i, q in enumerate(Q) if q["q"].endswith("Q" + y[2:])]
        if len(qs) != 4 or a.get("gp") is None:
            continue
        for key in ("adjOpInc", "adjFcf", "sbc"):
            s = sum((P[i][key] or 0) for i in qs)
            if a.get(key) is not None and abs(s - a[key]) > 0.6:
                err.append(f"{y} 年 {key} 四季加總 {s:.1f} ≠ 全年 {a[key]}")
    g = D["guidance"]
    if not (g["nextQ"]["revLo"] <= g["nextQ"]["revHi"] and g["year"]["revLo"] <= g["year"]["revHi"]):
        err.append("guidance 區間上下限顛倒")


CHECKS = {"tsmc": tsmc, "pltr": pltr}
SCHEMA_CHECKS = {"v1": v1_generic}


def main():
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    bycode = {c["code"]: c for c in cfg["companies"]}
    codes = sys.argv[1:] or [c["code"] for c in cfg["companies"] if c.get("enabled")]
    failed = False
    if not sys.argv[1:]:
        err = []
        check_config(cfg, err)
        print("[companies.json] " + ("通過" if not err else f"{len(err)} 項未通過"))
        for e in err:
            print("   -", e)
        failed |= bool(err)
    for code in codes:
        err = []
        try:
            D = load(code)
            common(code, D, err)
            schema = bycode.get(code, {}).get("schema", "v1")
            if schema in SCHEMA_CHECKS:
                SCHEMA_CHECKS[schema](D, err)
            if code in CHECKS:
                CHECKS[code](D, err)
            elif schema not in SCHEMA_CHECKS:
                print(f"[{code}] 注意：schema {schema} 沒有通用核對，也沒有專屬核對函式（tools/validate.py 的 CHECKS），只做共通檢查")
        except Exception as e:  # noqa
            err.append(f"讀取失敗：{e!r}")
        print(f"[{code}] " + ("通過" if not err else f"{len(err)} 項未通過"))
        for e in err:
            print("   -", e)
        failed |= bool(err)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
