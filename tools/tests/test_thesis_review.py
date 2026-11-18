import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import thesis as T


def Q(vals, k="rev"):
    return [{"q": f"{(i % 4) + 1}Q{20 + i // 4}", "rev": v} for i, v in enumerate(vals)]


class Review(unittest.TestCase):
    def rows(self, vals, op, thr, group="biz"):
        th = {"metrics": [{"k": "revYoyQ", "name": "x", "op": op, "thr": thr, "group": group}]}
        return T.review_rows(th, Q(vals), None, None)[0]

    def test_break_flag(self):
        # 單季營收年增：前 6 次 ≥ 20%，最近 2 次約 10%
        r = self.rows([100] * 4 + [130] * 4 + [160, 160, 143, 143], ">=", 20)
        self.assertEqual(r["miss"], 2)
        self.assertIn("可能破功", r["flags"])

    def test_val_not_too_tight(self):
        r = self.rows([100] * 4 + [150] * 4 + [300] * 4, "<=", 10, group="val")
        self.assertNotIn("門檻太緊", r["flags"])

    def test_too_loose(self):
        r = self.rows([100] * 4 + [200] * 4 + [400] * 4, ">=", 20)   # 年增都是 100%，門檻 20，8/8 達標
        self.assertIn("門檻太鬆", r["flags"])


if __name__ == "__main__":
    unittest.main()
