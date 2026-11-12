"""每月本益比的唯一計算處（build.py 與 validate.py 都呼叫這裡；前端只畫圖，不重算）。

輸入：
  quarters  data/<代號>.json 的 quarters[]（要有 q、eps、rd；依時間排序）
  prices    data/prices/<代號>.json（monthly[]：每月最後交易日收盤價；forward[]：分析師預估快照）
輸出：valuation = {symbol, currency, monthly:[{m,d,c,eps4,pe,why,ntm,fpe,fwhy,few}], stats:{...}}

規則（對照「每月本益比 執行計畫」第 2 節）：
  歷史本益比 ＝ 月底收盤價 ÷ 「那一天為止已公布」的最近四季 EPS 加總
  why：loss 近四季 EPS 加總 ≤ 0；short 已公布未滿四季；missing EPS 或公布日待確認；price 股價待確認
  不估計、不內插、不拿兩季乘以 2。
預估本益比 ＝ 月底收盤價 ÷ 未來 12 個月 EPS；NTM ＝ w×今年度預估 ＋ (1−w)×下年度預估，w ＝ 今年度剩餘天數 ÷ 365。
  只用當月快照，不回填。
"""
import datetime as dt, statistics

NDIG = 1


def _day(s):
    return dt.date.fromisoformat(s)


def window_at(quarters, d):
    """回傳 (window, why)。window＝d 當天已公布的最近四季（list），或 None 並附原因。"""
    j = -1
    for i, q in enumerate(quarters):
        if q.get("rd") and q["rd"] <= d:
            j = i
    # 公布日空白的季度：只要它後面某一季的公布日已過，就一定也公布了（依序公布）
    if j + 1 < len(quarters) and not quarters[j + 1].get("rd"):
        return None, "missing"          # 下一季公布日待確認，無法判斷 d 當天它公布了沒有
    if j < 3:
        # 前面可能有 rd 為空但已確定公布的季度；數量不足四季一律算 short
        return None, "short"
    w = quarters[j - 3:j + 1]
    if any(q.get("eps") is None for q in w):
        return None, "missing"
    return w, None


def forward_ntm(f, d):
    """f＝forward 快照，d＝月底日。回傳 (ntm, fwhy, few)。"""
    if not f:
        return None, "none", False
    if f.get("why"):
        return None, "missing", False
    e1, e2, fy1 = f.get("eps1"), f.get("eps2"), f.get("fy1End")
    if e1 is None or e2 is None or not fy1:
        return None, "missing", False
    left = (_day(fy1) - _day(d)).days
    if left <= 0:
        return None, "missing", False
    w = min(left, 365) / 365
    ntm = w * e1 + (1 - w) * e2
    few = min(f.get("n1") or 0, f.get("n2") or 0) < 3
    if ntm <= 0:
        return None, "loss", few
    return ntm, None, few


def percentile(sorted_vals, x):
    below = sum(1 for v in sorted_vals if v < x)
    equal = sum(1 for v in sorted_vals if v == x)
    return round((below + 0.5 * equal) / len(sorted_vals) * 100)


def compute(quarters, prices):
    if not prices:
        return None
    fwd = {f["m"]: f for f in prices.get("forward", [])}
    out = []
    for p in prices["monthly"]:
        row = {"m": p["m"], "d": p["d"], "c": p.get("c"), "eps4": None, "pe": None, "why": None, "ntm": None, "fpe": None, "fwhy": None, "few": False}
        if p.get("c") is None:
            row["why"] = "price"
        else:
            w, why = window_at(quarters, p["d"])
            if w is None:
                row["why"] = why
            else:
                s = round(sum(q["eps"] for q in w), 4)
                row["eps4"] = s
                if s <= 0:
                    row["why"] = "loss"
                else:
                    row["pe"] = round(p["c"] / s, NDIG)
        f = fwd.get(p["m"])
        if f is not None and p.get("c") is not None:
            ntm, fwhy, few = forward_ntm(f, p["d"])
            row["fwhy"], row["few"] = fwhy, few
            if ntm is not None:
                row["ntm"] = round(ntm, 4)
                row["fpe"] = round(p["c"] / ntm, NDIG)
        out.append(row)
    pes = [(r["m"], r["pe"]) for r in out if r["pe"] is not None]
    st = {"latest": None, "latestM": None, "med5": None, "med10": None, "pct10": None, "fpeLatest": None, "fpeM": None}
    if out:
        last = out[-1]
        st["priceM"] = last["m"]
        if last["pe"] is not None:
            st["latest"], st["latestM"] = last["pe"], last["m"]
        fl = [r for r in out if r["fpe"] is not None]
        if fl:
            st["fpeLatest"], st["fpeM"] = fl[-1]["fpe"], fl[-1]["m"]
    if pes:
        def since(years):
            y, m = map(int, pes[-1][0].split("-"))
            lo = f"{y - years:04d}-{m:02d}"
            return [v for mm, v in pes if mm > lo]
        for k, yrs in (("med5", 5), ("med10", 10)):
            v = since(yrs)
            if len(v) >= 12:
                st[k] = round(statistics.median(v), NDIG)
        v10 = since(10)
        if len(v10) >= 24 and st["latest"] is not None:
            st["pct10"] = percentile(sorted(v10), st["latest"])
    return {"symbol": prices.get("symbol"), "currency": prices.get("currency"), "monthly": out, "stats": st}


# ---------- 固定測試案例（validate.py 一併執行）----------
def selftest():
    errs = []

    def Q(rows):
        return [{"q": f"{(i % 4) + 1}Q{20 + i // 4}", "eps": e, "rd": r} for i, (e, r) in enumerate(rows)]

    def P(c, d="2021-02-26"):
        return {"symbol": "T", "currency": "USD", "monthly": [{"m": d[:7], "d": d, "c": c}], "forward": []}

    base = Q([(1.0, "2020-04-30"), (1.0, "2020-07-30"), (1.0, "2020-10-29"), (1.0, "2021-02-04"), (1.0, "2021-04-29")])
    r = compute(base, P(40))["monthly"][0]
    if r["pe"] != 10.0 or r["eps4"] != 4.0:
        errs.append(f"正常案例：期望 10.0，得到 {r}")
    r = compute(Q([(-1.0, "2020-04-30"), (0.5, "2020-07-30"), (0.5, "2020-10-29"), (-1.0, "2021-02-04")]), P(40))["monthly"][0]
    if r["why"] != "loss" or r["pe"] is not None:
        errs.append(f"虧損案例：{r}")
    r = compute(Q([(1.0, "2020-10-29"), (1.0, "2021-02-04")]), P(40))["monthly"][0]
    if r["why"] != "short":
        errs.append(f"未滿四季案例：{r}")
    q2 = Q([(1.0, "2020-04-30"), (1.0, "2020-07-30"), (1.0, "2020-10-29"), (1.0, "2021-02-26"), (2.0, "2021-04-29")])
    r1 = compute(q2, P(40, "2021-02-26"))["monthly"][0]      # 公布日＝月底當天：算已公布
    q2[3]["rd"] = "2021-03-01"
    r2 = compute(q2, P(40, "2021-02-26"))["monthly"][0]      # 隔天才公布：還不算
    if r1["eps4"] != 4.0 or r2["why"] != "short":
        errs.append(f"公布日邊界案例：{r1} / {r2}")
    q3 = Q([(1.0, "2020-04-30"), (1.0, "2020-07-30"), (1.0, "2020-10-29"), (1.0, "2021-02-04"), (1.0, None)])
    r = compute(q3, P(40, "2021-03-31"))["monthly"][0]
    if r["why"] != "missing":
        errs.append(f"rd 為空案例：{r}")
    r = compute(base, {"symbol": "T", "currency": "USD", "monthly": [{"m": "2021-02", "d": "2021-02-26", "c": None}], "forward": []})["monthly"][0]
    if r["why"] != "price":
        errs.append(f"股價為空案例：{r}")
    # 預估本益比：w＝(2021-06-30−2021-02-26)/365＝124/365
    pf = P(40)
    pf["forward"] = [{"m": "2021-02", "asOf": "2021-03-02", "fy1End": "2021-06-30", "fy2End": "2022-06-30", "eps1": 3.0, "eps2": 5.0, "n1": 10, "n2": 8}]
    r = compute(base, pf)["monthly"][0]
    w = 124 / 365
    ntm = w * 3.0 + (1 - w) * 5.0
    if r["ntm"] != round(ntm, 4) or r["fpe"] != round(40 / ntm, 1):
        errs.append(f"預估正常案例：{r}")
    pf["forward"][0].update(eps1=-3.0, eps2=-1.0)
    r = compute(base, pf)["monthly"][0]
    if r["fwhy"] != "loss" or r["fpe"] is not None:
        errs.append(f"預估虧損案例：{r}")
    pf["forward"][0] = {"m": "2021-02", "asOf": "2021-03-02", "fy1End": "2021-06-30", "eps1": 3.0, "eps2": None, "n1": 10, "n2": 0}
    r = compute(base, pf)["monthly"][0]
    if r["fwhy"] != "missing" or r["fpe"] is not None:
        errs.append(f"預估缺下年度案例：{r}")
    return errs


if __name__ == "__main__":
    e = selftest()
    print("pe.py 測試案例：" + ("全部通過（9 項）" if not e else "\n".join(e)))
    raise SystemExit(1 if e else 0)
