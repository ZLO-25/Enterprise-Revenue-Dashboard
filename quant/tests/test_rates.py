"""執行：python -m unittest discover -s quant/tests -p 'test_*.py'
檢查利率資料的整理規則（解析 FRED CSV、只留變動日、接兩段序列、月底值）。"""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from fetch_rates import parse_fred_csv, compress_changes, month_end, stitch  # noqa: E402

CSV = "observation_date,DFEDTAR\n1997-12-31,5.50\n1998-01-02,5.50\n1998-01-05,.\n1998-01-06,5.50\n1998-01-07,5.25\n1998-01-08,5.25\n"


class RatesTest(unittest.TestCase):
    def test_parse_skips_missing(self):
        pts = parse_fred_csv(CSV)
        self.assertEqual(len(pts), 5)           # '.' 不補
        self.assertEqual(pts[0], ("1997-12-31", 5.5))

    def test_parse_rejects_bad_header(self):
        with self.assertRaises(ValueError):
            parse_fred_csv("<html>blocked</html>\n")

    def test_compress_keeps_level_before_since_and_changes(self):
        out = compress_changes(parse_fred_csv(CSV), since="1998-01-01")
        self.assertEqual(out, [["1997-12-31", 5.5], ["1998-01-07", 5.25]])

    def test_month_end(self):
        pts = [("1999-12-31", 6.0), ("2000-01-03", 6.5), ("2000-01-31", 6.7), ("2000-02-01", 6.6)]
        self.assertEqual(month_end(pts, since="2000-01-01"), [["2000-01-31", 6.7], ["2000-02-01", 6.6]])

    def test_stitch(self):
        old = [("2008-12-15", 1.0), ("2008-12-16", 9.9)]
        new = [("2008-12-15", 8.8), ("2008-12-16", 0.25)]
        self.assertEqual(stitch(old, new, "2008-12-16"), [("2008-12-15", 1.0), ("2008-12-16", 0.25)])


if __name__ == "__main__":
    unittest.main()
