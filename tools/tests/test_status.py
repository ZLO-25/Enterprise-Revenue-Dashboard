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


class FetchRunsRetry(unittest.TestCase):
    def setUp(self):
        self.sleeps = []
        self._sl, S.time.sleep = S.time.sleep, self.sleeps.append
        self._hj = S.http_json

    def tearDown(self):
        S.time.sleep = self._sl
        S.http_json = self._hj

    def test_retries_then_succeeds(self):
        calls = []

        def fake(url, token):
            calls.append(url)
            if len(calls) < 3:
                raise OSError("boom")
            return {"workflow_runs": [{"conclusion": "success"}]}
        S.http_json = fake
        self.assertEqual(S.fetch_runs("o/r", "x.yml", "t"), [{"conclusion": "success"}])
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.sleeps, [2, 4])

    def test_gives_up_after_three(self):
        def fake(url, token):
            raise OSError("boom")
        S.http_json = fake
        with self.assertRaises(OSError):
            S.fetch_runs("o/r", "x.yml", "t")
        self.assertEqual(self.sleeps, [2, 4])

    def test_branch_param(self):
        urls = []
        S.http_json = lambda url, token: urls.append(url) or {"workflow_runs": []}
        S.fetch_runs("o/r", "sec-raw.yml", "t", branch="sec-raw")
        S.fetch_runs("o/r", "ci.yml", "t")
        self.assertTrue(urls[0].endswith("&branch=sec-raw"))
        self.assertNotIn("branch=", urls[1])


class OndemandAndMcap(unittest.TestCase):
    NOW = S.parse("2026-11-23T03:00:00Z")

    def setUp(self):
        self._fr, self._env = S.fetch_runs, dict(os.environ)
        os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"] = "o/r", "t"

    def tearDown(self):
        S.fetch_runs = self._fr
        os.environ.clear(); os.environ.update(self._env)

    def test_ondemand_gray_never_alerts(self):
        S.fetch_runs = lambda repo, wf, tok, branch=None, tries=3: [{"conclusion": "failure", "updated_at": "2026-11-20T00:00:00Z"}]
        rows = S.ondemand_block(self.NOW, True)
        self.assertEqual({r["id"] for r in rows}, {"ci", "bs-fetch", "rd-twse", "sec-raw", "tw-raw", "alerts-worker-deploy"})
        self.assertTrue(all(r["light"] == "gray" and r["group"] == "ondemand" and r["freq"] and r["retry"] for r in rows))
        self.assertIn("11/20 08:00 失敗", rows[0]["note"])
        ci = next(r for r in rows if r["id"] == "ci")
        self.assertIn("失敗不一定是問題", ci["note"])
        self.assertNotIn("失敗不一定是問題", next(r for r in rows if r["id"] == "bs-fetch")["note"])
        S.fetch_runs = lambda *a, **k: []
        self.assertTrue(all(r["note"] == "查不到紀錄" for r in S.ondemand_block(self.NOW, True)))
        S.fetch_runs = lambda repo, wf, tok, branch=None, tries=3: [{"conclusion": "failure", "updated_at": "2026-11-20T00:00:00Z"}]
        out = S.build(self.NOW, True)
        self.assertFalse([a for a in out["alerts"] if "PR 自動檢查" in a or "SEC 原始資料" in a or "資產負債表" in a])
        self.assertEqual(out["version"], 2)
        self.assertIn("ondemand", out)

    def test_every_row_has_info(self):
        out = S.build(self.NOW, False)
        for r in out["actions"] + out["routines"] + out["ondemand"]:
            for k in ("group", "freq", "method", "retry"):
                self.assertTrue(r.get(k), f"{r['id']} 缺 {k}")

    def test_mcap_row(self):
        rows = S.routines_block(dt.date(2026, 11, 23))
        m = next(r for r in rows if r["id"] == "mcap")
        self.assertNotEqual(m["light"], "red")
        self.assertEqual(m["group"], "routine")
        self.assertEqual(m["light"], "gray")          # 2026-11-27 起停用：固定灰燈
        far = S.routines_block(dt.date(2027, 6, 1))   # 很久沒有紀錄也不變黃、不紅
        self.assertEqual(next(r for r in far if r["id"] == "mcap")["light"], "gray")


if __name__ == "__main__":
    unittest.main()
