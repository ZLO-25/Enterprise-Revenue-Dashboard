import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pending as P

L = P.qkey("3Q27")


class Classify(unittest.TestCase):
    def test_note(self):
        self.assertEqual(P.classify("每股股利：不發放", L), "note")

    def test_recent(self):
        self.assertEqual(P.classify("待確認：3Q27 的財報公布日", L), "recent")
        self.assertEqual(P.classify("待確認：2Q27 營收", L), "recent")       # 前一季也算近期

    def test_y3_boundary(self):
        self.assertEqual(P.classify("待確認：4Q24 EPS", L), "y3")              # 11 季前
        self.assertEqual(P.classify("待確認：3Q24 EPS", L), "old")             # 12 季前

    def test_range_uses_later_end(self):
        self.assertEqual(P.classify("待確認：欄位 1Q10～3Q27 沒有值", L), "recent")
        self.assertEqual(P.classify("待確認：1Q09–4Q17 的產品類別", L), "old")

    def test_no_quarter(self):
        self.assertEqual(P.classify("待確認：年報業務章節尚未讀到", L), "noq")


if __name__ == "__main__":
    unittest.main()
