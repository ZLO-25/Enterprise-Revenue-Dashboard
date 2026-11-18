"""股票酬勞（sbc）抓取與合併：bs_fetch 的季度對齊、年度累計拆單季，bs_merge --only sbc 不動其他欄位。"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bs_fetch as F, bs_merge as M  # noqa: E402


def fact(start, end, val, filed="2026-01-01"):
    return {"start": start, "end": end, "val": val * 1e6, "filed": filed, "accn": "x", "form": "10-Q"}


class QuarterEnds(unittest.TestCase):
    def test_near_days_blocks_coincidental_match(self):
        # 我們的 1Q14（名目期末 2014-03-31）淨利 12.3；SEC 2013-09-30 的 11.9 也在 0.6 以內，但期末日差太遠，不可配到它
        ni = [fact("2013-07-01", "2013-09-30", 11.9), fact("2014-01-01", "2014-03-31", 12.3)]
        ours = [{"q": "1Q14", "ni": 12.3}]
        self.assertEqual(F.quarter_ends(ni, ours, "12-31")[0], ["2014-03-31"])
        # 沒給會計年度結束日時是舊行為（第一個相近的淨利）
        self.assertEqual(F.quarter_ends(ni, ours)[0], ["2013-09-30"])

    def test_date_pass_fills_unmatched_between_neighbours(self):
        ni = [fact("2024-01-01", "2024-03-31", 10), fact("2024-04-01", "2024-06-30", 99), fact("2024-07-01", "2024-09-30", 12)]
        ours = [{"q": "1Q24", "ni": 10}, {"q": "2Q24", "ni": 11}, {"q": "3Q24", "ni": 12}]
        self.assertEqual(F.quarter_ends(ni, ours, "12-31")[0], ["2024-03-31", "2024-06-30", "2024-09-30"])
        self.assertEqual(F.quarter_ends(ni, ours)[0], ["2024-03-31", None, "2024-09-30"])

    def test_date_pass_needs_end_within_10_days(self):
        ni = [fact("2024-01-01", "2024-03-31", 10), fact("2024-04-01", "2024-07-20", 99), fact("2024-07-21", "2024-09-30", 12)]
        ours = [{"q": "1Q24", "ni": 10}, {"q": "2Q24", "ni": 11}, {"q": "3Q24", "ni": 12}]
        self.assertEqual(F.quarter_ends(ni, ours, "12-31")[0][1], None)


class FlowYtd(unittest.TestCase):
    # 會計年度 2024-11-04 開始（52／53 週，像 avgo）：年初累計 3、6、9、12 個月
    S = "2024-11-04"
    L = [fact(S, "2025-02-02", 1280), fact(S, "2025-05-04", 3051), fact(S, "2025-08-03", 5373), fact(S, "2025-11-02", 7568)]

    def test_q1_direct_and_later_quarters_are_ytd_differences(self):
        ends = ["2025-02-02", "2025-05-04", "2025-08-03", "2025-11-02"]
        got = [F.flow(self.L, e, p, "ytd")[1] / 1e6 for e, p in zip(ends, [None] + ends[:-1])]
        self.assertEqual([round(x) for x in got], [1280, 1771, 2322, 2195])
        self.assertEqual(round(sum(got)), 7568)       # 四季加總＝全年

    def test_missing_previous_ytd_gives_null(self):
        self.assertEqual(F.flow(self.L[1:], "2025-05-04", "2025-02-02", "ytd"), (None, None))


class MergeSbc(unittest.TestCase):
    def test_reject_rules(self):
        self.assertIsNone(M.sbc_reject(None, 100))
        self.assertIsNone(M.sbc_reject(30, 100))
        self.assertIn("負值", M.sbc_reject(-1, 100))
        self.assertIn("60%", M.sbc_reject(61, 100))
        self.assertIsNone(M.sbc_reject(5, None))

    def test_only_sbc_touches_nothing_else(self):
        D = {"quarters": [{"q": "1Q25", "rev": 100, "ni": 10, "eps": 1, "cash": 7, "debt": None},
                          {"q": "2Q25", "rev": 100, "ni": 10, "eps": 1, "cash": 8, "debt": None},
                          {"q": "3Q25", "rev": 100, "ni": 10, "eps": 1, "cash": 9, "debt": None}],
             "notes": {"unavailable": ["待確認：資產負債表欄位 有息負債（debt）：3 季沒有值", "待確認：別的事"]}}
        raw = {"quarters": [{"q": "1Q25", "vals": {"sbc": 5, "cash": 999}, "why": {}},
                            {"q": "2Q25", "vals": {"sbc": 80, "cash": 999}, "why": {}},
                            {"q": "3Q25", "vals": {}, "why": {"*": "淨利對不上"}}]}
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "data", "bs-raw"))
            for path, obj in ((("data", "t.json"), D), (("data", "bs-raw", "t.json"), raw)):
                with open(os.path.join(d, *path), "w", encoding="utf8") as fh:
                    json.dump(obj, fh, ensure_ascii=False)
            old_root, old_argv = M.ROOT, sys.argv
            try:
                M.ROOT, sys.argv = d, ["bs_merge.py", "--only", "sbc", "t"]
                M.main()
            finally:
                M.ROOT, sys.argv = old_root, old_argv
            with open(os.path.join(d, "data", "t.json"), encoding="utf8") as fh:
                out = json.load(fh)
        self.assertEqual([q["sbc"] for q in out["quarters"]], [5, None, None])
        self.assertEqual([q["cash"] for q in out["quarters"]], [7, 8, 9])          # 其他欄位不動
        un = out["notes"]["unavailable"]
        self.assertIn("待確認：資產負債表欄位 有息負債（debt）：3 季沒有值", un)     # 別的欄位的待確認行不動
        self.assertIn("待確認：別的事", un)
        line = [x for x in un if "股票酬勞（sbc）" in x][0]
        self.assertIn("2Q25", line)                                                # 剔除的季度列出季別
        self.assertIn("10-Q", line)                                                # 最新一季：等 10-Q


if __name__ == "__main__":
    unittest.main()
