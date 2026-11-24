"""總經儀表板的資料：抓官方來源 → data/macro/latest.json。只由 GitHub Actions（macro-weekly）執行，不經過 Claude。

  data/macro/config.json（指標清單，Claude 維護）
        │
        ▼
  FRED（美國聖路易聯準銀行，免金鑰 CSV）──┐
  國發會景氣指標查詢系統（台灣景氣燈號）──┴─▶ 整理、算年增率與方向燈 ─▶ data/macro/latest.json

規則（資料誠實，和網站其他地方一樣）：
  · 每條序列都記來源網址與資料截至日；不估計、不內插、不從記憶補數字
  · 某條序列這次抓失敗：沿用上一次 latest.json 裡的那條，並在 unavailable 寫「待確認：」說明；從沒抓到過就留空
  · 年增率、方向燈、警訊計數、觀念提醒有沒有成立，都是這支程式用公式算的（唯一計算處），頁面只畫不算
  · 長期運作：每條序列「多久沒有新資料」也在這裡算（health.stale），外部連結每次順便連一次（links.dead）；
    tools/status.py 讀這兩塊，在「系統健康」頁亮燈

用法：
  python3 tools/macro_fetch.py            正式抓取、寫檔（全部序列都失敗才回傳非 0）
  python3 tools/macro_fetch.py --check    只看 latest.json 是不是 18 小時內抓過（寫 stale=true/false 到 $GITHUB_OUTPUT）
  python3 tools/macro_fetch.py --probe    只試探：印出台灣官方資料檔的頭尾幾行、檢查外部連結有沒有失效（不寫檔）
"""
import csv
import io
import json
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
STALE_HOURS = 18        # 這麼多小時內抓過就不重抓：daily-prep 平日每天叫醒一次 → 等於平日每天抓一次（VIX、利差、殖利率等日資料才不會落後好幾天）


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


def to_ann(points, n=3):
    """n 個月的變動換算成年率（%）：(現在 ÷ n 個月前) ^ (12 ÷ n) − 1。比年增率更早看到轉折，但也更容易跳動。"""
    out = []
    for a, b in zip(points, points[n:]):
        if a[1] > 0 and b[1] > 0:
            out.append((b[0], ((b[1] / a[1]) ** (12 / n) - 1) * 100))
    return out


def ratio_points(num, den, mult=1.0):
    """兩條序列相除（例如 股票市值 ÷ GDP）。den 是季資料（日期＝季初）；每一季取 num 在那一季裡最後一筆（num 也是季資料時就是同一筆）。
    那一季 num 沒有資料、或 den 是 0 → 那一季不算（不補）。"""
    by = {}
    for d, v in num:
        by[d[:7]] = v
    out = []
    for d, v in den:
        y, m, nv = int(d[:4]), int(d[5:7]), None
        for k in (2, 1, 0):
            mm = m + k
            key = f"{y + (mm - 1) // 12}-{(mm - 1) % 12 + 1:02d}"
            if key in by:
                nv = by[key]
                break
        if nv is None or v == 0:
            continue
        out.append((d, nv / v * mult))
    return out


def diff_points(a, b):
    """兩條已經算好的序列相減（例如 商品消費年增率 − 服務消費年增率），只算兩邊同一個月都有值的。"""
    bm = {d[:7]: v for d, v in b}
    return [(d, v - bm[d[:7]]) for d, v in a if d[:7] in bm]


def combo_points(parts):
    """幾條 FRED 序列加權相加（例如 淨流動性＝聯準會資產 − 逆回購×1000 − 財政部帳戶）。parts＝[(原始序列, 倍數)]。
    每條先降成每月最後一筆，只算「每一條那個月都有值」的月份（不補）；日期用第一條那一筆的真正日期。"""
    ms = [({d[:7]: (d, v) for d, v in month_last(pts)}, mult) for pts, mult in parts]
    out = []
    for ym in sorted(ms[0][0]):
        if all(ym in m for m, _ in ms):
            out.append((ms[0][0][ym][0], sum(m[ym][1] * k for m, k in ms)))
    return out


def transform(raw, show):
    """原始序列 → (頻率, 要畫的序列, 降到每月後的原始序列)。每日／每週一律先降成每月最後一筆。"""
    freq = detect_freq(raw)
    base = month_last(raw) if freq in ("d", "w") else list(raw)
    if show == "yoy":
        pts = to_yoy(base)
    elif show == "chg":
        pts = to_chg(base)
    elif show == "ann3":
        if freq == "q":
            raise ValueError("ann3（三個月年率）只能用在月資料")
        pts = to_ann(base, 3)
    elif show == "level":
        pts = base
    else:
        raise ValueError(f"不認得的 show：{show!r}")
    return freq, pts, base


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def robust_sd(xs):
    """不怕極端值的「平常幅度」：MAD（和中位數的距離的中位數）× 1.4826。"""
    m = median(xs)
    return 1.4826 * median([abs(x - m) for x in xs])


def light_name(z, bad, thr):
    if bad not in ("up", "down") or z is None:
        return None
    worse = z >= thr if bad == "up" else z <= -thr
    better = z <= -thr if bad == "up" else z >= thr
    return "worse" if worse else "better" if better else "flat"


def z_at(vals, i, freq, years=10):
    """第 i 筆的 (半年變動, 平常幅度, z)。只用第 i 筆（含）以前的資料，所以可以拿來回算歷史上每個月當時的燈。算不出來回傳 None。"""
    step, yr = (2, 4) if freq == "q" else (6, 12)
    if i < step:
        return None
    chg = vals[i] - vals[i - step]
    win = vals[max(0, i + 1 - (years * yr + step)):i + 1]
    diffs = [b - a for a, b in zip(win, win[step:])]
    if len(diffs) < 2 * yr:      # 至少兩年的樣本才算
        return chg, None, None
    sd = robust_sd(diffs)
    if sd <= 0:
        return chg, None, None
    return chg, sd, chg / sd


def light_series(points, freq, bad, thr=1.0, years=10):
    """每一筆資料當時的燈：[(日期, worse／flat／better)]。和 stats() 用同一個公式（z_at），只是往回每一筆都算。"""
    if bad not in ("up", "down"):
        return []
    vals, out = [v for _, v in points], []
    for i in range(len(points)):
        r = z_at(vals, i, freq, years)
        if r and r[2] is not None:
            out.append((points[i][0], light_name(r[2], bad, thr)))
    return out


def stats(points, freq, bad, thr=1.0, years=10):
    """方向燈與幾個事實（全部是公式）。
      半年變動 chg ＝ 最新值 − 半年前的值（月資料往前 6 筆，季資料往前 2 筆）
      sd          ＝ 過去 10 年「每一個半年變動」平常的幅度。用中位數算（MAD × 1.4826，常態分布下等於標準差），
                    不用一般的標準差：2020 年疫情那種極端值會把標準差拉到很大，之後十年燈都不會亮
      z = chg ÷ sd：|z| < 門檻 → 持平（flat）；≥ 門檻且往 bad 的方向 → 轉差（worse）；反方向 → 轉好（better）
      門檻 thr 與回看年數 years 寫在 config.json 的 light（預設 1 倍、10 年）
      bad 是空白的指標（沒有固定好壞方向）不亮燈（light = None）
      lightSince／lightPrev：現在這個燈從哪一筆資料開始亮、之前是什麼燈（頁面「最近的燈號變化」用）
      另外給三年高低點與離高低點多遠（看「創新低」「右端翹起」用），以及最新值在過去 10 年的百分位。"""
    if not points:
        return None
    step, yr = (2, 4) if freq == "q" else (6, 12)
    vals = [v for _, v in points]
    last_d, last = points[-1]
    out = {"last": last, "lastDate": last_d}
    r = z_at(vals, len(vals) - 1, freq, years)
    if r:
        out["prev"], out["prevDate"], out["chg"] = vals[-1 - step], points[-1 - step][0], r[0]
        if r[2] is not None:
            out["sd"], out["z"] = r[1], r[2]
            light = light_name(r[2], bad, thr)
            if light:
                out["light"] = light
                hist = light_series(points[-(years * yr + step + 3 * yr):], freq, bad, thr, years)
                since, prev = last_d, None
                for d, l in reversed(hist):
                    if l != light:
                        prev = l
                        break
                    since = d
                out["lightSince"] = since
                if prev:
                    out["lightPrev"] = prev
    w3 = points[-3 * yr:]
    hi, lo = max(w3, key=lambda p: p[1]), min(w3, key=lambda p: p[1])
    out.update(hi3=hi[1], hi3Date=hi[0], lo3=lo[1], lo3Date=lo[0])
    if lo[1] > 0:      # 現在比三年低點高多少 %、比三年高點低多少 %（只有正數的序列才有意義；年增率這類會跨 0 的不算）
        out["fromLo3"], out["fromHi3"] = round((last / lo[1] - 1) * 100, 1), round((last / hi[1] - 1) * 100, 1)
    w10 = vals[-10 * yr:]
    if len(w10) >= 2 * yr:
        out["pct10"] = round(100 * sum(1 for v in w10 if v <= last) / len(w10))
    return out


def base_effect(pts, freq):
    """基期：年增率是和去年同期比，所以「去年同期的年增率」特別高或特別低，今年的年增率就容易被拉低或墊高。
    回傳 (去年同期的年增率, 它在過去 10 年年增率裡的百分位)；資料不夠回傳 None。"""
    yr = 4 if freq == "q" else 12
    if len(pts) <= yr + 2 * yr:
        return None
    base = pts[-1 - yr][1]
    w10 = [v for _, v in pts[-10 * yr:]]
    return base, round(100 * sum(1 for v in w10 if v <= base) / len(w10))


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


def build_series(spec, raw, since, light=None, keep_lights=None):
    """一條設定 + 原始資料 → 寫進 latest.json 的那一塊。light＝config 的 light（門檻、年數）；
    keep_lights 給一個 dict 的話，順便把這條序列歷史上每一筆的燈放進去（警訊計數回算用，不寫進檔案）。"""
    light = light or {}
    thr, years = light.get("threshold", 1.0), light.get("years", 10)
    freq, pts, base = transform(raw, spec["show"])
    bad = spec.get("bad") or ""
    st = stats(pts, freq, bad, thr, years)
    digits = spec.get("digits", 1)
    for k in ("last", "prev", "chg", "sd", "z", "hi3", "lo3"):
        if st and k in st:
            st[k] = rnd(st[k], digits)
    if st and spec["show"] == "yoy":
        be = base_effect(pts, freq)
        if be:
            st["baseYoy"], st["basePct10"] = rnd(be[0], digits), be[1]
    if st and spec.get("run"):      # 連續上升／下降了幾期（書摘的「連續 5 季下修」這類門檻用）
        st["downRun"], st["upRun"] = run_len(pts, -1), run_len(pts, 1)
    if keep_lights is not None and bad:
        keep_lights[spec["key"]] = light_series(pts, freq, bad, thr, years)
    out = {"freq": freq, "through": raw[-1][0], "stats": st,
           "points": [[d, rnd(v, digits)] for d, v in pts if d >= since]}
    if spec["show"] != "level":
        out["rawLast"] = [base[-1][0], base[-1][1]]      # 年增率／增減的指標，另外附上原始水準（頁面顯示在小字）
    return out


def run_len(pts, sign):
    """最新一筆往回數，連續上升（sign=1）或下降（sign=-1）了幾期。"""
    n = 0
    for a, b in zip(reversed(pts[:-1]), reversed(pts[1:])):
        if (b[1] - a[1]) * sign > 0:
            n += 1
        else:
            break
    return n


# ---------------------------------------------------------------- 警訊計數（回算歷史）、觀念提醒、長期運作的健康檢查

def month_add(ym, n):
    y, m = int(ym[:4]), int(ym[5:7]) + n
    return f"{y + (m - 1) // 12}-{(m - 1) % 12 + 1:02d}"


def score_series(lights, checks, start, end, carry=4):
    """把每條序列歷史上的燈，排成「每個月有幾個燈轉差」。
      lights：{key: [(日期, 燈)]}；checks：[[key, …], …]（書裡的「榮景期尾聲七大指標」，一項裡任何一條轉差就算這一項亮）
      每個月用「那個月（含）以前、最近 carry 個月內」的最新一筆（季資料、公布較慢的資料才不會漏掉）
    注意：這是用今天看到的（修正後的）資料、照資料所屬月份回算，沒有扣掉公布落後；當時的人看到的數字可能不同。"""
    maps = {k: {d[:7]: l for d, l in v} for k, v in lights.items()}
    months, m = [], start
    while m <= end:
        months.append(m)
        m = month_add(m, 1)

    def at(key, ym):
        mp = maps.get(key) or {}
        for back in range(carry):
            l = mp.get(month_add(ym, -back))
            if l:
                return l
        return None

    out = {"months": months, "worse": [], "better": [], "n": [], "boom": []}
    for ym in months:
        ls = {k: at(k, ym) for k in maps}
        have = [l for l in ls.values() if l]
        out["n"].append(len(have))
        out["worse"].append(sum(1 for l in have if l == "worse"))
        out["better"].append(sum(1 for l in have if l == "better"))
        out["boom"].append(sum(1 for c in checks if any(ls.get(k) == "worse" for k in c)))
    return out


def score_table(score, recessions, items):
    """警訊計數有沒有用，攤開來看：每次衰退開始前 12 個月，七項裡最多同時亮幾項；以及亮 k 項的月份，各落在哪一種時期。"""
    idx = {m: i for i, m in enumerate(score["months"])}
    kind = ["other"] * len(score["months"])
    rows = []
    for a, b in recessions:
        if a not in idx:
            continue
        i0 = idx[a]
        for i in range(max(0, i0 - 12), i0):
            kind[i] = "pre"
        for i in range(i0, idx.get(b, len(kind) - 1) + 1):
            kind[i] = "rec"
        pre = score["boom"][max(0, i0 - 12):i0]
        rows.append({"start": a, "end": b, "preMax": max(pre) if pre else None, "atStart": score["boom"][i0]})
    dist = {k: [0] * (items + 1) for k in ("pre", "rec", "other")}
    for i, k in enumerate(kind):
        dist[k][min(score["boom"][i], items)] += 1
    return {"recessions": rows, "dist": dist}


def eval_cond(c, S, tw=None, boom=None):
    """觀念提醒的條件（寫在 config.json 的 reminders[].when）。S＝{key: 那條序列的 stats}。資料缺的條件一律算「不成立」。
      {"key":k,"light":"worse"}            那個指標現在的燈
      {"key":k,"lt":x}／{"key":k,"gt":x}    最新值小於／大於 x
      {"key":k,"downRun":n}／{"upRun":n}    連續下降／上升至少 n 期
      {"key":k,"baseHi":85}／{"baseLo":15}  去年同期的年增率在過去十年的百分位 ≥ 85／≤ 15（基期偏高／偏低）
      {"count":{"keys":[…],"light":"worse","min":a,"max":b}}   那幾個指標裡，亮那種燈的個數在 a～b 之間
      {"key":k,"pctHi":90}／{"pctLo":10}    最新值在過去十年的百分位 ≥ 90／≤ 10
      {"boom":{"min":a,"max":b}}            榮景期尾聲七大指標現在亮了幾項（boom＝項數，由呼叫的人算好傳進來）
      {"tw":"紅"}                           台灣景氣燈號
      {"all":[…]}、{"any":[…]}、{"not":…}"""
    if "all" in c:
        return all(eval_cond(x, S, tw, boom) for x in c["all"])
    if "any" in c:
        return any(eval_cond(x, S, tw, boom) for x in c["any"])
    if "not" in c:
        return not eval_cond(c["not"], S, tw, boom)
    if "boom" in c:
        return boom is not None and c["boom"].get("min", 0) <= boom <= c["boom"].get("max", 99)
    if "tw" in c:
        return bool(tw) and tw.get("name") == c["tw"]
    if "count" in c:
        q = c["count"]
        n = sum(1 for k in q["keys"] if (S.get(k) or {}).get("light") == q["light"])
        return q.get("min", 0) <= n <= q.get("max", len(q["keys"]))
    st = S.get(c.get("key")) or {}
    if not st:
        return False
    if "light" in c:
        return st.get("light") == c["light"]
    if "lt" in c:
        return st.get("last") is not None and st["last"] < c["lt"]
    if "gt" in c:
        return st.get("last") is not None and st["last"] > c["gt"]
    if "downRun" in c:
        return st.get("downRun", 0) >= c["downRun"]
    if "upRun" in c:
        return st.get("upRun", 0) >= c["upRun"]
    if "pctHi" in c:
        return st.get("pct10") is not None and st["pct10"] >= c["pctHi"]
    if "pctLo" in c:
        return st.get("pct10") is not None and st["pct10"] <= c["pctLo"]
    if "baseHi" in c:
        return st.get("basePct10") is not None and st["basePct10"] >= c["baseHi"]
    if "baseLo" in c:
        return st.get("basePct10") is not None and st["basePct10"] <= c["baseLo"]
    raise ValueError(f"不認得的提醒條件：{c}")


LAG_LIMIT = {"d": 14, "w": 28, "m": 110, "q": 290}      # 資料「截至日」離今天超過幾天，算停更（月資料本來就晚 1～2 個月公布、季資料晚 3～5 個月）


def stale_series(specs, series, today):
    """多久沒有新資料：來源停止更新、改代號、政府關門延後公布，都會先在這裡看到。回傳 [{key,name,through,days,limit}]。"""
    out = []
    for spec in specs:
        s = series.get(spec["key"])
        if not s or not s.get("through"):
            continue
        days = _days(s["through"][:10], today)
        limit = spec.get("maxLag") or LAG_LIMIT.get(s.get("freq"), 110)
        if days > limit:
            out.append({"key": spec["key"], "name": spec["name"], "through": s["through"], "days": days, "limit": limit})
    return out


BROWSER_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
              "Accept": "text/html,*/*", "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8"}


def link_status(url, timeout=15):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=BROWSER_UA), timeout=timeout) as r:
            return r.status
    except Exception as e:  # noqa: BLE001
        return getattr(e, "code", None) or f"{type(e).__name__}: {e}"


def config_urls(cfg):
    """設定檔裡所有給人點的網址：外部網站、觀念的出處、來源筆記。"""
    urls = [it["url"] for g in cfg.get("links", []) for it in g["items"]]
    urls += [c["src"]["url"] for c in cfg.get("concepts", []) if (c.get("src") or {}).get("url")]
    urls += [n["url"] for n in (cfg.get("about") or {}).get("notes", [])]
    return list(dict.fromkeys(urls))


def dead_links(cfg, status=link_status):
    """只有 404／410（頁面真的不見了）才算失效；403、逾時多半是網站擋機器人，不算。"""
    return [u for u in config_urls(cfg) if status(u) in (404, 410)]


# ---------------------------------------------------------------- 台灣：國發會景氣指標查詢系統

DATAGOV_API = "https://data.gov.tw/api/v2/rest/dataset/{id}"


def http_bytes(url, timeout=60, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(3 * (i + 1))
    raise last


def decode(b):
    for enc in ("utf-8-sig", "big5", "cp950"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return b.decode("utf-8", errors="replace")


def datagov_files(dataset_id):
    """政府資料開放平臺的資料集 → [(檔名, 文字內容)]。下載網址每次都向平臺的 API 查（網址換了也不會壞）；ZIP 會解開。"""
    import zipfile
    meta = json.loads(http_get(DATAGOV_API.format(id=dataset_id), timeout=40))
    out = []
    for dist in meta["result"]["distribution"]:
        url, fmt = dist["resourceDownloadUrl"], (dist.get("resourceFormat") or "").upper()
        b = http_bytes(url)
        if fmt == "ZIP" or b[:2] == b"PK":
            z = zipfile.ZipFile(io.BytesIO(b))
            for info in z.infolist():
                name = info.filename
                try:
                    name = name.encode("cp437").decode("big5")
                except Exception:  # noqa: BLE001
                    pass
                out.append((name, decode(z.read(info))))
        else:
            out.append((url.rsplit("/", 1)[-1][:40], decode(b)))
    return out


def probe():
    """來源試探：只在 Actions 上跑。印出台灣官方資料檔的檔名與頭尾幾行（確認格式），再把設定檔裡的外部連結各連一次（找失效連結）。"""
    cfg = load_json(CFG)
    for did in sorted({t["dataset"] for t in cfg.get("tw", {}).get("files", [])}):
        print(f"\n===== data.gov.tw dataset {did}")
        try:
            files = datagov_files(did)
        except Exception as e:  # noqa: BLE001
            print(f"失敗：{type(e).__name__}: {e}")
            continue
        for name, text in files:
            lines = text.splitlines()
            print(f"--- {name}：{len(lines)} 行")
            for l in lines[:3] + ["..."] + lines[-3:]:
                print("   ", l[:400])
    print("\n===== 外部連結檢查（403 多半是網站擋機器人，不代表連結壞掉；404 才要修）")
    for u in config_urls(cfg):
        print(f"  {link_status(u, 25)}  {u}")


TW_LIGHTS = ("紅", "黃紅", "綠", "黃藍", "藍")


def parse_ym_csv(text, cols):
    """國發會開放資料的 CSV：第一欄 Date（YYYYMM），其餘是各指標；缺值是 '-' 或空白 → 跳過（不補）。
    回傳 {欄名: [(YYYY-MM-01, 值)]}；文字欄（燈號）原樣保留。欄位不在表頭、日期格式不對或沒有遞增 → 丟錯（寧可標待確認）。"""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or rows[0][0].strip() != "Date":
        raise ValueError("不是預期的國發會 CSV 格式：" + (",".join(rows[0])[:80] if rows else "空檔"))
    head = [h.strip() for h in rows[0]]
    at = {}
    for c in cols:      # 欄名先找完全一樣的；沒有就找「以它開頭」而且只有一欄的（官方偶爾會改括號裡的單位或基期）
        hit = [i for i, h in enumerate(head) if h == c] or [i for i, h in enumerate(head) if h.startswith(c)]
        if len(hit) != 1:
            raise ValueError(f"表頭找不到唯一的「{c}」這一欄：{head}")
        at[c] = hit[0]
    out, prev = {c: [] for c in cols}, ""
    for r in rows[1:]:
        if not r or not r[0].strip():
            continue
        d = r[0].strip()
        if len(d) != 6 or not d.isdigit() or not 1 <= int(d[4:]) <= 12:
            raise ValueError(f"日期格式不對：{d!r}")
        if d <= prev:
            raise ValueError(f"日期沒有遞增：{d}")
        prev = d
        iso = f"{d[:4]}-{d[4:]}-01"
        for c in cols:
            v = r[at[c]].strip() if at[c] < len(r) else ""
            if v in ("", "-"):
                continue
            if c == "景氣對策信號":
                if v not in TW_LIGHTS:
                    raise ValueError(f"不認得的燈號：{d} {v!r}")
                out[c].append((iso, v))
            else:
                out[c].append((iso, float(v)))
    return out


def score_ranges(scores, lights, years=10):
    """每種燈號對應的分數範圍，直接從官方檔最近 years 年的「分數＋燈號」配對算出來（不靠記憶寫死）。"""
    lm = dict(lights)
    out = {}
    for d, v in scores[-12 * years:]:
        name = lm.get(d)
        if name:
            lo, hi = out.get(name, [v, v])
            out[name] = [min(lo, v), max(hi, v)]
    return out


def fetch_tw(cfg, since, files_of=None):
    """台灣：國發會的景氣對策信號（分數與燈號）、領先／同時指標與它們的構成項目（出口、外銷訂單動向、半導體設備進口、M1B、股價指數…）、
    採購經理人指數。來源＝政府資料開放平臺的官方資料檔。
    回傳 (tw 區塊或 None, 待確認清單)。某個檔抓不到或格式不對 → 那個檔的指標不顯示並標待確認，不猜。"""
    tw_cfg = cfg.get("tw") or {}
    files_of = files_of or datagov_files
    series, unavailable, light, lights, ranges, cache = {}, [], None, [], {}, {}
    for f in tw_cfg.get("files", []):
        specs = [s for s in tw_cfg["series"] if s["file"] == f["id"]]
        cols = [s["col"] for s in specs] + ([f["lightCol"]] if f.get("lightCol") else [])
        try:
            if f["dataset"] not in cache:      # 同一個資料集（ZIP）只下載一次
                cache[f["dataset"]] = files_of(f["dataset"])
            files = cache[f["dataset"]]
            # 同一個 ZIP 裡還有 schema-xxx.csv（欄位說明）與 manifest.csv，要跳過
            hit = [t for n, t in files if f["match"] in n and not n.startswith(("schema", "manifest"))] if f.get("match") else [t for _, t in files]
            if not hit:
                raise ValueError(f"資料集裡找不到「{f['match']}」這個檔（有：{[n for n, _ in files]}）")
            got = parse_ym_csv(hit[0], cols)
        except Exception as e:  # noqa: BLE001
            unavailable.append(f"待確認：台灣「{f['source']}」這次抓取失敗或格式不符，相關指標沿用舊資料或不顯示（{type(e).__name__}: {e}）")
            print(f"台灣 {f['id']} 失敗：{type(e).__name__}: {e}")
            continue
        for spec in specs:      # 一條一條來：其中一條有問題，不拖累同一個檔的其他指標
            try:
                pts = got[spec["col"]]
                lo, hi = spec.get("range", [None, None])
                bad_v = [p for p in pts if (lo is not None and p[1] < lo) or (hi is not None and p[1] > hi)]
                if bad_v or len(pts) < 24:
                    raise ValueError(f"數值超出合理範圍或筆數太少：{bad_v[:3]}，共 {len(pts)} 筆")
                series[spec["key"]] = dict(build_series(spec, pts, since, cfg.get("light")), url=f["url"], src=f["source"])
                print(f"{spec['key']:8s} 台灣 {len(pts):4d} 筆，最新 {pts[-1][0][:7]} = {pts[-1][1]}")
            except Exception as e:  # noqa: BLE001
                unavailable.append(f"待確認：台灣「{spec['name']}」這次格式不符，沿用舊資料或不顯示（{type(e).__name__}: {e}）")
                print(f"台灣 {spec['key']} 失敗：{type(e).__name__}: {e}")
        sc_key = next((s["key"] for s in specs if s["col"] == f.get("scoreCol", "景氣對策信號綜合分數")), None)
        if f.get("lightCol") and (sc_key is None or sc_key in series):      # 分數那一欄沒過檢查，燈號也不顯示（同一張表，寧可標待確認）
            lights = [[d[:7], v] for d, v in got[f["lightCol"]]][-36:]
            light = {"date": lights[-1][0], "name": lights[-1][1]} if lights else None
            sc = next((s["col"] for s in specs if s["key"] == "twscore"), None)
            if sc and sc in got:
                ranges = score_ranges(got[sc], got[f["lightCol"]])
    if not series:
        return None, unavailable
    return {"series": series, "light": light, "lights": lights, "scoreRanges": ranges}, unavailable


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
    return age.total_seconds() >= STALE_HOURS * 3600


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
    doc, ok, total = build_doc(cfg, prev)
    if ok == 0:
        print("所有 FRED 序列都抓不到，不寫檔", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print(f"\n寫入 data/macro/latest.json：{ok}/{total} 條成功")
    for u in doc["unavailable"]:
        print(u)
    for x in doc["health"]["stale"]:
        print(f"停更？{x['name']}：資料只到 {x['through']}（{x['days']} 天前，上限 {x['limit']} 天）")
    for u in doc["links"]["dead"]:
        print("連結失效：" + u)
    print("觀念提醒成立：" + ("、".join(doc["reminders"]) or "無"))
    return 0


def build_doc(cfg, prev, fetch=None, tw_fetch=None, link_check=None, now=None):
    """抓全部資料、算好要寫進 latest.json 的整份內容。回傳 (doc, 成功條數, 總條數)。fetch／tw_fetch／link_check 是給測試換掉網路用的。"""
    now = now or datetime.now(timezone.utc)
    since, light = cfg.get("since", "1990-01-01"), cfg.get("light") or {}
    raw_cache = {}

    def raw_of(fid):
        if fid not in raw_cache:
            raw_cache[fid] = (fetch or (lambda i: parse_fred_csv(http_get(FRED_CSV.format(id=i)))))(fid)
            if not fetch:
                time.sleep(0.4)
        return raw_cache[fid]

    series, unavailable, ok, hist = {}, [], 0, {}
    specs = [s for g in cfg["groups"] for s in g["series"]]
    for spec in specs:      # 第一輪：直接來自 FRED 的序列，以及兩條 FRED 序列相除的
        key = spec["key"]
        if spec.get("diff"):
            continue
        if spec.get("fred"):
            label = spec["fred"]
        elif spec.get("combo"):
            label = " ".join(("+ " if k > 0 else "− ") + f + ("" if abs(k) == 1 else f"×{abs(k):g}") for f, k in spec["combo"]).lstrip("+ ")
        else:
            label = f"{spec['ratio']['num']} ÷ {spec['ratio']['den']}"
        try:
            if spec.get("combo"):
                raw = combo_points([(raw_of(f), k) for f, k in spec["combo"]])
                if len(raw) < 24:
                    raise ValueError("幾條序列對得上的月份太少")
                series[key] = dict(build_series(spec, raw, since, light, hist), fred=label, url=FRED_PAGE.format(id=spec["combo"][0][0]),
                                   formula="FRED " + label + "（每條取每月最後一筆，同一個月才相加減）", parts=[f for f, _ in spec["combo"]])
            elif spec.get("ratio"):
                r = spec["ratio"]
                raw = ratio_points(raw_of(r["num"]), raw_of(r["den"]), r.get("mult", 1.0))
                if not raw:
                    raise ValueError("兩條序列沒有對得上的季度")
                series[key] = dict(build_series(spec, raw, since, light, hist), fred=label, url=FRED_PAGE.format(id=r["num"]),
                                   formula=f"FRED {r['num']} ÷ {r['den']}（同一季；單位換算 ×{r.get('mult', 1.0)}）")
            else:
                series[key] = dict(build_series(spec, raw_of(spec["fred"]), since, light, hist), fred=label, url=FRED_PAGE.format(id=spec["fred"]))
            ok += 1
            s = series[key]
            print(f"{key:9s} {label:24s} {s['freq']} {len(s['points']):4d} 筆，最新 {s['stats']['lastDate']} = {s['stats']['last']}"
                  f"（{(s['stats'] or {}).get('light') or '不亮燈'}）")
        except Exception as e:  # noqa: BLE001
            old = (prev.get("series") or {}).get(key)
            if old and old.get("points"):
                series[key] = old
                unavailable.append(f"待確認：{spec['name']}（FRED {label}）這次抓取失敗，沿用資料截至 {old.get('through')} 的舊資料（{type(e).__name__}: {e}）")
            else:
                unavailable.append(f"待確認：{spec['name']}（FRED {label}）：抓不到資料，沒有顯示（{type(e).__name__}: {e}）")
            print(f"{key:9s} {label:24s} 失敗：{type(e).__name__}: {e}")
    for spec in specs:      # 第二輪：兩條已經算好的序列相減（例如 商品消費年增率 − 服務消費年增率）
        if not spec.get("diff"):
            continue
        key, (a, b) = spec["key"], spec["diff"]
        try:
            pa, pb = series[a]["points"], series[b]["points"]
            raw = diff_points([tuple(p) for p in pa], [tuple(p) for p in pb])
            if len(raw) < 24:
                raise ValueError("對得上的月份太少")
            series[key] = dict(build_series(spec, raw, since, light, hist), formula=f"公式：{a} − {b}（本頁兩條序列相減）", parts=[a, b])
            ok += 1
        except Exception as e:  # noqa: BLE001
            unavailable.append(f"待確認：{spec['name']}：算不出來，沒有顯示（{type(e).__name__}: {e}）")
    recessions = prev.get("recessions") or []
    rid = cfg.get("recession")
    if rid:
        try:
            recessions = [r for r in recession_ranges(raw_of(rid)) if r[1] >= since[:7]]
        except Exception as e:  # noqa: BLE001
            unavailable.append(f"待確認：衰退期間灰底（FRED {rid}）這次抓取失敗，沿用舊的（{type(e).__name__}: {e}）")
    tw, tw_un = (tw_fetch or fetch_tw)(cfg, since)
    old_tw = prev.get("tw") or {}
    if tw is None:
        tw = old_tw or None
    else:
        for k, v in (old_tw.get("series") or {}).items():      # 這次沒抓到的台灣指標：沿用上一次的
            tw["series"].setdefault(k, v)
        if not tw.get("light") and old_tw.get("light"):
            tw["light"], tw["lights"] = old_tw["light"], old_tw.get("lights") or []
    unavailable += tw_un

    # 警訊計數：回算歷史上每個月有幾個燈轉差（只有這次真的抓到的序列才有歷史；沿用舊資料的不算進去）
    boom = next((p for p in cfg.get("phases", []) if p.get("id") == "boom"), {})
    checks = [c["keys"] for c in boom.get("checks", [])]
    score = prev.get("score")
    if hist:
        end = max(d[:7] for v in hist.values() for d, _ in v[-1:])
        sc = score_series(hist, checks, (cfg.get("score") or {}).get("start", "1995-01"), end)
        score = dict(sc, items=len(checks), table=score_table(sc, recessions, len(checks)))

    # 觀念提醒：條件寫在 config.json，成立與否在這裡判斷
    S = {k: (v.get("stats") or {}) for k, v in series.items()}
    S.update({k: (v.get("stats") or {}) for k, v in ((tw or {}).get("series") or {}).items()})
    boom_now = sum(1 for c in checks if any(S.get(k, {}).get("light") == "worse" for k in c))
    fired = []
    for r in cfg.get("reminders", []):
        try:
            if eval_cond(r["when"], S, (tw or {}).get("light"), boom_now):
                fired.append(r["id"])
        except Exception as e:  # noqa: BLE001
            unavailable.append(f"待確認：觀念提醒「{r.get('id')}」的條件有問題，沒有判斷（{type(e).__name__}: {e}）")

    today = now.strftime("%Y-%m-%d")
    tw_specs = (cfg.get("tw") or {}).get("series", [])
    health = {"checked": today, "stale": stale_series(specs, series, today) + stale_series(tw_specs, (tw or {}).get("series") or {}, today),
              "failed": len(unavailable)}
    links = {"checked": today, "dead": (link_check or dead_links)(cfg)}
    doc = {"version": 2, "updated": now.strftime("%Y-%m-%d %H:%M UTC"), "since": since, "light": {"threshold": light.get("threshold", 1.0), "years": light.get("years", 10)},
           "series": series, "recessions": recessions, "tw": tw, "score": score, "boomNow": boom_now, "reminders": fired,
           "health": health, "links": links, "unavailable": unavailable}
    return doc, ok, len(specs)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
