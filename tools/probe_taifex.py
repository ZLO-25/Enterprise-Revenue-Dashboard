# 暫時用：測試期交所日 K 下載格式（只印欄位、筆數、日期、比較結果，不印價格）
import urllib.request, urllib.parse, csv, io, re, collections, statistics
UA = {"User-Agent": "Mozilla/5.0"}
def post(url, form):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(form).encode(), headers=dict(UA, **{"Content-Type": "application/x-www-form-urlencoded"}))
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read(), r.headers.get("Content-Type")
def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read(), r.headers.get("Content-Type")
def dec(raw):
    for enc in ("utf-8", "cp950"):
        try: return raw.decode(enc)
        except Exception: pass
def q(a, b):
    raw, ct = post("https://www.taifex.com.tw/cht/3/futDataDown", {"down_type": "1", "commodity_id": "TX", "commodity_id2": "", "queryStartDate": a, "queryEndDate": b})
    t = dec(raw)
    if "html" in ct and "MS950" not in ct:
        txt = re.sub(r"<[^>]+>", " ", t); txt = re.sub(r"\s+", " ", txt)
        print(f"== {a}~{b} HTML: {txt[:300]}"); return None
    rows = list(csv.reader(io.StringIO(t)))
    print(f"== {a}~{b} rows={len(rows)} dates={len(set(r[0] for r in rows[1:]))}")
    return rows
for a, b in [("2026/10/19", "2026/11/18"), ("2023/11/20", "2023/12/19"), ("2023/11/01", "2023/11/30"), ("2021/01/04", "2021/01/29"), ("2016/01/04", "2016/01/29"), ("2006/01/02", "2006/01/27"), ("1998/07/21", "1998/08/20")]:
    try: q(a, b)
    except Exception as e: print("ERR", a, b, e)
# 夜盤歸屬：比較 盤後(D) 與 一般(D) / 一般(次一日) 的關係（只印平均差距的比例，不印價格）
rows = q("2026/10/19", "2026/11/18")
if rows:
    day, night = {}, {}
    for r in rows[1:]:
        if len(r) < 18 or "/" in r[2] or r[3].strip() in ("", "-"): continue
        d, m, s = r[0].strip(), r[2].strip(), r[17].strip()
        (day if s == "一般" else night)[(d, m)] = (float(r[3]), float(r[6]))
    dates = sorted({k[0] for k in day})
    A, B = [], []  # A: 盤後(D).open vs 一般(D).close  B: 盤後(D).close vs 一般(next).open ; C: 盤後(D).close vs 一般(D).open
    C, Dd = [], []
    for i, d in enumerate(dates):
        for (dd, m), (no, nc) in night.items():
            if dd != d or (d, m) not in day: continue
            do, dc = day[(d, m)]
            A.append(abs(no - dc) / dc); C.append(abs(nc - do) / do)
            if i > 0 and (dates[i-1], m) in day:
                po, pc = day[(dates[i-1], m)]; Dd.append(abs(no - pc) / pc)
            if i + 1 < len(dates) and (dates[i+1], m) in day:
                B.append(abs(nc - day[(dates[i+1], m)][0]) / day[(dates[i+1], m)][0])
    f = lambda x: f"{statistics.mean(x)*100:.3f}% n={len(x)}" if x else "-"
    print("盤後(D)開 vs 一般(D)收:", f(A), "| 盤後(D)收 vs 一般(次日)開:", f(B))
    print("盤後(D)收 vs 一般(D)開:", f(C), "| 盤後(D)開 vs 一般(前日)收:", f(Dd))
    print("weekdays with 盤後:", collections.Counter(__import__('datetime').date(*map(int, k[0].split('/'))).strftime('%a') for k in night))
# 歷史資料下載頁：列出 zip/csv 連結
for u in ["https://www.taifex.com.tw/cht/3/dlFutDataDown", "https://www.taifex.com.tw/cht/3/dlFutPrevious30DaysSalesData"]:
    try:
        raw, ct = get(u); t = dec(raw)
        links = sorted(set(re.findall(r'''(?:href|value)=["']([^"']*(?:zip|csv|ZIP|CSV)[^"']*)["']''', t)))
        print("==", u, ct, len(raw), "links:", links[:40])
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
        for kw in ("近", "年", "歷史"):
            for m in re.finditer(kw, txt):
                pass
        i = txt.find("歷史"); print("  text:", txt[max(0,i-100):i+400])
    except Exception as e: print("ERR", u, e)
