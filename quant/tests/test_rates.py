"""執行：python -m unittest discover -s quant/tests -p 'test_*.py'
檢查利率資料的整理規則（解析 FRED CSV、只留變動日、接兩段序列、月底值）。"""
import sys, unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fetch_rates  # noqa: E402
from fetch_rates import parse_fred_csv, compress_changes, month_end, stitch, parse_cbc_rediscount, parse_tpex_10y  # noqa: E402

CSV = "observation_date,DFEDTAR\n1997-12-31,5.50\n1998-01-02,5.50\n1998-01-05,.\n1998-01-06,5.50\n1998-01-07,5.25\n1998-01-08,5.25\n"


BDDYS100 = [  # 櫃買中心 BDdys100.20261113-C.xls 的實際內容（Actions 試抓，2026-11-17）
    ["債券等殖成交系統指標利率行情表 Daily", "", ""], ["日期 Date：2026/11/13", "", ""],
    ["到期年限(年)", "指標公債", "平均殖利率(%)"], ["Year", "Bond", "Average Yield(%)"],
    [2.0, "A15204", 1.5525], [5.0, "A15108", 1.71], [10.0, "A15109R", 1.93], [20.0, "A15107", 2.1159],
    ["註：", "", ""],
]


class RatesTest(unittest.TestCase):
    def test_tpex_10y(self):
        self.assertEqual(parse_tpex_10y(BDDYS100), ("A15109R", 1.93))
        old = [r[:] for r in BDDYS100]; old[6] = [10.0, "A94107 ", 1.798]   # 2005 年舊格式代號後有空白
        self.assertEqual(parse_tpex_10y(old), ("A94107", 1.798))

    def test_tpex_10y_rejects(self):
        with self.assertRaises(ValueError):
            parse_tpex_10y([["<html>404</html>"]])
        bad = [r[:] for r in BDDYS100]; bad[6] = [10.0, "B12345", 1.93]
        with self.assertRaises(ValueError):
            parse_tpex_10y(bad)
        no10 = [r for r in BDDYS100 if r[0] != 10.0]
        with self.assertRaises(ValueError):
            parse_tpex_10y(no10)

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

    def test_cbc_rediscount(self):
        head = '"日","重貼現(%)","擔保放款融通(%)","短期融通(%)"\n'
        rows = "".join(f'"{1990 + i // 2}{(i % 2) * 6 + 1:02d}01","{2 + (i % 5) * 0.125:.3f}","3.0","4.0"\n' for i in range(30))
        pts = parse_cbc_rediscount(head + rows)
        self.assertEqual(len(pts), 30)
        self.assertEqual(pts[0], ("1990-01-01", 2.0))
        with self.assertRaises(ValueError):
            parse_cbc_rediscount("<html>x</html>")
        with self.assertRaises(ValueError):
            parse_cbc_rediscount(head + '"20200101","2.0"\n' * 25)   # 日期沒遞增

class HttpGetRetry(unittest.TestCase):
    class Resp:
        def __init__(self, b): self.b = b
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self.b

    def test_retries_then_ok(self):
        calls = [OSError("x"), OSError("y"), self.Resp(b"ok")]
        def fake(req, timeout=0):
            r = calls.pop(0)
            if isinstance(r, Exception): raise r
            return r
        with mock.patch.object(fetch_rates.urllib.request, "urlopen", fake), mock.patch.object(fetch_rates.time, "sleep") as sl:
            self.assertEqual(fetch_rates.http_get("http://x"), "ok")
        self.assertEqual([c.args[0] for c in sl.call_args_list], [2, 4])

    def test_gives_up_after_three(self):
        n = []
        def fake(req, timeout=0):
            n.append(1); raise OSError("boom")
        with mock.patch.object(fetch_rates.urllib.request, "urlopen", fake), mock.patch.object(fetch_rates.time, "sleep"):
            with self.assertRaises(OSError):
                fetch_rates.http_get("http://x")
        self.assertEqual(len(n), 3)


if __name__ == "__main__":
    unittest.main()
