import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import buffett as B, health as H  # noqa: E402


def mkQ(n, fye_end_q="4Q", **over):
    """n 季的手造資料（曆年會計年度）：季別從 1Q10 起算。"""
    Q = []
    for i in range(n):
        q = {"q": f"{i % 4 + 1}Q{10 + i // 4}", "rev": 100.0, "gm": 50.0, "ni": 10.0, "eps": 1.0, "ocf": 15.0, "capex": 5.0, "dps": None,
             "rd": f"{2010 + i // 4}-{(i % 4) * 3 + 4:02d}-15" if (i % 4) < 3 else f"{2011 + i // 4}-02-15",
             "shOut": 100.0, "cash": 50.0, "debt": 20.0, "buyback": 0.0, "equity": 200.0, "opInc": 20.0, "pretax": 12.0, "tax": 2.0}
        q.update({k: (v(i) if callable(v) else v) for k, v in over.items()})
        Q.append(q)
    return Q


def mkVal(Q, pe=15.0, c=30.0, months=None, cur="USD"):
    mon = months or [{"m": "2020-10", "d": "2020-10-30", "c": c, "eps4": c / pe, "pe": pe, "why": None}]
    return {"currency": cur, "monthly": mon, "stats": {"med5": 20.0}}


RATES = {"series": {"us_10y": {"name": "美十", "source": "FRED", "points": [["2020-09-30", 3.0], ["2020-10-30", 4.0], ["2020-11-13", 5.0]]},
                    "tw_10y": {"name": "台十", "source": "櫃買", "points": [["2020-10-30", 1.5]]}}}


class Months(unittest.TestCase):
    def test_shift(self):
        self.assertEqual(B.shift("2026-01", -1), "2025-12")
        self.assertEqual(B.shift("2026-10", -60), "2021-10")
        self.assertEqual(B.shift("2026-10", 3), "2027-01")

    def test_window_calendar_fy(self):
        w = B.window_months("4Q20", "12-31")
        self.assertEqual((w[0], w[-1], len(w)), ("2020-01", "2020-12", 12))

    def test_window_fy_ends_early_in_month(self):
        # 美光式：會計年度 09-03 結束，4Q26 期末 2026-09-03 → 終點算 2026-08
        w = B.window_months("4Q26", "09-03")
        self.assertEqual((w[0], w[-1]), ("2025-09", "2026-08"))

    def test_window_fy_sep(self):
        # 蘋果式：1Q26 期末 2025-12-31 → 2025-12；窗口 2025-01 ~ 2025-12
        w = B.window_months("1Q26", "09-30")
        self.assertEqual((w[0], w[-1]), ("2025-01", "2025-12"))

    def test_window_fy_jan(self):
        # 輝達式：3Q27（fye 01-31）期末 2026-10-31
        self.assertEqual(B.end_month("3Q27", "01-31"), "2026-10")


class Points(unittest.TestCase):
    def test_points_every_four_quarters(self):
        self.assertEqual(B.points(list(range(20))), [3, 7, 11, 15, 19])      # 19, 15, 11, 7, 3
        self.assertEqual(len(B.points(list(range(80)))), 11)
        self.assertEqual(B.points(list(range(2))), [])                       # 不足三季沒有近四季

    def test_ten_year_null_when_quarter_missing(self):
        Q = mkQ(12, eps=lambda i: None if i == 10 else 1.0)
        rows = B.ten_year(Q, None, B.points(Q))
        self.assertIsNone(rows[-1]["eps"])          # 近四季含缺的一季 → null
        self.assertEqual(rows[-1]["why"]["eps"], "missing")
        self.assertEqual(rows[0]["eps"], 4.0)


class EY(unittest.TestCase):
    def test_usd_spread(self):
        e = B.calc_ey("USD", mkVal(None, pe=20), RATES)
        self.assertEqual(e["ey"], 5.0)
        self.assertEqual(e["bond"]["v"], 5.0)         # 最新一點
        self.assertEqual(e["spread"], 0.0)
        self.assertEqual(e["series"][0], ["2020-10", 5.0, 4.0, 1.0])   # 公債取該月最後一點

    def test_twd_uses_tw_bond(self):
        e = B.calc_ey("TWD", mkVal(None, pe=20, cur="TWD"), RATES)
        self.assertEqual(e["bond"]["v"], 1.5)
        self.assertEqual(e["spread"], 3.5)

    def test_other_currency_ref_only(self):
        e = B.calc_ey("EUR", mkVal(None, pe=20, cur="EUR"), RATES)
        self.assertIsNone(e["bond"])
        self.assertIsNone(e["spread"])
        self.assertEqual(e["bondWhy"], "nobond")
        self.assertEqual(e["ref"]["v"], 5.0)
        self.assertIn("美國十年期", e["refNote"])

    def test_pe_unusable(self):
        for row, why in (({"m": "2020-10", "d": "2020-10-30", "c": 3, "pe": None, "why": "loss"}, "loss"),
                         ({"m": "2020-10", "d": "2020-10-30", "c": 3, "pe": 250.0, "why": None}, "noisy"),
                         ({"m": "2020-10", "d": "2020-10-30", "c": 3, "pe": -2.0, "why": None}, "loss")):
            e = B.calc_ey("USD", mkVal(None, months=[row]), RATES)
            self.assertIsNone(e["ey"])
            self.assertIsNone(e["spread"])
            self.assertEqual(e["why"], why)

    def test_no_rates(self):
        e = B.calc_ey("USD", mkVal(None), None)
        self.assertEqual(e["bondWhy"], "norates")
        self.assertIsNone(e["spread"])
        self.assertEqual(B.spread_series(mkVal(None, cur="KRW"), RATES)[0][2], None)


class Implied(unittest.TestCase):
    def test_pe15_exit15_is_10pct(self):
        self.assertAlmostEqual(B.implied_g(15, 15), 0.10, places=9)

    def test_values(self):
        e = B.calc_ey("USD", mkVal(None, pe=30), RATES)
        o = B.calc_implied(e, [])
        self.assertAlmostEqual(o["g"]["15"], ((30 * 1.1 ** 10 / 15) ** 0.1 - 1) * 100, places=1)
        self.assertEqual(o["g"]["20"], round(((30 * 1.1 ** 10 / 20) ** 0.1 - 1) * 100, 1))

    def test_null(self):
        e = B.calc_ey("USD", mkVal(None, months=[{"m": "2020-10", "d": "2020-10-30", "c": 3, "pe": None, "why": "loss"}]), RATES)
        o = B.calc_implied(e, [])
        self.assertEqual(o["g"], {})
        self.assertEqual(o["why"], "loss")

    def test_eps_cagr(self):
        rows = [{"eps": 1.0}] + [{"eps": None}] * 4 + [{"eps": 2.0}]
        e = B.calc_ey("USD", mkVal(None, pe=15), RATES)
        self.assertEqual(B.calc_implied(e, rows)["epsCagr5"], round((2 ** 0.2 - 1) * 100, 1))
        rows[0]["eps"] = -1.0
        self.assertIsNone(B.calc_implied(e, rows)["epsCagr5"])


class Summary(unittest.TestCase):
    def test_roe_trend_and_gm(self):
        Q = mkQ(44, gm=lambda i: 60.0 - i * 0.5)
        pts = B.points(Q)
        hq = [{"q": q["q"], "roe": 20.0 - (j % 7), "why": {}} for j, q in enumerate(Q)]
        rows = B.ten_year(Q, {"quarterly": hq}, pts)
        s = B.summarize(rows, hq)
        self.assertEqual(s["years"], 11)
        self.assertEqual(s["lossYears"], 0)
        self.assertEqual(s["epsUp"], {"up": 0, "n": 10})            # eps 全部相同
        self.assertEqual(s["roeOk40"]["of"], 40)
        self.assertLess(s["gmChg3"], 0)                              # 毛利率逐年下降
        st = B.calc_structure(rows, s)
        self.assertIs(st["gmDown3"], s["gmChg3"] < -5)

    def test_roe_trend_true(self):
        rows = [{"roe": v, "eps": 1.0, "gm": 50.0, "bvps": 1.0} for v in (30, 25, 20, 15)]
        s = B.summarize(rows, [])
        self.assertTrue(s["roeTrend3"])
        rows[2]["roe"] = 26
        self.assertFalse(B.summarize(rows, [])["roeTrend3"])
        rows[2]["roe"] = None
        self.assertIsNone(B.summarize(rows, [])["roeTrend3"])

    def test_bv_cagr(self):
        rows = [{"roe": None, "eps": 1.0, "gm": 50.0, "bvps": b} for b in (10, 0, 0, 0, 0, 20)]
        rows[1:5] = [{"roe": None, "eps": 1.0, "gm": 50.0, "bvps": 1}] * 4
        self.assertEqual(B.summarize(rows, [])["bvCagr5"], round((2 ** 0.2 - 1) * 100, 1))

    def test_loss_years(self):
        Q = mkQ(24, eps=lambda i: -1.0 if i > 20 else 1.0)
        rows = B.ten_year(Q, None, B.points(Q))
        self.assertEqual(B.summarize(rows, [])["lossYears"], 1)
        self.assertTrue(B.calc_structure(rows, B.summarize(rows, []))["lossNow"])


class Record(unittest.TestCase):
    def hq(self, Q, f):
        return [{"q": q["q"], "roe": f(i), "why": {}} for i, q in enumerate(Q)]

    def run_rec(self, Q, hq):
        rows = B.ten_year(Q, {"quarterly": hq}, B.points(Q))
        return B.calc_record(Q, rows, hq, B.summarize(rows, hq))

    def test_ok(self):
        Q = mkQ(44)
        self.assertTrue(self.run_rec(Q, self.hq(Q, lambda i: 18.0))["tenYearOk"])

    def test_not_enough_quarters(self):
        Q = mkQ(30)
        self.assertFalse(self.run_rec(Q, self.hq(Q, lambda i: 18.0))["tenYearOk"])

    def test_loss_year(self):
        Q = mkQ(44, eps=lambda i: -1.0 if 20 <= i <= 23 else 1.0)
        self.assertFalse(self.run_rec(Q, self.hq(Q, lambda i: 18.0))["tenYearOk"])

    def test_roe_rate(self):
        Q = mkQ(44)
        self.assertTrue(self.run_rec(Q, self.hq(Q, lambda i: 18.0 if i % 5 else 5.0))["tenYearOk"])    # 達標約 80% 以上
        self.assertFalse(self.run_rec(Q, self.hq(Q, lambda i: 18.0 if i % 2 else 5.0))["tenYearOk"])   # 只有一半

    def test_roe_none_is_null(self):
        Q = mkQ(44)
        self.assertIsNone(self.run_rec(Q, self.hq(Q, lambda i: None))["tenYearOk"])


class Buyback(unittest.TestCase):
    def months(self, pes):
        out = []
        for k, p in enumerate(pes):
            m = B.shift("2010-01", k)
            out.append({"m": m, "d": m + "-28", "c": 10.0, "eps4": 1.0, "pe": p, "why": None})
        return out

    def test_where_tags(self):
        Q = mkQ(12, buyback=lambda i: 10.0 if i >= 8 else 0.0)
        # 4Q12 的窗口 2012-01..2012-12；這 12 個月 pe 都是 30，中位數 20 → 30 > 22 偏貴
        mon = self.months([20.0] * 24 + [30.0] * 12)       # 2010-01 起 36 個月；2012-01 是第 24 個
        val = mkVal(Q, months=mon)
        out = B.calc_buyback(Q, val, B.points(Q), "12-31", (None, None, "noprice"))
        last = out["rows"][-1]
        self.assertEqual((last["q"], last["from"], last["to"]), ("4Q12", "2012-01", "2012-12"))
        self.assertEqual(last["avgPe"], 30.0)
        self.assertEqual(last["where"], "偏貴時買")
        self.assertEqual(last["buyback"], 40.0)
        self.assertIsNone(out["rows"][0]["where"])          # 回購為 0 不標
        val["monthly"] = self.months([10.0] * 36)
        self.assertEqual(B.calc_buyback(Q, val, B.points(Q), "12-31", (None, None, None))["rows"][-1]["where"], "偏便宜時買")
        val["monthly"] = self.months([21.0] * 36)
        self.assertEqual(B.calc_buyback(Q, val, B.points(Q), "12-31", (None, None, None))["rows"][-1]["where"], "接近平常")

    def test_fewer_than_six_months(self):
        Q = mkQ(8, buyback=5.0)
        val = mkVal(Q, months=self.months([20.0] * 5))
        out = B.calc_buyback(Q, val, B.points(Q), "12-31", (None, None, None))
        self.assertTrue(all(r["avgPe"] is None and r["where"] is None for r in out["rows"]))

    def test_yield_and_shchg(self):
        Q = mkQ(28, buyback=2.0, shOut=lambda i: 100.0 - i)
        pts = B.points(Q)
        mc = (1000.0, 27, None)
        out = B.calc_buyback(Q, mkVal(Q), pts, "12-31", mc)
        self.assertEqual(out["buybackYield"], round(8.0 / 1000 * 100, 2))
        self.assertEqual(out["shChg5"], round((Q[pts[-1]]["shOut"] / Q[pts[-6]]["shOut"] - 1) * 100, 1))


def set_rd(Q):
    for i, q in enumerate(Q):
        q["rd"] = f"{2010 + i // 4}-{(i % 4) * 3 + 4:02d}-15" if i % 4 < 3 else f"{2011 + i // 4}-01-20"


class Retained(unittest.TestCase):
    def val(self):
        # 2011-03-28 與 60 個月後的 2016-03-28：兩個時間點都已有已公布的季度
        return {"currency": "USD", "stats": {}, "monthly": [{"m": "2011-03", "d": "2011-03-28", "c": 10.0, "pe": 5}, {"m": "2016-03", "d": "2016-03-28", "c": 30.0, "pe": 5}]}

    def test_noDiv_and_ratio(self):
        Q = mkQ(24)
        set_rd(Q)
        val = self.val()
        mc = B.mcap_at(Q, val["monthly"][-1])
        out = B.calc_retained(Q, val, mc)
        self.assertTrue(out["noDiv"])
        self.assertEqual((out["m0"], out["mNow"]), ("2011-03", "2016-03"))
        self.assertEqual(out["kept"], 200.0)                 # 20 季 × 淨利 10，沒有股利
        self.assertEqual(out["mcap0"], 1000.0)               # 10 × 100 股
        self.assertEqual(out["mcapChg"], 2000.0)             # 3000 − 1000
        self.assertEqual(out["ratio"], 10.0)

    def test_dividend_subtracted(self):
        Q = mkQ(24, dps=0.5)
        set_rd(Q)
        val = self.val()
        out = B.calc_retained(Q, val, B.mcap_at(Q, val["monthly"][-1]))
        self.assertFalse(out["noDiv"])
        self.assertEqual(out["div20"], 20 * 0.5 * 100.0)     # 每季 0.5 × 100 股 = 50，20 季 1000
        self.assertEqual(out["kept"], 200.0 - 1000.0)
        self.assertIsNone(out["ratio"])                      # 保留盈餘 ≤ 0
        self.assertEqual(out["why"], "neg")

    def test_missing_dps_is_null(self):
        Q = mkQ(24, dps=lambda i: 0.5 if i > 10 else None)
        set_rd(Q)
        val = self.val()
        out = B.calc_retained(Q, val, B.mcap_at(Q, val["monthly"][-1]))
        self.assertIsNone(out["kept"])
        self.assertEqual(out["why"], "missing")

    def test_no_price_month_five_years_ago(self):
        Q = mkQ(24)
        set_rd(Q)
        val = self.val()
        val["monthly"][0]["m"] = "2011-04"
        out = B.calc_retained(Q, val, B.mcap_at(Q, val["monthly"][-1]))
        self.assertIsNone(out["ratio"])
        self.assertEqual(out["why"], "short")

    def test_short_history(self):
        Q = mkQ(10)
        self.assertEqual(B.calc_retained(Q, mkVal(Q), (1.0, 9, None))["why"], "short")

    def test_pays_dividend_but_not_recorded_is_null(self):
        # dps 全空，但資料說明寫了「每股股利…留空」：公司有配息、只是沒收錄 → 不能把股利當 0
        Q = mkQ(24)
        set_rd(Q)
        val = self.val()
        D = {"notes": {"unavailable": ["每股股利：一年配一次現金股利，本頁 dps 欄位全部留空"]}}
        out = B.calc_retained(Q, val, B.mcap_at(Q, val["monthly"][-1]), D)
        self.assertFalse(out["noDiv"])
        self.assertIsNone(out["kept"])
        self.assertIsNone(out["ratio"])
        self.assertEqual(out["why"], "nodps")
        # 資料說明沒提到股利 → 視為不配息，照舊當 0
        out = B.calc_retained(Q, val, B.mcap_at(Q, val["monthly"][-1]), {"notes": {"unavailable": ["待確認：1Q20 的財報公布日（rd）"]}})
        self.assertTrue(out["noDiv"])
        self.assertEqual(out["ratio"], 10.0)


class VsIndex(unittest.TestCase):
    def mk(self):
        dates = ["2019-12-30", "2020-12-30", "2022-12-29", "2024-12-30", "2025-12-30"]
        return {"USD": {"name": "S", "dates": dates, "close": [100.0, 110.0, 150.0, 200.0, 220.0]}}

    def test_usd(self):
        pr = {"monthly": [{"m": "2019-12", "d": "2019-12-31", "c": 10.0}, {"m": "2024-12", "d": "2024-12-31", "c": 40.0}, {"m": "2025-12", "d": "2025-12-31", "c": 50.0}]}
        v = B.calc_vs_index("USD", pr, self.mk())
        r1 = v["rows"][0]
        self.assertEqual((r1["from"], r1["to"]), ("2024-12", "2025-12"))
        self.assertEqual(r1["stock"], 25.0)
        self.assertEqual(r1["index"], 10.0)
        self.assertEqual(r1["diff"], 15.0)
        self.assertIsNone(v["rows"][1]["stock"])               # 2022-12 沒有股價
        self.assertEqual(v["rows"][1]["why"], "short")

    def test_other_currency_null(self):
        for cur in ("EUR", "KRW"):
            v = B.calc_vs_index(cur, {"monthly": []}, self.mk())
            self.assertEqual(v["why"], "noidx")
            self.assertEqual(v["rows"], [])

    def test_twd_without_index_file(self):
        self.assertEqual(B.calc_vs_index("TWD", {"monthly": [{"m": "2025-12", "d": "2025-12-31", "c": 5.0}]}, self.mk())["why"], "noidx")

    def test_index_stale(self):
        self.assertIsNone(B.idx_close(self.mk()["USD"], "2025-12-31") and None)
        self.assertEqual(B.idx_close(self.mk()["USD"], "2025-12-31"), 220.0)
        self.assertIsNone(B.idx_close(self.mk()["USD"], "2026-03-31"))      # 超過 5 天沒有資料


class NormPe(unittest.TestCase):
    def test_avg(self):
        Q = mkQ(24)
        rows = B.ten_year(Q, None, B.points(Q))
        o = B.calc_norm_pe(rows, mkVal(Q, c=40.0))
        self.assertEqual(o["avgEps"], 4.0)
        self.assertEqual(o["normPe"], 10.0)

    def test_short_and_neg(self):
        Q = mkQ(12)
        self.assertEqual(B.calc_norm_pe(B.ten_year(Q, None, B.points(Q)), mkVal(Q))["why"], "short")
        Q = mkQ(24, eps=-1.0)
        self.assertEqual(B.calc_norm_pe(B.ten_year(Q, None, B.points(Q)), mkVal(Q))["why"], "neg")


class Compute(unittest.TestCase):
    def test_smoke(self):
        Q = mkQ(44, dps=0.1)
        D = {"quarters": Q}
        out = B.compute({"currency": "USD"}, D, Q, mkVal(Q), None, None, RATES, {}, {"type": "growth"})
        for k in ("ey", "tenYear", "summary", "buyback", "retained", "vsIndex", "implied", "normPe", "quality", "structure", "record"):
            self.assertIn(k, out)
        self.assertEqual(out["type"], "growth")
        self.assertEqual(out["quality"]["payout"], round(4 * 0.1 * 100 / 40.0 * 100, 0))
        self.assertIsNone(out["record"]["tenYearOk"])        # health 沒給 → ROE 完全沒有值
        self.assertIsNone(B.compute({}, {"quarters": []}, [], None, None, None, None, {}, None))


if __name__ == "__main__":
    unittest.main()
