"""核對各公司資料與設定；任何一項沒過就以非 0 結束（排程看到失敗就不要發佈）。

用法：python3 tools/validate.py [代號 ...]    不給代號＝所有啟用中的公司（並一併檢查 companies.json）

檢查分三層，新增公司通常「一行程式都不用加」：
  1. 設定層 companies.json：欄位齊全、代號唯一、path＝代號/、資料檔／模板／SOURCES.md 都存在
  2. 共通層（所有 schema）：asOf、events、milestones、fabs 的日期與欄位格式
  3. 資料層：
     - schema v1 → 通用核對 v1_generic（季度順序、毛利率／營益率自洽、FCF、四季＝全年、segments 加總、waterfall 加總、財測區間）
     - 另外若 CHECKS 有該公司的專屬函式（例：tsmc、pltr）就再多做一層
"""
import datetime as dt, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe as PE
import rd_import as RDI

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATE_RE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?|-Q[1-4]|-H[12])?$")
DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
Q_RE = re.compile(r"^[1-4]Q\d{2}$")
REQUIRED_CFG = ("code", "name", "nameEn", "ticker", "exchange", "sector", "currency", "frequency", "path", "schema", "template", "title", "description", "enabled")


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
        sec = c.get("sector")
        if not isinstance(sec, str) or not sec.strip() or len(sec.strip()) > 12:
            err.append(f"companies.json [{tag}] sector 要填產業名稱（首頁分頁籤用，12 字以內，例如「半導體」）")
        if not c.get("enabled"):
            continue
        for rel in (("data", tag + ".json"), ("templates", c.get("template", "") + ".frag.html"), ("companies", tag, "SOURCES.md")):
            if not os.path.exists(os.path.join(ROOT, *rel)):
                err.append(f"[{tag}] 找不到 {'/'.join(rel)}")
        if "price" not in c:
            err.append(f"companies.json [{tag}] 缺 price（有股價填 {{yahoo, from, currency}}；未上市填 null）")
        elif c["price"] is not None:
            pc = c["price"]
            for k in ("yahoo", "from", "currency"):
                if not pc.get(k):
                    err.append(f"companies.json [{tag}] price 缺 {k}")
            pf = os.path.join(ROOT, "data", "prices", tag + ".json")
            if not os.path.exists(pf):
                err.append(f"[{tag}] 找不到 data/prices/{tag}.json（先手動觸發 prices-monthly 工作流程）")
            else:
                try:
                    if json.load(open(pf, encoding="utf8")).get("symbol") != pc.get("yahoo"):
                        err.append(f"[{tag}] data/prices/{tag}.json 的 symbol 與 companies.json price.yahoo 不一致")
                except Exception as e:  # noqa: BLE001
                    err.append(f"[{tag}] data/prices/{tag}.json 讀取失敗：{e!r}")
        if not c.get("primarySource", {}).get("url"):
            err.append(f"companies.json [{tag}] 缺 primarySource {{n, url}}（首頁「資料新鮮度與來源」要用）")


# ---------- 2. 共通層 ----------
def check_summary(code, D, err):
    """summary（一頁摘要）、summaryHistory、guidanceHistory：來源標籤、口頭內容要有逐字稿連結、市場預期要對得上快照檔。"""
    qs = {q["q"] for q in D.get("quarters", [])}
    iso = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    gh = D.get("guidanceHistory")
    if gh is not None:
        prev = ""
        for g in gh:
            if not iso.match(str(g.get("issued", ""))):
                err.append("guidanceHistory 缺 issued（YYYY-MM-DD）")
                continue
            if g["issued"] < prev:
                err.append(f"guidanceHistory 沒有依發布日由舊到新排序：{g['issued']}")
            prev = g["issued"]
            if D.get("guidance", {}).get("issued") and g["issued"] >= D["guidance"]["issued"]:
                err.append(f"guidanceHistory {g['issued']} 不早於目前財測的發布日（目前財測放 guidance，歷史只放被取代的舊財測）")
            for it in g.get("items", []):
                lo, hi = it.get("lo"), it.get("hi")
                if not it.get("label") or not it.get("period"):
                    err.append(f"guidanceHistory {g['issued']} 有項目缺 label／period")
                if lo is not None and hi is not None and lo > hi:
                    err.append(f"guidanceHistory {g['issued']} 「{it.get('label')}」區間上下限顛倒")
    S = D.get("summary")
    if not S:
        return

    def tagcheck(where, it):
        t = it.get("tag")
        if t not in ("w", "o", "e", "v"):
            err.append(f"summary {where} 缺來源標籤 tag（w 書面／o 口頭／e 分析師預估／v 觀點）：{str(it.get('t') or it.get('q'))[:20]}")
        if t == "o":
            src = it.get("src") or {}
            if not str(src.get("url", "")).startswith("http") or not src.get("speaker") or not src.get("n"):
                err.append(f"summary {where} 口頭內容要附逐字稿來源 src:{{n,url,speaker}}：{str(it.get('t') or it.get('q'))[:20]}")
        if t == "w" and it.get("src") is not None and not str(it["src"].get("url", "")).startswith("http"):
            err.append(f"summary {where} 書面來源連結不是網址")
    if S.get("q") not in qs:
        err.append(f"summary.q {S.get('q')} 不在 quarters 裡（摘要只能針對已有資料的季度）")
    if S.get("status") not in ("flash", "final"):
        err.append("summary.status 要是 flash（初版）或 final（定稿）")
    if not iso.match(str(S.get("flashDate", ""))):
        err.append("summary.flashDate 缺（YYYY-MM-DD）")
    if S.get("status") == "final" and not iso.match(str(S.get("finalDate", ""))):
        err.append("summary 定稿但缺 finalDate")
    if S.get("headline"):
        tagcheck("headline", S["headline"])
    for sec in ("mgmt", "qa", "risks"):
        for it in S.get(sec, []) or []:
            tagcheck(sec, it)
            if sec in ("mgmt", "qa") and it.get("tag") != "o":
                err.append(f"summary.{sec} 的內容來自電話會議，tag 要是 o（口頭）")
            if sec == "risks" and it.get("tag") != "v":
                err.append("summary.risks 是判斷，tag 要是 v（觀點）")
    if S.get("outlook"):
        if S["outlook"].get("dir") not in ("up", "flat", "down", "na"):
            err.append("summary.outlook.dir 要是 up／flat／down／na")
        for it in S["outlook"].get("items", []) or []:
            tagcheck("outlook", it)
    cons_file = os.path.join(ROOT, "data", "consensus", code + ".json")
    snaps = json.load(open(cons_file, encoding="utf8"))["snapshots"] if os.path.exists(cons_file) else []
    for r in S.get("scorecard", []) or []:
        if r.get("k") not in ("rev", "gm", "om", "eps") and not r.get("label"):
            err.append(f"summary.scorecard 的 k 要是 rev／gm／om／eps：{r.get('k')}")
        c = r.get("cons")
        if c:
            if c.get("v") is None or not iso.match(str(c.get("snap", ""))):
                err.append("summary.scorecard.cons 要有 v（數字）與 snap（快照日）")
                continue
            match = [x for x in snaps if x["period"] == S.get("q") and x["date"] == c["snap"]]
            if not match:
                err.append(f"summary.scorecard.cons 的快照 {c['snap']} 不在 data/consensus/{code}.json（市場預期只能用事前快照，不可事後補）")
            else:
                m = match[0]
                if S.get("flashDate") and c["snap"] > S["flashDate"]:
                    err.append("市場預期快照日晚於快報日（疑似事後補）")
                if r.get("k") == "rev" and m.get("revAvg"):
                    if abs(m["revAvg"] / 1e6 - c["v"]) > max(0.5, abs(c["v"]) * 0.001):
                        err.append(f"summary 營收市場預期 {c['v']} 與快照 {m['revAvg'] / 1e6:.1f} 不符")
                if r.get("k") == "eps" and m.get("epsAvg") is not None and abs(m["epsAvg"] - c["v"]) > 0.006:
                    err.append(f"summary EPS 市場預期 {c['v']} 與快照 {m['epsAvg']} 不符")
    for h in D.get("summaryHistory", []) or []:
        if not h.get("q") or h.get("q") == S.get("q"):
            err.append(f"summaryHistory 的 {h.get('q')} 與目前摘要同一季或缺季度")


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
        elif D.get("asOf") and e["date"] < D["asOf"]:
            err.append(f"events 有早於 asOf 的舊公布日 {e['date']}：已處理的公布日要從 events 移除（asOf 只在該公司資料真的更新或確認時才改）")
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
    # 待確認清單
    un = (D.get("notes") or {}).get("unavailable", [])
    if not isinstance(un, list) or any(not isinstance(t, str) or not t.strip() for t in un):
        err.append("notes.unavailable 必須是非空字串的清單（不確定的數字寫「待確認：…」）")
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
    """每一季 rev 與該季三個月 monthly 加總相差不超過 200（百萬元）。
    quartersEarly（2000–2014）只有「季度基準 b 與該年月營收基準 monthlyBasis 相同」時才比對（單一公司對單一公司、合併對合併）。"""
    for q in D["quarters"]:
        qi, yy = int(q["q"][0]), 2000 + int(q["q"][2:])
        ms = D["monthly"].get(str(yy), [])[(qi - 1) * 3:qi * 3]
        if len(ms) == 3 and abs(sum(ms) - q["rev"]) > 200:
            err.append(f"{q['q']} 季營收 {q['rev']} 與月營收加總 {sum(ms)} 差 {abs(sum(ms) - q['rev'])} 超過 200")
    early = D.get("quartersEarly", [])
    basis = D.get("monthlyBasis", {})
    seen = []
    for q in early:
        if not Q_RE.match(q["q"]) or q["b"] not in ("u", "c"):
            err.append(f"quartersEarly 格式錯誤：{q.get('q')}")
            continue
        seen.append(q["q"])
        qi, yy = int(q["q"][0]), 2000 + int(q["q"][2:])
        if yy >= 2015:
            err.append(f"quartersEarly 只放 2014 以前：{q['q']}")
        ms = D["monthly"].get(str(yy), [])[(qi - 1) * 3:qi * 3]
        if len(ms) == 3 and basis.get(str(yy)) == q["b"] and abs(sum(ms) - q["rev"]) > 200:
            err.append(f"{q['q']} 季營收 {q['rev']} 與月營收加總 {sum(ms)} 差 {abs(sum(ms) - q['rev'])} 超過 200")
        if not 0 < (q["gm"] or 1) < 100 or (q["om"] is not None and not -50 < q["om"] < 100):
            err.append(f"{q['q']} 毛利率／營益率超出合理範圍")
        if q["gm"] is not None and q["om"] is not None and q["om"] > q["gm"]:
            err.append(f"{q['q']} 營益率 {q['om']} 高於毛利率 {q['gm']}")
        if q["eps"] is not None and q["ni"] and not 5 < q["ni"] / 1000 / q["eps"] < 40:
            err.append(f"{q['q']} 淨利 ÷ EPS 推得股數 {q['ni'] / 1000 / q['eps']:.1f} 十億股，不在 5–40 之間")
    ordered = sorted(seen, key=qkey)
    if seen != ordered or len(set(seen)) != len(seen):
        err.append("quartersEarly 季度未依時間排序或有重複")
    if early and D["quarters"] and qkey(seen[-1]) >= qkey(D["quarters"][0]["q"]):
        err.append("quartersEarly 與 quarters 的季度重疊")
    for y in (1999, 2000, 2001, 2007):
        if y in D.get("yoyOverrideYears", []) and (f"yoy{y}" not in D or f"yoy{y}Total" not in D or len(D[f"yoy{y}"]) != 12):
            err.append(f"yoy{y} 官方年增率欄位不完整")


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


# ---------- 本益比：公布日 rd、股價、預估 ----------
def month_of(d):
    return d[:7]


def check_valuation(code, D, cfg_c, err, warn):
    pc = (cfg_c or {}).get("price")
    Q = D.get("quarters", [])
    if pc is None and "price" in (cfg_c or {}):
        return
    fye = (D.get("company") or {}).get("fiscalYearEnd") or "12-31"
    un = (D.get("notes") or {}).get("unavailable", []) if isinstance(D.get("notes"), dict) else []
    last = None
    for q in Q:
        if "rd" not in q:
            err.append(f"{q['q']} 缺 rd（財報公布日 YYYY-MM-DD；讀不到填 null 並在 notes.unavailable 寫待確認）")
            continue
        rd = q["rd"]
        if rd is None:
            if not any(q["q"] in t and "公布日" in t and t.startswith("待確認") for t in un):
                err.append(f"{q['q']} rd 是 null，但 notes.unavailable 沒有對應的「待確認：{q['q']} 的財報公布日…」")
            continue
        if not DAY_RE.match(rd):
            err.append(f"{q['q']} rd 格式錯誤：{rd}"); continue
        if q.get("rdB") not in ("f", "p", "c", "t"):
            err.append(f"{q['q']} 有 rd 但 rdB 不是 f／p／c／t（申報日／新聞稿日／法說會日／證交所生效日）")
        if last and rd < last:
            err.append(f"{q['q']} rd {rd} 早於前一季的 {last}（公布日要依季度遞增）")
        last = rd
        ne = RDI.nominal_end(q["q"], fye)
        days = (dt.date.fromisoformat(rd) - ne).days
        if not 5 <= days <= 120:
            err.append(f"{q['q']} rd {rd} 與推得季度結束日 {ne} 相差 {days} 天，不在 5～120 天內")
    if Q and Q[-1].get("rd") is None and "rd" in Q[-1]:
        err.append(f"最新一季 {Q[-1]['q']} 的 rd 不可為 null")
    if pc is None:
        return
    try:
        P = json.load(open(os.path.join(ROOT, "data", "prices", code + ".json"), encoding="utf8"))
    except Exception as e:  # noqa: BLE001
        err.append(f"股價檔讀取失敗：{e!r}"); return
    M = P.get("monthly", [])
    ms = [r["m"] for r in M]
    if len(ms) != len(set(ms)):
        err.append("股價檔月份重複")
    if ms != sorted(ms):
        err.append("股價檔月份沒有依時間排序")
    for a, b in zip(ms, ms[1:]):
        y, m = map(int, a.split("-")); nxt = f"{y + (m == 12):04d}-{m % 12 + 1:02d}"
        if nxt != b:
            err.append(f"股價檔月份不連續：{a} 後面是 {b}")
    for i, r in enumerate(M):
        if not r["d"].startswith(r["m"]):
            err.append(f"{r['m']} 的日期 {r['d']} 不在該月")
        # 例外：台股農曆春節長假（1～2 月）最後交易日可能早於 23 日（2025 年是 1 月 22 日），且該日已有證交所收盤價核對
        cny = r.get("x") == "twse" and r["m"][5:] in ("01", "02") and int(r["d"][8:]) >= 20
        if i > 0 and int(r["d"][8:]) < 23 and not cny:
            err.append(f"{r['m']} 的日期 {r['d']} 不是月底（應為 23 日以後的最後交易日）")
        if r.get("c") is None:
            if not str(r.get("why", "")).startswith("待確認："):
                err.append(f"{r['m']} 股價是 null 但沒有以「待確認：」開頭的 why")
        elif not r["c"] > 0:
            err.append(f"{r['m']} 股價必須大於 0")
    F = P.get("forward", [])
    fm = [f["m"] for f in F]
    if len(fm) != len(set(fm)):
        err.append("forward 月份重複")
    for f in F:
        if f["m"] not in ms:
            err.append(f"forward {f['m']} 在股價檔沒有對應月份")
            continue
        if f.get("why"):
            if not str(f["why"]).startswith("待確認："):
                err.append(f"forward {f['m']} why 要以「待確認：」開頭")
            continue
        for k in ("asOf", "fy1End", "fy2End", "eps1", "eps2", "n1", "n2"):
            if k not in f:
                err.append(f"forward {f['m']} 缺 {k}")
        if all(k in f for k in ("asOf", "fy1End", "fy2End")):
            mrow = next(r for r in M if r["m"] == f["m"])
            ds = (dt.date.fromisoformat(f["asOf"]) - dt.date.fromisoformat(mrow["d"])).days
            me = PE_month_end(f["m"])
            ds = (dt.date.fromisoformat(f["asOf"]) - me).days
            if not 0 <= ds <= 10:
                err.append(f"forward {f['m']} asOf {f['asOf']} 不在月底後 0～10 天內")
            if f["fy1End"] <= me.isoformat():
                err.append(f"forward {f['m']} fy1End {f['fy1End']} 沒有晚於月底")
            if f["fy2End"] <= f["fy1End"]:
                err.append(f"forward {f['m']} fy2End 沒有晚於 fy1End")
    V = PE.compute(Q, P)
    mo = V["monthly"]
    for a, b in zip(mo, mo[1:]):
        if a["pe"] and b["pe"] and a["eps4"] == b["eps4"]:
            ratio = b["pe"] / a["pe"]
            if ratio > 3 or ratio < 1 / 3:
                err.append(f"{b['m']} 與 {a['m']} 用同樣四季 EPS，但本益比 {a['pe']}→{b['pe']} 變動超過 3 倍：股價與 EPS 的股數基準可能不一致（股票分割？）")
    stale_m = (dt.date.today().replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    if dt.date.today().day > 12 and ms and ms[-1] < stale_m:
        warn.append(f"股價檔最新只到 {ms[-1]}，上個月 {stale_m} 還沒進來（頁面會顯示「股價待更新」）")


def PE_month_end(m):
    y, mo = map(int, m.split("-"))
    return dt.date(y + (mo == 12), mo % 12 + 1, 1) - dt.timedelta(days=1)


def check_calendar(cfg, err):
    """data/calendar.json：每日排程的狀態檔（tools/daily.py 說明）。"""
    p = os.path.join(ROOT, "data", "calendar.json")
    if not os.path.exists(p):
        err.append("缺 data/calendar.json")
        return
    cal = json.load(open(p, encoding="utf8"))
    codes = {c["code"] for c in cfg["companies"]}
    for k in ("lastRun", "lastSuccess"):
        v = cal.get(k)
        if v is not None and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(v)):
            err.append(f"calendar.json {k} 日期格式錯誤：{v}")
    for code, e in cal.get("companies", {}).items():
        if code not in codes:
            err.append(f"calendar.json 有不存在的公司 {code}")
        if e.get("state") not in ("waiting", "flash", "completed", "stuck"):
            err.append(f"calendar.json {code} 狀態不合法：{e.get('state')}")
        if e.get("state") in ("flash", "completed", "stuck") and not e.get("target"):
            err.append(f"calendar.json {code} 進行中但沒有 target（哪一季）")
        if not isinstance(e.get("tries", 0), int) or e.get("tries", 0) < 0:
            err.append(f"calendar.json {code} tries 要是 0 以上整數")
        if e.get("state") == "stuck" and not e.get("note"):
            err.append(f"calendar.json {code} 卡住了但沒寫原因 note")


CHECKS = {"tsmc": tsmc, "pltr": pltr}
SCHEMA_CHECKS = {"v1": v1_generic}


def main():
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    bycode = {c["code"]: c for c in cfg["companies"]}
    codes = sys.argv[1:] or [c["code"] for c in cfg["companies"] if c.get("enabled")]
    failed = False
    t = PE.selftest()
    print("[pe.py 測試案例] " + ("通過（9 項）" if not t else f"{len(t)} 項未通過"))
    for e in t:
        print("   -", e)
    failed |= bool(t)
    if not sys.argv[1:]:
        err = []
        check_config(cfg, err)
        check_calendar(cfg, err)
        print("[companies.json + calendar.json] " + ("通過" if not err else f"{len(err)} 項未通過"))
        for e in err:
            print("   -", e)
        failed |= bool(err)
    for code in codes:
        err = []
        try:
            D = load(code)
            common(code, D, err)
            check_summary(code, D, err)
            schema = bycode.get(code, {}).get("schema", "v1")
            if schema in SCHEMA_CHECKS:
                SCHEMA_CHECKS[schema](D, err)
            if code in CHECKS:
                CHECKS[code](D, err)
            elif schema not in SCHEMA_CHECKS:
                print(f"[{code}] 注意：schema {schema} 沒有通用核對，也沒有專屬核對函式（tools/validate.py 的 CHECKS），只做共通檢查")
            warn = []
            check_valuation(code, D, bycode.get(code), err, warn)
            for w in warn:
                print(f"[{code}] 警告：{w}")
        except Exception as e:  # noqa
            err.append(f"讀取失敗：{e!r}")
        print(f"[{code}] " + ("通過" if not err else f"{len(err)} 項未通過"))
        for e in err:
            print("   -", e)
        failed |= bool(err)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
