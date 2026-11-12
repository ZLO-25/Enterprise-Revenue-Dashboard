"""資產負債表與股數欄位回補（階段 3）：從 SEC XBRL（companyconcept）讀 8 個新欄位，對齊每家公司的季度。
只有 GitHub Actions 讀得到 data.sec.gov（容器內被擋），所以由 .github/workflows/bs-fetch.yml 手動觸發。

  python3 tools/bs_fetch.py --probe              只印各公司各概念有幾筆事實（用來決定 BS_MAP）
  python3 tools/bs_fetch.py [--company nvda]     產生 data/bs-raw/<代號>.json（提案，不直接改 data/<代號>.json）

提案之後由 tools/bs_merge.py 核對並合併進 data/<代號>.json。原則（資料誠實）：讀不到就是 null，不估計、不內插。
"""
import datetime as dt, json, os, sys, time, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Enterprise-Revenue-Dashboard research contact@example.com"
PROBE = [
    "StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "CommonStockSharesOutstanding",
    "WeightedAverageNumberOfDilutedSharesOutstanding", "IncomeTaxExpenseBenefit",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic", "IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign",
    "PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity", "TreasuryStockValueAcquiredCostMethod",
    "CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents", "ShortTermInvestments", "MarketableSecuritiesCurrent",
    "AvailableForSaleSecuritiesDebtSecuritiesCurrent", "MarketableSecuritiesNoncurrent", "LongTermInvestments", "AvailableForSaleSecuritiesDebtSecuritiesNoncurrent",
    "LongTermDebt", "LongTermDebtCurrent", "LongTermDebtNoncurrent", "DebtCurrent", "ShortTermBorrowings", "CommercialPaper", "ConvertibleNotesPayable",
    "ConvertibleNotesPayableCurrent", "ConvertibleDebt", "ConvertibleDebtNoncurrent", "NotesPayable", "SeniorNotes", "DebtLongtermAndShorttermCombinedAmount",
    "LongTermDebtAndCapitalLeaseObligations", "LongTermNotesPayable", "NotesPayableCurrent", "LongTermLineOfCredit", "LineOfCredit", "UnsecuredDebt",
    "FinanceLeaseLiability", "LongTermDebtAndCapitalLeaseObligationsCurrent", "CapitalLeaseObligationsNoncurrent", "SecuredDebt",
    "NetIncomeLoss", "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
]


def get(url):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 * (i + 1))
        except Exception:  # noqa
            time.sleep(2 * (i + 1))
    raise RuntimeError("讀取失敗 " + url)


def concept(cik, name):
    d = get(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{name}.json")
    time.sleep(0.15)
    if not d:
        return []
    out = []
    for unit, facts in d["units"].items():
        for f in facts:
            out.append(dict(f, unit=unit))
    return out


def probe(cfg, only):
    for c in cfg["companies"]:
        if not c.get("cik") or not c.get("enabled") or (only and c["code"] != only):
            continue
        row = []
        for n in PROBE:
            fs = concept(c["cik"], n)
            if fs:
                row.append(f"{n}:{len(fs)}({min(f['end'] for f in fs)[:4]}-{max(f['end'] for f in fs)[:7]})")
        print(f"## {c['code']}\n  " + "\n  ".join(row), flush=True)


# ---------------------------------------------------------------------------------------------
# 提案模式：BS_MAP 是「每家公司每個欄位用哪些 XBRL 概念」的配方。配方依各公司最新 10-Q／10-K 資產負債表逐項對過
# （companies/<代號>/SOURCES.md 的「資產負債表欄位」一節寫明口徑）。任何一個必要成分在那一季讀不到 → 整個欄位 null，不做部分加總。
#   instant 欄位：{"all":[成分…]}，成分 ＝ 概念名單（第一個有值的）；"opt" 成分有就加、沒有當 0（只用於確實會是 0 的科目，如該期間沒有商業本票）
# ---------------------------------------------------------------------------------------------
BS_MAP = json.load(open(os.path.join(ROOT, "tools", "bs_map.json"), encoding="utf8")) if os.path.exists(os.path.join(ROOT, "tools", "bs_map.json")) else {}
FY_DAYS, Q_DAYS = (350, 380), (80, 100)


def dur(f):
    return (dt.date.fromisoformat(f["end"]) - dt.date.fromisoformat(f["start"])).days if f.get("start") else None


def latest(facts):
    """同一個 (start,end) 只留最後申報的那筆（最新、可能是重編後的）。"""
    best = {}
    for f in facts:
        k = (f.get("start"), f["end"])
        if k not in best or f["filed"] > best[k]["filed"]:
            best[k] = f
    return list(best.values())


def splits_for(symbol):
    try:
        import yfinance as yf
        sp = yf.Ticker(symbol).splits
        return [(d.strftime("%Y-%m-%d"), float(r)) for d, r in sp.items() if r and r != 1]
    except Exception as e:  # noqa
        print("  分割資料讀取失敗", e)
        return None


def factor(splits, filed):
    f = 1.0
    for d, r in splits:
        if d > filed:
            f *= r
    return f


def quarter_ends(ni_facts, ours):
    """用淨利對齊：回傳 [(end, 該季是否為第四季推算)] 對應 ours（無法對上填 None）。"""
    L = latest(ni_facts)
    cand = {}
    for f in L:
        d = dur(f)
        if d and Q_DAYS[0] <= d <= Q_DAYS[1]:
            cand[f["end"]] = f["val"] / 1e6
    # 第四季＝全年 − 前九個月（同一個 start）
    for f in L:
        d = dur(f)
        if d and FY_DAYS[0] <= d <= FY_DAYS[1]:
            n9 = [g for g in L if g.get("start") == f["start"] and 250 <= (dur(g) or 0) <= 290]
            if n9:
                cand.setdefault(f["end"], (f["val"] - n9[0]["val"]) / 1e6)
    ends = sorted(cand)
    out, ptr = [], 0
    for q in ours:
        hit = None
        for k in range(ptr, min(ptr + 4, len(ends))):
            if q.get("ni") is not None and abs(cand[ends[k]] - q["ni"]) <= 0.6:
                hit = k
                break
        if hit is None:
            out.append(None)
        else:
            out.append(ends[hit])
            ptr = hit + 1
    return out, ends


def inst(facts_by_name, names, end):
    for n in names:
        fs = [f for f in latest(facts_by_name.get(n, [])) if f["end"] == end and not f.get("start")]
        if fs:
            return fs[0], n
    return None, None


def flow(facts, end, prev_end, kind):
    """kind: q＝單季（10-Q 有 3 個月值，第四季＝全年－9 個月）；ytd＝現金流量表年初累計相減。"""
    L = latest(facts)
    if kind == "q":
        q = [f for f in L if f["end"] == end and f.get("start") and Q_DAYS[0] <= dur(f) <= Q_DAYS[1]]
        if q:
            return q[0], q[0]["val"]
        fy = [f for f in L if f["end"] == end and f.get("start") and FY_DAYS[0] <= dur(f) <= FY_DAYS[1]]
        if fy:
            n9 = [g for g in L if g.get("start") == fy[0]["start"] and 250 <= (dur(g) or 0) <= 290]
            if n9:
                return fy[0], fy[0]["val"] - n9[0]["val"]
        return None, None
    ytd = sorted([f for f in L if f["end"] == end and f.get("start") and dur(f) >= 80], key=lambda f: dur(f), reverse=True)
    ytd = [f for f in ytd if dur(f) <= 380]
    if not ytd:
        return None, None
    y = ytd[0]
    if dur(y) <= 100:
        return y, y["val"]
    pv = [f for f in L if f.get("start") == y["start"] and f["end"] == prev_end]
    return (y, y["val"] - pv[0]["val"]) if pv else (None, None)


def build(cfg, only):
    os.makedirs(os.path.join(ROOT, "data", "bs-raw"), exist_ok=True)
    for c in cfg["companies"]:
        if not c.get("cik") or not c.get("enabled") or (only and c["code"] != only):
            continue
        code = c["code"]
        M = BS_MAP.get(code)
        if not M:
            print(code, "沒有配方（tools/bs_map.json），略過")
            continue
        D = json.load(open(os.path.join(ROOT, "data", code + ".json"), encoding="utf8"))
        Q = D["quarters"]
        names = set(n for v in M.values() if isinstance(v, dict) for part in v.get("all", []) + v.get("opt", []) for n in part) | {"NetIncomeLoss"}
        names |= set(M.get("ni", ["NetIncomeLoss"]))
        F = {n: concept(c["cik"], n) for n in sorted(names)}
        ni_facts = [f for n in M.get("ni", ["NetIncomeLoss"]) for f in F.get(n, [])]
        ends, allends = quarter_ends(ni_facts, Q)
        splits = splits_for(c["price"]["yahoo"]) if c.get("price") else []
        if splits is None:
            print(code, "沒有分割資料 → 股數欄位不產生")
            splits = None
        out = {"code": code, "fetched": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"), "splits": splits, "quarters": []}
        for i, q in enumerate(Q):
            E = ends[i]
            row = {"q": q["q"], "end": E, "vals": {}, "prov": {}, "why": {}}
            if E is None:
                row["why"]["*"] = "淨利對不上 SEC 季度資料（可能早於 XBRL 或公司尚未上市）"
                out["quarters"].append(row)
                continue
            prev_end = ends[i - 1] if i > 0 and ends[i - 1] else None
            for field, spec in M.items():
                if field in ("ni", "shNote"):
                    continue
                kind = spec["kind"]
                if kind == "inst":
                    total, prov, bad = 0.0, [], False
                    for part in spec.get("all", []):
                        f, n = inst(F, part, E)
                        if not f:
                            bad = True
                            row["why"][field] = "缺 " + "/".join(part)
                            break
                        v = f["val"]
                        if spec.get("shares"):
                            if splits is None:
                                bad = True; row["why"][field] = "沒有分割資料"; break
                            v *= factor(splits, f["filed"])
                        total += v
                        prov.append({"c": n, "acc": f["accn"], "filed": f["filed"]})
                    if bad:
                        continue
                    for part in spec.get("opt", []):
                        f, n = inst(F, part, E)
                        if f:
                            total += f["val"]
                            prov.append({"c": n, "acc": f["accn"], "filed": f["filed"]})
                    row["vals"][field] = round(total / 1e6, 3)
                    row["prov"][field] = prov
                else:
                    f, v = None, None
                    for part in spec["all"][0]:
                        f, v = flow(F.get(part, []), E, prev_end, kind)
                        if f:
                            break
                    if f is None:
                        row["why"][field] = "讀不到單季值"
                        continue
                    if spec.get("shares"):
                        if splits is None:
                            row["why"][field] = "沒有分割資料"; continue
                        v *= factor(splits, f["filed"])
                    row["vals"][field] = round(v / 1e6, 3)
                    row["prov"][field] = [{"c": part, "acc": f["accn"], "filed": f["filed"]}]
            out["quarters"].append(row)
        n_ok = {k: sum(1 for r in out["quarters"] if k in r["vals"]) for k in M if k not in ("ni", "shNote")}
        print(code, f"季數 {len(Q)}，對齊 {sum(1 for e in ends if e)}，各欄位有值：{n_ok}", flush=True)
        with open(os.path.join(ROOT, "data", "bs-raw", code + ".json"), "w", encoding="utf8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=0)
            fh.write("\n")


def balance_probe(cfg, only):
    """companyfacts：列出每家公司最近一個資產負債表日、所有「現金／證券／投資／債務／借款／租賃／股數／權益」相關的概念與數值（用來訂 bs_map.json 配方）。"""
    import re
    pat = re.compile(r"Cash|Securit|Investment|Debt|Notes|Borrow|Lease|Paper|Equity|SharesOutstanding|Convertible", re.I)
    for c in cfg["companies"]:
        if not c.get("cik") or not c.get("enabled") or (only and c["code"] != only):
            continue
        d = get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c['cik']}.json")
        time.sleep(0.2)
        facts = d["facts"].get("us-gaap", {})
        ends = {}
        for name, v in facts.items():
            for unit, fs in v["units"].items():
                for f in fs:
                    if not f.get("start") and f.get("form") in ("10-Q", "10-K"):
                        ends[f["end"]] = ends.get(f["end"], 0) + 1
        top = sorted(ends)[-1]
        print(f"## {c['code']} 最近資產負債表日 {top}", flush=True)
        for name, v in sorted(facts.items()):
            if not pat.search(name):
                continue
            for unit, fs in v["units"].items():
                hit = [f for f in fs if f["end"] == top and not f.get("start")]
                if hit:
                    h = sorted(hit, key=lambda f: f["filed"])[-1]
                    print(f"  {name} [{unit}] {h['val']}")


def main():
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    only = sys.argv[sys.argv.index("--company") + 1] if "--company" in sys.argv else None
    if "--balance" in sys.argv:
        return balance_probe(cfg, only)
    if "--probe" in sys.argv:
        return probe(cfg, only)
    build(cfg, only)


if __name__ == "__main__":
    main()
