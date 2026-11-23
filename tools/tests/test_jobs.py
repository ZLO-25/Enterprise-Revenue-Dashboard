"""自動工作清單（data/status/jobs.json）的一致性守門：新增 workflow 或 Claude 排程卻沒登記，這裡會失敗。"""
import glob, json, os, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import daily_brief

JOBS = json.load(open(os.path.join(ROOT, "data", "status", "jobs.json"), encoding="utf8"))["jobs"]
RETRY = os.path.join(ROOT, "tools", "retry.sh")


class JobsRegistry(unittest.TestCase):
    def test_every_workflow_registered(self):
        have = {os.path.basename(f) for f in glob.glob(os.path.join(ROOT, ".github", "workflows", "*.yml"))}
        reg = {j["workflow"] for j in JOBS if j.get("workflow") and j.get("branch") == "main"}
        missing = sorted(have - reg)
        self.assertFalse(missing, f"新增 workflow 要登記到 data/status/jobs.json：{missing}")

    def test_registered_workflow_files_exist(self):
        for j in JOBS:
            if j.get("branch") == "main" and j.get("workflow"):
                self.assertTrue(os.path.exists(os.path.join(ROOT, ".github", "workflows", j["workflow"])), f"{j['id']}：找不到 {j['workflow']}")

    def test_fields(self):
        ids = [j["id"] for j in JOBS]
        self.assertEqual(len(ids), len(set(ids)), "id 重複")
        for j in JOBS:
            for k in ("freq", "method", "retry", "label"):
                self.assertTrue((j.get(k) or "").strip(), f"{j['id']} 的 {k} 是空的")
            self.assertIn(j["group"], ("actions", "routine", "ondemand", "check"), j["id"])
            self.assertIn(j.get("kind"), ("daily", "weekly", "monthly", None), j["id"])
            if j["group"] == "ondemand":
                self.assertIsNone(j["kind"], j["id"])
            else:
                self.assertIsNotNone(j["kind"], j["id"])
            if j["group"] in ("routine", "check"):   # Claude 排程與「檢查列」不是 workflow
                self.assertIsNone(j.get("workflow"), j["id"])
            else:
                self.assertTrue(j.get("workflow"), j["id"])

    def test_required_ids(self):
        ids = {j["id"] for j in JOBS}
        for i in ("daily-prep", "sec-feed", "consensus-daily", "prices-daily", "futures-daily", "quant-prices", "mcap-weekly", "rates-weekly",
                  "macro-weekly", "prices-monthly", "sec-feed-file", "macro-data", "ci", "bs-fetch", "rd-twse", "sec-raw", "tw-raw", "daily", "news", "trend", "mcap"):
            self.assertIn(i, ids)

    def test_routine_triggers_match_daily_brief(self):
        # daily／trend／news 的 trigger id 必須登記，且與 daily_brief.TRIGGERS 一致
        for k, tid in daily_brief.TRIGGERS.items():
            self.assertTrue(any(j["id"] == k and j["group"] == "routine" and j.get("trigger") == tid for j in JOBS), k)


class RetryScript(unittest.TestCase):
    def run_retry(self, n, *cmd):
        return subprocess.run([RETRY, str(n), "0", *cmd], capture_output=True, text=True)

    def test_success_stops_at_first(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "n")
            r = self.run_retry(3, "sh", "-c", f"echo x >> {log}")
            self.assertEqual(r.returncode, 0)
            self.assertEqual(len(open(log).read().split()), 1)

    def test_fail_n_times_returns_last_code(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "n")
            r = self.run_retry(3, "sh", "-c", f"echo x >> {log}; exit 7")
            self.assertEqual(r.returncode, 7)
            self.assertEqual(len(open(log).read().split()), 3)
            self.assertIn("第 1 次失敗（exit 7），0 秒後重試", r.stderr)

    def test_succeeds_on_second_try(self):
        with tempfile.TemporaryDirectory() as d:
            log = os.path.join(d, "n")
            r = self.run_retry(3, "sh", "-c", f"echo x >> {log}; [ $(wc -l < {log}) -ge 2 ]")
            self.assertEqual(r.returncode, 0)
            self.assertEqual(len(open(log).read().split()), 2)


if __name__ == "__main__":
    unittest.main()
