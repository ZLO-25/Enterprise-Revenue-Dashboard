"""總經儀表板（tools/macro_fetch.py）的公式測試：FRED 解析、頻率判斷、年增率、方向燈、衰退期間、設定檔檢查。"""
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

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
        self.assertEqual(s["fromLo3"], 25.0)   # 25 比三年低點 20 高 25%
        self.assertEqual(s["fromHi3"], -50.0)

    def test_no_distance_when_low_is_not_positive(self):
        s = M.stats(monthly([1, -2, 3, -1, 2] * 10), "m", "down")
        self.assertNotIn("fromLo3", s)

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
        self.assertTrue(M.is_stale({"updated": (now - timedelta(hours=19)).strftime("%Y-%m-%d %H:%M UTC")}, now))      # 昨天這個時候抓的 → 今天要重抓
        self.assertFalse(M.is_stale({"updated": (now - timedelta(hours=6)).strftime("%Y-%m-%d %H:%M UTC")}, now))      # 同一天稍早抓過 → 跳過


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
        ym = [f"{2020 + i // 12}{i % 12 + 1:02d}" for i in range(60)]
        rows = "".join(f"{d},{100 + i * 0.1:.2f},{100 + i * 0.05:.2f},{20 + i % 12 if i % 24 < 12 else 32 + i % 6},{'綠' if i % 24 < 12 else '黃紅'}\n" for i, d in enumerate(ym))
        lights = '"Date","領先指標不含趨勢指數","同時指標不含趨勢指數","景氣對策信號綜合分數","景氣對策信號"\n' + rows
        # 官方檔的欄名帶單位與基期；最後一個月有的欄還沒公布（空白）
        comp = ('"Date","貨幣總計數M1B(百萬元)","股價指數(Index1966=100)","工業生產指數(Index2021=100)","工業及服務業加班工時(小時)","海關出口值(十億元)",'
                '"機械及電機設備進口值(十億元)","製造業銷售量指數(Index2021=100)","批發、零售及餐飲業營業額(十億元)"\n'
                + "".join(f"{d},{1000 + i},{10000 + 50 * i},{90 + i * 0.3:.1f},8.9,{1000 + 10 * i},{500 + 3 * i},{'' if i == 59 else 100 + i},{2000 + i}\n" for i, d in enumerate(ym)))
        leadc = ('"Date","外銷訂單動向指數(以家數計)","貨幣總計數M1B(百萬元)","股價指數(Index1966=100)","工業及服務業受僱員工淨進入率(%)",'
                 '"建築物開工樓地板面積(住宅類住宅、商業辦公、工業倉儲)(千平方公尺)","名目半導體設備進口(新臺幣百萬元)"\n'
                 + "".join(f"{d},{50 + i % 7},{1000 + i},{10000 + 50 * i},0.1,1500,{100000 + 500 * i}\n" for i, d in enumerate(ym)))
        pmi = "Date,PMI,NMI\n" + "".join(f"{d},{50 + i % 5},{'-' if i < 3 else 52}\n" for i, d in enumerate(ym))
        calls = []
        orig = M.datagov_files

        def fake(did):
            calls.append(did)
            if did == 6099:
                return [("schema-景氣指標與燈號.csv", "name,title\n"), ("景氣指標與燈號.csv", lights), ("景氣對策信號構成項目.csv", comp), ("領先指標構成項目.csv", leadc)]
            return [("x.csv", pmi)]
        M.datagov_files = fake
        try:
            tw, un = M.fetch_tw(cfg, "1990-01-01")
        finally:
            M.datagov_files = orig
        self.assertEqual(un, [])
        self.assertEqual(sorted(tw["series"]), sorted(s["key"] for s in cfg["tw"]["series"]))
        self.assertEqual(calls.count(6099), 1)                      # 同一個 ZIP 只下載一次
        self.assertEqual(tw["light"], {"date": "2024-12", "name": "綠"})
        self.assertEqual(len(tw["lights"]), 36)
        self.assertEqual(len(tw["series"]["twnmi"]["points"]), 57)
        self.assertEqual(tw["scoreRanges"], {"綠": [20.0, 31.0], "黃紅": [32.0, 37.0]})      # 分數範圍從官方檔的配對算出來
        exp = tw["series"]["twexp"]
        self.assertEqual(exp["points"][0][0], "2021-01-01")          # 年增率：第一年沒有去年同期，不算
        self.assertAlmostEqual(exp["points"][-1][1], (1590 / 1470 - 1) * 100, places=2)
        self.assertEqual(exp["rawLast"], ["2024-12-01", 1590.0])

    def test_column_prefix_match(self):
        text = '"Date","海關出口值(十億元)","海關出口值年增率(%)"\n202401,1,2\n'
        with self.assertRaises(ValueError):                         # 開頭一樣的有兩欄 → 不猜
            M.parse_ym_csv(text, ["海關出口值"])
        self.assertEqual(M.parse_ym_csv(text, ["海關出口值(十億元)"])["海關出口值(十億元)"], [("2024-01-01", 1.0)])

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
        # 分數出現 99（不在 9～45）→ 分數與燈號都不收（同一張表的其他欄不受拖累），並標待確認
        self.assertNotIn("twscore", tw["series"])
        self.assertIsNone(tw["light"])
        self.assertEqual(tw["lights"], [])
        self.assertIn("twlead", tw["series"])
        self.assertTrue(any("景氣對策信號綜合分數" in u for u in un))
        self.assertTrue(all(u.startswith("待確認：") for u in un))


class DerivedTest(unittest.TestCase):
    def test_ann3(self):
        pts = monthly([100, 101, 102, 103, 104], 2025, 1)
        out = M.to_ann(pts, 3)
        self.assertEqual([d for d, _ in out], ["2025-04-01", "2025-05-01"])
        self.assertAlmostEqual(out[0][1], ((103 / 100) ** 4 - 1) * 100)
        with self.assertRaises(ValueError):
            M.transform([("2024-01-01", 1.0), ("2024-04-01", 2.0), ("2024-07-01", 3.0), ("2024-10-01", 4.0)], "ann3")

    def test_ratio_uses_last_value_in_quarter_and_never_fills(self):
        num = [("2025-01-08", 10.0), ("2025-03-26", 30.0), ("2025-04-02", 40.0), ("2025-10-01", 99.0)]
        den = [("2025-01-01", 2.0), ("2025-04-01", 4.0), ("2025-07-01", 5.0), ("2025-10-01", 0.0)]
        # 第一季取 3 月那筆；第二季只有 4 月；第三季 num 沒資料 → 不算；第四季分母是 0 → 不算
        self.assertEqual(M.ratio_points(num, den, 0.5), [("2025-01-01", 7.5), ("2025-04-01", 5.0)])

    def test_diff_only_where_both_exist(self):
        a, b = monthly([5, 6, 7], 2025, 1), monthly([1, 1], 2025, 2)
        self.assertEqual(M.diff_points(a, b), [("2025-02-01", 5.0), ("2025-03-01", 6.0)])

    def test_run_len(self):
        self.assertEqual(M.run_len(monthly([5, 6, 5, 4, 3]), -1), 3)
        self.assertEqual(M.run_len(monthly([5, 6, 5, 4, 3]), 1), 0)
        self.assertEqual(M.run_len(monthly([3, 3, 4]), 1), 1)

    def test_base_effect(self):
        yoy = monthly([2.0] * 30 + [9.0] + [2.0] * 12)       # 去年同期那一筆特別高
        base, pct = M.base_effect(yoy, "m")
        self.assertEqual(base, 9.0)
        self.assertEqual(pct, 100)
        self.assertIsNone(M.base_effect(monthly([1.0] * 20), "m"))


class LightHistoryTest(unittest.TestCase):
    def series(self):
        import math
        vals = [100 + 3 * math.sin(i / 5) for i in range(150)] + [100 + 3 * math.sin(149 / 5) + 4 * (i + 1) for i in range(8)]
        return monthly(vals, 2010, 1)

    def test_history_matches_stats_at_every_point(self):
        """回算歷史用的燈，和「當時只看到那裡為止的資料」算出來的燈必須一樣（不能偷看未來）。"""
        pts = self.series()
        hist = dict(M.light_series(pts, "m", "up"))
        for i in (40, 90, 149, 157):
            st = M.stats(pts[:i + 1], "m", "up")
            self.assertEqual(hist.get(pts[i][0]), st.get("light"))

    def test_light_since_and_prev(self):
        st = M.stats(self.series(), "m", "up")
        self.assertEqual(st["light"], "worse")
        self.assertIn("lightSince", st)
        self.assertLess(st["lightSince"], st["lastDate"])
        self.assertIn(st["lightPrev"], ("flat", "better"))

    def test_threshold_from_config(self):
        pts = self.series()[:150]
        z = abs(M.stats(pts, "m", "up")["z"])
        self.assertEqual(M.stats(pts, "m", "up", thr=z + 0.1)["light"], "flat")
        self.assertNotEqual(M.stats(pts, "m", "up", thr=max(z - 0.1, 0.01))["light"], "flat")

    def test_score_counts_items_not_series(self):
        lights = {"a": [("2020-01-01", "worse"), ("2020-02-01", "flat")], "b": [("2020-01-01", "worse")], "q": [("2019-10-01", "worse")]}
        sc = M.score_series(lights, [["a", "b"], ["q"], ["zz"]], "2020-01", "2020-06")
        self.assertEqual(sc["months"][0], "2020-01")
        self.assertEqual(sc["boom"][0], 2)            # a、b 同一項只算一次；q 是季資料，往前找 3 個月內的最新一筆
        self.assertEqual(sc["worse"][0], 3)
        self.assertEqual(sc["boom"][1], 1)            # 2 月：a 轉持平，b 沿用 1 月（最近 4 個月內）→ 第一項還亮；q 已超過 4 個月
        self.assertEqual(sc["boom"][5], 0)            # 太久沒有新資料的不沿用
        self.assertEqual(sc["n"][5], 0)

    def test_score_table(self):
        sc = {"months": [M.month_add("2019-01", i) for i in range(24)], "boom": [0] * 6 + [3] * 6 + [5] * 6 + [1] * 6}
        t = M.score_table(sc, [["2020-07", "2020-09"]], 7)
        self.assertEqual(t["recessions"], [{"start": "2020-07", "end": "2020-09", "preMax": 5, "atStart": 1}])
        self.assertEqual(sum(sum(v) for v in t["dist"].values()), 24)
        self.assertEqual(t["dist"]["rec"][1], 3)
        self.assertEqual(t["dist"]["pre"][5], 6)


class ReminderTest(unittest.TestCase):
    S = {"vix": {"light": "worse", "last": 30, "pct10": 95}, "icsa4": {"light": "flat"}, "ccsa": {"light": "better"},
         "rpceq": {"downRun": 4, "last": 1.2}, "twexp": {"basePct10": 90}, "gsgap": {"last": -0.5}}

    def test_conditions(self):
        E = lambda c, **k: M.eval_cond(c, self.S, **k)
        self.assertTrue(E({"key": "vix", "light": "worse"}))
        self.assertTrue(E({"all": [{"key": "vix", "light": "worse"}, {"count": {"keys": ["icsa4", "ccsa"], "light": "worse", "max": 0}}]}))
        self.assertFalse(E({"count": {"keys": ["icsa4", "ccsa", "vix"], "light": "worse", "max": 0}}))
        self.assertTrue(E({"key": "rpceq", "downRun": 3}))
        self.assertFalse(E({"key": "rpceq", "downRun": 5}))
        self.assertTrue(E({"key": "gsgap", "lt": 0}))
        self.assertTrue(E({"key": "twexp", "baseHi": 85}))
        self.assertFalse(E({"key": "twexp", "baseLo": 15}))
        self.assertTrue(E({"key": "vix", "pctHi": 90}))
        self.assertTrue(E({"not": {"key": "icsa4", "light": "worse"}}))
        self.assertTrue(E({"tw": "紅"}, tw={"name": "紅"}))
        self.assertFalse(E({"tw": "紅"}, tw=None))
        self.assertTrue(E({"boom": {"min": 1, "max": 2}}, boom=2))
        self.assertFalse(E({"boom": {"min": 4}}, boom=None))

    def test_missing_data_never_fires(self):
        for c in ({"key": "nope", "light": "worse"}, {"key": "nope", "lt": 0}, {"key": "nope", "downRun": 1}, {"key": "icsa4", "gt": 1}):
            self.assertFalse(M.eval_cond(c, self.S))

    def test_unknown_condition_raises(self):
        with self.assertRaises(ValueError):
            M.eval_cond({"key": "vix", "bogus": 1}, self.S)


class HealthTest(unittest.TestCase):
    def test_stale_by_frequency(self):
        specs = [{"key": "w", "name": "週"}, {"key": "m", "name": "月"}, {"key": "q", "name": "季", "maxLag": 400}, {"key": "gone", "name": "沒資料"}]
        series = {"w": {"freq": "w", "through": "2026-10-01"}, "m": {"freq": "m", "through": "2026-09-01"}, "q": {"freq": "q", "through": "2025-12-01"}}
        out = M.stale_series(specs, series, "2026-11-21")
        self.assertEqual([x["key"] for x in out], ["w"])       # 週資料 51 天沒更新 → 停更；月資料 81 天、季資料有自訂上限 → 正常
        self.assertEqual(out[0]["days"], 51)

    def test_dead_links_only_404(self):
        cfg = {"links": [{"items": [{"url": "https://a/"}, {"url": "https://b/"}, {"url": "https://c/"}]}],
               "concepts": [{"src": {"url": "https://d/"}}], "about": {"notes": [{"url": "https://a/"}]}}
        st = {"https://a/": 200, "https://b/": 403, "https://c/": 404, "https://d/": "URLError: timeout"}
        self.assertEqual(M.dead_links(cfg, status=lambda u: st[u]), ["https://c/"])


class BuildDocTest(unittest.TestCase):
    """整條流程用假資料跑一次：設定檔裡每一條都要算得出來，而且一條抓不到不能拖垮整份。"""

    QUARTERLY = {"GDP", "GDPC1", "PCECC96", "NCBEILQ027S", "NFCPATAX", "GPDIC1", "OPHNFB", "DRCLACBS", "DRBLACBS", "DRCCLACBS", "DRTSCILM", "CP",
                 "PNFIC1", "PRFIC1", "SLEXPND", "A006RL1Q225SBEA", "DPCERL1Q225SBEA"}

    def fake(self, fid):
        import math
        if fid == "BROKEN":
            raise OSError("404")
        if fid == "USREC":
            return [(f"{y}-{m:02d}-01", 1.0 if y == 2008 else 0.0) for y in range(1990, 2027) for m in range(1, 13)]
        step = 3 if fid in self.QUARTERLY else 1
        seed = sum(map(ord, fid))
        return [(f"{y}-{m:02d}-01", 100 + 10 * math.sin((y * 12 + m + seed) / 9.0) + (y - 1985) * 0.5)
                for y in range(1985, 2027) for m in range(1, 13, step) if (y, m) <= (2026, 10)]

    def run_doc(self, cfg, prev=None):
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            return M.build_doc(cfg, prev or {}, fetch=self.fake, tw_fetch=lambda c, s: (None, []), link_check=lambda c: ["https://dead/"],
                               now=datetime(2026, 11, 21, tzinfo=timezone.utc))

    def test_whole_config_builds(self):
        cfg = json.load(open(os.path.join(ROOT, "data", "macro", "config.json"), encoding="utf8"))
        doc, ok, total = self.run_doc(cfg)
        self.assertEqual(ok, total)
        self.assertEqual(doc["unavailable"], [])
        self.assertEqual(doc["links"], {"checked": "2026-11-21", "dead": ["https://dead/"]})
        self.assertEqual(doc["health"]["stale"], [])
        sc = doc["score"]
        self.assertEqual(sc["months"][0], cfg["score"]["start"])
        self.assertEqual(len(sc["months"]), len(sc["boom"]))
        self.assertEqual(sc["items"], 7)
        self.assertTrue(all(0 <= b <= 7 for b in sc["boom"]))
        self.assertEqual(sc["table"]["recessions"][0]["start"], "2008-01")
        self.assertEqual(doc["boomNow"], sc["boom"][-1])       # 現在亮幾項，和回算序列的最後一個月是同一個算法
        self.assertTrue(set(doc["reminders"]) <= {r["id"] for r in cfg["reminders"]})
        self.assertIn("formula", doc["series"]["mcapgdp"])
        self.assertEqual(doc["series"]["gsgap"]["parts"], ["rpceg", "rpces"])

    def test_one_failure_keeps_old_data_and_marks_pending(self):
        cfg = {"groups": [{"id": "g", "series": [
            {"key": "a", "fred": "AAA", "name": "甲", "unit": "", "show": "level", "bad": "up", "digits": 1},
            {"key": "b", "fred": "BROKEN", "name": "乙", "unit": "", "show": "level", "bad": "up", "digits": 1},
            {"key": "c", "fred": "BROKEN", "name": "丙", "unit": "", "show": "level", "bad": "up", "digits": 1},
            {"key": "d", "diff": ["a", "b"], "name": "丁", "unit": "", "show": "level", "bad": "", "digits": 1}]}],
            "reminders": [{"id": "bad", "when": {"key": "a", "bogus": 1}}, {"id": "ok", "when": {"key": "a", "gt": 0}}]}
        old = {"series": {"b": {"freq": "m", "through": "2026-01-01", "stats": {"last": 1.0, "light": "worse"}, "points": [["2026-01-01", 1.0]]}}}
        doc, ok, total = self.run_doc(cfg, old)
        self.assertEqual((ok, total), (1, 4))
        self.assertEqual(doc["series"]["b"], old["series"]["b"])            # 沿用舊資料
        self.assertNotIn("c", doc["series"])                                # 從沒抓到過 → 不顯示
        self.assertNotIn("d", doc["series"])                                # 對不上的月份太少 → 不硬算
        self.assertEqual(doc["reminders"], ["ok"])
        self.assertEqual(len(doc["unavailable"]), 4)
        self.assertTrue(all(u.startswith("待確認：") for u in doc["unavailable"]))
        self.assertEqual([x["key"] for x in doc["health"]["stale"]], ["b"])  # 沿用太久的舊資料會被標成停更


class ConfigTest(unittest.TestCase):
    def test_config_is_well_formed(self):
        cfg = json.load(open(os.path.join(ROOT, "data", "macro", "config.json"), encoding="utf8"))
        keys, freds, specs = set(), set(), {}
        for g in cfg["groups"]:
            self.assertTrue(g["id"] and g["name"] and g["series"])
            for s in g["series"]:
                self.assertNotIn(s["key"], keys, "key 重複：" + s["key"])
                keys.add(s["key"]); specs[s["key"]] = s
                self.assertEqual(sum(1 for f in ("fred", "ratio", "diff") if s.get(f)), 1, f"{s['key']} 要剛好有 fred／ratio／diff 其中一個")
                if s.get("fred"):
                    self.assertNotIn((s["fred"], s["show"]), freds, "同一個 FRED 代號用同一種算法出現兩次：" + s["fred"])
                    freds.add((s["fred"], s["show"]))
                if s.get("ratio"):
                    self.assertTrue(s["ratio"]["num"] and s["ratio"]["den"] and s["ratio"].get("mult"))
                self.assertIn(s["show"], ("level", "yoy", "chg", "ann3"))
                self.assertIn(s.get("bad", ""), ("", "up", "down"))
                for f in ("name", "unit", "book", "read"):
                    self.assertTrue(s.get(f), f"{s['key']} 缺 {f}")
        for s in list(specs.values()) + cfg["tw"]["series"]:
            if s["show"] in ("yoy", "ann3"):
                self.assertEqual(s["unit"], "%", f"{s['key']} 顯示的是年增率，單位要寫 %（原始單位不會顯示）")
        order = [s["key"] for g in cfg["groups"] for s in g["series"]]
        for s in specs.values():
            for part in s.get("diff", []):
                self.assertIn(part, keys, f"{s['key']} 相減用了不存在的指標：{part}")
        for s in cfg["tw"]["series"]:
            self.assertNotIn(s["key"], keys, "key 重複：" + s["key"])
            keys.add(s["key"])
            self.assertIn(s["file"], [f["id"] for f in cfg["tw"]["files"]])
            self.assertIn(s["show"], ("level", "yoy", "chg"))
            for f in ("name", "unit", "book", "read", "col"):
                self.assertTrue(s.get(f), f"{s['key']} 缺 {f}")
        self.assertEqual([p["id"] for p in cfg["phases"]], ["recovery", "growth", "boom", "recession"])
        for ph in cfg["phases"]:
            for ch in ph["checks"]:
                for k in ch["keys"]:
                    self.assertIn(k, keys, f"{ph['name']} 的對照表用了不存在的指標：{k}")
        self.assertEqual(len(next(p for p in cfg["phases"] if p["id"] == "boom")["checks"]), 7)
        self.assertTrue(cfg["links"])
        for l in cfg["links"]:
            for it in l["items"]:
                self.assertTrue(it["url"].startswith("https://"), it["url"])
                self.assertTrue(it["name"] and it["note"])
        self.assertGreater(cfg["light"]["threshold"], 0)
        self.assertTrue(order)

    def test_teaching_content_is_sourced(self):
        """教學內容的規矩：每一則「他怎麼想」都要指到來源清單；提醒的條件只能用存在的指標，而且格式要看得懂。"""
        cfg = json.load(open(os.path.join(ROOT, "data", "macro", "config.json"), encoding="utf8"))
        keys = {s["key"] for g in cfg["groups"] for s in g["series"]} | {s["key"] for s in cfg["tw"]["series"]}
        src = cfg["about"]["sources"]
        for sid, x in src.items():
            self.assertTrue(x["name"] and x["kind"], sid)
            self.assertTrue(x["url"] == "" or x["url"].startswith("http"), sid)
        ids = set()
        for c in cfg["concepts"]:
            self.assertNotIn(c["id"], ids); ids.add(c["id"])
            self.assertTrue(c["title"] and c["text"] and c["srcs"], c["id"])
            for sid in c["srcs"]:
                self.assertIn(sid, src, f"{c['id']} 的出處不在來源清單：{sid}")
            for k in c.get("keys", []):
                self.assertIn(k, keys, f"{c['id']} 用了不存在的指標：{k}")
        rids = set()

        def walk(c):
            for sub in c.get("all", []) + c.get("any", []) + ([c["not"]] if "not" in c else []):
                yield from walk(sub)
            if "count" in c:
                for k in c["count"]["keys"]:
                    yield k
            if "key" in c:
                yield c["key"]
        S = {k: {} for k in keys}
        for r in cfg["reminders"]:
            self.assertNotIn(r["id"], rids); rids.add(r["id"])
            self.assertTrue(r["title"] and r["text"], r["id"])
            self.assertIn(r["concept"], ids, f"{r['id']} 指到不存在的觀念：{r['concept']}")
            self.assertIn(r.get("level"), ("calm", "watch"))
            for k in list(walk(r["when"])) + r.get("keys", []):
                self.assertIn(k, keys, f"{r['id']} 用了不存在的指標：{k}")
            M.eval_cond(r["when"], S, None, 0)      # 條件格式不對會丟錯
        for g in cfg["glossary"]:
            self.assertTrue(g["term"] and g["text"])
        self.assertGreaterEqual(len(cfg["howto"]), 3)


if __name__ == "__main__":
    unittest.main()
