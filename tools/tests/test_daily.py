import datetime as dt, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import daily


class SecHint(unittest.TestCase):
    today = dt.date(2026, 11, 18)

    def test_new_8k_newer_than_rd(self):
        f = {"earnings8k": [{"date": "2026-11-17"}]}
        self.assertTrue(daily.sec_hint(f, "2026-08-20", [], self.today))

    def test_announced_future_date_suppresses(self):   # MRVL 型誤報
        f = {"earnings8k": [{"date": "2026-11-02"}]}
        self.assertFalse(daily.sec_hint(f, "2026-08-28", [{"date": "2026-12-01", "t": "x"}], self.today))

    def test_est_future_does_not_suppress(self):
        f = {"earnings8k": [{"date": "2026-11-17"}]}
        self.assertTrue(daily.sec_hint(f, "2026-08-20", [{"date": "2026-12-01", "est": True}], self.today))

    def test_no_feed(self):
        self.assertFalse(daily.sec_hint(None, "2026-08-20", [], self.today))


class Missed(unittest.TestCase):
    def test_weekdays_only(self):
        # 上次成功週六 11/14，今天週三 11/18 → 缺週二 11/17 之前：日、一不算
        self.assertEqual(daily.missed_days("2026-11-14", dt.date(2026, 11, 18)), ["2026-11-17"])

    def test_none(self):
        self.assertEqual(daily.missed_days("2026-11-17", dt.date(2026, 11, 18)), [])




class AddMonths(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(daily.add_months(dt.date(2026, 12, 12), 3), dt.date(2027, 3, 12))

    def test_end_of_month(self):
        self.assertEqual(daily.add_months(dt.date(2026, 11, 30), 3), dt.date(2027, 2, 28))


class StoryLine(unittest.TestCase):
    def test_custom_and_default_names(self):
        D = {"story": {"t": "AI", "cats": ["arch", "product"]}, "categories": {"arch": "AI 晶片世代"}}
        self.assertEqual(daily.story_line(D), "核心故事線：AI［arch=AI 晶片世代、product=產品］")

    def test_missing(self):
        self.assertIn("缺", daily.story_line({}))


class DailyValuationSync(unittest.TestCase):
    def test_daily_ey_spread_and_implied_g(self):
        import daily_calc as DC
        Q = [{"q": f"{i + 1}Q25", "eps": 1.0, "rd": f"2025-{3 * i + 2:02d}-01", "rev": 100.0, "ocf": 30.0, "capex": 10.0,
              "shOut": 10.0, "debt": 50.0, "cash": 150.0} for i in range(4)]
        rows = [["2026-01-05", 40.0]]  # PE = 10.0 -> EY = 10.0%
        rates = {"series": {"us_10y": {"points": [["2026-01-05", 4.0]]}}}
        L = DC.latest(Q, Q, rows, valuation={"currency": "USD"}, rates=rates)
        self.assertEqual(L["ey"], 10.0)
        self.assertEqual(L["bond"], 4.0)
        self.assertEqual(L["eySpread"], 6.0)
        self.assertIsNotNone(L["impliedG"]["15"])
        self.assertIsNotNone(L["impliedG"]["20"])


if __name__ == "__main__":
    unittest.main()
