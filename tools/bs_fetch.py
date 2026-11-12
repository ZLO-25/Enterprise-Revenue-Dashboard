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


def main():
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    only = sys.argv[sys.argv.index("--company") + 1] if "--company" in sys.argv else None
    if "--probe" in sys.argv:
        return probe(cfg, only)
    sys.exit("提案模式尚未設定 BS_MAP（先用 --probe 看各公司有哪些概念）")


if __name__ == "__main__":
    main()
