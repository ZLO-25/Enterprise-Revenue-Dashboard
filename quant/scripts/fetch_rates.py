"""下載升降息週期分頁要用的利率資料 → quant/data/rates.json。由 .github/workflows/rates-weekly.yml 執行。

  FRED（美國聖路易聯準銀行，免金鑰 CSV）──┐
  台灣央行（重貼現率）＋櫃買中心（10 年期）┴─▶ 整理成 rates.json（只有這支程式會寫，Claude 不手填）

規則（資料誠實）：
  · 每條序列都記來源、網址、資料截至日；抓不到或對不起來 → points 留空，原因寫進 unavailable（以「待確認：」開頭）
  · 不估計、不內插、不從記憶補數字
  · 某條序列這次抓失敗：沿用上一次 rates.json 裡的那條（並在 unavailable 註明），全部失敗才讓整個流程紅燈

用法：
  python quant/scripts/fetch_rates.py            # 正式抓取、寫檔
  python quant/scripts/fetch_rates.py --probe    # 只試探來源：印出每個候選網址回應的前幾行（找台灣來源用）
"""
import csv
import io
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "rates.json"
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
SINCE = "1998-01-01"          # 顯示從 2000 年起，多留兩年才知道 2000 年初的利率水準與升降方向
UA = "Mozilla/5.0 (rates-weekly; +https://github.com/ZLO-25/Enterprise-Revenue-Dashboard)"


def http_get(url, timeout=60, tries=3):
    """抓文字網址（FRED、央行）。網路錯誤最多試 tries 次（失敗後等 2、4 秒）；最後一次還失敗就把錯誤丟出去。"""
    for i in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8-sig", errors="replace")
        except Exception:  # noqa: BLE001
            if i >= tries:
                raise
            time.sleep(2 * i)


def parse_fred_csv(text):
    """FRED 的 CSV：第一欄日期、第二欄數值；缺值是 '.' 或空白 → 跳過（不補）。"""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 2 or rows[0][0].strip().lower() not in ("observation_date", "date"):
        raise ValueError("不是預期的 FRED CSV 格式：" + (",".join(rows[0]) if rows else "空檔"))
    out = []
    for r in rows[1:]:
        if len(r) < 2:
            continue
        d, v = r[0].strip(), r[1].strip()
        if not v or v == ".":
            continue
        out.append((d, float(v)))
    out.sort()
    return out


def compress_changes(points, since=SINCE):
    """逐日資料 → 只留「數值有變動」的日期（階梯線）。
    第一筆 = since 之前最後一個水準（取 since 當天或之前最後一筆，若沒有則從 since 之後第一筆）。"""
    out, prev, started = [], None, False
    before = [p for p in points if p[0] < since]
    seq = ([before[-1]] if before else []) + [p for p in points if p[0] >= since]
    for d, v in seq:
        if prev is None or v != prev:
            out.append([d, v])
        prev = v
    return out


def month_end(points, since=SINCE):
    """逐日／逐週資料 → 每月最後一筆（檔案小一點）；since 之前的不要。"""
    last = {}
    for d, v in points:
        if d >= since:
            last[d[:7]] = (d, v)
    return [[d, v] for _, (d, v) in sorted(last.items())]


def stitch(old, new, cut):
    """old 用到 cut 之前、new 從 cut 起（FRED 的聯邦基金目標利率在 2008-12-16 換成區間，改用上限）。"""
    return [p for p in old if p[0] < cut] + [p for p in new if p[0] >= cut]


def series_meta(name, unit, source, url, points, through, **extra):
    """through＝原始資料最後一個有值的日期（「利率沒變」的日子也算；asOf 只是最後一次變動日）"""
    return {"name": name, "unit": unit, "source": source, "url": url,
            "asOf": points[-1][0] if points else None, "through": through, "points": points, **extra}


def fetch_us():
    unavailable, series = [], {}
    try:
        old = parse_fred_csv(http_get(FRED.format(id="DFEDTAR")))
        new = parse_fred_csv(http_get(FRED.format(id="DFEDTARU")))
        merged = stitch(old, new, "2008-12-16")
        pts = compress_changes(merged)
        series["us_policy"] = series_meta(
            "美國聯邦基金利率目標（上限）", "%",
            "FRED DFEDTAR（至 2008-12-15，單一目標）＋ DFEDTARU（2008-12-16 起，目標區間上限）",
            "https://fred.stlouisfed.org/series/DFEDTARU", pts, merged[-1][0], kind="changes")
    except Exception as e:  # noqa: BLE001
        unavailable.append(f"待確認：美國政策利率（FRED DFEDTAR/DFEDTARU）：抓取失敗（{type(e).__name__}: {e}）")
    try:
        raw = parse_fred_csv(http_get(FRED.format(id="DGS10")))
        pts = month_end(raw)
        series["us_10y"] = series_meta("美國 10 年期公債殖利率", "%", "FRED DGS10（每月最後一個有資料的日子）",
                                        "https://fred.stlouisfed.org/series/DGS10", pts, raw[-1][0], kind="monthly")
    except Exception as e:  # noqa: BLE001
        unavailable.append(f"待確認：美國 10 年期公債殖利率（FRED DGS10）：抓取失敗（{type(e).__name__}: {e}）")
    return series, unavailable


# ---- 台灣 ----
# 重貼現率：中央銀行「中央銀行利率」開放資料（政府資料開放平臺 dataset 10783），CSV 就是「每次調整的日期＋調整後利率」清單。
CBC_RATES_URL = "https://www.cbc.gov.tw/public/data/OpenData/%E7%B6%93%E7%A0%94%E8%99%95/EG28D01.csv"


def parse_cbc_rediscount(text):
    """央行 CSV：第一列 "日","重貼現(%)",…；之後每列 "YYYYMMDD","利率"。回傳 [(YYYY-MM-DD, 利率)]（依日期排序）。
    格式不符、日期不遞增、利率不在 0～20 之間 → 丟錯（寧可標待確認，也不收來路不明的數字）。"""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 2 or rows[0][0].strip() != "日" or "重貼現" not in rows[0][1]:
        raise ValueError("不是預期的央行利率 CSV 格式：" + (",".join(rows[0]) if rows else "空檔"))
    out = []
    for r in rows[1:]:
        if len(r) < 2 or not r[0].strip():
            continue
        d = r[0].strip()
        if len(d) != 8 or not d.isdigit():
            raise ValueError(f"日期格式不對：{d!r}")
        iso, v = f"{d[:4]}-{d[4:6]}-{d[6:]}", float(r[1])
        if not 0 < v < 20:
            raise ValueError(f"利率超出合理範圍：{iso} {v}")
        if out and iso <= out[-1][0]:
            raise ValueError(f"日期沒有遞增：{iso}")
        out.append((iso, v))
    if len(out) < 20:
        raise ValueError(f"資料列太少（{len(out)}）")
    return out


def fetch_tw():
    series, unavailable = {}, []
    try:
        rows = parse_cbc_rediscount(http_get(CBC_RATES_URL))
        pts = compress_changes(rows)
        # 官方清單列出「每一次」調整；清單最後一次調整之後利率沒變，所以資料截至日＝抓取日
        series["tw_policy"] = series_meta(
            "台灣中央銀行重貼現率", "%", "中央銀行「中央銀行利率」開放資料（EG28D01.csv，每次調整的日期與利率）",
            "https://data.gov.tw/dataset/10783", pts, datetime.now(timezone.utc).strftime("%Y-%m-%d"), kind="changes")
    except Exception as e:  # noqa: BLE001
        unavailable.append(f"待確認：台灣央行重貼現率：抓取失敗（{type(e).__name__}: {e}）")
    s10, u10 = fetch_tw_10y()
    series.update(s10)
    unavailable += u10
    return series, unavailable


# 10 年期：櫃買中心「債券等殖成交系統指標利率行情表」每日檔（BDdys100），10 年期指標公債的成交量加權平均殖利率。
# 網頁：https://www.tpex.org.tw/zh-tw/bond/info/statistics-gb/day/yield.html（殖利率曲線頁的資料也取自這份行情）
TPEX_10Y = "https://www.tpex.org.tw/storage/bond_zone/tradeinfo/govbond/{y}/{y}{m:02d}/BDdys100.{y}{m:02d}{d:02d}-C.xls"
TPEX_PAGE = "https://www.tpex.org.tw/zh-tw/bond/info/statistics-gb/day/yield.html"


def http_bytes(url, timeout=40):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def parse_tpex_10y(rows):
    """BDdys100 的工作表（list of rows）→ (指標公債代號, 平均殖利率)。
    找「到期年限」那一欄＝10 的列，第 2 欄是代號、第 3 欄是平均殖利率(%)。
    表頭不像、代號不是 A 開頭（中央政府公債）、殖利率不在 0～15 → 丟錯。"""
    head = " ".join(str(c) for r in rows[:5] for c in r)
    if "指標" not in head or "殖利率" not in head:
        raise ValueError("不是預期的櫃買中心指標利率行情表")
    for r in rows:
        try:
            yrs = float(str(r[0]).strip())
        except (ValueError, IndexError):
            continue
        if yrs == 10:
            code, v = str(r[1]).strip(), float(r[2])
            if not code.startswith("A"):
                raise ValueError(f"10 年期指標公債代號不對：{code!r}")
            if not 0 < v < 15:
                raise ValueError(f"殖利率超出合理範圍：{v}")
            return code, v
    raise ValueError("表內沒有 10 年期那一列")


def tpex_month_end(y, m):
    """某月最後一個有行情表的營業日 → (日期, 代號, 殖利率)；整個月最後 15 天都沒有檔 → None。
    櫃買中心找不到檔時回 HTTP 200 + HTML 404 頁，所以看檔頭是不是 Excel（d0cf11e0）。"""
    import calendar
    import xlrd
    last = calendar.monthrange(y, m)[1]
    for d in range(last, max(last - 15, 0), -1):
        dt = datetime(y, m, d)
        if dt.weekday() >= 5 or dt > datetime.now():
            continue
        b = None
        for attempt in range(3):
            try:
                b = http_bytes(TPEX_10Y.format(y=y, m=m, d=d))
                break
            except Exception:  # noqa: BLE001  網路錯誤 → 重試；連三次失敗才當作沒有檔
                time.sleep(2 * (attempt + 1))
        time.sleep(0.25)
        if not b or b[:4] != b"\xd0\xcf\x11\xe0":
            continue
        sh = xlrd.open_workbook(file_contents=b).sheet_by_index(0)
        rows = [[c.value for c in sh.row(i)] for i in range(sh.nrows)]
        code, v = parse_tpex_10y(rows)
        return dt.strftime("%Y-%m-%d"), code, v
    return None


def fetch_tw_10y(prev=None):
    """每月最後一個營業日的 10 年期指標公債殖利率。已抓過的月份沿用 rates.json（官方過去的行情不會變），
    只重抓最近 2 個月與缺的月份；往前抓到連續 6 個月都沒有檔就停（櫃買中心網站上的資料起點）。"""
    if prev is None:
        prev = {}
        if OUT.exists():
            prev = json.loads(OUT.read_text(encoding="utf8")).get("series", {}).get("tw_10y", {})
    try:
        import xlrd  # noqa: F401
    except ImportError:
        return {}, ["待確認：台灣 10 年期公債殖利率：執行環境沒有 xlrd，讀不了櫃買中心 .xls"]
    have = {p[0][:7]: p for p in prev.get("points", [])}
    now = datetime.now()
    y, m = now.year, now.month
    recent = {f"{y}-{m:02d}", f"{y - (m == 1)}-{(m - 2) % 12 + 1:02d}"}
    pts, empty, codes, errs = [], 0, set(), []
    while f"{y}-{m:02d}" >= SINCE[:7]:
        key = f"{y}-{m:02d}"
        if key in have and key not in recent:
            pts.append(have[key]); empty = 0
        else:
            try:
                r = tpex_month_end(y, m)
            except Exception as e:  # noqa: BLE001
                r = None
                errs.append(f"{key}（{type(e).__name__}: {e}）")
            if r:
                pts.append([r[0], r[2]]); codes.add(r[1]); empty = 0
            else:
                empty += 1
                if empty >= 6:
                    break
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)
    pts.sort()
    un = []
    if errs:
        un.append("待確認：台灣 10 年期公債殖利率以下月份讀檔失敗、沒有收：" + "、".join(errs[:12]))
    if not pts:
        return {}, un + ["待確認：台灣 10 年期公債殖利率：櫃買中心行情表一個月都沒抓到"]
    if pts[0][0] > "2000-01-31":
        un.append(f"待確認：台灣 10 年期公債殖利率 {pts[0][0][:7]} 以前：櫃買中心網站上沒有更早的指標利率行情表，沒有收（不估計）")
    gaps = []
    for a, b in zip(pts, pts[1:]):
        ya, ma = int(a[0][:4]), int(a[0][5:7])
        nxt = f"{ya + (ma == 12)}-{ma % 12 + 1:02d}"
        if b[0][:7] != nxt:
            gaps.append(f"{nxt}～{b[0][:7]}")
    if gaps:
        un.append("待確認：台灣 10 年期公債殖利率以下月份沒有行情表：" + "、".join(gaps[:12]))
    s = series_meta("台灣 10 年期公債殖利率", "%",
                    "櫃買中心「債券等殖成交系統指標利率行情表」（BDdys100），10 年期指標公債的成交量加權平均殖利率，每月最後一個營業日；"
                    "當天沒有成交時，櫃買中心沿用該券最近成交日的平均殖利率",
                    TPEX_PAGE, pts, pts[-1][0], kind="monthly")
    return {"tw_10y": s}, un


def probe_xls(url):
    """櫃買中心每日 .xls：印出大小、檔頭，能用 xlrd 讀就印出前 25 列"""
    print(f"\n===== {url}")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=40) as r:
            b, ct = r.read(), r.headers.get("Content-Type")
    except Exception as e:  # noqa: BLE001
        print(f"失敗：{type(e).__name__}: {e}")
        return
    print(f"{len(b)} bytes, Content-Type={ct}, 檔頭={b[:8].hex()}")
    try:
        import xlrd
        book = xlrd.open_workbook(file_contents=b)
        for sh in book.sheets()[:2]:
            print(f"  [工作表 {sh.name}] {sh.nrows} 列 x {sh.ncols} 欄")
            for i in range(min(sh.nrows, 25)):
                print("   ", [str(c.value)[:18] for c in sh.row(i)][:12])
    except Exception as e:  # noqa: BLE001
        print(f"  xlrd 讀不了：{type(e).__name__}: {e}；前 300 字：{b[:300]!r}")


def probe():
    """台灣來源試探：每個網址印出標題、疑似下載連結、含「重貼現」或「公債」的文字行（只在 Actions 上跑，用來找官方資料來源）"""
    import re
    tp = "https://www.tpex.org.tw/storage/bond_zone/tradeinfo/govbond/{y}/{y}{m}/{f}.{y}{m}{d}-C.xls"
    for y, m, d in (("2026", "11", "13"), ("2026", "10", "30"), ("2015", "06", "30"), ("2006", "01", "27"), ("2005", "12", "30")):
        for f in ("Curve", "BDdys100", "BDdys01a"):
            probe_xls(tp.format(y=y, m=m, d=d, f=f))
    urls = [
        "https://www.tpex.org.tw/zh-tw/bond/info/statistics-gb/day/yield.html",
    ]
    for url in urls:
        print(f"\n===== {url}")
        try:
            text = http_get(url, timeout=40)
        except Exception as e:  # noqa: BLE001
            print(f"失敗：{type(e).__name__}: {e}")
            continue
        if url.endswith(".csv"):
            lines = text.splitlines()
            print(f"CSV 共 {len(lines)} 行；前 6 行與最後 6 行：")
            for l in lines[:6] + ["..."] + lines[-6:]:
                print("  ", l[:300])
            continue
        t = re.search(r"<title>(.*?)</title>", text, re.S)
        print("標題：", (t.group(1).strip() if t else "?")[:120], f"[{len(text)} chars]")
        links = sorted(set(re.findall(r"""(?:href|src|data-[a-z-]+)=["']([^"']*(?:csv|json|xml|download|api|odata|\.xls|file)[^"']*)["']""", text, re.I)))
        print("疑似下載/API 連結：", len(links))
        for l in links[:30]:
            print("  ", l[:200])
        plain = re.sub(r"<[^>]+>", "\n", text)
        hits = [x.strip() for x in plain.splitlines() if re.search("重貼現|公債|殖利率|rediscount", x) and x.strip()]
        print("相關文字行：", len(hits))
        for h in hits[:15]:
            print("  ", h[:200])


def main():
    if "--probe" in sys.argv:
        probe()
        return 0
    prev = {}
    if OUT.exists():
        prev = json.loads(OUT.read_text(encoding="utf8")).get("series", {})
    series, unavailable = {}, []
    for fn in (fetch_us, fetch_tw):
        s, u = fn()
        series.update(s)
        unavailable += u
    # 這次沒抓到的序列：沿用上一次的（若有），並註明
    for key in ("us_policy", "us_10y", "tw_policy", "tw_10y"):
        if key not in series and prev.get(key, {}).get("points"):
            series[key] = prev[key]
            unavailable.append(f"待確認：{key} 這次抓取失敗，沿用 {prev[key].get('asOf')} 的舊資料")
    if not any(s.get("points") for s in series.values()):
        print("所有序列都沒有資料", file=sys.stderr)
        return 1
    for k, s in series.items():
        print(k, len(s["points"]), "筆，最後一筆", s["points"][-1] if s["points"] else None)
    doc = {"updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "since": SINCE,
           "series": series, "unavailable": unavailable}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf8")
    for u in unavailable:
        print(u)
    return 0


if __name__ == "__main__":
    sys.exit(main())
