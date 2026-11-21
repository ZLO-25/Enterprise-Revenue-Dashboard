"""總經儀表板（tools/macro_fetch.py）的公式測試：FRED 解析、頻率判斷、年增率、方向燈、衰退期間、設定檔檢查。"""
import json
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import macro_fetch as M

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def monthly(vals, y0=2010, m0=1):
    out = []
    for i, v in enumerate(vals):
        y, m = y0 + (m0 - 1 + i) // 12, (m0 - 1 + i) % 12 + 1
        out.append((f"{y}-{m:02d}-01", float(v)))
    return out


class ParseTest(unittest.TestCase):
    def test_skips_missing_and_sorts(self):
        text = "observation_date,ICSA\n2026-01-10,200\n2026-01-03,.\n2026-01-17,\n2026-01-24,210\n"
        self.assertEqual(M.parse_fred_csv(text), [("2026-01-10", 200.0), ("2026-01-24", 210.0)])

    def test_rejects_html(self):
        with self.assertRaises(ValueError):
            M.parse_fred_csv("<html><body>Not Found</body></html>")

    def test_rejects_empty_series(self):
        with self.assertRaises(ValueError):
            M.parse_fred_csv("observation_date,X\n2026-01-01,.\n")


class FreqTest(unittest.TestCase):
    def test_detect(self):
        daily = [(f"2026-03-{d:02d}", 1.0) for d in (2, 3, 4, 5, 6, 9, 10, 11, 12, 13)]
        weekly = [(f"2026-0{m}-{d:02d}", 1.0) for m, d in ((1, 3), (1, 10), (1, 17), (1, 24), (1, 31), (2, 7))]
        quarterly = [("2025-01-01", 1.0), ("2025-04-01", 1.0), ("2025-07-01", 1.0), ("2025-10-01", 1.0)]
        self.assertEqual(M.detect_freq(daily), "d")
        self.assertEqual(M.detect_freq(weekly), "w")
        self.assertEqual(M.detect_freq(monthly(range(20))), "m")
        self.assertEqual(M.detect_freq(quarterly), "q")

    def test_month_last_keeps_real_date(self):
        pts = [("2026-01-05", 1.0), ("2026-01-30", 2.0), ("2026-02-03", 3.0), ("2026-02-04", 4.0)]
        self.assertEqual(M.month_last(pts), [("2026-01-30", 2.0), ("2026-02-04", 4.0)])


class TransformTest(unittest.TestCase):
    def test_yoy_same_month_last_year(self):
        pts = monthly([100] * 12 + [110] * 12)
        yoy = M.to_yoy(pts)
        self.assertEqual(len(yoy), 12)
        self.assertEqual(yoy[0][0], "2011-01-01")
        self.assertAlmostEqual(yoy[0][1], 10.0)

    def test_yoy_never_fills_gaps(self):
        pts = [("2024-01-01", 100.0), ("2025-02-01", 120.0), ("2025-03-01", 0.0), ("2026-03-01", 5.0)]
        self.assertEqual(M.to_yoy(pts), [])        # 去年同月沒有資料、或去年是 0 → 不算

    def test_yoy_quarterly(self):
        pts = [("2024-01-01", 100.0), ("2024-04-01", 100.0), ("2025-01-01", 105.0), ("2025-04-01", 98.0)]
        got = M.to_yoy(pts)
        self.assertEqual([d for d, _ in got], ["2025-01-01", "2025-04-01"])
        self.assertAlmostEqual(got[0][1], 5.0)
        self.assertAlmostEqual(got[1][1], -2.0)

    def test_chg(self):
        self.assertEqual(M.to_chg(monthly([10, 13, 12])), [("2010-02-01", 3.0), ("2010-03-01", -1.0)])

    def test_daily_reduced_to_month_before_yoy(self):
        raw = [(f"2024-{m:02d}-{d:02d}", 100.0) for m in range(1, 13) for d in (10, 11, 12, 13, 14, 17, 18, 19, 20, 21)] + \
              [(f"2025-{m:02d}-{d:02d}", 150.0) for m in range(1, 13) for d in (10, 11, 12, 13, 14, 17, 18, 19, 20, 21)]
        freq, pts, base = M.transform(raw, "yoy")
        self.assertEqual(freq, "d")
        self.assertEqual(len(base), 24)
        self.assertEqual(len(pts), 12)
        self.assertAlmostEqual(pts[-1][1], 50.0)
        self.assertEqual(pts[-1][0], "2025-12-21")

    def test_unknown_show(self):
        with self.assertRaises(ValueError):
            M.transform(monthly(range(20)), "ratio")


class StatsTest(unittest.TestCase):
    def wobble(self, n=150):
        # 平常半年大約上下 1 的鋸齒
        return [10 + (1 if (i // 6) % 2 else 0) + (i % 3) * 0.1 for i in range(n)]

    def test_flat_when_small_move(self):
        s = M.stats(monthly(self.wobble() + [10.5] * 7), "m", "up")
        self.assertEqual(s["light"], "flat")

    def test_worse_and_better_follow_bad_direction(self):
        vals = self.wobble() + [10, 11, 12, 13, 14, 15, 16]
        self.assertEqual(M.stats(monthly(vals), "m", "up")["light"], "worse")
        self.assertEqual(M.stats(monthly(vals), "m", "down")["light"], "better")

    def test_no_light_without_direction(self):
        s = M.stats(monthly(self.wobble() + [10, 11, 12, 13, 14, 15, 16]), "m", "")
        self.assertNotIn("light", s)
        self.assertIn("z", s)

    def test_no_light_with_short_history(self):
        s = M.stats(monthly([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), "m", "up")
        self.assertNotIn("light", s)          # 樣本不到兩年，不算標準差、不亮燈
        self.assertEqual(s["last"], 10.0)

    def test_three_year_low_and_percentile(self):
        vals = [50] * 100 + [40, 30, 20] + [25] * 10
        s = M.stats(monthly(vals), "m", "up")
        self.assertEqual(s["lo3"], 20.0)
        self.assertEqual(s["hi3"], 50.0)
        self.assertEqual(s["chg"], 0.0)       # 半年前也是 25
        self.assertTrue(0 < s["pct10"] < 30)

    def test_quarterly_uses_two_quarters(self):
        pts = [(f"{2000 + i // 4}-{(i % 4) * 3 + 1:02d}-01", float(v)) for i, v in enumerate([2, 3] * 30 + [3, 3, 9])]
        s = M.stats(pts, "q", "down")
        self.assertEqual(s["prev"], 3.0)
        self.assertEqual(s["chg"], 6.0)
        self.assertEqual(s["light"], "better")

    def test_empty(self):
        self.assertIsNone(M.stats([], "m", "up"))


class RecessionTest(unittest.TestCase):
    def test_ranges(self):
        pts = monthly([0, 0, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1])
        self.assertEqual(M.recession_ranges(pts), [["2010-03", "2010-05"], ["2010-08", "2010-08"], ["2010-11", "2010-12"]])


class BuildTest(unittest.TestCase):
    def test_build_series_trims_and_keeps_raw(self):
        spec = {"key": "x", "fred": "X", "name": "x", "show": "yoy", "bad": "down", "digits": 1}
        raw = monthly([100 + i for i in range(60)], y0=2020)
        out = M.build_series(spec, raw, "2023-01-01")
        self.assertEqual(out["freq"], "m")
        self.assertEqual(out["through"], "2024-12-01")
        self.assertEqual(out["points"][0][0], "2023-01-01")
        self.assertEqual(out["rawLast"], ["2024-12-01", 159.0])
        self.assertAlmostEqual(out["stats"]["last"], round((159 / 147 - 1) * 100, 3))

    def test_stale(self):
        now = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(M.is_stale({}, now))
        self.assertTrue(M.is_stale({"updated": "2026-11-15 00:00 UTC"}, now))
        self.assertFalse(M.is_stale({"updated": "2026-11-18 00:00 UTC"}, now))


class ConfigTest(unittest.TestCase):
    def test_config_is_well_formed(self):
        cfg = json.load(open(os.path.join(ROOT, "data", "macro", "config.json"), encoding="utf8"))
        keys, freds = set(), set()
        for g in cfg["groups"]:
            self.assertTrue(g["id"] and g["name"] and g["series"])
            for s in g["series"]:
                self.assertNotIn(s["key"], keys, "key 重複：" + s["key"])
                self.assertNotIn(s["fred"], freds, "FRED 代號重複：" + s["fred"])
                keys.add(s["key"]); freds.add(s["fred"])
                self.assertIn(s["show"], ("level", "yoy", "chg"))
                self.assertIn(s.get("bad", ""), ("", "up", "down"))
                for f in ("name", "unit", "book", "read"):
                    self.assertTrue(s.get(f), f"{s['key']} 缺 {f}")
        for l in cfg.get("links", []):
            for grp in l["items"]:
                self.assertTrue(grp["url"].startswith("https://"), grp["url"])


if __name__ == "__main__":
    unittest.main()
