import io, json, os, sys, tempfile, unittest
from contextlib import redirect_stdout
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sec_inbox as S


class PrDue(unittest.TestCase):
    feed = {"earnings8k": [{"date": "2026-11-19", "acc": "a"}, {"date": "2026-08-27", "acc": "b"}]}

    def test_new_8k(self):
        self.assertEqual([e["acc"] for e in S.pr_due(self.feed, "2026-08-27", set())], ["a"])

    def test_already_have(self):
        self.assertEqual(S.pr_due(self.feed, "2026-08-27", {"2026-11-19"}), [])

    def test_up_to_date(self):
        self.assertEqual(S.pr_due(self.feed, "2026-11-19", set()), [])

    def test_no_rd_or_feed(self):
        self.assertEqual(S.pr_due(self.feed, None, set()), [])
        self.assertEqual(S.pr_due(None, "2026-08-27", set()), [])


class PickEx99(unittest.TestCase):
    def test_prefers_99_1(self):
        names = ["0001045810-26-000101-index.htm", "nvda-20261119.htm", "q3fy27pr.htm", "ex99-2.htm", "nvda-ex991.htm"]
        self.assertEqual(S.pick_ex99(names), "nvda-ex991.htm")

    def test_not_99_10(self):
        self.assertEqual(S.pick_ex99(["ex99-10.htm", "ex99_1.htm"]), "ex99_1.htm")

    def test_release_fallback(self):
        self.assertEqual(S.pick_ex99(["main.htm", "earningsrelease.htm"]), "earningsrelease.htm")

    def test_none(self):
        self.assertIsNone(S.pick_ex99(["main.htm", "0001045810-26-000101.txt"]))


class XbrlDue(unittest.TestCase):
    def test_states(self):
        self.assertTrue(S.xbrl_due("flash"))
        self.assertTrue(S.xbrl_due("completed"))
        self.assertFalse(S.xbrl_due("waiting"))   # 核對完的公司 10-Q 一定晚於 rd，不能當成「有新申報」
        self.assertFalse(S.xbrl_due("stuck"))


class MergeRecent(unittest.TestCase):
    def test_only_recent_replaced(self):
        old = {"code": "googl", "splits": [["2022-07-18", 20.0]], "quarters": [{"q": f"{i}Q", "vals": {"x": "old"}} for i in range(5)]}
        new = {"code": "googl", "fetched": "T", "quarters": [{"q": f"{i}Q", "vals": {"x": "new"}} for i in range(6)]}
        m = S.merge_recent(old, new, n=3)
        self.assertEqual([r["vals"]["x"] for r in m["quarters"]], ["old", "old", "old", "new", "new", "new"])
        self.assertEqual(m["splits"], old["splits"])
        self.assertEqual(m["fetched"], "T")

    def test_no_old(self):
        new = {"quarters": [{"q": "1Q"}]}
        self.assertIs(S.merge_recent(None, new), new)


class Close(unittest.TestCase):
    def test_money(self):
        self.assertTrue(S.close_enough("rev", 115844.0, 115844.4))
        self.assertTrue(S.close_enough("rev", 115844.0, 115900.0))   # 0.1% 以內（四捨五入口徑）
        self.assertFalse(S.close_enough("rev", 115844.0, 116000.0))

    def test_eps(self):
        self.assertTrue(S.close_enough("eps", 2.70, 2.705))
        self.assertFalse(S.close_enough("eps", 2.70, 2.72))

    def test_missing(self):
        self.assertIsNone(S.close_enough("rev", None, 1.0))


class Html(unittest.TestCase):
    def test_table_rows(self):
        t = S.html_text(b"<p>Revenue up</p><table><tr><td>Revenue</td><td>$ 115,844</td></tr></table><script>x</script>")
        self.assertIn("Revenue up", t)
        self.assertIn("Revenue | $ 115,844", t)
        self.assertNotIn("x\n", t)


class Report(unittest.TestCase):
    def test_marks(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "nvda"))
            open(os.path.join(d, "nvda", "pr-2026-11-19.txt"), "w").write("SOURCE https://www.sec.gov/x\n")
            json.dump({"fetched": "2026-11-20T00:00Z", "quarters": [
                {"q": "2Q27", "end": "2026-07-26", "rows": {"rev": {"ours": 1.0, "sec": 1.0, "ok": True}, "eps": {"ours": 1.0, "sec": 1.5, "ok": False}}},
                {"q": "3Q27", "end": None, "rows": {}, "why": "SEC XBRL 還沒有這一季"}]}, open(os.path.join(d, "nvda", "xbrl.json"), "w"))
            old, S.INBOX = S.INBOX, d
            try:
                buf = io.StringIO()
                with redirect_stdout(buf):
                    S.report(["nvda", "tsmc"])
            finally:
                S.INBOX = old
            out = buf.getvalue()
            self.assertIn("pr-2026-11-19.txt", out)
            self.assertIn("營收✓", out)
            self.assertIn("稀釋EPS✗(我們 1.0／SEC 1.5)", out)
            self.assertIn("3Q27：SEC XBRL 還沒有這一季", out)
            self.assertIn("【tsmc】", out)


if __name__ == "__main__":
    unittest.main()
