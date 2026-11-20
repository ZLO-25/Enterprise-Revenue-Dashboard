"""prices_update.adj_factor：Yahoo 已往回調整的分割／面額變更／股票股利，換回證交所當天原始價再比對。"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import prices_update as pu  # noqa: E402

ADJ = [{"ex": "2018-07-10", "r": 1.2}, {"ex": "2025-09-01", "r": 4}]


class AdjFactor(unittest.TestCase):
    def test_none(self):
        self.assertEqual(pu.adj_factor(None, "2020-01-31"), 1.0)
        self.assertEqual(pu.adj_factor([], "2020-01-31"), 1.0)

    def test_after_all_events(self):
        self.assertEqual(pu.adj_factor(ADJ, "2025-09-30"), 1.0)

    def test_ex_day_itself_is_new_basis(self):
        self.assertEqual(pu.adj_factor(ADJ, "2025-09-01"), 1.0)

    def test_between(self):
        self.assertEqual(pu.adj_factor(ADJ, "2024-12-31"), 4)

    def test_before_both(self):
        self.assertAlmostEqual(pu.adj_factor(ADJ, "2013-01-31"), 4.8)


class TwseRows(unittest.TestCase):
    def test_skip_no_trade_day(self):
        rows = [["107/04/02", "1", "1", "1", "1", "1", "1,050.00"], ["107/04/03", "0", "0", "--", "--", "--", "--"]]
        self.assertEqual(pu.parse_twse_rows(rows), {"2018-04-02": 1050.0})


if __name__ == "__main__":
    unittest.main()
