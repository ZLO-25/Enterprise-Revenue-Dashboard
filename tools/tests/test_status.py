import datetime as dt, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import status as S

UTC = dt.timezone.utc


def t(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=UTC)


class RunAge(unittest.TestCase):
    def test_fresh_green(self):
        now = t("2026-11-18T01:00:00")   # 台北週三 09:00
        self.assertEqual(S.eval_run_age("daily", t("2026-11-17T20:00:00"), None, now)[0], "green")

    def test_stale_midweek_red(self):
        now = t("2026-11-19T01:00:00")   # 台北週四
        self.assertEqual(S.eval_run_age("daily", t("2026-11-17T01:00:00"), None, now)[0], "red")   # 48h > 36h

    def test_weekend_allowance(self):
        now = t("2026-11-23T01:00:00")   # 台北週一 09:00，週六早上成功 → 約 50h
        self.assertEqual(S.eval_run_age("daily", t("2026-11-21T01:00:00"), None, now)[0], "green")
        # 週三仍沒跑就紅燈
        self.assertEqual(S.eval_run_age("daily", t("2026-11-21T01:00:00"), None, t("2026-11-25T01:00:00"))[0], "red")

    def test_failure_after_success_red(self):
        now = t("2026-11-18T01:00:00")
        done = {"conclusion": "failure", "at": t("2026-11-18T00:30:00")}
        self.assertEqual(S.eval_run_age("daily", t("2026-11-17T20:00:00"), done, now)[0], "red")

    def test_weekly_limit(self):
        now = t("2026-11-18T01:00:00")
        self.assertEqual(S.eval_run_age("weekly", t("2026-11-10T01:00:00"), None, now)[0], "green")   # 8 天
        self.assertEqual(S.eval_run_age("weekly", t("2026-11-09T01:00:00"), None, now)[0], "red")     # 9 天

    def test_no_success_yellow(self):
        self.assertEqual(S.eval_run_age("daily", None, None, t("2026-11-18T01:00:00"))[0], "yellow")


class MacroRowTest(unittest.TestCase):
    """總經資料的內容檢查：壞掉要看得到，但不要因為一條序列晚公布就寄信。"""
    NOW = S.parse("2026-11-21T18:00:00Z")

    def doc(self, **kw):
        d = {"updated": "2026-11-20 18:00 UTC", "series": {str(i): {} for i in range(60)}, "unavailable": [], "health": {"stale": []}, "links": {"dead": []}}
        d.update(kw)
        return d

    def test_green(self):
        r = S.macro_row(self.doc(), self.NOW)
        self.assertEqual(r["light"], "green")
        self.assertIn("60 條", r["note"])

    def test_missing_file_yellow(self):
        self.assertEqual(S.macro_row(None, self.NOW)["light"], "yellow")

    def test_stale_series_yellow_not_red(self):
        r = S.macro_row(self.doc(health={"stale": [{"key": "a", "name": "甲", "days": 200}]}, links={"dead": ["https://x/"]}), self.NOW)
        self.assertEqual(r["light"], "yellow")
        self.assertIn("甲", r["note"])
        self.assertIn("404", r["note"])

    def test_old_file_red(self):
        r = S.macro_row(self.doc(updated="2026-11-09 00:00 UTC"), self.NOW)
        self.assertEqual(r["light"], "red")

    def test_most_series_failed_red(self):
        r = S.macro_row(self.doc(unavailable=["待確認：x"] * 31), self.NOW)
        self.assertEqual(r["light"], "red")


if __name__ == "__main__":
    unittest.main()
