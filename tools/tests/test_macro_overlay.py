"""美元・利率・通膨對照圖的資料（tools/macro_overlay.py）：收盤判斷、K 棒清理、目標區間、失敗沿用。不上網。"""
import contextlib
import io
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import macro_overlay as O  # noqa: E402


class PureTest(unittest.TestCase):
    def test_cutoff_waits_for_us_close(self):
        # 2026-11-24 21:00 UTC＝美東 16:00（還沒過 17:15）→ 只收到前一天
        self.assertEqual(O.closed_cutoff(datetime(2026, 11, 24, 21, 0, tzinfo=timezone.utc)), "2026-11-23")
        # 2026-11-24 23:00 UTC＝美東 18:00 → 當天收完
        self.assertEqual(O.closed_cutoff(datetime(2026, 11, 24, 23, 0, tzinfo=timezone.utc)), "2026-11-24")
        # 台北早上（UTC 前一天深夜）→ 美東前一天已收完
        self.assertEqual(O.closed_cutoff(datetime(2026, 11, 25, 0, 30, tzinfo=timezone.utc)), "2026-11-24")

    def test_clean_ohlc_drops_nan_bad_and_unclosed(self):
        nan = float("nan")
        rows = [("1999-12-31", 1, 1, 1, 1), ("2026-01-02", 100, 101, 99, 100.5), ("2026-01-05", nan, nan, nan, nan),
                ("2026-01-06", 100, 99, 98, 100), ("2026-01-07", 100, 102, 99, 101), ("2026-01-08", 101, 103, 100, 102)]
        bars, pending = O.clean_ohlc(rows, "2026-01-07")
        self.assertEqual([b[0] for b in bars], ["2026-01-02", "2026-01-07"])
        self.assertEqual([p["date"] for p in pending], ["2026-01-06"])
        self.assertTrue(pending[0]["reason"].startswith("待確認："))

    def test_target_steps_only_changes(self):
        single = [("1999-12-30", 5.5), ("2000-01-03", 5.5), ("2000-02-02", 5.75), ("2000-02-03", 5.75), ("2008-12-15", 1.0)]
        lo = [("2008-12-16", 0.0), ("2008-12-17", 0.0), ("2015-12-17", 0.25)]
        hi = [("2008-12-16", 0.25), ("2008-12-17", 0.25), ("2015-12-17", 0.5)]
        self.assertEqual(O.target_steps(single, lo, hi), [["2000-01-03", 5.5, 5.5], ["2000-02-02", 5.75, 5.75], ["2008-12-15", 1.0, 1.0],
                                                          ["2008-12-16", 0.0, 0.25], ["2015-12-17", 0.25, 0.5]])


class BuildTest(unittest.TestCase):
    NOW = datetime(2026, 11, 25, 0, 30, tzinfo=timezone.utc)

    def fred(self, fid):
        if fid == "CPIAUCSL":
            return [(f"{y}-{m:02d}-01", 100 + (y - 2000) * 3 + m * 0.1) for y in range(1999, 2027) for m in range(1, 13) if (y, m) <= (2026, 10)]
        if fid == "BROKEN":
            raise RuntimeError("x")
        return [("2026-11-20", 4.0), ("2026-11-21", 4.1)]

    def yahoo(self, sym):
        return [("2026-11-21", 100, 101, 99, 100.5), ("2026-11-24", 100, 101, 99, 100.2), ("2026-11-25", 100, 101, 99, 100.9)]

    def run_build(self, prev=None, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return O.build(prev or {}, now=self.NOW, fred_fn=kw.get("fred_fn", self.fred), yahoo_fn=kw.get("yahoo_fn", self.yahoo))

    def test_builds_all(self):
        doc, ok, total = self.run_build()
        self.assertEqual((ok, total), (8, 8))
        self.assertEqual(doc["unavailable"], [])
        self.assertEqual(doc["series"]["dxy"]["through"], "2026-11-24")     # 11/25 還沒收盤，不收
        self.assertEqual(doc["series"]["spy"]["pts"][-1], ["2026-11-24", 100.2])
        cpi = doc["series"]["cpi"]["pts"]
        self.assertEqual(cpi[0][0], "2000-01-01")
        self.assertAlmostEqual(cpi[0][1], round((100.1 / 97.1 - 1) * 100, 2))

    def test_failure_keeps_old_and_marks_pending(self):
        def yahoo_fail(sym):
            raise RuntimeError("down")
        old = {"series": {"dxy": {"through": "2026-11-01", "bars": [["2026-11-01", 1, 1, 1, 1]]}}}
        doc, ok, total = self.run_build(old, yahoo_fn=yahoo_fail)
        self.assertEqual((ok, total), (6, 8))
        self.assertEqual(doc["series"]["dxy"], old["series"]["dxy"])
        self.assertNotIn("spy", doc["series"])
        self.assertEqual(len(doc["unavailable"]), 2)
        self.assertTrue(all(u.startswith("待確認：") for u in doc["unavailable"]))


if __name__ == "__main__":
    unittest.main()
