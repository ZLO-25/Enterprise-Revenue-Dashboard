"""每日收盤價延伸出來的估值數字：唯一計算處（GitHub Actions 的 prices_daily.py 與 build.py 都呼叫這裡；前端只顯示）。

輸入：
  quarters  data/<代號>.json 的 quarters[]（要有 q、eps、rd；台積電舊格式先經 health.normq 換成百萬單位）
  rows      data/daily/<代號>.json 的 rows：[[日期, 收盤價], …]（Yahoo 日線 Close，已依分割調整、不含股利調整；收盤價待確認時是 null）
  prices    data/prices/<代號>.json（只拿 forward[] 分析師預估快照）
  valuation pe.compute() 的結果（只拿 stats.med5，近 5 年每月本益比中位數）
  thesis    已確認（approved）的論點卡（只拿估值門檻 group:"val"）

公式（每一個都只用「那一天為止已公布」的財報，同 pe.py 的規則）：
  本益比      ＝ 收盤價 ÷ 近四季 EPS 加總
  預估本益比  ＝ 收盤價 ÷ 未來 12 個月預估 EPS（用最新一筆月底快照的今年度／下年度預估，按「今天」的今年度剩餘天數加權；分析師預估）
  市值        ＝ 收盤價 × 期末流通股數（最近一季有公布股數的季度；不是最新一季時會標出用哪一季）
  股價營收比  ＝ 市值 ÷ 近四季營收（P/S）
  EV/Sales    ＝（市值 ＋ 有息負債 − 現金與投資）÷ 近四季營收（負債、現金和股數取同一季）
  FCF 殖利率  ＝ 近四季自由現金流 ÷ 市值
  距估值上限  ＝ 論點卡估值門檻 ÷ 現值 − 1（本益比、EV/Sales、預估本益比是「≤ 門檻」，正值＝還有多少空間）
  上限對應股價＝ 讓指標剛好等於門檻的收盤價（本益比：門檻 × 近四季 EPS；EV/Sales：(門檻×營收 − 負債 + 現金) ÷ 股數）
不估計、不內插；算不出來就是 null，原因寫在 why。
"""
import datetime as dt

import pe as PE

NDIG = 2


def r(x, n=NDIG):
    return None if x is None else round(x, n)


def _published(Q, d):
    """d 當天已公布的最後一季 index；下一季公布日空白時回傳 None（無法判斷）。"""
    j = -1
    for i, q in enumerate(Q):
        if q.get("rd") and q["rd"] <= d:
            j = i
    if j + 1 < len(Q) and not Q[j + 1].get("rd"):
        return None
    return j


def _s4(Q, j, k):
    if j is None or j < 3:
        return None
    v = [Q[i].get(k) for i in range(j - 3, j + 1)]
    return None if any(x is None for x in v) else sum(v)


def series(quarters, rows):
    """每日本益比：[[日期, 收盤價, 本益比|None]]"""
    out = []
    for d, c in rows:
        pe = None
        if c is not None:
            w, _ = PE.window_at(quarters, d)
            if w:
                s = sum(q["eps"] for q in w)
                if s > 0:
                    pe = round(c / s, 1)
        out.append([d, c, pe])
    return out


def latest(Q, quarters, rows, prices=None, valuation=None, thesis=None):
    """最新一個交易日的所有數字。Q＝normq 後的季度（金額單位百萬），quarters＝原始季度（pe.py 用）。"""
    have = [x for x in rows if x[1] is not None]
    if not have:
        return None
    d, c = have[-1]
    L = {"d": d, "c": c, "why": {}}
    W = L["why"]
    if rows[-1][1] is None:
        W["c"] = f"待確認：{rows[-1][0]} 收盤價未通過核對，下面用 {d}"
    prev = have[-2] if len(have) > 1 else None
    if prev:
        L["prevD"], L["prevC"], L["chg"] = prev[0], prev[1], r((c / prev[1] - 1) * 100)
    yr = (dt.date.fromisoformat(d) - dt.timedelta(days=365)).isoformat()
    y1 = [x[1] for x in have if x[0] > yr]
    L["hi52"], L["lo52"] = max(y1), min(y1)
    L["fromHi"] = r((c / L["hi52"] - 1) * 100)
    # 本益比
    w, why = PE.window_at(quarters, d)
    L["pe"] = L["eps4"] = L["q"] = None
    if w is None:
        W["pe"] = why
    else:
        s = round(sum(q["eps"] for q in w), 4)
        L["eps4"], L["q"] = s, w[-1]["q"]
        if s <= 0:
            W["pe"] = "loss"
        else:
            L["pe"] = round(c / s, 1)
    med5 = ((valuation or {}).get("stats") or {}).get("med5")
    L["med5"] = med5
    L["vsMed5"] = r((L["pe"] / med5 - 1) * 100, 1) if L["pe"] is not None and med5 else None
    # 預估本益比（分析師預估，最新一筆有數字的月底快照）
    L["fpe"] = L["ntm"] = L["fSnap"] = None
    fs = [f for f in (prices or {}).get("forward", []) if not f.get("why")]
    if not fs:
        W["fpe"] = "none"
    else:
        f = fs[-1]
        ntm, fwhy, few = PE.forward_ntm(f, d)
        L["fSnap"], L["few"] = f["m"], few
        if ntm is None:
            W["fpe"] = fwhy
        else:
            L["ntm"], L["fpe"] = round(ntm, 4), round(c / ntm, 1)
    # 市值、P/S、EV/Sales、FCF 殖利率
    j = _published(Q, d)
    L["mcap"] = L["ps"] = L["evS"] = L["fcfY"] = L["shQ"] = None
    if j is None or j < 0:
        W["mcap"] = "missing"
    else:
        k = next((i for i in range(j, -1, -1) if Q[i].get("shOut") is not None), None)
        if k is None:
            W["mcap"] = "missing"
        else:
            sh = Q[k]["shOut"]
            L["shQ"], L["shLatest"] = Q[k]["q"], k == j
            mc = c * sh
            L["mcap"] = round(mc, 1)
            rev = _s4(Q, j, "rev")
            ocf, cap = _s4(Q, j, "ocf"), _s4(Q, j, "capex")
            if rev is None or rev <= 0:
                W["ps"] = W["evS"] = "missing" if rev is None else "neg"
            else:
                L["ps"] = r(mc / rev)
                B = Q[k]
                if B.get("debt") is None or B.get("cash") is None:
                    W["evS"] = "missing"
                else:
                    L["evS"] = r((mc + B["debt"] - B["cash"]) / rev)
            if ocf is None or cap is None:
                W["fcfY"] = "missing"
            else:
                L["fcfY"] = r((ocf - cap) / mc * 100)
            L["_sh"], L["_rev"], L["_debt"], L["_cash"], L["_fcf"] = sh, rev, Q[k].get("debt"), Q[k].get("cash"), (None if ocf is None or cap is None else ocf - cap)
    # 距估值上限（只有已確認的論點卡）
    caps = []
    for m in (thesis or {}).get("metrics", []):
        if m.get("group") != "val" or m["k"] not in ("pe", "evS", "fpe", "fcfY"):
            continue
        now = L.get(m["k"])
        row = {"k": m["k"], "name": m["name"], "op": m["op"], "thr": m["thr"], "now": now, "room": None, "px": None, "ok": None}
        if now is not None and now > 0:
            row["ok"] = now <= m["thr"] if m["op"] == "<=" else now >= m["thr"]
            row["room"] = r((m["thr"] / now - 1) * 100, 1) if m["op"] == "<=" else r((now / m["thr"] - 1) * 100, 1)
            if m["k"] == "pe" and L["eps4"]:
                row["px"] = r(m["thr"] * L["eps4"])
            elif m["k"] == "fpe" and L["ntm"]:
                row["px"] = r(m["thr"] * L["ntm"])
            elif m["k"] == "evS" and L.get("_sh") and L.get("_rev"):
                px = (m["thr"] * L["_rev"] - L["_debt"] + L["_cash"]) / L["_sh"]
                row["px"] = r(px) if px > 0 else None
            elif m["k"] == "fcfY" and L.get("_sh") and L.get("_fcf") and L["_fcf"] > 0:
                row["px"] = r(L["_fcf"] / (m["thr"] / 100) / L["_sh"])
        caps.append(row)
    L["caps"] = caps
    for k in ("_sh", "_rev", "_debt", "_cash", "_fcf"):
        L.pop(k, None)
    return L


def compute(Q, quarters, daily, prices=None, valuation=None, thesis=None):
    """回傳 {d, c, …latest, series:[[d,c,pe]]}；沒有每日股價檔時回傳 None。"""
    if not daily or not daily.get("rows"):
        return None
    rows = daily["rows"]
    L = latest(Q, quarters, rows, prices, valuation, thesis)
    if L is None:
        return None
    return {"symbol": daily.get("symbol"), "currency": daily.get("currency"), "fetched": daily.get("fetched"), "check": daily.get("check"),
            "latest": L, "series": series(quarters, rows)}


# ---------- 固定測試案例（validate.py 一併執行）----------
def selftest():
    errs = []
    Q = [{"q": f"{i + 1}Q25", "eps": 1.0, "rd": f"2025-{3 * i + 2:02d}-01", "rev": 100.0, "ocf": 30.0, "capex": 10.0,
          "shOut": 10.0 if i < 3 else None, "debt": 50.0, "cash": 150.0} for i in range(4)]
    rows = [["2026-01-02", 39.0], ["2026-01-05", 40.0]]
    L = latest(Q, Q, rows, thesis={"metrics": [{"k": "pe", "name": "本益比", "op": "<=", "thr": 12, "group": "val"},
                                                {"k": "evS", "name": "EV/Sales", "op": "<=", "thr": 1.5, "group": "val"}]})
    if L["pe"] != 10.0 or L["eps4"] != 4.0:
        errs.append(f"本益比：期望 10.0，得到 {L['pe']}")
    if L["mcap"] != 400.0 or L["shQ"] != "3Q25" or L["shLatest"] is not False:
        errs.append(f"市值（股數用最近有公布的一季）：{L['mcap']} {L['shQ']} {L.get('shLatest')}")
    if L["ps"] != 1.0 or L["evS"] != 0.75 or L["fcfY"] != 20.0:
        errs.append(f"P/S、EV/Sales、FCF 殖利率：{L['ps']} {L['evS']} {L['fcfY']}")
    if L["chg"] != r((40 / 39 - 1) * 100):
        errs.append(f"日漲跌：{L['chg']}")
    c0, c1 = L["caps"]
    if c0["room"] != 20.0 or c0["px"] != 48.0 or c0["ok"] is not True:
        errs.append(f"距本益比上限：{c0}")
    if c1["px"] != r((1.5 * 400 - 50 + 150) / 10):
        errs.append(f"EV/Sales 上限對應股價：{c1}")
    L = latest(Q, Q, [["2025-10-01", 40.0]])
    if L["pe"] is not None or L["why"].get("pe") != "short":
        errs.append(f"未滿四季：{L['pe']} {L['why']}")
    L = latest(Q, Q, [["2026-01-02", 39.0], ["2026-01-05", None]])
    if L["d"] != "2026-01-02" or "c" not in L["why"]:
        errs.append(f"最新收盤價待確認時退回前一天：{L['d']} {L['why']}")
    # 52 週高低只看近 365 天：兩年前的高價不算
    rows = [["2024-01-02", 100.0], ["2025-06-02", 20.0], ["2026-01-02", 30.0], ["2026-01-05", 40.0]]
    L = latest(Q, Q, rows)
    if L["hi52"] != 40.0 or L["lo52"] != 20.0:
        errs.append(f"52 週高低應忽略 365 天前的價格：{L['hi52']} {L['lo52']}")
    # series：一列一筆，收盤價 null → 本益比 null
    S = series(Q, [["2026-01-02", 39.0], ["2026-01-03", None], ["2026-01-05", 40.0]])
    if len(S) != 3 or S[1][1] is not None or S[1][2] is not None or S[2][2] != 10.0:
        errs.append(f"series 每列一筆、null 收盤價 → null 本益比：{S}")
    return errs


if __name__ == "__main__":
    e = selftest()
    print("daily_calc.py 測試案例：" + ("全部通過（10 項）" if not e else "\n".join(e)))
    raise SystemExit(1 if e else 0)
