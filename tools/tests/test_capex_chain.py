"""AI 資本支出鏈（tools/capex_chain.py）：日曆季對齊、加總、年增率、多幣別格式化、近 4Q 嚴格連續檢查、財測擷取、新興買方與缺資料防護。"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import capex_chain as C


def co(code, name=None, currency="USD", enabled=True, schema=None):
    out = {"code": code, "name": name or code.upper(), "path": code + "/", "currency": currency, "enabled": enabled}
    if schema:
        out["schema"] = schema
    return out


def data(fye, rows, **extra):
    """rows = [(季別, 資本支出, 營收)]"""
    doc = {"company": {"fiscalYearEnd": fye}, "quarters": [{"q": q, "capex": c, "rev": r} for q, c, r in rows]}
    doc.update(extra)
    return doc


class HelpersTest(unittest.TestCase):
    def test_cal_quarter(self):
        self.assertEqual(C.cal_quarter("2026-09"), "2026Q3")
        self.assertEqual(C.cal_quarter("2026-12"), "2026Q4")
        self.assertIsNone(C.cal_quarter("2026-10"))     # 輝達這種 1／4／7／10 月結帳的對不上日曆季

    def test_prev_year_and_qnum_and_yoy(self):
        self.assertEqual(C.prev_year("3Q26"), "3Q25")
        self.assertEqual(C.prev_year("1Q00"), "1Q99")
        self.assertEqual(C.qnum("4Q99") + 1, C.qnum("1Q00"))
        self.assertEqual(C.qnum("1Q80"), 1980 * 4)
        self.assertEqual(C.qnum("4Q79"), 2079 * 4 + 3)
        self.assertEqual(C.yoy(150, 100), 50.0)
        self.assertIsNone(C.yoy(150, None))
        self.assertIsNone(C.yoy(None, 100))
        self.assertIsNone(C.yoy(150, 0))
        self.assertIsNone(C.yoy(150, -10))

    def test_fmt_capex_multicurrency(self):
        self.assertEqual(C.fmt_capex(None, "USD"), "—")
        # USD
        self.assertEqual(C.fmt_capex(39367, "USD"), "$393.7 億")
        self.assertEqual(C.fmt_capex(135920, "USD"), "$1,359.2 億")
        self.assertEqual(C.fmt_capex(532, "USD"), "$5.32 億")
        self.assertEqual(C.fmt_capex(100.7, "USD"), "$1.01 億")
        self.assertEqual(C.fmt_capex(13.98, "USD"), "$14.0 百萬")
        self.assertEqual(C.fmt_capex(0.28, "USD"), "$0.28 百萬")
        # TWD
        self.assertEqual(C.fmt_capex(1646877, "TWD"), "NT$1.65 兆")
        self.assertEqual(C.fmt_capex(443206, "TWD"), "NT$4,432 億")
        self.assertEqual(C.fmt_capex(17625.6, "TWD"), "NT$176.3 億")
        self.assertEqual(C.fmt_capex(1200, "TWD"), "NT$12.0 億")
        self.assertEqual(C.fmt_capex(560.85, "TWD"), "NT$5.61 億")
        self.assertEqual(C.fmt_capex(18.7, "TWD"), "NT$18.7 百萬")
        self.assertEqual(C.fmt_capex(0.094, "TWD"), "NT$0.09 百萬")
        # KRW
        self.assertEqual(C.fmt_capex(26900000, "KRW"), "₩26.90 兆")
        self.assertEqual(C.fmt_capex(69690000, "KRW"), "₩69.69 兆")
        self.assertEqual(C.fmt_capex(850000, "KRW"), "₩8,500 億")
        # EUR
        self.assertEqual(C.fmt_capex(1560, "EUR"), "€15.6 億")
        self.assertEqual(C.fmt_capex(413.3, "EUR"), "€4.13 億")
        self.assertEqual(C.fmt_capex(15.2, "EUR"), "€15.2 百萬")
        self.assertEqual(C.fmt_capex(7.2, "EUR"), "€7.20 百萬")
        # 半值四捨五入（ROUND_HALF_UP，與 JS toLocaleString 一致）
        self.assertEqual(C.fmt_capex(51355.0, "USD"), "$513.6 億")
        self.assertEqual(C.fmt_capex(775.5, "USD"), "$7.76 億")


class CapexSeriesAndGuidanceTest(unittest.TestCase):
    def test_ttm_contiguous_and_gaps(self):
        # 滿 8 季連續
        rows = C.company_rows([{"q": q, "capex": 100.0, "rev": 1000.0} for q in
                               ("1Q25", "2Q25", "3Q25", "4Q25", "1Q26", "2Q26", "3Q26", "4Q26")], "12-31")
        h = C.compute_capex_series(rows)
        self.assertIsNone(h[2]["ttm"])
        self.assertEqual(h[2]["ttmWhy"], "short")
        self.assertEqual(h[3]["ttm"], 400.0)
        self.assertIsNone(h[3]["ttmWhy"])
        self.assertEqual(h[7]["ttm"], 400.0)
        self.assertEqual(h[7]["ttmYoy"], 0.0)

        # 中間缺一季 capex=None → gap
        rows_gap = C.company_rows([
            {"q": "1Q25", "capex": 100.0, "rev": 1000.0},
            {"q": "2Q25", "capex": None, "rev": 1000.0},
            {"q": "3Q25", "capex": 100.0, "rev": 1000.0},
            {"q": "4Q25", "capex": 100.0, "rev": 1000.0},
            {"q": "1Q26", "capex": 100.0, "rev": 1000.0},
        ], "12-31")
        hg = C.compute_capex_series(rows_gap)
        self.assertIsNone(hg[3]["ttm"])
        self.assertEqual(hg[3]["ttmWhy"], "gap")
        self.assertIsNone(hg[4]["ttm"])
        self.assertEqual(hg[4]["ttmWhy"], "gap")

        # 跳季不連續（缺 2Q25）→ gap
        rows_skip = C.company_rows([
            {"q": "1Q25", "capex": 100.0, "rev": 1000.0},
            {"q": "3Q25", "capex": 100.0, "rev": 1000.0},
            {"q": "4Q25", "capex": 100.0, "rev": 1000.0},
            {"q": "1Q26", "capex": 100.0, "rev": 1000.0},
        ], "12-31")
        hs = C.compute_capex_series(rows_skip)
        self.assertIsNone(hs[3]["ttm"])
        self.assertEqual(hs[3]["ttmWhy"], "gap")

    def test_extract_guidance_capex_budget(self):
        D = {"capexBudget": {"y": 2026, "lo": 60, "hi": 64, "note": "7 月上修，原 520–560 億"}}
        g = C.extract_capex_guidance(D, "TWD")
        self.assertEqual(g["kind"], "written")
        self.assertEqual(g["tag"], "書面")
        self.assertEqual(g["text"], "2026 全年 600–640 億美元")
        self.assertIn("原 520–560 億", g["note"])

    def test_extract_guidance_with_history(self):
        D = {
            "guidance": {
                "issued": "2026-10-22",
                "items": [{"label": "全年資本支出", "period": "2026", "lo": 2100, "hi": 2300, "unit": "百萬美元", "note": ""}],
            },
            "guidanceHistory": [
                {"issued": "2026-07-23", "items": [{"label": "全年資本支出", "period": "2026", "lo": 2000, "hi": 2400, "unit": "百萬美元", "note": ""}]}
            ],
        }
        g = C.extract_capex_guidance(D, "USD")
        self.assertEqual(g["kind"], "written")
        self.assertEqual(g["text"], "2026 全年 $21–23 億")
        self.assertEqual(g["note"], "原 $20–24 億")

    def test_extract_guidance_oral_and_guards(self):
        # 正例：tag="o" 且具備合法 url + speaker
        ok_doc = {
            "summary": {
                "outlook": {
                    "items": [
                        {
                            "tag": "o",
                            "t": "管理層預期 2027 全年資本支出將維持在 180 億美元以上。",
                            "src": {"n": "3Q26 逐字稿", "url": "https://example.com/transcript", "speaker": "CFO"},
                        }
                    ]
                }
            }
        }
        g = C.extract_capex_guidance(ok_doc, "USD")
        self.assertEqual(g["kind"], "oral")
        self.assertEqual(g["tag"], "口頭")
        self.assertIn("180 億美元", g["text"])
        self.assertEqual(g["src"]["speaker"], "CFO")

        # 反例 1：PANW 收購上限句不可誤抓
        panw_doc = {
            "summary": {
                "mgmt": [
                    {
                        "tag": "o",
                        "t": "收購 Applied Compute（全部用股票）：預期到 FY2029 為 NGS ARR 增加超過 10 億美元；到 FY2030 資本支出少於 30 億美元，預計 FY2027 第三季完成交易。",
                        "src": {"n": "逐字稿", "url": "https://example.com/panw", "speaker": "CEO"},
                    }
                ]
            }
        }
        self.assertIsNone(C.extract_capex_guidance(panw_doc, "USD"))

        # 反例 2：缺 speaker 或 url 不採用
        no_speaker = {
            "summary": {
                "outlook": {
                    "items": [{"tag": "o", "t": "預期全年資本支出 50 億美元。", "src": {"n": "逐字稿", "url": "https://example.com/x"}}]
                }
            }
        }
        self.assertIsNone(C.extract_capex_guidance(no_speaker, "USD"))

        # 反例 3：tag="v" 觀點不採用
        view_only = {
            "summary": {
                "outlook": {
                    "items": [{"tag": "v", "t": "預期全年資本支出 50 億美元。", "src": {"n": "觀點", "url": "https://example.com/x", "speaker": "分析師"}}]
                }
            }
        }
        self.assertIsNone(C.extract_capex_guidance(view_only, "USD"))

        # 反例 4：去年全年實際值、收購 FY2028、今年已投入實際值皆不誤抓
        for bad_txt in (
            "去年全年資本支出約 30 億美元。",
            "收購 X：到 FY2028 資本支出少於 30 億美元。",
            "今年前三季已投入資本支出 30 億美元。",
        ):
            bad_doc = {
                "summary": {
                    "mgmt": [
                        {
                            "tag": "o",
                            "t": bad_txt,
                            "src": {"n": "逐字稿", "url": "https://example.com/bad", "speaker": "CFO"},
                        }
                    ]
                }
            }
            self.assertIsNone(C.extract_capex_guidance(bad_doc, "USD"), bad_txt)


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
        self.assertEqual(s["capex"]["latest"], 9)

    def test_unknown_company_is_reported_not_guessed(self):
        out = C.compute({"buyers": ["a", "zzz"], "suppliers": []}, self.cos, self.ds, since="2025Q1")
        self.assertEqual([b["code"] for b in out["buyers"]], ["a"])
        self.assertTrue(any("zzz" in m for m in out["missing"]))

    def test_buyer_off_calendar_is_rejected(self):
        out = C.compute({"buyers": ["s"], "suppliers": []}, self.cos, self.ds, since="2025Q1")
        self.assertEqual(out["rows"], [])
        self.assertTrue(any("不能和其他買方加總" in m for m in out["missing"]))

    def test_tiers_and_gm_qchg(self):
        self.ds["s"]["quarters"][0]["gm"] = 60.0
        self.ds["s"]["quarters"][1]["gm"] = 62.5
        chain = {"buyers": ["a", "b"], "tiers": [{"name": "① AI 算力晶片", "codes": ["s"]}]}
        out = C.compute(chain, self.cos, self.ds, since="2025Q1")
        self.assertEqual(len(out["tiers"]), 1)
        self.assertEqual(out["tiers"][0]["name"], "① AI 算力晶片")
        s = out["suppliers"][0]
        self.assertEqual(s["tier"], "① AI 算力晶片")
        self.assertEqual(s["gm"], 62.5)
        self.assertEqual(s["gmQchg"], 2.5)
        self.assertEqual(s["points"][-1], {"q": "3Q27", "end": "2026-10", "rev": 600, "yoy": 100.0})

    def test_emerging_buyers_lifecycle(self):
        cos = self.cos + [co("spcx", "SpaceX", enabled=True), co("anthropic", "Anthropic", enabled=False)]
        ds = dict(self.ds)
        ds["spcx"] = data("12-31", [("2Q26", 18369.0, 7814.0), ("3Q26", 19593.0, 14575.0)])
        ds["anthropic"] = data("12-31", [("1Q24", None, None)])
        chain = {
            "buyers": ["a", "b"],
            "emergingBuyers": [
                {"code": "spcx", "note": "三部門合計"},
                {"code": "anthropic", "note": "424B4 已定價"},
            ],
            "suppliers": ["s"],
        }
        out = C.compute(chain, cos, ds, since="2025Q1")
        eb = {x["code"]: x for x in out["emergingBuyers"]}
        self.assertEqual(eb["spcx"]["status"], "ok")
        self.assertEqual(eb["spcx"]["path"], "spcx/")
        self.assertEqual(eb["spcx"]["capex"]["latestPctRev"], 134.4)
        self.assertEqual(eb["spcx"]["capex"]["ttmWhy"], "short")
        self.assertEqual(eb["anthropic"]["status"], "pending_ipo")
        self.assertEqual(eb["anthropic"]["path"], "")
        self.assertIsNone(eb["anthropic"]["capex"])
        self.assertEqual(eb["anthropic"]["history"], [])
        self.assertFalse(any("anthropic" in m.lower() for m in out["missing"]))

        # 模擬未來 anthropic 啟用並公布首季財報
        cos_up = self.cos + [co("spcx", "SpaceX", enabled=True), co("anthropic", "Anthropic", enabled=True)]
        ds_up = dict(ds)
        ds_up["anthropic"] = data("12-31", [("1Q24", None, None), ("4Q26", 3200.0, 4000.0)])
        out2 = C.compute(chain, cos_up, ds_up, since="2025Q1")
        ant2 = next(x for x in out2["emergingBuyers"] if x["code"] == "anthropic")
        self.assertEqual(ant2["status"], "ok")
        self.assertEqual(ant2["path"], "anthropic/")
        self.assertEqual(ant2["capex"]["latest"], 3200.0)
        self.assertEqual(len(ant2["history"]), 1)

    def test_real_site_data(self):
        out = C.load()
        self.assertEqual([b["code"] for b in out["buyers"]], ["msft", "amzn", "googl", "meta"])
        self.assertEqual([b["code"] for b in out["buyerCards"]], ["msft", "amzn", "googl", "meta"])
        self.assertEqual([b["code"] for b in out["emergingBuyers"]], ["spcx", "anthropic"])
        self.assertEqual(len(out["tiers"]), 5)
        self.assertEqual(len(out["suppliers"]), 19)
        full = [r for r in out["rows"] if r["total"] is not None]
        self.assertGreater(len(full), 20)
        for r in full:
            self.assertAlmostEqual(r["total"], sum(r["capex"].values()), places=1)
        # 驗證 25 家重點資料
        by_b = {x["code"]: x for x in out["buyerCards"] + out["emergingBuyers"]}
        by_s = {x["code"]: x for x in out["suppliers"]}
        self.assertEqual(by_b["meta"]["capex"]["guidance"]["kind"], "written")
        self.assertEqual(by_b["spcx"]["capex"]["latestPctRev"], 134.4)
        self.assertEqual(by_b["anthropic"]["status"], "pending_ipo")
        self.assertEqual(by_b["anthropic"]["path"], "")
        self.assertEqual(by_s["tsmc"]["capex"]["guidance"]["text"], "2026 全年 600–640 億美元")
        self.assertIsNotNone(by_s["axti"]["capex"]["latest"])
        self.assertTrue(any(h["capex"] is None for h in by_s["axti"]["history"]))


if __name__ == "__main__":
    unittest.main()
