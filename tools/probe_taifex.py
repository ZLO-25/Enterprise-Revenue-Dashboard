# 暫時用：測試期交所日 K 下載格式（只印欄位、筆數、日期，不印價格）
import urllib.request, urllib.parse, csv, io, collections
URL = "https://www.taifex.com.tw/cht/3/futDataDown"
def q(a, b):
    data = urllib.parse.urlencode({"down_type": "1", "commodity_id": "TX", "commodity_id2": "", "queryStartDate": a, "queryEndDate": b}).encode()
    req = urllib.request.Request(URL, data=data, headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read(); ct = r.headers.get("Content-Type")
    for enc in ("utf-8", "big5", "cp950"):
        try:
            t = raw.decode(enc); break
        except Exception: pass
    rows = list(csv.reader(io.StringIO(t)))
    print(f"== {a}~{b} type={ct} bytes={len(raw)} enc={enc} rows={len(rows)}")
    if not rows: return
    print("header:", rows[0])
    print("ncols:", collections.Counter(len(r) for r in rows))
    if len(rows) > 1:
        h = rows[0]
        def col(name):
            for i, x in enumerate(h):
                if name in x: return i
        for nm in ("交易日期", "契約", "到期月份", "交易時段"):
            i = col(nm)
            if i is not None:
                print(nm, sorted(collections.Counter(r[i].strip() for r in rows[1:] if len(r) > i).items())[:40])
        # 每欄是否為空或 '-' 的統計（不印值）
        for i, x in enumerate(h):
            vals = [r[i].strip() for r in rows[1:] if len(r) > i]
            print(f"  col{i} {x}: empty/-={sum(1 for v in vals if v in ('', '-'))}/{len(vals)}")
    else:
        print("text head:", t[:300].replace("\n", " | "))
for a, b in [("2026/11/10", "2026/11/18"), ("1998/07/21", "1998/08/31"), ("2026/08/01", "2026/11/18"), ("2020/01/01", "2020/12/31")]:
    try: q(a, b)
    except Exception as e: print("ERR", a, b, e)
