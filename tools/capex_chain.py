"""AI 資本支出鏈：把本站已有的財報數字，照「日曆季」加總並計算個別上下游公司資本支出指標（總經儀表板用）。建置時算，不存檔。

  買方（雲端大廠）每季資本支出 ──加總──▶ 四家合計、年增率、占營收比重
        │  （它們的支出，就是下游的營收；另設新興 AI 買方獨立觀測）
        ▼
  賣方（晶片、記憶體、網通、代工與電力）每季營收年增率、資本支出與毛利率

規則：
  · 數字全部來自 data/<代號>.json（各公司財報），這裡只做加總、年增率、滾動 4Q 與財測擷取，不估計、不內插
  · 會計年度不同的公司（例如微軟 6 月結帳）用季末月份對到日曆季；季末不在 3／6／9／12 月的公司不能當主買方（對不齊）
  · 某一季只要有一家主買方缺資本支出，合計就留空，並在 missing 寫「待確認：」，不用其他家去推
  · 滾動近 4Q（ttm）必須嚴格檢查 4 季連續且皆有值，任一季缺值或跳季都回傳 None 並標 ttmWhy
清單在 data/macro/config.json 的 chain。用法：python3 tools/capex_chain.py（印最近 8 季與買賣方資本支出摘要）
"""
from decimal import Decimal, ROUND_HALF_UP
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import buffett as B
import health as H

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_CAPEX_KW_RE = re.compile(r"(資本支出|資本開支|capex)", re.I)
_ANNUAL_PERIOD_RE = re.compile(r"^(\d{4}|FY\d{4})$", re.I)
_MA_PREFIX_RE = re.compile(r"^\s*(?:有意)?(?:收購|併購|合併)")
_MA_BEFORE_RE = re.compile(r"(?:收購|併購|交易|合併)")
_MA_GROUP_ALLOW_RE = re.compile(r"(?:合併後公司全年|集團全年)")
_FAR_YEAR_RE = re.compile(r"到\s*FY?\s*20\d\d", re.I)
_FUTURE_HINT_RE = re.compile(
    r"(預估|預期|預計|展望|目標|指引|財測|計畫|打算|明年|下季|維持|上調|上修|下調|下修|收窄|控制在|少於|高於|低於|超過|FY\s*20\d\d|20\d\d\s*年)"
)
_FUTURE_VERB_RE = re.compile(r"(預估|預期|預計|展望|目標|指引|財測|計畫|打算|明年|下季)")
_PAST_HINT_RE = re.compile(r"(去年|前年|上年度|過去|歷史|已支出|已投入|實際支出)")
_PAST_ONLY_RE = re.compile(r"^(?:第[一二三四]季|\dQ\d{2}|上季|本季|當季).*?(?:實際|為|共|花了|支出)")
_NOTE_ORIG_RE = re.compile(r"(原|前|收窄|上修|下修|上調|下調)")


def qnum(label):
    """'3Q26' → 2026*4 + 2；支援 1980–2079 兩位數年份（yy >= 80 → 1900+yy，否則 2000+yy）。"""
    yy = int(label[2:])
    year = (1900 if yy >= 80 else 2000) + yy
    return year * 4 + (int(label[0]) - 1)


def prev_year(label):
    """'3Q26' → '3Q25'（跨世紀 00 → 99 對齊）。"""
    yy = int(label[2:])
    return f"{label[:2]}{(yy - 1) % 100:02d}"


def cal_quarter(end_month):
    """季末月份 'YYYY-MM' → '2026Q3'；不是 3／6／9／12 月 → None（和日曆季對不齊）"""
    y, m = int(end_month[:4]), int(end_month[5:7])
    return f"{y}Q{m // 3}" if m % 3 == 0 else None


def yoy(now, before):
    if now is None or before is None or before <= 0:
        return None
    return round((now / before - 1) * 100, 1)


def pct_rev(capex, rev):
    if capex is None or rev is None or rev <= 0:
        return None
    return round(capex / rev * 100, 1)


def _fmt_num(val, decimals):
    """與 JS Number.toLocaleString 四捨五入一致的 Decimal ROUND_HALF_UP 格式化。"""
    q = Decimal("1") if decimals <= 0 else Decimal("1." + "0" * decimals)
    d = Decimal(str(float(val))).quantize(q, rounding=ROUND_HALF_UP)
    if d == 0:
        d = Decimal("0").quantize(q)
    return f"{d:,}"


def fmt_capex(val_millions, currency="USD"):
    """多幣別動態單位換算（輸入永遠是 normq 後的原幣百萬元）；與前端 macro.frag.html 邏輯 100% 一致。"""
    if val_millions is None:
        return "—"
    v = float(val_millions)
    av = abs(v)
    cur = (currency or "USD").upper()
    if cur == "TWD":
        if av >= 1_000_000:
            return f"NT${_fmt_num(v / 1_000_000, 2)} 兆"
        if av >= 100:
            u = v / 100
            au = abs(u)
            dp = 0 if au >= 1000 else (1 if au >= 10 else 2)
            return f"NT${_fmt_num(u, dp)} 億"
        dp = 1 if av >= 10 else 2
        return f"NT${_fmt_num(v, dp)} 百萬"
    if cur == "KRW":
        if av >= 1_000_000:
            return f"₩{_fmt_num(v / 1_000_000, 2)} 兆"
        return f"₩{_fmt_num(v / 100, 0)} 億"
    if cur == "EUR":
        if av >= 100:
            u = v / 100
            return f"€{_fmt_num(u, 1 if abs(u) >= 10 else 2)} 億"
        return f"€{_fmt_num(v, 1 if av >= 10 else 2)} 百萬"
    # 預設 USD
    if av >= 100:
        u = v / 100
        return f"${_fmt_num(u, 1 if abs(u) >= 10 else 2)} 億"
    return f"${_fmt_num(v, 1 if av >= 10 else 2)} 百萬"


def _fmt_yi_num(v_yi):
    """格式化「億」的純數值（整除或近整數去掉 .0，其餘保留 1–2 位小數，採四捨五入）。"""
    if abs(v_yi - round(v_yi)) < 1e-6:
        return f"{int(round(v_yi)):,}"
    return _fmt_num(v_yi, 1 if abs(v_yi) >= 10 else 2)


def _fmt_guidance_range(lo, hi, unit, currency):
    """將 guidance item 的 lo/hi（通常單位為百萬原幣）格式化成清晰區間文字。"""
    if lo is None and hi is None:
        return ""
    u_str = str(unit or "")
    cur = (currency or "USD").upper()
    prefix = {"USD": "$", "TWD": "NT$", "KRW": "₩", "EUR": "€"}.get(cur, "$")
    is_millions = ("百萬" in u_str) or (u_str == "")
    if is_millions:
        lo_v = hi if lo is None else lo
        hi_v = lo if hi is None else hi
        if lo_v == hi_v:
            return f"約 {fmt_capex(lo_v, cur)}"
        if cur in ("USD", "EUR", "TWD") and abs(lo_v) >= 100 and abs(hi_v) >= 100 and max(abs(lo_v), abs(hi_v)) < 1_000_000:
            return f"{prefix}{_fmt_yi_num(lo_v / 100)}–{_fmt_yi_num(hi_v / 100)} 億"
        if cur == "KRW" and abs(lo_v) >= 1_000_000 and abs(hi_v) >= 1_000_000:
            return f"{prefix}{_fmt_num(lo_v / 1_000_000, 2)}–{_fmt_num(hi_v / 1_000_000, 2)} 兆"
        return f"{fmt_capex(lo_v, cur)}–{fmt_capex(hi_v, cur)}"
    # 其他單位（如十億美元等）直接附原單位
    lo_v = hi if lo is None else lo
    hi_v = lo if hi is None else hi
    if lo_v == hi_v:
        return f"約 {lo_v:g} {u_str}".strip()
    return f"{lo_v:g}–{hi_v:g} {u_str}".strip()


def _beautify_millions_note(note, unit):
    """若 unit 為百萬美元且 note 中寫有如 130,000–145,000 的百萬數字，轉成易讀的億美元（1,300–1,450 億美元）。"""
    if not note or "百萬美元" not in str(unit or ""):
        return note or ""

    def repl(m):
        a = float(m.group(1).replace(",", ""))
        b = float(m.group(2).replace(",", ""))
        if a >= 1000 and b >= 1000:
            return f"{_fmt_yi_num(a / 100)}–{_fmt_yi_num(b / 100)} 億美元"
        return m.group(0)

    return re.sub(r"(\d{1,3}(?:,\d{3})+)\s*[–\-~～]\s*(\d{1,3}(?:,\d{3})+)", repl, note)


def extract_capex_guidance(D, currency="USD"):
    """擷取資本支出「全年財測／原預估／口頭展望」，沒給回傳 None。

    優先順序：
      1. capexBudget（如台積電，單位為十億美元）
      2. guidance.items（+ guidanceHistory 比對原預估）
      3. summary 電話會議口頭展望（僅 tag == "o"，必備合法 src.url 與 src.speaker，且排除收購／過去式回顧）
    """
    if not isinstance(D, dict):
        return None
    # 1. 書面 capexBudget
    cb = D.get("capexBudget")
    if isinstance(cb, dict) and (cb.get("lo") is not None or cb.get("hi") is not None):
        lo = cb.get("lo")
        hi = cb.get("hi")
        lo_v = hi if lo is None else lo
        hi_v = lo if hi is None else hi
        lo_yi = lo_v * 10
        hi_yi = hi_v * 10
        rng = f"約 {lo_yi:g} 億美元" if lo_yi == hi_yi else f"{lo_yi:g}–{hi_yi:g} 億美元"
        y = cb.get("y") or ""
        prefix = f"{y} 全年 " if y else "全年 "
        return {
            "kind": "written",
            "tag": "書面",
            "period": str(y),
            "text": f"{prefix}{rng}".strip(),
            "note": cb.get("note") or "",
            "src": None,
        }

    # 2. 書面 guidance.items（＋ guidanceHistory 比對原預估）
    g = D.get("guidance")
    if isinstance(g, dict) and isinstance(g.get("items"), list):
        cands = [it for it in g["items"] if isinstance(it, dict) and _CAPEX_KW_RE.search(str(it.get("label") or ""))]
        if cands:
            def _is_annual(it):
                per = str(it.get("period") or "")
                lbl = str(it.get("label") or "")
                return bool(_ANNUAL_PERIOD_RE.match(per)) or ("全年" in lbl)

            annual_cands = [it for it in cands if _is_annual(it)]
            it = annual_cands[0] if annual_cands else cands[0]
            lo, hi = it.get("lo"), it.get("hi")
            unit = it.get("unit") or ""
            rng = _fmt_guidance_range(lo, hi, unit, currency)
            if rng:
                period = str(it.get("period") or "")
                if _ANNUAL_PERIOD_RE.match(period):
                    text = f"{period} 全年 {rng}"
                elif period:
                    text = f"{period} {rng}"
                else:
                    text = rng
                note = _beautify_millions_note(str(it.get("note") or "").strip(), unit)
                if not _NOTE_ORIG_RE.search(note):
                    gh = D.get("guidanceHistory") or []
                    for h in reversed(gh):
                        if not isinstance(h, dict):
                            continue
                        hit = None
                        for oit in (h.get("items") or []):
                            if not isinstance(oit, dict):
                                continue
                            if str(oit.get("period") or "") == period and _CAPEX_KW_RE.search(str(oit.get("label") or "")):
                                hit = oit
                                break
                        if hit and (hit.get("lo"), hit.get("hi")) != (lo, hi):
                            old_rng = _fmt_guidance_range(hit.get("lo"), hit.get("hi"), hit.get("unit") or unit, currency)
                            if old_rng:
                                note = f"{note}；原 {old_rng}" if note else f"原 {old_rng}"
                            break
                return {
                    "kind": "written",
                    "tag": "書面",
                    "period": period,
                    "text": text,
                    "note": note,
                    "src": None,
                }

    # 3. 口頭 summary 展望（僅 tag == "o"，必附 src.url 與 src.speaker）
    sm = D.get("summary")
    if isinstance(sm, dict):
        items = []
        outlook = sm.get("outlook")
        if isinstance(outlook, dict):
            for it in (outlook.get("items") or []):
                if isinstance(it, dict):
                    items.append(("outlook", it))
        for sec in ("mgmt", "qa"):
            arr = sm.get(sec)
            if isinstance(arr, list):
                for it in arr:
                    if isinstance(it, dict):
                        items.append((sec, it))
        for sec, it in items:
            if it.get("tag") != "o":
                continue
            src = it.get("src") or {}
            url = str(src.get("url") or "").strip()
            speaker = str(src.get("speaker") or "").strip()
            if not (url.startswith("http://") or url.startswith("https://")) or not speaker:
                continue
            full_txt = str(it.get("a") if sec == "qa" else it.get("t") or "").strip()
            if not full_txt or _MA_PREFIX_RE.match(full_txt):
                continue
            clauses = [c.strip() for c in re.split(r"[。；;]", full_txt) if c.strip()]
            for idx, cl in enumerate(clauses):
                if not _CAPEX_KW_RE.search(cl):
                    continue
                before = "".join(clauses[:idx])
                if _MA_BEFORE_RE.search(before):
                    if _FAR_YEAR_RE.search(cl) or not _MA_GROUP_ALLOW_RE.search(cl):
                        continue
                if _MA_BEFORE_RE.search(cl) and not _MA_GROUP_ALLOW_RE.search(cl):
                    continue
                if _PAST_HINT_RE.search(cl) and not _FUTURE_VERB_RE.search(cl):
                    continue
                if not (_FUTURE_HINT_RE.search(cl) and re.search(r"\d", cl)):
                    continue
                # 若沒有明確未來展望動詞或未來期間詞，且看起來是過去季實際值則跳過
                has_future_period = bool(_FUTURE_VERB_RE.search(cl) or re.search(r"(FY\s*20\d\d|20\d\d\s*年)", cl, re.I))
                if not has_future_period and _PAST_ONLY_RE.match(cl):
                    continue
                return {
                    "kind": "oral",
                    "tag": "口頭",
                    "period": "",
                    "text": cl,
                    "note": "",
                    "src": {
                        "n": str(src.get("n") or "逐字稿"),
                        "url": url,
                        "speaker": speaker,
                    },
                }
    return None


def company_rows(Q, fye):
    """每季：{q, end（季末月份）, capex, rev, revYoy, gm, gmPrev}"""
    by = {q["q"]: q for q in Q}
    out = []
    for idx, q in enumerate(Q):
        p = by.get(prev_year(q["q"]))
        prev_q = Q[idx - 1] if idx > 0 else None
        out.append({
            "q": q["q"],
            "end": B.end_month(q["q"], fye),
            "capex": q.get("capex"),
            "rev": q.get("rev"),
            "revYoy": yoy(q.get("rev"), p.get("rev") if p else None),
            "gm": q.get("gm"),
            "gmPrev": prev_q.get("gm") if prev_q else None,
        })
    return out


def compute_capex_series(all_rows):
    """過濾空殼佔位季後，對有效季度計算單季年增率、資本密集度、嚴格連續近 4Q（ttm）與近 4Q 年增率（ttmYoy）。"""
    valid_pts = [r for r in all_rows if not (r.get("rev") is None and r.get("capex") is None)]
    by_q = {r["q"]: r for r in valid_pts}
    history = []
    for i, r in enumerate(valid_pts):
        cap = r.get("capex")
        rev = r.get("rev")
        py = by_q.get(prev_year(r["q"]))
        cyoy = yoy(cap, py.get("capex") if py else None)
        pr = pct_rev(cap, rev)
        if i < 3:
            ttm, ttm_why = None, "short"
        else:
            w = valid_pts[i - 3: i + 1]
            has_all = all(x.get("capex") is not None for x in w)
            contiguous = all(qnum(w[k + 1]["q"]) - qnum(w[k]["q"]) == 1 for k in range(3))
            if has_all and contiguous:
                ttm = round(sum(x["capex"] for x in w), 3)
                ttm_why = None
            else:
                ttm, ttm_why = None, "gap"
        history.append({
            "q": r["q"],
            "end": r["end"],
            "rev": rev,
            "capex": cap,
            "yoy": cyoy,
            "pctRev": pr,
            "ttm": ttm,
            "ttmWhy": ttm_why,
        })
    # 近 4Q 年增率（必須相隔剛好 4 個連續季度且兩期 ttm 皆非 None 且前值 > 0）
    for i, h in enumerate(history):
        if i >= 4 and h["ttm"] is not None:
            prev_h = history[i - 4]
            if qnum(h["q"]) - qnum(prev_h["q"]) == 4 and prev_h["ttm"] is not None and prev_h["ttm"] > 0:
                h["ttmYoy"] = round((h["ttm"] / prev_h["ttm"] - 1) * 100, 1)
            else:
                h["ttmYoy"] = None
        else:
            h["ttmYoy"] = None
    return history


def _build_entity(code, c_meta, D, valid_history, note="", allow_disabled=False):
    enabled = bool(c_meta.get("enabled"))
    currency = c_meta.get("currency", "USD")
    path = c_meta.get("path", "") if enabled else ""
    if valid_history:
        last = valid_history[-1]
        status = "ok"
        status_text = ""
        capex_obj = {
            "latestQ": last["q"],
            "latestEnd": last["end"],
            "latest": last["capex"],
            "latestYoy": last["yoy"],
            "latestPctRev": last["pctRev"],
            "ttm": last["ttm"],
            "ttmYoy": last["ttmYoy"],
            "ttmWhy": last["ttmWhy"],
            "guidance": extract_capex_guidance(D, currency) if D else None,
        }
    else:
        capex_obj = None
        if not enabled and allow_disabled:
            status = "pending_ipo"
            status_text = note or "待首份季報揭露單季資本支出後自動帶入"
        else:
            status = "no_data"
            status_text = note or "待確認：尚無有效季度資料"
    return {
        "code": code,
        "name": c_meta["name"],
        "path": path,
        "enabled": enabled,
        "currency": currency,
        "note": note,
        "status": status,
        "statusText": status_text,
        "capex": capex_obj,
        "history": [
            {
                "q": h["q"],
                "end": h["end"],
                "rev": h["rev"],
                "capex": h["capex"],
                "yoy": h["yoy"],
                "pctRev": h["pctRev"],
                "ttm": h["ttm"],
                "ttmWhy": h["ttmWhy"],
            }
            for h in valid_history
        ],
    }


def _supplier_specs(chain):
    """從 chain['tiers'] 或 chain['suppliers'] 取得 (代號, 層級名稱) 清單。"""
    tiers = chain.get("tiers")
    if tiers:
        specs = []
        seen = set()
        for t in tiers:
            tname = t.get("name") or ""
            for code in t.get("codes", []):
                if code not in seen:
                    specs.append((code, tname))
                    seen.add(code)
        for code in chain.get("suppliers", []):
            if code not in seen:
                specs.append((code, ""))
                seen.add(code)
        return specs
    return [(code, "") for code in chain.get("suppliers", [])]


def _emerging_specs(chain):
    """解析 chain['emergingBuyers']，支援字串或 {code, note} 物件。"""
    out = []
    for item in chain.get("emergingBuyers", []) or []:
        if isinstance(item, dict):
            code = item.get("code")
            if code:
                out.append((code, item.get("note") or ""))
        elif isinstance(item, str) and item:
            out.append((item, ""))
    return out


def compute(chain, companies, datasets, since="2015Q1"):
    """chain = {"buyers":[代號…], "emergingBuyers":[{code, note}…], "suppliers":[代號…], "tiers":[{name, codes}…]?}；
    companies = companies.json 的公司清單；datasets = {代號: data}。"""
    C = {c["code"]: c for c in companies}
    sup_specs = _supplier_specs(chain)
    eb_specs = _emerging_specs(chain)
    rows_of, hist_of, missing = {}, {}, []

    main_codes = list(chain["buyers"]) + [s for s, _ in sup_specs]
    for code in main_codes:
        if code not in C or code not in datasets:
            missing.append(f"待確認：{code} 不在網站追蹤清單裡，資本支出鏈沒有算進去")
            continue
        D = datasets[code]
        fye = (D.get("company") or {}).get("fiscalYearEnd") or "12-31"
        rows_of[code] = company_rows(H.normq(D, C[code].get("schema")), fye)
        hist_of[code] = compute_capex_series(rows_of[code])

    for code, _ in eb_specs:
        if code in rows_of or code not in C:
            continue
        D = datasets.get(code)
        if not D:
            if C[code].get("enabled"):
                missing.append(f"待確認：{code} 不在網站追蹤清單裡，資本支出鏈沒有算進去")
            continue
        fye = (D.get("company") or {}).get("fiscalYearEnd") or "12-31"
        rows_of[code] = company_rows(H.normq(D, C[code].get("schema")), fye)
        hist_of[code] = compute_capex_series(rows_of[code])

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

    buyer_cards = [
        _build_entity(b, C[b], datasets[b], hist_of[b])
        for b in buyers
    ]
    emerging_cards = []
    for code, note in eb_specs:
        if code not in C:
            continue
        D = datasets.get(code)
        h = hist_of.get(code, [])
        if C[code].get("enabled") and not h:
            missing.append(f"待確認：{code} 尚無有效季度資料")
        emerging_cards.append(_build_entity(code, C[code], D, h, note=note, allow_disabled=True))

    sup = []
    for s, tier_name in sup_specs:
        if s not in rows_of:
            continue
        all_pts = rows_of[s]
        pts = [{"q": r["q"], "end": r["end"], "rev": r["rev"], "yoy": r["revYoy"]} for r in all_pts if r["end"] >= since[:4] + "-01"]
        last_r = all_pts[-1] if all_pts else None
        gm = round(last_r["gm"], 1) if last_r and last_r.get("gm") is not None else None
        gm_prev = last_r.get("gmPrev") if last_r else None
        gm_qchg = round(gm - gm_prev, 1) if (gm is not None and gm_prev is not None) else None
        ent = _build_entity(s, C[s], datasets[s], hist_of[s])
        sup.append({
            "code": s,
            "name": C[s]["name"],
            "path": C[s]["path"],
            "enabled": ent["enabled"],
            "currency": C[s].get("currency", ""),
            "tier": tier_name,
            "gm": gm,
            "gmQchg": gm_qchg,
            "points": pts,
            "capex": ent["capex"],
            "history": ent["history"],
        })
    tiers_out = []
    if chain.get("tiers"):
        by_code = {x["code"]: x for x in sup}
        for t in chain["tiers"]:
            tname = t.get("name") or ""
            items = [by_code[c] for c in t.get("codes", []) if c in by_code]
            tiers_out.append({"name": tname, "suppliers": items})
    return {
        "buyers": [{"code": b, "name": C[b]["name"], "path": C[b]["path"]} for b in buyers],
        "buyerCards": buyer_cards,
        "emergingBuyers": emerging_cards,
        "rows": rows,
        "suppliers": sup,
        "tiers": tiers_out,
        "missing": missing,
    }


def load():
    with open(os.path.join(ROOT, "companies.json"), encoding="utf8") as f:
        cfg = json.load(f)
    with open(os.path.join(ROOT, "data", "macro", "config.json"), encoding="utf8") as f:
        chain = json.load(f)["chain"]
    all_cos = cfg["companies"]
    C = {c["code"]: c for c in all_cos}
    sup_codes = [s for s, _ in _supplier_specs(chain)]
    eb_codes = [e for e, _ in _emerging_specs(chain)]
    data = {}
    for code in list(chain["buyers"]) + sup_codes:
        p = os.path.join(ROOT, "data", code + ".json")
        if os.path.exists(p) and code in C and C[code].get("enabled"):
            with open(p, encoding="utf8") as f:
                data[code] = json.load(f)
    for code in eb_codes:
        if code in data or code not in C:
            continue
        p = os.path.join(ROOT, "data", code + ".json")
        if os.path.exists(p):
            with open(p, encoding="utf8") as f:
                data[code] = json.load(f)
    return compute(chain, all_cos, data)


if __name__ == "__main__":
    out = load()
    names = [b["name"] for b in out["buyers"]]
    print("日曆季   " + "  ".join(f"{n:>8s}" for n in names) + "      合計   年增%  占營收%")
    for r in out["rows"][-8:]:
        print(f"{r['cq']}  " + "  ".join(f"{(r['capex'][b['code']] if r['capex'][b['code']] is not None else float('nan')):>10,.0f}" for b in out["buyers"]) +
              f"  {r['total'] if r['total'] is not None else '—':>9}  {r['yoy'] if r['yoy'] is not None else '—':>6}  {r['pctRev'] if r['pctRev'] is not None else '—':>6}")
    def _fmt_pct(v):
        return "—" if v is None else f"{v}%"

    print("\n--- 買方（四大雲端＋新興 AI 買方）---")
    for b in out.get("buyerCards", []) + out.get("emergingBuyers", []):
        cx = b.get("capex")
        if cx:
            g = cx.get("guidance")
            g_str = f" | 財測：{g['text']}" if g else ""
            print(f"{b['name']}（{cx['latestQ']}）：單季 {fmt_capex(cx['latest'], b['currency'])}（年增 {_fmt_pct(cx['latestYoy'])}，占營收 {_fmt_pct(cx['latestPctRev'])}）| 近4Q {fmt_capex(cx['ttm'], b['currency'])}{g_str}")
        else:
            print(f"{b['name']}：{b['status']}（{b['statusText']}）")
    print("\n--- 下游供應鏈 ---")
    for s in out["suppliers"]:
        p = s["points"][-1]
        cx = s.get("capex") or {}
        print(f"{s['name']}：{p['q']}（季末 {p['end']}）營收年增 {_fmt_pct(p['yoy'])} | 資本支出 {fmt_capex(cx.get('latest'), s['currency'])}（近4Q {fmt_capex(cx.get('ttm'), s['currency'])}）")
    for m in out["missing"]:
        print(m)
