"""體質指標的唯一計算處（build.py 與 validate.py 呼叫；前端只畫圖，不重算這裡的指標）。

用 quarters[] 的 8 個資產負債表／股數欄位（shOut、dilSh、cash、debt、buyback、equity、pretax、tax）＋本益比月資料，
算出 6 個新指標。公式固定一種（和網站「指標小辭典」一致）：

  ROE   ＝ 近四季淨利 ÷ 平均股東權益（本季與四季前兩個期末的平均）
  ROIC  ＝ 近四季稅後營業利益 ÷ 平均投入資本；稅後營業利益 ＝ 近四季營業利益 ×（1 − 有效稅率），有效稅率 ＝ 近四季所得稅 ÷ 近四季稅前淨利；
          投入資本 ＝ 股東權益 ＋ 有息負債 − 現金與投資（排除現金與投資）；投入資本 ≤ 0 或稅前淨利 ≤ 0 或有效稅率不在 0～100% 時不計算，寫原因
  FCF 殖利率 ＝ 近四季自由現金流 ÷ 市值；市值 ＝ 月底收盤價 × 那一天已公布的最新一季期末流通股數
  EV/Sales   ＝（市值 ＋ 有息負債 − 現金與投資）÷ 近四季營收（同一個「當時已公布」的季度）
  PEG   ＝ 預估本益比 ÷ 預估 EPS 成長率（%）；成長率 ＝ 預估次年度 EPS ÷ 今年度 EPS − 1；成長率 ≤ 0 不計算；全部是分析師預估，只有有預估快照的月份才有，不回填
  回購與股數  當季回購金額、近四季回購；稀釋加權股數年增率（本季對四季前，兩者都有才算）

輸出 health = {quarterly:[{q,roe,roic,buyback,buybackTtm,dilYoy,why:{...}}], monthly:[{m,fcfY,evS,peg,why:{...}}]}（中位數與百分位由前端 assets/health.js 統一算）
任何輸入欄位是 null 就不算，原因寫在 why（missing＝欄位待確認、neg＝分母不是正數、tax＝有效稅率不合理、loss＝稅前虧損、nopx＝沒有預估）。
"""
NEW = ("shOut", "dilSh", "cash", "debt", "buyback", "equity", "pretax", "tax")
NAMES = {"shOut": "期末流通股數", "dilSh": "稀釋加權股數", "cash": "現金與投資", "debt": "有息負債", "buyback": "回購金額", "equity": "股東權益", "pretax": "稅前淨利", "tax": "所得稅費用"}


def s4(Q, i, k):
    if i < 3:
        return None
    v = [Q[j].get(k) for j in range(i - 3, i + 1)]
    return None if any(x is None for x in v) else sum(v)


def normq(D, schema=None):
    """台積電舊格式（schema tsmc-legacy）：rev／ni 是百萬元、ocf／capex 是「十億元」（assets/adapters.js 同樣換算）。
    這裡換成和其他公司一樣的「百萬」單位，並補上 fcf、opInc（＝營收×營業利益率，om 是公司公布值）。其他格式原樣回傳。"""
    Q = D["quarters"]
    if schema != "tsmc-legacy":
        return Q
    out = []
    for q in Q:
        x = dict(q)
        for k in ("ocf", "capex"):
            x[k] = None if q.get(k) is None else q[k] * 1000
        x["fcf"] = None if x["ocf"] is None or x["capex"] is None else x["ocf"] - x["capex"]
        x["opInc"] = None if q.get("om") is None or q.get("rev") is None else q["rev"] * q["om"] / 100
        out.append(x)
    return out


def r(x, n=2):
    return None if x is None else round(x, n)


def quarterly(Q):
    out = []
    for i, q in enumerate(Q):
        row = {"q": q["q"], "roe": None, "roic": None, "buyback": q.get("buyback"), "buybackTtm": r(s4(Q, i, "buyback"), 1), "dilYoy": None, "why": {}}
        W = row["why"]
        # ROE
        ni, e0, e1 = s4(Q, i, "ni"), q.get("equity"), Q[i - 4].get("equity") if i >= 4 else None
        if ni is None or e0 is None or e1 is None:
            W["roe"] = "missing"
        else:
            avg = (e0 + e1) / 2
            if avg <= 0:
                W["roe"] = "neg"
            else:
                row["roe"] = r(ni / avg * 100, 1)
        # ROIC
        op, tax, pt = s4(Q, i, "opInc"), s4(Q, i, "tax"), s4(Q, i, "pretax")
        def ic(j):
            x = Q[j]
            return None if None in (x.get("equity"), x.get("debt"), x.get("cash")) else x["equity"] + x["debt"] - x["cash"]
        i0, i1 = ic(i), ic(i - 4) if i >= 4 else None
        if None in (op, tax, pt, i0, i1):
            W["roic"] = "missing"
        elif pt <= 0:
            W["roic"] = "loss"
        elif not (0 <= tax / pt <= 1):
            W["roic"] = "tax"
        elif (i0 + i1) / 2 <= 0:
            W["roic"] = "neg"
        else:
            row["roic"] = r(op * (1 - tax / pt) / ((i0 + i1) / 2) * 100, 1)
        # 稀釋股數年增
        a, b = q.get("dilSh"), Q[i - 4].get("dilSh") if i >= 4 else None
        if a is not None and b:
            row["dilYoy"] = r((a / b - 1) * 100, 1)
        else:
            W["dilYoy"] = "missing"
        out.append(row)
    return out


def monthly(Q, valuation, prices):
    if not valuation:
        return []
    fwd = {f["m"]: f for f in (prices or {}).get("forward", [])}
    out = []
    for m in valuation["monthly"]:
        row = {"m": m["m"], "fcfY": None, "evS": None, "peg": None, "why": {}}
        W = row["why"]
        c, d = m.get("c"), m["d"]
        j = -1
        for i, q in enumerate(Q):
            if q.get("rd") and q["rd"] <= d:
                j = i
        if c is None:
            W["fcfY"] = W["evS"] = "price"
        elif j < 3 or (j + 1 < len(Q) and not Q[j + 1].get("rd")):
            W["fcfY"] = W["evS"] = "missing"
        else:
            L = Q[j]
            sh = L.get("shOut")
            fcf, rev = None, s4(Q, j, "rev")
            ocf, cap = s4(Q, j, "ocf"), s4(Q, j, "capex")
            fcf = None if ocf is None or cap is None else ocf - cap
            if sh is None:
                W["fcfY"] = W["evS"] = "missing"
            else:
                cap_m = c * sh            # 單位：和 quarters 一樣是「百萬」（shOut 以百萬股計）
                if fcf is None:
                    W["fcfY"] = "missing"
                else:
                    row["fcfY"] = r(fcf / cap_m * 100, 2)
                if L.get("debt") is None or L.get("cash") is None or rev is None:
                    W["evS"] = "missing"
                elif rev <= 0:
                    W["evS"] = "neg"
                else:
                    row["evS"] = r((cap_m + L["debt"] - L["cash"]) / rev, 2)
        f = fwd.get(m["m"])
        if m.get("fpe") is None:
            W["peg"] = "nopx"
        elif not f or f.get("eps1") in (None, 0) or f.get("eps2") is None:
            W["peg"] = "nopx"
        else:
            g = (f["eps2"] / f["eps1"] - 1) * 100 if f["eps1"] > 0 else None
            if g is None or g <= 0:
                W["peg"] = "loss"
            else:
                row["peg"] = r(m["fpe"] / g, 2)
        out.append(row)
    return out


def compute(Q, valuation, prices):
    q, m = quarterly(Q), monthly(Q, valuation, prices)
    if not any(x.get(k) is not None for x in q for k in ("roe", "roic", "buyback", "dilYoy")) and not any(x.get("fcfY") is not None or x.get("evS") is not None for x in m):
        return None                      # 完全沒有新欄位資料：頁面不顯示新指標
    return {"quarterly": q, "monthly": m}
