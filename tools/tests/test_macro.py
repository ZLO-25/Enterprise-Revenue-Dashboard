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
        pts = [(f"{2000 + i // 4}-{(i % 4) * 3 + 1:02d}-01", float(v)) for i, v in enumerate([2, 3, 3, 2] * 15 + [3, 3, 9])]
        s = M.stats(pts, "q", "down")
        self.assertEqual(s["prev"], 3.0)
        self.assertEqual(s["chg"], 6.0)
        self.assertEqual(s["light"], "better")

    def test_empty(self):
        self.assertIsNone(M.stats([], "m", "up"))

    def test_outlier_does_not_mute_the_light(self):
        # 像 2020 年疫情：中間有一次極端跳動。用一般標準差的話之後的燈都不會亮；用中位數算的幅度不受影響
        vals = self.wobble(80) + [10, 500, 10, 10, 10, 10] + self.wobble(60) + [10, 11, 12, 13, 14, 15, 16]
        s = M.stats(monthly(vals), "m", "up")
        self.assertEqual(s["light"], "worse")
        self.assertLess(s["sd"], 5)

    def test_robust_sd(self):
        self.assertAlmostEqual(M.robust_sd([1, 2, 3, 4, 100]), 1.4826)
        self.assertEqual(M.robust_sd([5, 5, 5, 5]), 0)

    def test_no_light_when_series_never_moves(self):
        s = M.stats(monthly([3.0] * 100 + [4.0]), "m", "up")
        self.assertNotIn("light", s)          # 平常幅度是 0（例如長期不動的利率）→ 算不出 z，不亮燈


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


class TaiwanTest(unittest.TestCase):
    HEAD = '"Date","領先指標不含趨勢指數","景氣對策信號綜合分數","景氣對策信號"\n'

    def test_parse_skips_dash(self):
        text = self.HEAD + "198201,100.3,-,-\n202608,104.1,40,紅\n202609,104.7,41,紅\n"
        got = M.parse_ym_csv(text, ["領先指標不含趨勢指數", "景氣對策信號綜合分數", "景氣對策信號"])
        self.assertEqual(got["景氣對策信號綜合分數"], [("2026-08-01", 40.0), ("2026-09-01", 41.0)])
        self.assertEqual(len(got["領先指標不含趨勢指數"]), 3)
        self.assertEqual(got["景氣對策信號"][-1], ("2026-09-01", "紅"))

    def test_rejects_bad_input(self):
        for text in ("<html>error</html>", self.HEAD + "2026-09,1,1,紅\n", self.HEAD + "202609,1,40,紅\n202608,1,40,紅\n",
                     self.HEAD + "202609,1,40,紫\n", self.HEAD + "202613,1,40,紅\n"):
            with self.assertRaises(ValueError):
                M.parse_ym_csv(text, ["景氣對策信號綜合分數", "景氣對策信號"])

    def test_missing_column(self):
        with self.assertRaises(ValueError):
            M.parse_ym_csv("Date,PMI\n202609,50\n", ["PMI", "NMI"])

    def test_fetch_tw_marks_pending_on_failure(self):
        cfg = json.load(open(os.path.join(ROOT, "data", "macro", "config.json"), encoding="utf8"))
        orig = M.datagov_files
        M.datagov_files = lambda did: (_ for _ in ()).throw(OSError("網路不通"))
        try:
            tw, un = M.fetch_tw(cfg, "1990-01-01")
        finally:
            M.datagov_files = orig
        self.assertIsNone(tw)
        self.assertEqual(len(un), len(cfg["tw"]["files"]))
        self.assertTrue(all(u.startswith("待確認：") for u in un))

    def test_fetch_tw_ok(self):
        cfg = json.load(open(os.path.join(ROOT, "data", "macro", "config.json"), encoding="utf8"))
        rows = "".join(f"{2020 + i // 12}{i % 12 + 1:02d},{100 + i * 0.1:.2f},{100 + i * 0.05:.2f},{20 + i % 20},綠\n" for i in range(60))
        lights = '"Date","領先指標不含趨勢指數","同時指標不含趨勢指數","景氣對策信號綜合分數","景氣對策信號"\n' + rows
        pmi = "Date,PMI,NMI\n" + "".join(f"{2020 + i // 12}{i % 12 + 1:02d},{50 + i % 5},{'-' if i < 3 else 52}\n" for i in range(60))
        orig = M.datagov_files
        M.datagov_files = lambda did: [("schema-景氣指標與燈號.csv", "name,title\n"), ("景氣指標與燈號.csv", lights)] if did == 6099 else [("x.csv", pmi)]
        try:
            tw, un = M.fetch_tw(cfg, "1990-01-01")
        finally:
            M.datagov_files = orig
        self.assertEqual(un, [])
        self.assertEqual(sorted(tw["series"]), ["twcoin", "twlead", "twnmi", "twpmi", "twscore"])
        self.assertEqual(tw["light"], {"date": "2024-12", "name": "綠"})
        self.assertEqual(len(tw["lights"]), 36)
        self.assertEqual(len(tw["series"]["twnmi"]["points"]), 57)

    def test_fetch_tw_rejects_out_of_range_score(self):
        cfg = json.load(open(os.path.join(ROOT, "data", "macro", "config.json"), encoding="utf8"))
        rows = "".join(f"{2020 + i // 12}{i % 12 + 1:02d},100,100,{99 if i == 5 else 30},綠\n" for i in range(60))
        lights = '"Date","領先指標不含趨勢指數","同時指標不含趨勢指數","景氣對策信號綜合分數","景氣對策信號"\n' + rows
        orig = M.datagov_files
        M.datagov_files = lambda did: [("景氣指標與燈號.csv", lights)] if did == 6099 else (_ for _ in ()).throw(OSError("x"))
        try:
            tw, un = M.fetch_tw(cfg, "1990-01-01")
        finally:
            M.datagov_files = orig
        self.assertIsNone(tw)                 # 分數出現 99（不在 9～45）→ 整個檔不收
        self.assertEqual(len(un), 2)


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
        for s in cfg["tw"]["series"]:
            self.assertNotIn(s["key"], keys, "key 重複：" + s["key"])
            keys.add(s["key"])
            self.assertIn(s["file"], [f["id"] for f in cfg["tw"]["files"]])
            for f in ("name", "unit", "book", "read", "col"):
                self.assertTrue(s.get(f), f"{s['key']} 缺 {f}")
        self.assertEqual([p["id"] for p in cfg["phases"]], ["recovery", "growth", "boom", "recession"])
        for ph in cfg["phases"]:
            for ch in ph["checks"]:
                for k in ch["keys"]:
                    self.assertIn(k, keys, f"{ph['name']} 的對照表用了不存在的指標：{k}")
        self.assertTrue(cfg["links"])
        for l in cfg["links"]:
            for it in l["items"]:
                self.assertTrue(it["url"].startswith("https://"), it["url"])
                self.assertTrue(it["name"] and it["note"])


if __name__ == "__main__":
    unittest.main()
