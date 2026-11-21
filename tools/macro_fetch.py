"""總經儀表板的資料：抓官方來源 → data/macro/latest.json。只由 GitHub Actions（macro-weekly）執行，不經過 Claude。

  data/macro/config.json（指標清單，Claude 維護）
        │
        ▼
  FRED（美國聖路易聯準銀行，免金鑰 CSV）──┐
  國發會景氣指標查詢系統（台灣景氣燈號）──┴─▶ 整理、算年增率與方向燈 ─▶ data/macro/latest.json

規則（資料誠實，和網站其他地方一樣）：
  · 每條序列都記來源網址與資料截至日；不估計、不內插、不從記憶補數字
  · 某條序列這次抓失敗：沿用上一次 latest.json 裡的那條，並在 unavailable 寫「待確認：」說明；從沒抓到過就留空
  · 年增率、方向燈都是這支程式用公式算的（唯一計算處），頁面只畫不算

用法：
  python3 tools/macro_fetch.py            正式抓取、寫檔（全部序列都失敗才回傳非 0）
  python3 tools/macro_fetch.py --check    只看 latest.json 是不是 5 天內抓過（寫 stale=true/false 到 $GITHUB_OUTPUT）
  python3 tools/macro_fetch.py --probe    只試探台灣來源、印出回應（找官方資料網址用，不寫檔）
"""
import csv
import io
import json
import math
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, "data", "macro", "config.json")
OUT = os.path.join(ROOT, "data", "macro", "latest.json")
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}"
FRED_PAGE = "https://fred.stlouisfed.org/series/{id}"
UA = "Mozilla/5.0 (macro-weekly; +https://github.com/ZLO-25/Enterprise-Revenue-Dashboard)"
STALE_DAYS = 5


def http_get(url, timeout=60, tries=3, data=None, headers=None):
    """抓一個網址（文字）。網路錯誤重試；最後一次還失敗就把錯誤丟出去，由呼叫的人決定怎麼標示。"""
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers=dict({"User-Agent": UA}, **(headers or {})))
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8-sig", errors="replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise last


# ---------------------------------------------------------------- FRED 解析與換算（純函式，tools/tests/test_macro.py 有測）

def parse_fred_csv(text):
    """FRED 的 CSV：第一欄日期、第二欄數值；缺值是 '.' 或空白 → 跳過（不補）。回傳 [(YYYY-MM-DD, float)]（依日期排序）。"""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or len(rows[0]) < 2 or rows[0][0].strip().lower() not in ("observation_date", "date"):
        raise ValueError("不是預期的 FRED CSV 格式：" + (",".join(rows[0])[:80] if rows else "空檔"))
    out = []
    for r in rows[1:]:
        if len(r) < 2:
            continue
        d, v = r[0].strip(), r[1].strip()
        if not v or v == ".":
            continue
        out.append((d, float(v)))
    out.sort()
    if not out:
        raise ValueError("FRED CSV 沒有任何有值的資料列")
    return out


def _days(a, b):
    return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days


def detect_freq(points):
    """看最近幾筆的日期間隔判斷頻率：d 每日、w 每週、m 每月、q 每季。"""
    tail = points[-13:]
    gaps = sorted(_days(a[0], b[0]) for a, b in zip(tail, tail[1:]))
    if not gaps:
        return "m"
    g = gaps[len(gaps) // 2]
    return "d" if g <= 4 else "w" if g <= 10 else "m" if g <= 45 else "q"


def month_last(points):
    """每日／每週資料 → 每月最後一筆（日期保留那一筆真正的日期，所以最新的月份就是最新一筆）。"""
    last = {}
    for d, v in points:
        last[d[:7]] = (d, v)
    return [last[k] for k in sorted(last)]


def to_yoy(points):
    """年增率（%）：和「去年同一個月」那一筆比。找不到去年同月、或去年是 0 → 那一期不算（不補）。"""
    by = {d[:7]: v for d, v in points}
    out = []
    for d, v in points:
        prev = by.get(f"{int(d[:4]) - 1}{d[4:7]}")
        if prev is None or prev == 0:
            continue
        out.append((d, (v / prev - 1) * 100))
    return out


def to_chg(points):
    """和上一期的差（例如非農就業每月增減）。"""
    return [(b[0], b[1] - a[1]) for a, b in zip(points, points[1:])]


def transform(raw, show):
    """原始序列 → (頻率, 要畫的序列, 降到每月後的原始序列)。每日／每週一律先降成每月最後一筆。"""
    freq = detect_freq(raw)
    base = month_last(raw) if freq in ("d", "w") else list(raw)
    if show == "yoy":
        pts = to_yoy(base)
    elif show == "chg":
        pts = to_chg(base)
    elif show == "level":
        pts = base
    else:
        raise ValueError(f"不認得的 show：{show!r}")
    return freq, pts, base


def stats(points, freq, bad):
    """方向燈與幾個事實（全部是公式）。
      半年變動 chg ＝ 最新值 − 半年前的值（月資料往前 6 筆，季資料往前 2 筆）
      sd          ＝ 過去 10 年「每一個半年變動」的標準差（這個指標平常半年會動多少）
      z = chg ÷ sd：|z| < 1 → 持平（flat）；≥ 1 且往 bad 的方向 → 轉差（worse）；反方向 → 轉好（better）
      bad 是空白的指標（沒有固定好壞方向）不亮燈（light = None）
      另外給三年高低點（看「創新低」「右端翹起」用）與最新值在過去 10 年的百分位。"""
    if not points:
        return None
    step, yr = (2, 4) if freq == "q" else (6, 12)
    vals = [v for _, v in points]
    last_d, last = points[-1]
    out = {"last": last, "lastDate": last_d}
    if len(vals) > step:
        out["prev"], out["prevDate"], out["chg"] = vals[-1 - step], points[-1 - step][0], last - vals[-1 - step]
        win = vals[-(10 * yr + step):]
        diffs = [b - a for a, b in zip(win, win[step:])]
        if len(diffs) >= 2 * yr:      # 至少兩年的樣本才算標準差
            mean = sum(diffs) / len(diffs)
            sd = math.sqrt(sum((x - mean) ** 2 for x in diffs) / (len(diffs) - 1))
            if sd > 0:
                z = out["chg"] / sd
                out["sd"], out["z"] = sd, z
                if bad in ("up", "down"):
                    worse = z >= 1 if bad == "up" else z <= -1
                    better = z <= -1 if bad == "up" else z >= 1
                    out["light"] = "worse" if worse else "better" if better else "flat"
    w3 = points[-3 * yr:]
    hi, lo = max(w3, key=lambda p: p[1]), min(w3, key=lambda p: p[1])
    out.update(hi3=hi[1], hi3Date=hi[0], lo3=lo[1], lo3Date=lo[0])
    w10 = vals[-10 * yr:]
    if len(w10) >= 2 * yr:
        out["pct10"] = round(100 * sum(1 for v in w10 if v <= last) / len(w10))
    return out


def recession_ranges(points):
    """FRED 的 USREC（1＝NBER 認定的衰退月份）→ [[開始月, 結束月], …]，畫圖時當灰底。"""
    out, start, prev = [], None, None
    for d, v in points:
        if v >= 0.5 and start is None:
            start = d
        if v < 0.5 and start is not None:
            out.append([start[:7], prev[:7]])
            start = None
        prev = d
    if start is not None:
        out.append([start[:7], prev[:7]])
    return out


def rnd(v, digits):
    return round(v, max(digits, 0) + 2)


def build_series(spec, raw, since):
    """一條設定 + 原始資料 → 寫進 latest.json 的那一塊。"""
    freq, pts, base = transform(raw, spec["show"])
    st = stats(pts, freq, spec.get("bad") or "")
    digits = spec.get("digits", 1)
    for k in ("last", "prev", "chg", "sd", "z", "hi3", "lo3"):
        if st and k in st:
            st[k] = rnd(st[k], digits)
    out = {"freq": freq, "through": raw[-1][0], "stats": st,
           "points": [[d, rnd(v, digits)] for d, v in pts if d >= since]}
    if spec["show"] != "level":
        out["rawLast"] = [base[-1][0], base[-1][1]]      # 年增率／增減的指標，另外附上原始水準（頁面顯示在小字）
    return out


# ---------------------------------------------------------------- 台灣：國發會景氣指標查詢系統

NDC_PAGE = "https://index.ndc.gov.tw/n/zh_tw/data/eco"
NDC_API = "https://index.ndc.gov.tw/n/json/data/eco/indicators"


def probe():
    """台灣來源試探：只在 Actions 上跑，把每個候選網址的回應印出來，用來確認官方資料的網址與格式。"""
    import re
    cands = [
        ("POST", NDC_API), ("GET", NDC_API),
        ("GET", "https://data.gov.tw/api/v2/rest/dataset/6099"),
        ("GET", "https://data.gov.tw/api/v2/rest/dataset/6100"),
        ("GET", "https://data.gov.tw/api/v2/rest/dataset/31564"),
        ("GET", NDC_PAGE),
    ]
    for method, url in cands:
        print(f"\n===== {method} {url}")
        try:
            text = http_get(url, timeout=40, tries=1, data=(b"" if method == "POST" else None),
                            headers={"Accept": "application/json, text/plain, */*", "Referer": NDC_PAGE,
                                     "X-Requested-With": "XMLHttpRequest"})
        except Exception as e:  # noqa: BLE001
            print(f"失敗：{type(e).__name__}: {e}")
            continue
        print(f"[{len(text)} chars] 前 1500 字：")
        print(text[:1500])
        if text.lstrip().startswith("{") or text.lstrip().startswith("["):
            try:
                j = json.loads(text)
                describe(j, "  ")
            except Exception as e:  # noqa: BLE001
                print(f"  不是合法 JSON：{e}")
        else:
            links = sorted(set(re.findall(r"""["']([^"']*(?:json|\.js|csv|zip|Download)[^"']*)["']""", text)))
            print("疑似資料／程式連結：", len(links))
            for l in links[:60]:
                print("  ", l[:200])


def describe(j, pad, depth=0):
    """把 JSON 的結構印出來（鍵、型別、清單長度與頭尾），找欄位用。"""
    if depth > 4:
        return
    if isinstance(j, dict):
        for k, v in list(j.items())[:40]:
            kind = type(v).__name__ + (f"[{len(v)}]" if isinstance(v, (list, dict, str)) else "")
            brief = "" if isinstance(v, (dict, list)) else " = " + repr(v)[:120]
            print(f"{pad}{k}: {kind}{brief}")
            describe(v, pad + "  ", depth + 1)
    elif isinstance(j, list) and j:
        print(f"{pad}[0] {repr(j[0])[:300]}")
        print(f"{pad}[-1] {repr(j[-1])[:300]}")
        if isinstance(j[0], (dict, list)):
            describe(j[0], pad + "  ", depth + 1)


def fetch_tw():
    """台灣景氣燈號：來源格式確認前先回空，並標待確認（不猜格式、不填數字）。"""
    return None, ["待確認：台灣景氣對策信號（國發會）：官方資料檔的網址與格式尚未確認，先只放外部連結"]


# ---------------------------------------------------------------- 主流程

def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf8") as f:
        return json.load(f)


def is_stale(doc, now=None):
    if not doc or not doc.get("updated"):
        return True
    now = now or datetime.now(timezone.utc)
    age = now - datetime.strptime(doc["updated"], "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
    return age.days >= STALE_DAYS


def main(argv):
    if "--probe" in argv:
        probe()
        return 0
    prev = load_json(OUT, {}) or {}
    if "--check" in argv:
        stale = is_stale(prev)
        print("stale=" + ("true" if stale else "false"))
        gh = os.environ.get("GITHUB_OUTPUT")
        if gh:
            with open(gh, "a", encoding="utf8") as f:
                f.write("stale=" + ("true" if stale else "false") + "\n")
        return 0
    cfg = load_json(CFG)
    since = cfg.get("since", "1990-01-01")
    series, unavailable, ok = {}, [], 0
    specs = [s for g in cfg["groups"] for s in g["series"]]
    for spec in specs:
        key, fid = spec["key"], spec["fred"]
        try:
            raw = parse_fred_csv(http_get(FRED_CSV.format(id=fid)))
            series[key] = dict(build_series(spec, raw, since), fred=fid, url=FRED_PAGE.format(id=fid))
            ok += 1
            s = series[key]
            print(f"{key:8s} {fid:18s} {s['freq']} {len(s['points']):4d} 筆，最新 {s['stats']['lastDate']} = {s['stats']['last']}"
                  f"（{(s['stats'] or {}).get('light') or '不亮燈'}）")
        except Exception as e:  # noqa: BLE001
            old = (prev.get("series") or {}).get(key)
            if old and old.get("points"):
                series[key] = old
                unavailable.append(f"待確認：{spec['name']}（FRED {fid}）這次抓取失敗，沿用資料截至 {old.get('through')} 的舊資料（{type(e).__name__}: {e}）")
            else:
                unavailable.append(f"待確認：{spec['name']}（FRED {fid}）：抓不到資料，沒有顯示（{type(e).__name__}: {e}）")
            print(f"{key:8s} {fid:18s} 失敗：{type(e).__name__}: {e}")
        time.sleep(0.4)
    recessions = prev.get("recessions") or []
    rid = cfg.get("recession")
    if rid:
        try:
            recessions = [r for r in recession_ranges(parse_fred_csv(http_get(FRED_CSV.format(id=rid)))) if r[1] >= since[:7]]
        except Exception as e:  # noqa: BLE001
            unavailable.append(f"待確認：衰退期間灰底（FRED {rid}）這次抓取失敗，沿用舊的（{type(e).__name__}: {e}）")
    tw, tw_un = fetch_tw()
    if tw is None and prev.get("tw"):
        tw = prev["tw"]
    unavailable += tw_un
    if ok == 0:
        print("所有 FRED 序列都抓不到，不寫檔", file=sys.stderr)
        return 1
    doc = {"version": 1, "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "since": since,
           "series": series, "recessions": recessions, "tw": tw, "unavailable": unavailable}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n寫入 data/macro/latest.json：{ok}/{len(specs)} 條成功")
    for u in unavailable:
        print(u)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
