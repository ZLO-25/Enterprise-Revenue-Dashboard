"""巴菲特＋蒙格檢查表用的指標：唯一計算處（build.py 建置時呼叫；前端 assets/buffett.js 只畫，不重算）。

只用 repo 既有欄位（quarters[]、data/prices、quant/data 的公債與指數價格），不估計、不內插、不補數字。
算不出來的項目值是 null，並在 why 寫原因代碼（前端 assets/buffett.js 的 WHY 對照中文）：
  missing 欄位待確認　neg 分母不是正數或虧損　short 資料不足　noprice 沒有股價檔　loss 虧損或本益比不可用　noisy 本益比超過參考上限
  norates 讀不到公債資料　nobond 網站沒有該國公債資料　noidx 網站沒有不含股息的同幣別指數資料　nosbc 股票酬勞（sbc）欄位待確認（來源不是 SEC XBRL 或尚未讀取）　nodps 沒有股利資料（欄位全空；有配息但沒收錄時保留盈餘測試也不算）

輸出 buffett = {type, ey, tenYear, summary, buyback, retained, vsIndex, implied, normPe, quality, structure, record, owner}（格式見 docs/DATA_SCHEMA.md「buffett」）。

固定定義：
  年度點    從最新一季往回每四季取一點，最多 11 點；每點的「近四季」＝該季與前三季加總，缺任一季該點為 null（前面不足三季的點略過）。標籤用該點的季別。
  回購期間對月份  一個年度點對應「12 個月」：以該季名目期末日（tools/rd_import.py 的 nominal_end，由 fiscalYearEnd 推得）的所在月份為終點，
            期末日在 15 日（含）以後算當月，14 日（含）以前算前一個月（例：美光 4Q26 期末 2026-09-03 → 終點 2026-08），往前數 12 個月。
  盈餘殖利率 ＝ 100 ÷ 本益比；本益比用 valuation.monthly 的最新一個月（那個月算不出來就不算，不拿更舊的月份）。
  價格隱含的成長 g ＝ ((本益比 × 1.1^10) ÷ 終點本益比)^(1/10) − 1（假設：十年後本益比回到 15 或 20 倍、不計股利與回購、要求年報酬 10%）。
"""
import calendar, json, os, statistics, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import health as H, pe as PE, rd_import as RDI  # noqa: E402

MAXPTS = 11
ROE_BAR = 15.0                   # 巴菲特常看的門檻：長期 ROE 15% 以上
REQ = 10.0                       # 價格隱含成長假設：要求年報酬 10%
EXIT_PES = (15, 20)              # 假設十年後本益比
YEARS = (1, 3, 5, 10)
CURRENCY_BOND = {"TWD": "tw_10y", "USD": "us_10y"}
CURRENCY_INDEX = {"USD": ("_GSPC", "標普 500 價格指數（S&P 500，不含股息）"), "TWD": ("_TWII", "臺灣加權股價指數（不含股息）")}
_RATES = None


def r(x, n=2):
    return None if x is None else round(x, n)


# ---------- 讀檔 ----------
def load_rates(root=None):
    global _RATES
    if root is None and _RATES is not None:
        return _RATES
    p = os.path.join(root or ROOT, "quant", "data", "rates.json")
    try:
        v = json.load(open(p, encoding="utf8"))
    except Exception:  # noqa: BLE001
        v = None
    if root is None:
        _RATES = v
    return v


def load_index_prices(root=None):
    out = {}
    for cur, (sym, name) in CURRENCY_INDEX.items():
        p = os.path.join(root or ROOT, "quant", "data", "prices", sym + ".json")
        try:
            d = json.load(open(p, encoding="utf8"))
            out[cur] = {"symbol": d.get("symbol"), "name": name, "dates": d["dates"], "close": d["close"]}
        except Exception:  # noqa: BLE001
            pass
    return out


# ---------- 月份與年度點 ----------
def shift(m, k):
    y, mo = int(m[:4]), int(m[5:7])
    t = y * 12 + mo - 1 + k
    return f"{t // 12:04d}-{t % 12 + 1:02d}"


def end_month(label, fye):
    """季別 → 12 個月窗口的終點月份（規則見檔頭）。"""
    d = RDI.nominal_end(label, fye or "12-31")
    m = f"{d.year:04d}-{d.month:02d}"
    return shift(m, -1) if d.day < 15 else m


def window_months(label, fye):
    e = end_month(label, fye)
    return [shift(e, -k) for k in range(11, -1, -1)]


def points(Q, maxn=MAXPTS):
    """年度點的季度索引（舊到新）。前面不足三季、沒有近四季的點略過。"""
    idx = [len(Q) - 1 - 4 * k for k in range(maxn)]
    return [i for i in reversed(idx) if i >= 3]


def pub_idx(Q, d):
    """d 當天已公布的最新一季索引（規則同 tools/pe.py、tools/health.py）；下一季公布日待確認時無法判斷 → None。"""
    j = -1
    for i, q in enumerate(Q):
        if q.get("rd") and q["rd"] <= d:
            j = i
    if j < 0 or (j + 1 < len(Q) and not Q[j + 1].get("rd")):
        return None
    return j


def mcap_at(Q, row):
    """valuation.monthly 的一列 → 市值（百萬）＝收盤價 × 當時已公布的期末股數；回傳 (市值, 季度索引, why)。"""
    if row is None or row.get("c") is None:
        return None, None, "noprice"
    j = pub_idx(Q, row["d"])
    if j is None or Q[j].get("shOut") in (None, 0):
        return None, j, "missing"
    return row["c"] * Q[j]["shOut"], j, None


def wavg(Q, i, k):
    """近四季以營收加權的比率（毛利率）。"""
    if i < 3:
        return None
    w = Q[i - 3:i + 1]
    if any(q.get(k) is None or q.get("rev") is None for q in w):
        return None
    tot = sum(q["rev"] for q in w)
    return sum(q[k] * q["rev"] for q in w) / tot if tot else None


def divq(Q, i):
    """當季股利總額（百萬）＝ dps × 期末股數；任一個缺 → None。"""
    q = Q[i]
    return None if q.get("dps") is None or q.get("shOut") is None else q["dps"] * q["shOut"]


# ---------- 1. 盈餘殖利率對公債 ----------
def valid_pe(row):
    """最新月份的本益比是否可用 → (pe, why)。"""
    if row is None:
        return None, "noprice"
    if row.get("pe") is None:
        return None, row.get("why") or "loss"
    if row["pe"] <= 0:
        return None, "loss"
    if PE.pe_noisy(row["pe"]):
        return None, "noisy"
    return row["pe"], None


def bond_of(rates, key):
    s = ((rates or {}).get("series") or {}).get(key)
    if not s or not s.get("points"):
        return None
    return s


def monthly_bond(series, m):
    """該月份當月最後一點的殖利率；該月沒有點 → None。"""
    v = [p for p in series["points"] if p[0][:7] == m]
    return v[-1][1] if v else None


def spread_series(val, rates):
    """每月 [月份, 盈餘殖利率, 公債殖利率, 差]。沒有該幣別公債時 bond 與差是 None。thesis.py 的 eySpread 也用這個。"""
    if not val:
        return []
    key = CURRENCY_BOND.get(val.get("currency"))
    bs = bond_of(rates, key) if key else None
    out = []
    for row in val["monthly"]:
        pe, _ = valid_pe(row)
        ey = None if pe is None else 100 / pe
        b = monthly_bond(bs, row["m"]) if bs else None
        out.append([row["m"], r(ey, 2), b, r(ey - b, 2) if ey is not None and b is not None else None])
    return out


def calc_ey(cur, val, rates):
    out = {"currency": cur, "ey": None, "pe": None, "m": None, "bond": None, "ref": None, "spread": None, "series": [], "why": None, "bondWhy": None}
    row = val["monthly"][-1] if val and val.get("monthly") else None
    out["m"] = row["m"] if row else None
    pe, why = valid_pe(row)
    if pe is not None:
        out["pe"], out["ey"] = pe, r(100 / pe, 3)
    else:
        out["why"] = why
    if not rates:
        out["bondWhy"] = "norates"
        return out
    key = CURRENCY_BOND.get(cur)
    pack = lambda s: {"v": s["points"][-1][1], "d": s["points"][-1][0], "name": s.get("name"), "src": s.get("source"), "url": s.get("url")}  # noqa: E731
    if key and bond_of(rates, key):
        out["bond"] = pack(bond_of(rates, key))
        if out["ey"] is not None:
            out["spread"] = r(out["ey"] - out["bond"]["v"], 3)
    else:
        out["bondWhy"] = "nobond" if key is None else "norates"
        if bond_of(rates, "us_10y"):
            out["ref"] = pack(bond_of(rates, "us_10y"))
            out["refNote"] = "網站沒有該國公債資料，以美國十年期當參考"
    out["series"] = spread_series(val, rates)
    return out


# ---------- 2. 十年成績單 ----------
def ten_year(Q, health, pts):
    hq = (health or {}).get("quarterly") or []
    rows = []
    prev = None
    for i in pts:
        q = Q[i]
        W = {}
        eps = H.s4(Q, i, "eps")
        ni, rev = H.s4(Q, i, "ni"), H.s4(Q, i, "rev")
        ocf, cap = H.s4(Q, i, "ocf"), H.s4(Q, i, "capex")
        fcf = None if ocf is None or cap is None else ocf - cap
        if eps is None:
            W["eps"] = "missing"
        yoy = None
        if prev is not None and prev["eps"] is not None and eps is not None:
            if prev["eps"] > 0:
                yoy = r((eps / prev["eps"] - 1) * 100, 1)
            else:
                W["epsYoy"] = "neg"
        elif eps is not None:
            W["epsYoy"] = "short" if prev is None else "missing"
        roe = hq[i]["roe"] if i < len(hq) else None
        if roe is None:
            W["roe"] = (hq[i]["why"].get("roe") if i < len(hq) else None) or "missing"
        roic = hq[i].get("roic") if i < len(hq) else None
        if roic is None:
            W["roic"] = (hq[i]["why"].get("roic") if i < len(hq) else None) or "missing"
        gm = wavg(Q, i, "gm")
        if gm is None:
            W["gm"] = "missing"
        npm = None
        if ni is None or rev is None:
            W["npm"] = "missing"
        elif rev <= 0:
            W["npm"] = "neg"
        else:
            npm = ni / rev * 100
        fcf_ni = capex_ni = nd_ni = None
        if ni is None:
            W["fcfNi"] = W["capexNi"] = W["netDebtNi"] = "missing"
        elif ni <= 0:
            W["fcfNi"] = W["capexNi"] = W["netDebtNi"] = "neg"
        else:
            if fcf is None:
                W["fcfNi"] = "missing"
            else:
                fcf_ni = fcf / ni * 100
            if cap is None:
                W["capexNi"] = "missing"
            else:
                capex_ni = cap / ni * 100
            if q.get("debt") is None or q.get("cash") is None:
                W["netDebtNi"] = "missing"
            else:
                nd_ni = (q["debt"] - q["cash"]) / ni
        bv = None
        if q.get("equity") is None or not q.get("shOut"):
            W["bvps"] = "missing"
        else:
            bv = q["equity"] / q["shOut"]
        row = {"q": q["q"], "eps": r(eps, 3), "epsYoy": yoy, "roe": roe, "roic": roic, "gm": r(gm, 1), "npm": r(npm, 1), "fcfNi": r(fcf_ni, 0), "capexNi": r(capex_ni, 0),
               "netDebtNi": r(nd_ni, 1), "bvps": r(bv, 2), "why": W}
        rows.append(row)
        prev = {"eps": eps}
    return rows


def count_roe(hq, n):
    v = [x.get("roe") for x in hq[-n:]]
    v = [x for x in v if x is not None]
    return {"ok": sum(1 for x in v if x >= ROE_BAR), "n": len(v), "of": min(n, len(hq))}


def summarize(rows, hq):
    eps = [x["eps"] for x in rows]
    cmp_ = [(a, b) for a, b in zip(eps, eps[1:]) if a is not None and b is not None]
    have = [e for e in eps if e is not None]
    roes = [x["roe"] for x in rows][-4:]
    roics = [x.get("roic") for x in rows][-4:]
    gms = [x["gm"] for x in rows]
    bv = [x["bvps"] for x in rows]
    s = {"roeOk": count_roe(hq, 20), "roeOk40": count_roe(hq, 40),
         "epsUp": {"up": sum(1 for a, b in cmp_ if b > a), "n": len(cmp_)},
         "lossYears": sum(1 for e in have if e <= 0), "years": len(have), "bvCagr5": None, "roeTrend3": None, "roicTrend3": None, "gmChg3": None, "why": {}}
    if len(bv) >= 6 and bv[-1] is not None and bv[-6] is not None and bv[-1] > 0 and bv[-6] > 0:
        s["bvCagr5"] = r(((bv[-1] / bv[-6]) ** (1 / 5) - 1) * 100, 1)
    else:
        s["why"]["bvCagr5"] = "short" if len(bv) < 6 else ("neg" if None not in (bv[-1], bv[-6]) else "missing")
    if len(roes) == 4 and None not in roes:
        s["roeTrend3"] = roes[1] < roes[0] and roes[2] < roes[1] and roes[3] < roes[2]
    else:
        s["why"]["roeTrend3"] = "short" if len(roes) < 4 else "missing"
    if len(roics) == 4 and None not in roics:
        s["roicTrend3"] = roics[1] < roics[0] and roics[2] < roics[1] and roics[3] < roics[2]
    else:
        s["why"]["roicTrend3"] = "short" if len(roics) < 4 else "missing"
    if len(gms) >= 4 and gms[-1] is not None and gms[-4] is not None:
        s["gmChg3"] = r(gms[-1] - gms[-4], 1)
    else:
        s["why"]["gmChg3"] = "short" if len(gms) < 4 else "missing"
    return s


# ---------- 3. 資本配置成績單 ----------
def calc_buyback(Q, val, pts, fye, mcap):
    med = ((val or {}).get("stats") or {}).get("med5")
    pe_by_m = {x["m"]: x["pe"] for x in (val or {}).get("monthly", []) if x.get("pe") is not None and x["pe"] > 0 and not PE.pe_noisy(x["pe"])}
    rows = []
    for i in pts:
        bb = H.s4(Q, i, "buyback")
        months = window_months(Q[i]["q"], fye)
        v = [pe_by_m[m] for m in months if m in pe_by_m]
        avg = sum(v) / len(v) if len(v) >= 6 else None
        where = None
        if bb and avg is not None and med:
            where = "偏貴時買" if avg > med * 1.1 else ("偏便宜時買" if avg < med * 0.9 else "接近平常")
        rows.append({"q": Q[i]["q"], "buyback": r(bb, 1), "avgPe": r(avg, 1), "nMonths": len(v), "med5": med, "where": where, "from": months[0], "to": months[-1]})
    out = {"rows": rows, "shChg5": None, "buybackYield": None, "why": {}}
    if len(pts) >= 6 and Q[pts[-1]].get("shOut") and Q[pts[-6]].get("shOut"):
        out["shChg5"] = r((Q[pts[-1]]["shOut"] / Q[pts[-6]]["shOut"] - 1) * 100, 1)
    else:
        out["why"]["shChg5"] = "short" if len(pts) < 6 else "missing"
    bb = H.s4(Q, pts[-1], "buyback") if pts else None
    if bb is None or mcap[0] is None:
        out["why"]["buybackYield"] = mcap[2] or "missing"
    elif mcap[0] > 0:
        out["buybackYield"] = r(bb / mcap[0] * 100, 2)
    return out


# ---------- 4. 保留盈餘測試 ----------
def div_unrecorded(D):
    """每股股利全部是 null，但 notes.unavailable 有寫「每股股利」：公司有配息、只是本站沒收錄（例：台達電、萬潤、三星）。
    這種情況不能把股利當 0（會高估留下的盈餘），保留盈餘測試算不出來。"""
    n = (D or {}).get("notes")
    u = n.get("unavailable") if isinstance(n, dict) else []
    return any(isinstance(x, str) and ("股利" in x or "dps" in x) for x in (u or []))


def div_lines(D):
    n = (D or {}).get("notes")
    u = n.get("unavailable") if isinstance(n, dict) else []
    return [x for x in (u or []) if isinstance(x, str) and ("股利" in x or "dps" in x)]


def div_flagged_unrecorded(D):
    """notes 明寫「這家公司的股利本站未收錄」（不是「不是缺資料」「沒有發放」那種說明）。"""
    return any(any(w in x for w in ("未收錄", "不收錄", "暫不收錄", "全部留空")) and "不是缺資料" not in x for x in div_lines(D))


def calc_retained(Q, val, mcap, D=None):
    out = {"kept": None, "ni20": None, "div20": None, "noDiv": False, "preDivQ": 0, "mcapNow": r(mcap[0], 0), "mcap0": None, "mcapChg": None, "ratio": None, "m0": None, "mNow": None, "why": None, "note": None}
    n = len(Q)
    if n < 20:
        out["why"] = "short"; return out
    idx = range(n - 20, n)
    ni = [Q[i].get("ni") for i in idx]
    if any(x is None for x in ni):
        out["why"] = "missing"; return out
    out["ni20"] = sum(ni)
    has_dps = any(q.get("dps") is not None for q in Q)
    if not has_dps and div_unrecorded(D):
        out["why"] = "nodps"; out["note"] = "這家公司有配息，但本站沒有收錄每股股利（見資料說明），不把股利當 0"; out["ni20"] = r(out["ni20"], 0); return out
    if not has_dps:
        out["noDiv"], out["div20"] = True, 0.0
    else:
        dv = [divq(Q, i) for i in idx]
        dps = [Q[i].get("dps") for i in idx]
        first = next((k for k, x in enumerate(dps) if x is not None), None)
        gaps = [] if first is None else [Q[n - 20 + k]["q"] for k in range(first, 20) if dps[k] is None]
        nosh = [Q[n - 20 + k]["q"] for k in range(20) if dps[k] is not None and Q[n - 20 + k].get("shOut") is None]
        if first is None or gaps or nosh:
            out["why"] = "missing"; out["ni20"] = r(out["ni20"], 0)
            out["note"] = ("近 20 季的每股股利都沒有值，不補" if first is None else
                           ("已經開始配息，但 " + "、".join(gaps) + " 的每股股利是空的（待確認），不補；只有開始配息以前的空白才當 0" if gaps else
                            f"有 {len(nosh)} 季的期末流通股數待確認（{'、'.join(nosh) if len(nosh) <= 4 else nosh[0] + '～' + nosh[-1]}），股利總額算不出來，不補"))
            return out
        if first > 0:
            # 第一個有值的股利之前連續空白：資料格式定義「不配息 → null」，視為當時還沒開始配息、當 0。
            # 例外：資料說明明寫股利未收錄，或那幾季被列在「待確認」裡（那是缺資料，不是沒配息）→ 算不出來。
            lead = [Q[i]["q"] for i in list(idx)[:first]]
            lines = div_lines(D)
            if div_flagged_unrecorded(D) or any(q in x and "待確認" in x for q in lead for x in lines):
                out["why"] = "missing"; out["note"] = "股利開始前的空白季度被資料說明列為缺資料或未收錄，不當 0"; out["ni20"] = r(out["ni20"], 0); return out
            out["preDivQ"] = first
        out["div20"] = sum(x for x in dv if x is not None)
    out["kept"] = out["ni20"] - out["div20"]
    mon = (val or {}).get("monthly") or []
    if not mon or mcap[0] is None:
        out["why"] = mcap[2] or "noprice"; return out
    now = mon[-1]
    m0 = shift(now["m"], -60)
    row0 = next((x for x in mon if x["m"] == m0), None)
    c0 = mcap_at(Q, row0)
    out["mNow"], out["m0"] = now["m"], m0
    if c0[0] is None:
        out["why"] = "missing" if c0[2] == "missing" else "short"; return out
    out["mcap0"] = r(c0[0], 0)
    out["mcapChg"] = r(mcap[0] - c0[0], 0)
    if out["kept"] <= 0:
        out["why"] = "neg"
    else:
        out["ratio"] = r(out["mcapChg"] / out["kept"], 2)
    out["ni20"], out["div20"], out["kept"] = r(out["ni20"], 0), r(out["div20"], 0), r(out["kept"], 0)
    return out


# ---------- 4b. 股票酬勞與業主盈餘（近似） ----------
SBC_YEARS = 20          # 近五年（20 季）sbcRev 中位數的季數
SBC_SERIES = 40         # 體質總覽畫圖用：最近 40 季的 [季別, sbcRev, fcfSbcRate]
SBC_MIN = 8             # 至少要有這麼多季算得出來才給中位數


def sbc_series(Q):
    """每一季 [季別, sbcRev, fcfSbcRate]（近四季，%）。sbcRev ＝ 近四季股票酬勞 ÷ 近四季營收；fcfSbcRate ＝（近四季自由現金流 − 近四季股票酬勞）÷ 近四季營收。
    缺任一季或營收 ≤ 0 → None。thesis.py 的 sbcRev、fcfSbcRate 與 owner 區塊都用這個函式（唯一計算處）。"""
    out = []
    for i in range(len(Q)):
        sb, rv, oc, cp = H.s4(Q, i, "sbc"), H.s4(Q, i, "rev"), H.s4(Q, i, "ocf"), H.s4(Q, i, "capex")
        ok = rv is not None and rv > 0
        out.append([Q[i]["q"], r(sb / rv * 100, 2) if ok and sb is not None else None,
                    r((oc - cp - sb) / rv * 100, 2) if ok and None not in (sb, oc, cp) else None])
    return out


def calc_owner(Q, mcap, ey):
    """扣股票酬勞後的自由現金流（業主盈餘的近似；財報沒有拆維持性與成長性資本支出，所以只是近似）。
    市值與 TTM 用同一個「當時已公布的季度」（mcap[1]，同 health 的自由現金流殖利率）。"""
    out = {"q": None, "sbc4": None, "rev4": None, "fcf4": None, "fcfRate": None, "sbcRev": None, "fcfSbc": None, "fcfSbcRate": None, "oeYield": None, "bond": None, "oeSpread": None,
           "sbcRev5med": None, "n5": 0, "series": [], "have": sum(1 for q in Q if q.get("sbc") is not None), "why": {}, "approx": "近似：財報沒有分維持性與成長性資本支出，這裡把全部資本支出都扣掉"}
    if not Q:
        return out
    W = out["why"]
    ser = sbc_series(Q)
    last = len(Q) - 1
    # 最新一季的股票酬勞常要等 10-Q 才有：最新算不出來時，往前最多退兩季取算得出來的那一季，並在 q 標明
    for back in range(0, 3):
        if last - back >= 3 and ser[last - back][1] is not None:
            last -= back
            break
    out["q"] = Q[last]["q"]
    out["series"] = [x for x in ser[-SBC_SERIES:]]
    med = [x[1] for x in ser[-SBC_YEARS:] if x[1] is not None]
    out["n5"] = len(med)
    if len(med) >= SBC_MIN:
        out["sbcRev5med"] = r(statistics.median(med), 2)
    if out["have"] == 0:
        W["sbcRev"] = W["fcfSbc"] = W["fcfSbcRate"] = W["oeYield"] = W["oeSpread"] = "nosbc"
        return out
    sb, rv, oc, cp = (H.s4(Q, last, k) for k in ("sbc", "rev", "ocf", "capex"))
    out["sbcRev"], out["fcfSbcRate"] = ser[last][1], ser[last][2]
    if rv is None or rv <= 0:
        W["sbcRev"] = W["fcfSbcRate"] = "neg" if rv is not None else "missing"
    elif sb is None:
        W["sbcRev"] = W["fcfSbcRate"] = "missing"
    elif oc is None or cp is None:
        W["fcfSbcRate"] = "missing"
    out["sbc4"], out["rev4"] = r(sb, 1), r(rv, 1)
    if None not in (oc, cp):
        out["fcf4"] = r(oc - cp, 1)
    if None not in (sb, oc, cp):
        out["fcfSbc"] = r(oc - cp - sb, 1)
    out["fcfRate"] = None if out["fcf4"] is None or not rv or rv <= 0 else r(out["fcf4"] / rv * 100, 2)
    # 殖利率：用市值對應的已公布季度
    j = mcap[1]
    if mcap[0] is None or j is None:
        W["oeYield"] = mcap[2] or "missing"
    else:
        sb_j, oc_j, cp_j = (H.s4(Q, j, k) for k in ("sbc", "ocf", "capex"))
        if None in (sb_j, oc_j, cp_j):
            W["oeYield"] = "missing"
        elif mcap[0] > 0:
            out["oeYield"] = r((oc_j - cp_j - sb_j) / mcap[0] * 100, 2)
    b = (ey or {}).get("bond")
    if out["oeYield"] is None:
        W["oeSpread"] = W.get("oeYield") or "missing"
    elif b is None:
        W["oeSpread"] = (ey or {}).get("bondWhy") or "nobond"
    else:
        out["bond"] = b
        out["oeSpread"] = r(out["oeYield"] - b["v"], 2)
    return out


# ---------- 5. 對指數 ----------
def idx_close(ix, d):
    """指數在 d（含）以前最後一個收盤；超過 5 天沒有資料 → None。"""
    import bisect
    dates = ix["dates"]
    k = bisect.bisect_right(dates, d) - 1
    if k < 0:
        return None
    import datetime as dt
    if (dt.date.fromisoformat(d) - dt.date.fromisoformat(dates[k])).days > 5:
        return None
    return ix["close"][k]


def calc_vs_index(cur, prices, index_prices):
    out = {"index": None, "rows": [], "why": None, "note": "兩邊都不含股利（股價用分割調整、不含股利調整的收盤價）"}
    ix = (index_prices or {}).get(cur)
    if cur not in CURRENCY_INDEX or not ix:
        out["why"] = "noidx"; return out
    out["index"] = ix.get("name")
    mon = [x for x in ((prices or {}).get("monthly") or []) if x.get("c") is not None]
    if not mon:
        out["why"] = "noprice"; return out
    by = {x["m"]: x for x in mon}
    last = mon[-1]
    for n in YEARS:
        row = {"years": n, "stock": None, "index": None, "diff": None, "from": shift(last["m"], -12 * n), "to": last["m"], "why": None}
        a = by.get(row["from"])
        if a is None:
            row["why"] = "short"
        else:
            i0, i1 = idx_close(ix, a["d"]), idx_close(ix, last["d"])
            if i0 is None or i1 is None:
                row["why"] = "noidx"
            else:
                row["stock"] = r((last["c"] / a["c"] - 1) * 100, 1)
                row["index"] = r((i1 / i0 - 1) * 100, 1)
                row["diff"] = r(row["stock"] - row["index"], 1)
        out["rows"].append(row)
    return out


# ---------- 6. 價格隱含的成長 ----------
def implied_g(pe, exit_pe):
    return ((pe * (1 + REQ / 100) ** 10) / exit_pe) ** 0.1 - 1


def calc_implied(ey, rows):
    out = {"assume": {"exitPe": list(EXIT_PES), "years": 10, "req": REQ, "text": "假設：十年後本益比回到 15 倍（另算 20 倍）、不計股利與回購、要求年報酬 10%"}, "pe": ey["pe"], "g": {}, "epsCagr5": None, "why": None}
    if ey["pe"] is None:
        out["why"] = ey["why"] or "loss"
    else:
        for e in EXIT_PES:
            out["g"][str(e)] = r(implied_g(ey["pe"], e) * 100, 1)
    e = [x["eps"] for x in rows]
    if len(e) >= 6 and e[-1] is not None and e[-6] is not None and e[-1] > 0 and e[-6] > 0:
        out["epsCagr5"] = r(((e[-1] / e[-6]) ** (1 / 5) - 1) * 100, 1)
    return out


# ---------- 7. 十年平均獲利本益比 ----------
def calc_norm_pe(rows, val):
    out = {"normPe": None, "avgEps": None, "n": 0, "close": None, "m": None, "why": None}
    mon = (val or {}).get("monthly") or []
    if not mon or mon[-1].get("c") is None:
        out["why"] = "noprice"; return out
    v = [x["eps"] for x in rows if x["eps"] is not None]
    out["n"], out["close"], out["m"] = len(v), mon[-1]["c"], mon[-1]["m"]
    if len(v) < 5:
        out["why"] = "short"; return out
    avg = sum(v) / len(v)
    out["avgEps"] = r(avg, 3)
    if avg <= 0:
        out["why"] = "neg"; return out
    out["normPe"] = r(mon[-1]["c"] / avg, 1)
    return out


# ---------- 8. 其他常看指標 ----------
def calc_quality(Q, rows, pts, summ):
    L = rows[-1] if rows else None
    out = {"q": L["q"] if L else None, "npm": None, "capexNi": None, "fcfNi": None, "debtYears": None, "netDebtYears": None, "bvCagr5": summ["bvCagr5"], "payout": None, "why": {}}
    if not L:
        return out
    for k in ("npm", "capexNi", "fcfNi"):
        out[k] = L[k]
        if L[k] is None:
            out["why"][k] = L["why"].get(k, "missing")
    out["netDebtYears"] = L["netDebtNi"]
    if L["netDebtNi"] is None:
        out["why"]["netDebtYears"] = L["why"].get("netDebtNi", "missing")
    i = pts[-1]
    ni = H.s4(Q, i, "ni")
    if ni is None or ni <= 0 or Q[i].get("debt") is None:
        out["why"]["debtYears"] = "neg" if ni is not None and ni <= 0 else "missing"
    else:
        out["debtYears"] = r(Q[i]["debt"] / ni, 1)
    if summ["bvCagr5"] is None:
        out["why"]["bvCagr5"] = summ["why"].get("bvCagr5", "missing")
    if not any(q.get("dps") is not None for q in Q):
        out["why"]["payout"] = "nodps"
    else:
        dv = [divq(Q, j) for j in range(i - 3, i + 1)]
        if None in dv or ni is None:
            out["why"]["payout"] = "missing"
        elif ni <= 0:
            out["why"]["payout"] = "neg"
        else:
            out["payout"] = r(sum(dv) / ni * 100, 0)
    return out


# ---------- 9、10 ----------
def structure_basis(thesis):
    """結構檢查「連續三年下滑」看哪一個報酬率：卡片核心指標有 roic 而沒有 roe → roic；其餘（有 roe，或沒有論點卡）→ roe。"""
    ks = {m.get("k") for m in ((thesis or {}).get("metrics") or [])}
    return "roic" if "roic" in ks and "roe" not in ks else "roe"


def calc_structure(rows, summ, thesis=None):
    gm = summ["gmChg3"]
    basis = structure_basis(thesis)
    down = summ["roicTrend3"] if basis == "roic" else summ["roeTrend3"]
    return {"basis": basis, "down3": down, "down3Why": None if down is not None else summ["why"].get(basis + "Trend3", "missing"),
            "roeDown3": summ["roeTrend3"], "roicDown3": summ["roicTrend3"], "gmDown3": None if gm is None else gm < -5, "gmChg3": gm,
            "lossNow": None if not rows or rows[-1]["eps"] is None else rows[-1]["eps"] <= 0}


def calc_record(Q, rows, hq, summ):
    pts10 = rows[-10:]
    eps10 = [x["eps"] for x in pts10 if x["eps"] is not None]
    loss10 = sum(1 for e in eps10 if e <= 0)
    c = count_roe(hq, 40)
    out = {"quarters": len(Q), "lossYears10": loss10, "years10": len(eps10), "roe40": c, "tenYearOk": None, "why": []}
    if c["n"] == 0:
        out["why"].append("ROE 完全沒有值（股東權益或股數欄位待確認）")
        return out
    ok = True
    if len(Q) < 40:
        ok = False; out["why"].append(f"只有 {len(Q)} 季，不到 40 季")
    if loss10 > 0:
        ok = False; out["why"].append(f"近 10 個年度點有 {loss10} 個近四季 EPS ≤ 0")
    if c["n"] < 20:
        ok = False; out["why"].append(f"近 40 季 ROE 有值的只有 {c['n']} 季，不到 20 季")
    elif c["ok"] / c["n"] < 0.8:
        ok = False; out["why"].append(f"近 40 季 ROE 達 {ROE_BAR:.0f}% 的比例 {c['ok']}/{c['n']}，不到 80%")
    out["tenYearOk"] = ok
    return out


def compute(code_cfg, D, Q, valuation, health, prices, rates, index_prices, thesis):
    if not Q:
        return None
    cur = (code_cfg or {}).get("currency") or (valuation or {}).get("currency")
    fye = (D.get("company") or {}).get("fiscalYearEnd") or "12-31"
    hq = (health or {}).get("quarterly") or []
    pts = points(Q)
    mon = (valuation or {}).get("monthly") or []
    mc = mcap_at(Q, mon[-1] if mon else None)
    ey = calc_ey(cur, valuation, rates)
    if not pts:      # 還不到四季：只給能算的（盈餘殖利率、對指數、類型資格）
        empty = {"summary": None, "buyback": None, "retained": None, "quality": None, "structure": None}
        return dict({"type": (thesis or {}).get("type"), "currency": cur, "ey": ey, "tenYear": [], "implied": calc_implied(ey, []), "normPe": calc_norm_pe([], valuation),
                     "vsIndex": calc_vs_index(cur, prices, index_prices), "record": calc_record(Q, [], hq, None), "owner": calc_owner(Q, mc, ey), "short": True}, **empty)
    rows = ten_year(Q, health, pts)
    summ = summarize(rows, hq)
    return {"type": (thesis or {}).get("type"), "currency": cur, "ey": ey, "tenYear": rows, "summary": summ,
            "buyback": calc_buyback(Q, valuation, pts, fye, mc), "retained": calc_retained(Q, valuation, mc, D),
            "vsIndex": calc_vs_index(cur, prices, index_prices), "implied": calc_implied(ey, rows), "normPe": calc_norm_pe(rows, valuation),
            "quality": calc_quality(Q, rows, pts, summ), "structure": calc_structure(rows, summ, thesis), "record": calc_record(Q, rows, hq, summ),
            "owner": calc_owner(Q, mc, ey)}


def for_company(c, D, valuation, health, prices, thesis=None):
    """build.py 與 thesis.py review 用：載入公債與指數檔後呼叫 compute()。"""
    return compute(c, D, H.normq(D, c.get("schema")), valuation, health, prices, load_rates(), load_index_prices(), thesis)


if __name__ == "__main__":
    import thesis as T
    for code in sys.argv[1:] or ["aapl"]:
        D, val, hl, Q = T.context(code)
        c = next(x for x in json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))["companies"] if x["code"] == code)
        pf = os.path.join(ROOT, "data", "prices", code + ".json")
        pr = json.load(open(pf, encoding="utf8")) if os.path.exists(pf) else None
        print(json.dumps(for_company(c, D, val, hl, pr), ensure_ascii=False, indent=1)[:6000])
