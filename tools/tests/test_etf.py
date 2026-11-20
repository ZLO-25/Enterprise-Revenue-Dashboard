import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import etf_update as E
import kbar_update as K

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def series(start, n, f):
    import datetime as dt
    d0 = dt.date.fromisoformat(start)
    return [[(d0 + dt.timedelta(days=i)).isoformat(), f(i)] for i in range(n)]


class Config(unittest.TestCase):
    def test_real_config_ok(self):
        cfg = E.config()
        self.assertEqual(E.check_config(cfg), [])
        cos = {c["code"] for c in json.load(open(os.path.join(ROOT, "companies.json")))["companies"]}
        for e in cfg["etfs"]:
            self.assertNotIn(e["code"], cos)
        for code in cfg["aliases"].values():
            self.assertIn(code, cos)

    def test_bad_config(self):
        bad = {"groups": ["大盤"], "etfs": [{"code": "VOO", "group": "其他"}, {"code": "etf_a", "group": "大盤", "from": "2026"}]}
        err = "\n".join(E.check_config(bad))
        self.assertIn("etf_ 開頭", err)
        self.assertIn("不在 groups", err)
        self.assertIn("YYYY-MM", err)
        self.assertIn("缺 ticker", err)


class Returns(unittest.TestCase):
    def test_windows(self):
        rows = series("2020-01-01", 2200, lambda i: 100 + i * 0.1)   # 到 2026-01-08 左右
        R = E.returns(rows)
        self.assertEqual(R["last"]["d"], rows[-1][0])
        self.assertIsNotNone(R["ret"]["y5"])
        self.assertIsNotNone(R["ret"]["y5a"])
        # 1 年：基準是一年前同一天的收盤
        last = R["last"]["c"]
        b = [r for r in rows if r[0] == R["base"]["y1"]][0][1]
        self.assertAlmostEqual(R["ret"]["y1"], round((last / b - 1) * 100, 2))
        self.assertEqual(R["base"]["ytd"], "2025-12-31")

    def test_short_history_is_null(self):
        rows = series("2026-04-02", 200, lambda i: 10 + i)
        R = E.returns(rows)
        self.assertIsNone(R["ret"]["y1"])
        self.assertIsNone(R["ret"]["y3"])
        self.assertIsNone(R["ret"]["y3a"])
        self.assertIsNone(R["ret"]["y5a"])
        self.assertIsNotNone(R["ret"]["m3"])
        self.assertIsNone(R["ret"]["ytd"])          # 去年底還沒掛牌

    def test_null_close_skipped(self):
        rows = [["2026-01-01", 10.0], ["2026-01-02", None], ["2026-02-02", 11.0], ["2026-02-03", None]]
        R = E.returns(rows)
        self.assertEqual(R["last"], {"d": "2026-02-02", "c": 11.0})
        self.assertEqual(R["ret"]["m1"], 10.0)

    def test_empty(self):
        self.assertIsNone(E.returns([])["last"])


class Holdings(unittest.TestCase):
    cos = [{"code": "nvda", "name": "NVIDIA", "path": "nvda/", "price": {"yahoo": "NVDA"}, "ticker": "NVDA"},
           {"code": "tsmc", "name": "台積電", "path": "tsmc/", "price": {"yahoo": "2330.TW"}, "ticker": "2330"},
           {"code": "asml", "name": "ASML", "path": "asml/", "price": {"yahoo": "ASML.AS"}, "ticker": "ASML"}]

    def test_map_and_parse(self):
        smap = E.symbol_map(self.cos, {"TSM": "tsmc"})
        self.assertEqual(smap["NVDA"], "nvda")
        self.assertEqual(smap["TSM"], "tsmc")
        self.assertEqual(smap["ASML"], "asml")          # ASML.AS 的前段
        self.assertNotIn("2330", [k for k in smap if k == "2330" and smap[k] != "tsmc"])
        by = {c["code"]: c for c in self.cos}
        rows, s, flag = E.parse_holdings([("NVDA", "NVIDIA Corp", 0.2), ("TSM", "Taiwan Semi", 0.1), ("XYZ", "Other", 0.05), ("BAD", "nan", float("nan"))],
                                         smap, by, lambda c: (12.5, "2026-11-19") if c == "nvda" else None)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["href"], "nvda/")
        self.assertEqual(rows[0]["r1y"], 12.5)
        self.assertEqual(rows[1]["code"], "tsmc")
        self.assertNotIn("r1y", rows[1])
        self.assertNotIn("code", rows[2])
        self.assertEqual(s, 35.0)
        self.assertIsNone(flag)

    def test_bad_weights(self):
        _, _, f = E.parse_holdings([("A", "a", 1.5)], {}, {}, lambda c: None)
        self.assertTrue(f.startswith("待確認"))
        _, _, f = E.parse_holdings([(str(i), "x", 0.2) for i in range(6)], {}, {}, lambda c: None)
        self.assertIn("超過 100%", f)


class Expense(unittest.TestCase):
    def test_units(self):
        self.assertEqual(E.expense(0.0035, 0.35)["pct"], 0.35)
        self.assertNotIn("flag", E.expense(0.0035, 0.35))
        self.assertEqual(E.expense(None, 0.03)["pct"], 0.03)

    def test_flags(self):
        self.assertIn("flag", E.expense(None, None))
        o = E.expense(0.35, None)                      # 35% 不合理
        self.assertIsNone(o["pct"])
        self.assertIn("不合理", o["flag"])
        self.assertIn("不一致", E.expense(0.0035, 0.6)["flag"])


class Entry(unittest.TestCase):
    e = {"code": "etf_x", "ticker": "X", "name": "X ETF", "group": "大盤", "yahoo": "X", "currency": "USD", "issuer": "I", "why": "w", "issuerUrl": "https://i"}

    def test_keeps_previous_fund_data(self):
        prev = {"holdings": {"asOf": "2026-11-13", "rows": [{"sym": "NVDA", "w": 10, "code": "nvda"}], "src": "s"}, "er": {"pct": 0.1, "asOf": "2026-11-13"}}
        by = {"nvda": {"code": "nvda", "name": "輝達", "path": "nvda/"}}
        out = E.build_entry(self.e, {"rows": [["2026-11-19", 1.0]]}, prev, None, "2026-11-20", {"NVDA": "nvda"}, by, lambda c: (5.0, "2026-11-19"))
        self.assertEqual(out["er"]["pct"], 0.1)
        self.assertEqual(out["holdings"]["rows"][0]["r1y"], 5.0)
        # 抓了但沒抓到 → 沿用並註明
        out = E.build_entry(self.e, None, prev, {"items": [], "er_ops": None, "er_info": None}, "2026-11-20", {}, {}, lambda c: None)
        self.assertIn("沿用", out["holdings"]["stale"])
        self.assertIn("沿用", out["er"]["stale"])

    def test_never_fetched(self):
        out = E.build_entry(dict(self.e, twse="0050"), None, None, {"items": None}, "2026-11-20", {}, {}, lambda c: None)
        self.assertTrue(out["holdings"]["flag"].startswith("待確認"))
        self.assertIn("twse", out["links"])

    def test_due(self):
        self.assertTrue(E.due(None, "2026-11-20", 7))
        self.assertFalse(E.due({"holdings": {"asOf": "2026-11-15"}}, "2026-11-20", 7))
        self.assertTrue(E.due({"holdings": {"asOf": "2026-11-13"}}, "2026-11-20", 7))


class KbarIncludesEtf(unittest.TestCase):
    def test_etf_items(self):
        cos = K.companies()
        etfs = [c for c in cos if c["code"].startswith("etf_")]
        self.assertEqual(len(etfs), len(E.config()["etfs"]))
        self.assertTrue(all(c["dailyDir"].endswith(os.path.join("data", "etf", "daily")) for c in etfs))
        self.assertEqual([c["code"] for c in K.companies("etf_voo")], ["etf_voo"])

    def test_explicit_cfg_has_no_etf(self):
        self.assertEqual(K.companies(cfg={"companies": []}), [])


if __name__ == "__main__":
    unittest.main()


class KbarEtfHistory(unittest.TestCase):
    def test_default_from_and_refetch(self):
        it = [c for c in K.companies() if c["code"] == "etf_voo"][0]
        self.assertEqual(it["price"]["from"], K.ETF_FROM)
        daily = {"rows": [["2010-09-09", 1.0], ["2026-11-19", 2.0]]}
        self.assertTrue(K.etf_short(it, {"firstDate": "2016-01-04"}, daily))
        self.assertFalse(K.etf_short(it, {"firstDate": "2010-09-09"}, daily))
        self.assertFalse(K.etf_short({"price": {"from": "2016-01"}}, {"firstDate": "2026-10-22"}, daily))   # 公司不套用
        self.assertTrue(K.etf_short(it, {"firstDate": "2026-10-22"}))          # 沒有每日檔：用 from 判斷


class V2(unittest.TestCase):
    def test_since_inception_and_10y(self):
        rows = series("2012-01-02", 5400, lambda i: 100 + i * 0.05)
        R = E.returns(rows)
        self.assertIsNotNone(R["ret"]["y10"])
        self.assertIsNotNone(R["ret"]["y10a"])
        self.assertEqual(R["base"]["all"], "2012-01-02")
        self.assertAlmostEqual(R["ret"]["all"], round((rows[-1][1] / 100 - 1) * 100, 2))
        self.assertIsNotNone(R["ret"]["alla"])
        short = E.returns(series("2026-06-01", 100, lambda i: 10 + i))
        self.assertIsNone(short["ret"]["alla"])          # 不滿 1 年不算年化
        self.assertIsNotNone(short["ret"]["all"])

    def test_tw_names(self):
        self.assertEqual(E.tw_code("2330.TW"), "2330")
        self.assertEqual(E.tw_code("5274.TWO"), "5274")
        self.assertIsNone(E.tw_code("NVDA"))
        rows, _, _ = E.parse_holdings([("2454.TW", "MediaTek Inc", 0.07), ("NVDA", "NVIDIA", 0.1)], {}, {}, lambda c: None, {"2454": "聯發科"})
        self.assertEqual(rows[0]["zh"], "聯發科")
        self.assertNotIn("zh", rows[1])

    def test_commodity_has_note_not_flag(self):
        e = {"code": "etf_g", "ticker": "G", "name": "G", "group": "x", "yahoo": "G", "currency": "USD", "issuer": "i", "why": "w",
             "kind": "commodity", "holdingsNote": "持有實物黃金，沒有股票持股。"}
        out = E.build_entry(e, None, None, {"items": None, "er_ops": 0.004, "er_info": None}, "2026-11-20", {}, {}, lambda c: None)
        self.assertEqual(out["holdings"]["note"], e["holdingsNote"])
        self.assertNotIn("flag", out["holdings"])
        self.assertEqual(out["er"]["pct"], 0.4)
        out2 = E.build_entry(e, None, None, None, "2026-11-20", {}, {}, lambda c: None)
        self.assertEqual(out2["holdings"]["note"], e["holdingsNote"])


class Remap(unittest.TestCase):
    def test_daily_remap_without_refetch(self):
        e = {"code": "etf_x", "ticker": "X", "name": "X", "group": "g", "yahoo": "X", "currency": "USD", "issuer": "i", "why": "w"}
        prev = {"holdings": {"asOf": "2026-11-20", "rows": [{"sym": "005930.KQ", "name": "Samsung", "w": 19.0}]}}
        by = {"samsung": {"code": "samsung", "name": "三星電子", "path": "samsung/"}}
        out = E.build_entry(e, None, prev, None, "2026-11-21", {"005930.KQ": "samsung"}, by, lambda c: (10.0, "2026-11-20"))
        r = out["holdings"]["rows"][0]
        self.assertEqual((r["code"], r["co"], r["r1y"]), ("samsung", "三星電子", 10.0))
