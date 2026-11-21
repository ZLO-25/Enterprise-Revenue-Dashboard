"""AI 資本支出鏈（tools/capex_chain.py）：日曆季對齊、加總、年增率、缺資料時留空並標待確認。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import capex_chain as C


def co(code, name=None):
    return {"code": code, "name": name or code.upper(), "path": code + "/", "currency": "USD"}


def data(fye, rows):
    """rows = [(季別, 資本支出, 營收)]"""
    return {"company": {"fiscalYearEnd": fye}, "quarters": [{"q": q, "capex": c, "rev": r} for q, c, r in rows]}


class HelpersTest(unittest.TestCase):
    def test_cal_quarter(self):
        self.assertEqual(C.cal_quarter("2026-09"), "2026Q3")
        self.assertEqual(C.cal_quarter("2026-12"), "2026Q4")
        self.assertIsNone(C.cal_quarter("2026-10"))     # 輝達這種 1／4／7／10 月結帳的對不上日曆季

    def test_prev_year_and_yoy(self):
        self.assertEqual(C.prev_year("3Q26"), "3Q25")
        self.assertEqual(C.yoy(150, 100), 50.0)
        self.assertIsNone(C.yoy(150, None))
        self.assertIsNone(C.yoy(None, 100))
        self.assertIsNone(C.yoy(150, 0))
        self.assertIsNone(C.yoy(150, -10))


class ComputeTest(unittest.TestCase):
    def setUp(self):
        # a：日曆年；b：6 月結帳（1Q27 ＝ 2026 年 7～9 月），兩家要對到同一個日曆季
        self.cos = [co("a"), co("b"), co("s")]
        self.ds = {
            "a": data("12-31", [("3Q25", 100, 1000), ("4Q25", 110, 1100), ("3Q26", 200, 1500)]),
            "b": data("06-30", [("1Q26", 50, 500), ("2Q26", 60, 600), ("1Q27", 100, 500)]),
            "s": data("01-31", [("3Q26", 5, 300), ("3Q27", 9, 600)]),
        }
        self.chain = {"buyers": ["a", "b"], "suppliers": ["s"]}

    def test_fiscal_years_align_to_calendar_quarter(self):
        out = C.compute(self.chain, self.cos, self.ds, since="2025Q1")
        by = {r["cq"]: r for r in out["rows"]}
        self.assertEqual(by["2025Q3"]["total"], 150)
        self.assertEqual(by["2025Q3"]["capex"], {"a": 100, "b": 50})
        self.assertEqual(by["2026Q3"]["total"], 300)
        self.assertEqual(by["2026Q3"]["yoy"], 100.0)
        self.assertEqual(by["2026Q3"]["pctRev"], 15.0)      # 300 ÷（1500＋500）
        self.assertEqual(by["2025Q4"]["yoy"], None)         # 沒有前一年同季

    def test_missing_buyer_leaves_total_empty(self):
        self.ds["b"]["quarters"][-1]["capex"] = None
        out = C.compute(self.chain, self.cos, self.ds, since="2025Q1")
        last = out["rows"][-1]
        self.assertEqual(last["cq"], "2026Q3")
        self.assertIsNone(last["total"])                    # 不用另一家去推
        self.assertIsNone(last["yoy"])
        self.assertIsNone(last["pctRev"])
        self.assertTrue(any(m.startswith("待確認：2026Q3") and "B" in m for m in out["missing"]))

    def test_supplier_uses_own_fiscal_quarters(self):
        out = C.compute(self.chain, self.cos, self.ds, since="2025Q1")
        s = out["suppliers"][0]
        self.assertEqual(s["points"][-1], {"q": "3Q27", "end": "2026-10", "rev": 600, "yoy": 100.0})
        self.assertIsNone(s["points"][0]["yoy"])

    def test_unknown_company_is_reported_not_guessed(self):
        out = C.compute({"buyers": ["a", "zzz"], "suppliers": []}, self.cos, self.ds, since="2025Q1")
        self.assertEqual([b["code"] for b in out["buyers"]], ["a"])
        self.assertTrue(any("zzz" in m for m in out["missing"]))

    def test_buyer_off_calendar_is_rejected(self):
        out = C.compute({"buyers": ["s"], "suppliers": []}, self.cos, self.ds, since="2025Q1")
        self.assertEqual(out["rows"], [])
        self.assertTrue(any("不能和其他買方加總" in m for m in out["missing"]))

    def test_real_site_data(self):
        out = C.load()
        self.assertEqual([b["code"] for b in out["buyers"]], ["msft", "amzn", "googl", "meta"])
        full = [r for r in out["rows"] if r["total"] is not None]
        self.assertGreater(len(full), 20)
        for r in full:
            self.assertAlmostEqual(r["total"], sum(r["capex"].values()), places=1)


if __name__ == "__main__":
    unittest.main()
