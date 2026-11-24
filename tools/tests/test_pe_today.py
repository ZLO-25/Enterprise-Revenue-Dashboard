"""首頁「本益比（今日）」：data/daily/_pe.json 摘要只抄 calc.latest，不重算；缺值照原樣帶 why。"""
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import prices_daily as P


class PeSummary(unittest.TestCase):
    def test_copies_latest(self):
        files = {
            "a": {"fetched": "2026-11-24T01:00Z", "calc": {"latest": {"d": "2026-11-23", "pe": 17.7, "q": "3Q27", "why": {"fpe": "none"}}}},
            "b": {"fetched": "x", "calc": {"latest": {"d": "2026-11-23", "pe": None, "q": "3Q26", "why": {"pe": "loss"}}}},
            "c": {"calc": None},
            "d": None,
        }
        co = P.pe_summary(files)["co"]
        self.assertEqual(sorted(co), ["a", "b"])
        self.assertEqual(co["a"], {"d": "2026-11-23", "pe": 17.7, "why": None, "q": "3Q27", "fetched": "2026-11-24T01:00Z"})
        self.assertIsNone(co["b"]["pe"]); self.assertEqual(co["b"]["why"], "loss")


if __name__ == "__main__":
    unittest.main()
