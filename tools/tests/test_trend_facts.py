import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import trend_facts as T


class CalQ(unittest.TestCase):
    def test_fiscal_years(self):
        self.assertEqual(T.cal_q("1Q27", "06-30"), "2026Q3")   # MSFT 7～9 月
        self.assertEqual(T.cal_q("3Q27", "01-31"), "2026Q3")   # NVDA 8～10 月
        self.assertEqual(T.cal_q("4Q26", "09-26"), "2026Q3")   # AAPL 52/53 週
        self.assertEqual(T.cal_q("3Q26", "12-31"), "2026Q3")
        self.assertIsNone(T.cal_q("FY26", "12-31"))

    def test_prior_and_pct(self):
        self.assertEqual(T.prior_year("1Q09"), "1Q08")
        self.assertAlmostEqual(T.pct(150, 100), 50)
        self.assertIsNone(T.pct(1, 0))
        self.assertIsNone(T.pct(1, -5))   # 基期虧損不算年增
        self.assertIsNone(T.pct(None, 5))


class Hyper(unittest.TestCase):
    def test_only_full_quarters(self):
        mk = lambda fye, qs: {"company": {"fiscalYearEnd": fye}, "quarters": [{"q": q, "capex": v} for q, v in qs]}
        datas = {"msft": mk("06-30", [("1Q26", 10), ("1Q27", 20)]), "amzn": mk("12-31", [("3Q25", 10), ("3Q26", 20)]),
                 "googl": mk("12-31", [("3Q25", 10), ("3Q26", 20)]), "meta": mk("12-31", [("3Q25", 10)])}
        self.assertEqual(T.hyper_capex(datas), [("2025Q3", 40, None)])


if __name__ == "__main__":
    unittest.main()
