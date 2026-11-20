import datetime, json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import token_log as T


def line(mid, model, i, cr, cw, o, typ="assistant"):
    return json.dumps({"type": typ, "message": {"id": mid, "model": model, "usage": {
        "input_tokens": i, "cache_read_input_tokens": cr, "cache_creation_input_tokens": cw, "output_tokens": o}}})


class Transcript(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.uuid = "abc-123"
        d = os.path.join(self.home, ".claude", "projects", "-home-claude")
        os.makedirs(os.path.join(d, self.uuid, "subagents"))
        with open(os.path.join(d, self.uuid + ".jsonl"), "w") as f:
            # 同一則回覆串流成兩行：只算一次、取最大值
            f.write(line("m1", "claude-opus-5-5", 3, 1000, 200, 5) + "\n")
            f.write(line("m1", "claude-opus-5-5", 3, 1000, 200, 50) + "\n")
            f.write(line("m2", "claude-opus-5-5", 1, 2000, 10, 20) + "\n")
            f.write(json.dumps({"type": "user", "message": {"content": "x"}}) + "\n")
            f.write("not json\n")
        with open(os.path.join(d, self.uuid, "subagents", "agent-a.jsonl"), "w") as f:
            f.write(line("s1", "claude-haiku-5-5", 10, 300, 400, 60) + "\n")
        self.P = T.P
        T.P = os.path.join(self.home, "usage.json")

    def tearDown(self):
        T.P = self.P

    def test_sum_dedupes_and_includes_subagents(self):
        main, subs = T.transcript_files(self.uuid, self.home)
        m = T.sum_transcript(main + subs)
        self.assertEqual(m["claude-opus-5-5"], {"input": 4, "cacheRead": 3000, "cacheWrite": 210, "output": 70, "turns": 2})
        self.assertEqual(m["claude-haiku-5-5"]["output"], 60)

    def test_auto_records_estimate(self):
        env = {"CLAUDE_CODE_SESSION_ID": self.uuid, "CLAUDE_CODE_REMOTE_SESSION_ID": "cse_XYZ"}
        r = T.auto(datetime.date(2026, 11, 21), ["daily"], env=env, home=self.home)
        self.assertEqual(r["session"], "session_XYZ")
        self.assertFalse(r["exact"])
        self.assertEqual(r["turns"], 3)
        self.assertEqual(T.total(r), 3284 + 770)
        self.assertEqual(r["subagentFiles"], 1)
        # 同一個 session 再記一次會覆蓋，不會變兩筆
        T.auto(datetime.date(2026, 11, 21), ["daily"], env=env, home=self.home)
        self.assertEqual(len(T.load()["runs"]), 1)

    def test_exact_replaces_estimate(self):
        env = {"CLAUDE_CODE_SESSION_ID": self.uuid, "CLAUDE_CODE_REMOTE_SESSION_ID": "cse_XYZ"}
        T.auto(datetime.date(2026, 11, 21), ["daily"], env=env, home=self.home)
        T.exact(["cse_XYZ", "--cost", "2.5", "--turns", "40"])
        r = T.load()["runs"][0]
        self.assertTrue(r["exact"]); self.assertEqual(r["costUsd"], 2.5); self.assertEqual(r["turns"], 40)

    def test_rates_from_exact_runs(self):
        runs = [{"exact": True, "models": {"claude-opus-5-5": {"input": 0, "cacheRead": 2_000_000, "cacheWrite": 0, "output": 0, "costUsd": 1.0}}}]
        self.assertAlmostEqual(T.rates(runs)["opus"], 0.5)
        self.assertEqual(T.rates([])["haiku"], T.FALLBACK_RATE["haiku"])

    def test_missing_env_exits(self):
        with self.assertRaises(SystemExit):
            T.auto(datetime.date(2026, 11, 21), ["daily"], env={}, home=self.home)


if __name__ == "__main__":
    unittest.main()
