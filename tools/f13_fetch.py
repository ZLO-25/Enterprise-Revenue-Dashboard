"""13F 大師持股抓取（GitHub Actions 的 f13-quarterly 跑，不經過 Claude）。

資料來源：SEC EDGAR（data.sec.gov submissions、www.sec.gov Archives 的 primary_doc.xml 與 information table XML）。
寫入：data/13f/<id>.json（每位經理人最近 8 季）、data/13f/latest.json、data/13f/by-company.json。
設定：data/13f/config.json（Claude 維護）。說明：docs/F13.md。

用法：
  python3 tools/f13_fetch.py            完整抓取並寫檔（任何一位失敗就 exit 1，但不覆蓋那位的舊檔）
  python3 tools/f13_fetch.py --check    只看有沒有新申報；把 stale=true/false 寫到 $GITHUB_OUTPUT（約 10 秒）
  python3 tools/f13_fetch.py --only id  只抓一位（除錯用）
檢查（總值、列數、CUSIP 對照）在 tools/f13_check.py。

13F 規則（程式依此寫）：
  - value 單位：2023-01-03 之後申報的是「元」，之前是「千元」→ 一律換成元存檔。
  - Berkshire 同一檔分多列（otherManager 不同）→ 依 CUSIP＋putCall＋SH/PRN 合併（同 CUSIP 就是同一檔證券，titleOfClass 只是各家寫法不同）。
  - 修正版：RESTATEMENT＝整份取代；NEW HOLDINGS＝加到原始上；多份依申報順序套用。
  - 13F-NT（通知）：沒有持股表，只記下接手申報人的名稱；config 的 ciks 若列了接手申報人 CIK，該季改用接手申報人的 13F-HR。
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "data", "13f")
UA = "Enterprise-Revenue-Dashboard research contact@example.com"  # 同 tools/sec_feed.py（Actions 已實測可用）
FORMS = ("13F-HR", "13F-HR/A", "13F-NT", "13F-NT/A")
VALUE_IN_DOLLARS_FROM = "2023-01-03"   # 這天（含）之後申報的 value 是元，之前是千元
KEEP = 8                               # 存最近 8 季；多抓 1 季只為了算第 8 季的變化
HIST = KEEP + 1


class FetchError(Exception):
    pass


# ---------------------------------------------------------------- HTTP
class Http:
    """每次請求間隔 >= delay 秒、失敗重試 tries 次。測試用假物件取代（只要有 get(url)->bytes 與 json(url)）。"""

    def __init__(self, delay=0.15, tries=3):
        self.delay, self.tries, self.last = delay, tries, 0.0

    def get(self, url):
        err = None
        for i in range(self.tries):
            wait = self.delay - (time.time() - self.last)
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "identity"}), timeout=60) as r:
                    return r.read()
            except Exception as e:  # noqa
                err = e
                print("  重試", url, e)
                time.sleep(3 * (i + 1))
        raise FetchError(f"讀取失敗 {url}：{err}")

    def json(self, url):
        return json.loads(self.get(url).decode("utf8"))


# ---------------------------------------------------------------- 解析
def _strip(root):
    """XML 有 namespace（前綴不固定：ns1:、com:、預設）→ 全部拿掉，之後用純標籤名找。"""
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
    return root


def _text(el, path):
    x = el.find(path) if el is not None else None
    return (x.text or "").strip() if x is not None and x.text else ""


def _int(s):
    s = (s or "").strip().replace(",", "")
    if not s:
        return None
    return int(s) if re.fullmatch(r"-?\d+", s) else int(round(float(s)))


def date_iso(mmddyyyy):
    """'09-30-2026' → '2026-09-30'；已是 ISO 就原樣回傳。"""
    s = (mmddyyyy or "").strip()
    m = re.fullmatch(r"(\d\d)-(\d\d)-(\d{4})", s)
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else (s if re.fullmatch(r"\d{4}-\d\d-\d\d", s) else None)


def parse_primary(xml_bytes):
    """primary_doc.xml → 封面與摘要。entries／totalValue 是申報檔自己寫的原始值（單位依申報日，用 scale_value 換成元）。"""
    r = _strip(ET.fromstring(xml_bytes))
    cover, summ = r.find("formData/coverPage"), r.find("formData/summaryPage")
    others = []
    for om in (cover.findall("otherManagersInfo/otherManager") if cover is not None else []):
        others.append({"cik": _text(om, "cik"), "name": _text(om, "name"), "file": _text(om, "form13FFileNumber")})
    return {
        "form": _text(r, "headerData/submissionType"),
        "period": date_iso(_text(r, "headerData/filerInfo/periodOfReport") or _text(cover, "reportCalendarOrQuarter")),
        "isAmendment": _text(cover, "isAmendment").lower() == "true",
        "amendType": _text(cover, "amendmentInfo/amendmentType").upper() or None,   # RESTATEMENT／NEW HOLDINGS／None
        "reportType": _text(cover, "reportType"),
        "manager": _text(cover, "filingManager/name"),
        "fileNo": _text(cover, "form13FFileNumber"),
        "otherManagers": others,                     # 13F-NT：接手申報的人
        "note": _text(cover, "additionalInformation"),
        "entries": _int(_text(summ, "tableEntryTotal")),
        "totalValue": _int(_text(summ, "tableValueTotal")),
        "confidentialOmitted": _text(summ, "isConfidentialOmitted").lower() == "true",
    }


def parse_info_table(xml_bytes):
    """information table → 原始列（未合併）。value 是申報檔原值。"""
    r = _strip(ET.fromstring(xml_bytes))
    rows = []
    for t in r.iter("infoTable"):
        rows.append({
            "name": _text(t, "nameOfIssuer"), "cls": _text(t, "titleOfClass"), "cusip": _text(t, "cusip").upper(),
            "value": _int(_text(t, "value")) or 0,
            "shares": _int(_text(t, "shrsOrPrnAmt/sshPrnamt")) or 0,
            "type": _text(t, "shrsOrPrnAmt/sshPrnamtType").upper() or "SH",
            "putCall": _text(t, "putCall").title() or "",
        })
    return rows


def scale_value(v, filed):
    """申報日在 2023-01-03 以前，value 的單位是千元 → 換成元；之後本來就是元。"""
    if v is None:
        return None
    return v * 1000 if (filed or "") < VALUE_IN_DOLLARS_FROM else v


def merge_rows(rows, filed):
    """同 CUSIP＋putCall＋SH/PRN 的列加總（Berkshire 同一檔分多列）→ 依市值大到小。value 已換成元。"""
    m = {}
    for r in rows:
        k = (r["cusip"], r["putCall"], r["type"])
        v = scale_value(r["value"], filed)
        if k not in m:
            m[k] = {"cusip": r["cusip"], "name": r["name"], "cls": r["cls"], "value": 0, "shares": 0, "type": r["type"], "putCall": r["putCall"], "_top": -1}
        h = m[k]
        h["value"] += v
        h["shares"] += r["shares"]
        if v > h["_top"]:   # 名稱與類別取最大的那一列（原文）
            h["_top"], h["name"], h["cls"] = v, r["name"], r["cls"]
    out = sorted(m.values(), key=lambda h: (-h["value"], h["cusip"]))
    for h in out:
        h.pop("_top")
    return out


def acc_nodash(acc):
    return acc.replace("-", "")


def filing_url(cik, acc):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash(acc)}/{acc}-index.htm"


def folder_url(cik, acc):
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_nodash(acc)}/"


def pick_xml_names(index_json):
    """filing 資料夾的 index.json → (primary_doc 檔名, [information table 可能的檔名])。檔名不固定（60471.xml、F13InfoTable_77922.xml…）。"""
    items = (index_json.get("directory") or {}).get("item") or []
    names = [i.get("name", "") for i in items if i.get("type") != "dir" or i.get("name", "").lower().endswith(".xml")]
    xml = [n for n in names if n.lower().endswith(".xml")]
    primary = "primary_doc.xml" if "primary_doc.xml" in xml else None
    return primary, [n for n in xml if n != "primary_doc.xml"]


def load_filing(http, cik, acc, need_table=True):
    """讀一份申報：回傳 (primary 摘要, 原始列 or None)。NT 沒有持股表。"""
    base = folder_url(cik, acc)
    primary, tables = pick_xml_names(http.json(base + "index.json"))
    if not primary:
        raise FetchError(f"{acc}：資料夾裡沒有 primary_doc.xml")
    p = parse_primary(http.get(base + primary))
    rows = None
    if need_table and p["form"].startswith("13F-HR"):
        for n in tables:
            b = http.get(base + n)
            if b"informationTable" in b[:2000] or b"infoTable" in b:
                rows = parse_info_table(b)
                break
        if rows is None:
            raise FetchError(f"{acc}：找不到 information table（檔案：{tables}）")
    return p, rows


# ---------------------------------------------------------------- 申報清單
def list_filings(http, cik, want_periods=HIST):
    """submissions → 這個 CIK 的 13F 系列申報。recent 不夠 want_periods 個季度才讀 filings.files 的舊頁。"""
    sub = http.json(f"https://data.sec.gov/submissions/CIK{cik}.json")
    out = []

    def take(block):
        for i, form in enumerate(block.get("form") or []):
            if form in FORMS and block["reportDate"][i]:
                out.append({"cik": cik, "form": form, "acc": block["accessionNumber"][i], "filed": block["filingDate"][i], "period": block["reportDate"][i]})
    take(sub["filings"]["recent"])
    for f in (sub["filings"].get("files") or []):
        if len({x["period"] for x in out}) >= want_periods:
            break
        take(http.json("https://data.sec.gov/submissions/" + f["name"]))
    out.sort(key=lambda x: (x["filed"], x["acc"]))
    return sub.get("name") or "", out


def prev_quarter(period):
    y, m = int(period[:4]), int(period[5:7])
    return f"{y - 1}-12-31" if m == 3 else (f"{y}-03-31" if m == 6 else (f"{y}-06-30" if m == 9 else f"{y}-09-30"))


# ---------------------------------------------------------------- 一季的組裝
def _apply(q, p, rows, filed, cik, acc, form, first):
    """把一份申報（原始或修正）套進 q 的累積列。回傳要記進 notes 的字串或 None。"""
    t = scale_value(p["totalValue"], filed)
    note = None
    if first or (p["amendType"] or "RESTATEMENT") == "RESTATEMENT":
        if not first and p["amendType"] is None:
            note = f"待確認：{acc} 是 {form} 但封面沒寫 amendmentType，先當作整份取代（RESTATEMENT）"
        q["_raw"] = [dict(r, _f=filed) for r in rows]
        q["entries"], q["totalValue"] = p["entries"], t
    else:                                         # NEW HOLDINGS：加到原有的上面
        q["_raw"] += [dict(r, _f=filed) for r in rows]
        q["entries"] = (q["entries"] or 0) + (p["entries"] or 0)
        q["totalValue"] = (q["totalValue"] or 0) + (t or 0)
    q["confidential"] = q.get("confidential") or p["confidentialOmitted"]
    return note


def assemble(http, filings, fixed_cik=None):
    """同一個 CIK、同一季的申報 → 一季資料（持股已合併、尚未算變化）。filings 已依申報日排序。"""
    hr = [f for f in filings if f["form"] == "13F-HR"]
    am = [f for f in filings if f["form"] == "13F-HR/A"]
    nt = [f for f in filings if f["form"].startswith("13F-NT")]
    notes = []
    if hr or am:
        base = hr[0] if hr else am[0]
        if len(hr) > 1:
            notes.append(f"待確認：同一季有 {len(hr)} 份 13F-HR（{', '.join(h['acc'] for h in hr)}），以最早的為準")
        if not hr:
            notes.append(f"待確認：找不到原始 13F-HR（可能在較舊的申報清單），改用最早的修正版 {base['acc']}")
        p0, rows0 = load_filing(http, base["cik"], base["acc"])
        q = {"period": p0["period"] or base["period"], "filed": base["filed"], "form": base["form"], "acc": base["acc"], "cik": base["cik"],
             "url": filing_url(base["cik"], base["acc"]), "amended": False, "amendments": [], "holdingsKnown": True}
        n = _apply(q, p0, rows0, base["filed"], base["cik"], base["acc"], base["form"], True)
        for a in am:
            if a["acc"] == base["acc"]:
                continue
            pa, ra = load_filing(http, a["cik"], a["acc"])
            if ra is None or not ra:
                notes.append(f"待確認：修正版 {a['acc']} 沒有持股表，沒有套用")
                continue
            n = _apply(q, pa, ra, a["filed"], a["cik"], a["acc"], a["form"], False)
            if n:
                notes.append(n)
            q["amended"] = True
            q["amendments"].append({"acc": a["acc"], "form": a["form"], "filed": a["filed"], "type": pa["amendType"], "url": filing_url(a["cik"], a["acc"])})
        q["notes"] = notes
        q["rawRows"] = len(q["_raw"])
        q["holdings"] = merge_rows_multi(q.pop("_raw"))
        return q
    # 只有通知（13F-NT）：沒有持股表
    last = nt[-1]
    p, _ = load_filing(http, last["cik"], last["acc"], need_table=False)
    return {"period": p["period"] or last["period"], "filed": last["filed"], "form": last["form"], "acc": last["acc"], "cik": last["cik"],
            "url": filing_url(last["cik"], last["acc"]), "amended": False, "amendments": [], "holdingsKnown": False,
            "notice": {"by": p["otherManagers"], "note": p["note"]}, "totalValue": None, "entries": None, "rawRows": 0, "holdings": [],
            "notes": [], "confidential": False}


def merge_rows_multi(raw):
    """各列帶自己那份申報的申報日（_f）：先依申報日換成元，再合併（原始＋NEW HOLDINGS 可能來自不同日期）。"""
    rows = [dict({k: v for k, v in r.items() if k != "_f"}, value=scale_value(r["value"], r["_f"])) for r in raw]
    return merge_rows(rows, "9999-12-31")   # 已是元；遠未來日期避免重複 ×1000


# ---------------------------------------------------------------- 變化
def finish_quarter(q, code_map):
    """加 pct、code；算 sumValue。"""
    hs = q["holdings"]
    q["sumValue"] = sum(h["value"] for h in hs) if q["holdingsKnown"] else None
    tot = q.get("totalValue") or q["sumValue"] or 0
    for h in hs:
        h["pct"] = round(h["value"] / tot * 100, 4) if tot else None
        h["code"] = code_map.get(h["cusip"])
        h["chg"], h["chgPct"], h["prev"] = None, None, None


def apply_changes(cur, prev):
    """cur 與 prev（上一個日曆季）比股數。上一季沒申報／只有 NT／不是相鄰季 → 變化留 None（不猜）。出清的列補進去（value 0）。"""
    if not cur["holdingsKnown"]:
        return
    ok = prev is not None and prev["holdingsKnown"] and prev["period"] == prev_quarter(cur["period"])
    cur["chgNote"] = None if ok else "待確認：上一季沒有可比較的 13F-HR（沒申報、只有 13F-NT，或季別不連續），本季變化不顯示"
    if not ok:
        return
    pm = {(h["cusip"], h["putCall"], h["type"]): h for h in prev["holdings"]}
    seen = set()
    for h in cur["holdings"]:
        k = (h["cusip"], h["putCall"], h["type"])
        seen.add(k)
        p = pm.get(k)
        if p is None:
            h["chg"], h["prev"], h["chgPct"] = "new", 0, None
        else:
            h["prev"] = p["shares"]
            if h["shares"] > p["shares"]:
                h["chg"] = "add"
            elif h["shares"] < p["shares"]:
                h["chg"] = "reduce"
            else:
                h["chg"] = "same"
            h["chgPct"] = round((h["shares"] - p["shares"]) / p["shares"] * 100, 2) if p["shares"] else None
    gone = []
    for k, p in pm.items():
        if k not in seen:
            gone.append({"cusip": p["cusip"], "name": p["name"], "cls": p["cls"], "value": 0, "shares": 0, "type": p["type"], "putCall": p["putCall"],
                         "pct": 0, "code": p.get("code"), "chg": "exit", "chgPct": -100.0, "prev": p["shares"]})
    cur["holdings"] += sorted(gone, key=lambda h: -(pm[(h["cusip"], h["putCall"], h["type"])]["value"]))


# ---------------------------------------------------------------- 一位經理人
def manager_ciks(m):
    return m.get("ciks") or [m["cik"]]


def select_filings(per_cik, ciks):
    """per_cik: {cik: [申報]}。回傳 {period: (使用的 cik, 該 CIK 這季的申報, via 說明或 None, notes)}；主 CIK（ciks[0]）優先。"""
    periods = sorted({f["period"] for fl in per_cik.values() for f in fl}, reverse=True)[:HIST]
    out = {}
    for per in periods:
        by = {c: [f for f in per_cik.get(c, []) if f["period"] == per] for c in ciks}
        has_hr = [c for c in ciks if any(f["form"] in ("13F-HR", "13F-HR/A") for f in by[c])]
        notes = []
        if has_hr:
            use = has_hr[0]
            if len(has_hr) > 1:
                notes.append(f"待確認：{per} 主 CIK 與接手申報人都有 13F-HR（{', '.join(has_hr)}），以主 CIK {use} 為準")
            via = use if use != ciks[0] else None
            nts = [f for f in by[ciks[0]] if f["form"].startswith("13F-NT")] if via else []
            fl = [f for f in by[use] if f["form"] in ("13F-HR", "13F-HR/A")]
            out[per] = (use, fl, (via, nts), notes)
        else:
            use = next((c for c in ciks if by[c]), None)
            if use:
                out[per] = (use, by[use], (None, []), notes)
    return out


def build_manager(http, m, code_map):
    ciks = manager_ciks(m)
    per_cik, sec_name = {}, ""
    for c in ciks:
        nm, fl = list_filings(http, c)
        per_cik[c] = fl
        sec_name = sec_name or nm
    sel = select_filings(per_cik, ciks)
    if not sel:
        raise FetchError(f"{m['id']}：submissions 裡沒有任何 13F 申報")
    qs = []
    for per in sorted(sel, reverse=True):
        use, fl, (via, nts), notes = sel[per]
        q = assemble(http, fl)
        q["notes"] = list(notes) + q.get("notes", [])
        if via:
            q["via"] = {"cik": use, "form": q["form"], "name": None}
            if nts:
                pn, _ = load_filing(http, nts[-1]["cik"], nts[-1]["acc"], need_table=False)
                q["via"]["name"] = next((o["name"] for o in pn["otherManagers"] if o["cik"].lstrip("0") == use.lstrip("0")), None)
                q["via"]["primaryNotice"] = {"acc": nts[-1]["acc"], "url": filing_url(nts[-1]["cik"], nts[-1]["acc"]), "form": nts[-1]["form"]}
        if q.get("period") != per:
            q["notes"].append(f"待確認：submissions 的 reportDate 是 {per}，申報檔寫 {q.get('period')}")
            q["period"] = per
        finish_quarter(q, code_map)
        qs.append(q)
    for i, q in enumerate(qs):
        apply_changes(q, qs[i + 1] if i + 1 < len(qs) else None)
    qs = qs[:KEEP]
    for q in qs:
        q.pop("cik", None)
    seen = sorted({f["acc"] for fl in per_cik.values() for f in fl})
    return {"id": m["id"], "name": m["name"], "secName": sec_name, "zh": m.get("zh"), "ciks": ciks, "fetched": now_iso(), "seen": seen, "quarters": qs}


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


# ---------------------------------------------------------------- 彙整檔
def combine(rows):
    """同一本站公司的多列（例如 Alphabet A、C 兩個 CUSIP）加總：股數、市值、占比、上季股數 → 變化。"""
    v = sum(h["value"] for h in rows)
    sh = sum(h["shares"] for h in rows)
    pct = sum(h["pct"] or 0 for h in rows)
    if any(h["chg"] is None for h in rows):
        return v, sh, pct, None, None
    pv = sum(h["prev"] or 0 for h in rows)
    if pv == 0 and sh > 0:
        chg = "new"
    elif sh == 0:
        chg = "exit"
    else:
        chg = "add" if sh > pv else ("reduce" if sh < pv else "same")
    return v, sh, round(pct, 4), chg, (round((sh - pv) / pv * 100, 2) if pv else None)


def build_latest(docs, cfg):
    mg = {}
    for m in cfg["managers"]:
        d = docs.get(m["id"])
        if not d or not d["quarters"]:
            continue
        q = d["quarters"][0]
        hs = [h for h in q["holdings"] if h["chg"] != "exit"]
        mg[m["id"]] = {"period": q["period"], "filed": q["filed"], "form": q["form"], "acc": q["acc"], "url": q["url"], "amended": q["amended"],
                       "holdingsKnown": q["holdingsKnown"], "count": len(hs), "totalValue": q.get("totalValue"), "via": q.get("via"), "notice": q.get("notice"),
                       "top10": hs[:10], "periods": [x["period"] for x in d["quarters"]]}
    return {"fetched": now_iso(), "source": "SEC EDGAR 13F（書面）", "managers": mg}


def build_by_company(docs, cfg):
    tracked = cfg.get("tracked") or {}
    latest_by = {mid: d["quarters"][0]["period"] for mid, d in docs.items() if d["quarters"]}
    top = max(latest_by.values()) if latest_by else None
    comps = {}
    for code, t in tracked.items():
        entry = {"cusipsKnown": bool(t.get("cusips")), "managers": []}
        for m in cfg["managers"]:
            d = docs.get(m["id"])
            if not d or not d["quarters"]:
                continue
            q = d["quarters"][0]
            if not q["holdingsKnown"]:
                continue
            rows = [h for h in q["holdings"] if h.get("code") == code]
            if not rows:
                continue
            v, sh, pct, chg, chgPct = combine(rows)
            entry["managers"].append({"id": m["id"], "period": q["period"], "shares": sh, "value": v, "pct": pct, "chg": chg, "chgPct": chgPct})
        comps[code] = entry
    return {"fetched": now_iso(), "period": top, "latestByManager": latest_by, "notCovered": cfg.get("notCovered") or {}, "companies": comps}


def write_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    os.replace(tmp, path)


def load_config():
    with open(os.path.join(DIR, "config.json"), encoding="utf8") as f:
        return json.load(f)


def code_map_of(cfg):
    return {c: code for code, t in (cfg.get("tracked") or {}).items() for c in (t.get("cusips") or [])}


def load_docs(cfg):
    docs = {}
    for m in cfg["managers"]:
        p = os.path.join(DIR, m["id"] + ".json")
        if os.path.exists(p):
            with open(p, encoding="utf8") as f:
                docs[m["id"]] = json.load(f)
    return docs


# ---------------------------------------------------------------- --check
def check_stale(http, cfg, out=None):
    """有沒有新申報：每位經理人的 submissions（recent）裡，最近 HIST 季的 13F 系列 accession 是否都已在 <id>.json 的 seen 裡。"""
    docs = load_docs(cfg)
    for m in cfg["managers"]:
        d = docs.get(m["id"])
        if not d:
            print(m["id"], "還沒有資料檔")
            return True
        now = set()
        for c in manager_ciks(m):
            _, fl = list_filings_recent(http, c)
            now |= {f["acc"] for f in fl}
        new = now - set(d.get("seen") or [])
        if new:
            print(m["id"], "有新申報：", sorted(new))
            return True
    return False


def list_filings_recent(http, cik):
    sub = http.json(f"https://data.sec.gov/submissions/CIK{cik}.json")
    b, out = sub["filings"]["recent"], []
    for i, form in enumerate(b.get("form") or []):
        if form in FORMS and b["reportDate"][i]:
            out.append({"acc": b["accessionNumber"][i], "period": b["reportDate"][i], "form": form})
    keep = {f["period"] for f in sorted(out, key=lambda x: x["period"], reverse=True)}
    keep = set(sorted(keep, reverse=True)[:HIST])
    return sub.get("name") or "", [f for f in out if f["period"] in keep]


def gh_output(k, v):
    p = os.environ.get("GITHUB_OUTPUT")
    if p:
        with open(p, "a") as f:
            f.write(f"{k}={v}\n")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    cfg = load_config()
    http = Http()
    if "--check" in argv:
        try:
            stale = check_stale(http, cfg)
        except Exception as e:  # noqa  查不到就當作需要抓（抓失敗會標紅燈）
            print("檢查失敗，改成直接抓：", e)
            stale = True
        print("stale=" + str(stale).lower())
        gh_output("stale", str(stale).lower())
        return 0
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    cm = code_map_of(cfg)
    os.makedirs(DIR, exist_ok=True)
    bad = []
    for m in cfg["managers"]:
        if only and m["id"] != only:
            continue
        try:
            d = build_manager(http, m, cm)
        except Exception as e:  # noqa  失敗：不覆蓋舊檔
            print("✗", m["id"], e)
            bad.append(m["id"])
            continue
        write_json(os.path.join(DIR, m["id"] + ".json"), d)
        q = d["quarters"][0]
        print("✓", m["id"], q["period"], q["form"], "持股", len(q["holdings"]), "季數", len(d["quarters"]))
    docs = load_docs(cfg)
    if docs:
        write_json(os.path.join(DIR, "latest.json"), build_latest(docs, cfg))
        write_json(os.path.join(DIR, "by-company.json"), build_by_company(docs, cfg))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
