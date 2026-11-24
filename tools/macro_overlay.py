"""總經頁「美元・利率・通膨對照圖」的資料 → data/macro/overlay.json。只由 GitHub Actions（macro-weekly）執行，不經過 Claude。

  Yahoo：美元指數 DXY（ICE，DX-Y.NYB）每日開高低收、SPY 每日收盤 ──┐
  FRED：聯邦基金有效利率 FEDFUNDS（月平均）、目標區間、CPI、        ├─▶ data/macro/overlay.json ─▶ macro/ 頁畫圖
        西德州原油、2 年期公債、10 年期實質利率                      ──┘

和 latest.json 的差別：latest.json 為了算方向燈，每日資料只留「每月最後一筆」；這張圖要畫每天的 K 棒，所以另外存每日資料。

資料誠實規則（和網站其他地方一樣）：
  · 只放來源原值；不估計、不內插。CPI 年增率＝和去年同月比（tools/macro_fetch.py 的 to_yoy，同一個算法）
  · 美東還沒收盤的那一天不收（K 棒還在變）
  · 開高低收不合理的 K 棒不放，寫進 pending（待確認）
  · 某條這次抓失敗：沿用上一次 overlay.json 的那條，並寫進 unavailable（「待確認：」開頭）；從沒抓到過就留空
  · DXY 與 SPY 只有 Yahoo 一個來源（沒有第二個免費來源可以核對），頁面會註明

用法：python3 tools/macro_overlay.py   （需要 yfinance；全部都失敗才回傳非 0）
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import macro_fetch as M   # noqa: E402  FRED 下載、解析與年增率不複製

OUT = os.path.join(ROOT, "data", "macro", "overlay.json")
SINCE = "2000-01-01"
NY = ZoneInfo("America/New_York")
YAHOO_PAGE = "https://finance.yahoo.com/quote/{}/history"

# FRED 序列：key → (FRED 代號, 名稱, 小數位)
FRED_LINES = {
    "fedfunds": ("FEDFUNDS", "聯邦基金有效利率（月平均）", 2),
    "wti": ("DCOILWTICO", "西德州原油（美元／桶）", 2),
    "dgs2": ("DGS2", "2 年期公債殖利率", 2),
    "dfii10": ("DFII10", "10 年期實質利率（TIPS）", 2),
}


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- 純函式（tools/tests/test_macro_overlay.py 有測）

def closed_cutoff(now_utc, close_hour=17, close_min=15):
    """最後一個「美東已經收盤」的日期（YYYY-MM-DD）。DXY 在 ICE 美東 17:00 收，SPY 16:00 收；統一用 17:15 之後才算當天收完。"""
    ny = now_utc.astimezone(NY)
    d = ny.date()
    if (ny.hour, ny.minute) < (close_hour, close_min):
        d -= timedelta(days=1)
    return d.isoformat()


def ok_num(x):
    return isinstance(x, (int, float)) and x == x and abs(x) != float("inf")


def clean_ohlc(rows, cutoff, digits=3):
    """[(date, o, h, l, c)] → (bars, pending)。缺值（NaN）的列跳過不補；高低不合理的列不放、記成待確認；cutoff 之後的不收。"""
    bars, pending = [], []
    for d, o, h, l, c in rows:
        if d > cutoff or d < SINCE:
            continue
        if not all(ok_num(x) for x in (o, h, l, c)):
            continue
        if not (h >= max(o, c) - 1e-9 and l <= min(o, c) + 1e-9 and min(o, h, l, c) > 0):
            pending.append({"date": d, "reason": "待確認：開高低收不合理（最高價低於開／收盤或最低價高於開／收盤），沒有採用"})
            continue
        bars.append([d] + [round(x, digits) for x in (o, h, l, c)])
    return bars, pending


def target_steps(single, lo, hi):
    """聯準會目標：2008-12-16 以前是單一數字（DFEDTAR），之後是區間（DFEDTARL～DFEDTARU）。
    只留「改變的那一天」：[[日期, 下限, 上限]]（單一目標時下限＝上限）。"""
    lo_by = dict(lo)
    rows = [(d, v, v) for d, v in single if d < (lo[0][0] if lo else "9999")]
    rows += [(d, lo_by[d], v) for d, v in hi if d in lo_by]
    out, last = [], None
    for d, a, b in sorted(rows):
        if d < SINCE:
            continue
        if not out or (a, b) != last:      # 第一筆是起點（當時的目標），之後只留改變的那一天
            out.append([d, a, b])
            last = (a, b)
    return out


def line(points, digits):
    return [[d, round(v, digits)] for d, v in points if d >= SINCE]


# ---------------------------------------------------------------- 網路

def fred(fid):
    pts = M.parse_fred_csv(M.http_get(M.FRED_CSV.format(id=fid)))
    time.sleep(0.4)
    return pts


def yahoo(sym):
    """Yahoo 日線（auto_adjust=False：不扣股利，和網站其他股價一樣）。回傳 [(date, o, h, l, c)]，可含 NaN。"""
    import yfinance as yf
    err = None
    for i in range(4):
        try:
            df = yf.Ticker(sym).history(start=SINCE, interval="1d", auto_adjust=False, actions=False)
            if df is None or df.empty:
                raise RuntimeError("沒有日線資料")
            return [(ts.date().isoformat(), float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"])) for ts, r in df.iterrows()]
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"{sym} 抓取失敗：{type(err).__name__}: {err}")


# ---------------------------------------------------------------- 組合

def build(prev, now=None, fred_fn=fred, yahoo_fn=yahoo):
    now = now or datetime.now(timezone.utc)
    cut = closed_cutoff(now)
    S, un, ok, total = {}, [], 0, 0
    old = prev.get("series") or {}

    def attempt(key, label, fn):
        nonlocal ok, total
        total += 1
        try:
            S[key] = fn()
            if not (S[key].get("bars") or S[key].get("pts") or S[key].get("steps")):
                raise ValueError("沒有資料")
            ok += 1
            n = len(S[key].get("bars") or S[key].get("pts") or S[key].get("steps"))
            log(f"{key:9s} {label:24s} {n:5d} 筆，資料到 {S[key]['through']}")
        except Exception as e:  # noqa: BLE001
            S.pop(key, None)
            if old.get(key):
                S[key] = old[key]
                un.append(f"待確認：{label} 這次抓取失敗，沿用資料到 {old[key].get('through')} 的舊資料（{type(e).__name__}: {e}）")
            else:
                un.append(f"待確認：{label} 抓不到資料，沒有顯示（{type(e).__name__}: {e}）")
            log(f"{key:9s} {label:24s} 失敗：{type(e).__name__}: {e}")

    def dxy():
        bars, pending = clean_ohlc(yahoo_fn("DX-Y.NYB"), cut, 3)
        return {"name": "美元指數 DXY（ICE）", "src": "Yahoo DX-Y.NYB", "url": YAHOO_PAGE.format("DX-Y.NYB"), "single": True,
                "through": bars[-1][0] if bars else None, "bars": bars, "pending": pending}

    def spy():
        bars, pending = clean_ohlc(yahoo_fn("SPY"), cut, 2)
        return {"name": "SPY（標普 500 ETF，收盤）", "src": "Yahoo SPY", "url": YAHOO_PAGE.format("SPY"), "single": True,
                "through": bars[-1][0] if bars else None, "pts": [[b[0], b[4]] for b in bars], "pending": pending}

    def fred_line(key):
        fid, name, digits = FRED_LINES[key]
        pts = line(fred_fn(fid), digits)
        return {"name": name, "src": "FRED " + fid, "url": M.FRED_PAGE.format(id=fid), "through": pts[-1][0] if pts else None, "pts": pts}

    def cpi():
        raw = fred_fn("CPIAUCSL")
        pts = line(M.to_yoy(raw), 2)
        return {"name": "CPI 年增率", "src": "FRED CPIAUCSL（勞工統計局）", "url": M.FRED_PAGE.format(id="CPIAUCSL"),
                "formula": "和去年同一個月比", "through": pts[-1][0] if pts else None, "pts": pts}

    def target():
        steps = target_steps(fred_fn("DFEDTAR"), fred_fn("DFEDTARL"), fred_fn("DFEDTARU"))
        hi = fred_fn("DFEDTARU")
        return {"name": "聯準會目標區間", "src": "FRED DFEDTAR／DFEDTARL／DFEDTARU", "url": M.FRED_PAGE.format(id="DFEDTARU"),
                "through": hi[-1][0] if hi else None, "steps": steps}

    attempt("dxy", "美元指數 DXY（Yahoo DX-Y.NYB）", dxy)
    attempt("fedfunds", "聯邦基金有效利率（FRED FEDFUNDS）", lambda: fred_line("fedfunds"))
    attempt("cpi", "CPI 年增率（FRED CPIAUCSL）", cpi)
    attempt("target", "聯準會目標區間（FRED）", target)
    attempt("wti", "西德州原油（FRED DCOILWTICO）", lambda: fred_line("wti"))
    attempt("spy", "SPY（Yahoo）", spy)
    attempt("dgs2", "2 年期公債殖利率（FRED DGS2）", lambda: fred_line("dgs2"))
    attempt("dfii10", "10 年期實質利率（FRED DFII10）", lambda: fred_line("dfii10"))
    doc = {"version": 1, "updated": now.strftime("%Y-%m-%d %H:%M UTC"), "since": SINCE, "cutoff": cut, "series": S, "unavailable": un}
    return doc, ok, total


def main():
    prev = M.load_json(OUT, {}) or {}
    doc, ok, total = build(prev)
    if ok == 0:
        print("對照圖的序列全部抓不到，不寫檔", file=sys.stderr)
        return 1
    with open(OUT, "w", encoding="utf8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    log(f"\n寫入 data/macro/overlay.json：{ok}/{total} 條成功")
    for u in doc["unavailable"]:
        log(u)
    return 0


if __name__ == "__main__":
    sys.exit(main())
