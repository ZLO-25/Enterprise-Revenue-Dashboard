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


if __name__ == "__main__":
    unittest.main()
