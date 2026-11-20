import datetime as dt, json, os, shutil, sys, tempfile, unittest, zlib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import kbar_update as K

PW = "test-password-123456"


def B(d, c=10.0, v=100, o=None, h=None, l=None):
    o = c if o is None else o
    return [d, o, max(o, c) + 1 if h is None else h, min(o, c) - 1 if l is None else l, c, v]


def daily(rows, check=None):
    return {"rows": [list(r) for r in rows], "check": check}


def make_key(root):
    import base64
    os.makedirs(os.path.join(root, "data", "futures"))
    json.dump({"salt": base64.b64encode(b"0123456789abcdef").decode(), "iter": 1000},
              open(os.path.join(root, "data", "futures", "key.json"), "w"))


class Split(unittest.TestCase):
    def test_cut_date(self):
        self.assertEqual(K.cut_date(dt.date(2026, 11, 19)), "2025-01-01")
        self.assertEqual(K.cut_date("2027-01-01"), "2026-01-01")

    def test_boundary(self):
        bars = [B("2024-12-31"), B("2025-01-01"), B("2025-01-02")]
        h, r = K.split_bars(bars, "2025-01-01")
        self.assertEqual([b[0] for b in h], ["2024-12-31"])
        self.assertEqual([b[0] for b in r], ["2025-01-01", "2025-01-02"])

    def test_no_hist(self):
        h, r = K.split_bars([B("2025-03-01")], "2025-01-01")
        self.assertEqual(h, [])
        self.assertEqual(K.hist_decision(None, False, "x", h)[0], "none")

    def test_plain_matches_pack(self):
        o = {"code": "x", "bars": [["2025-01-01", 1.5, 2, 1, 1.2, None]]}
        self.assertEqual(zlib.decompress(K.FU.pack(o)), K.plain_bytes(o))


class HistSha(unittest.TestCase):
    hist = [B("2024-06-03", 5), B("2024-06-04", 6)]

    def test_same_keeps(self):
        sha = K.hist_sha("x", self.hist)
        prev = {"hist": {"sha": sha, "bars": 2}}
        self.assertEqual(K.hist_decision(prev, True, "x", self.hist)[0], "keep")

    def test_split_changes_sha(self):   # 分割後歷史價格整批調整
        prev = {"hist": {"sha": K.hist_sha("x", self.hist), "bars": 2}}
        adj = [[b[0]] + [round(p / 2, 4) for p in b[1:5]] + [b[5]] for b in self.hist]
        act, sha, why = K.hist_decision(prev, True, "x", adj)
        self.assertEqual(act, "rewrite")
        self.assertNotIn("5", why.replace("2024-06-04", ""))  # 原因只含筆數與日期

    def test_missing_file_rewrites(self):
        prev = {"hist": {"sha": K.hist_sha("x", self.hist)}}
        self.assertEqual(K.hist_decision(prev, False, "x", self.hist)[0], "rewrite")

    def test_first_time(self):
        self.assertEqual(K.hist_decision(None, False, "x", self.hist)[0], "rewrite")


class DailyCheck(unittest.TestCase):
    bars = [B("2026-11-16", 10), B("2026-11-17", 11), B("2026-11-18", 12)]

    def test_later_than_daily_dropped(self):
        d = daily([("2026-11-16", 10), ("2026-11-17", 11)])
        kept, pend, chk = K.verify_with_daily(self.bars, d)
        self.assertEqual([b[0] for b in kept], ["2026-11-16", "2026-11-17"])
        self.assertEqual(pend, [])

    def test_daily_null_blocks_from_that_day(self):
        d = daily([("2026-11-16", 10), ("2026-11-17", None), ("2026-11-18", 12)])
        kept, pend, _ = K.verify_with_daily(self.bars, d)
        self.assertEqual([b[0] for b in kept], ["2026-11-16"])
        self.assertTrue(pend[0]["reason"].startswith("待確認：") and "2026-11-17" in pend[0]["reason"])

    def test_diff_over_half_percent(self):
        d = daily([("2026-11-16", 10), ("2026-11-17", 11.1), ("2026-11-18", 12)])   # 0.9%
        kept, pend, _ = K.verify_with_daily(self.bars, d)
        self.assertEqual([b[0] for b in kept], ["2026-11-16"])
        self.assertIn("2026-11-17", pend[0]["reason"])
        self.assertNotIn("11.1", pend[0]["reason"])   # 不印價格

    def test_within_tolerance(self):
        d = daily([("2026-11-16", 10), ("2026-11-17", 11.04), ("2026-11-18", 12)])   # 0.36%
        kept, pend, chk = K.verify_with_daily(self.bars, d)
        self.assertEqual(len(kept), 3)
        self.assertEqual(pend, [])
        self.assertIn("一致", chk["note"])

    def test_no_daily_file(self):
        kept, pend, chk = K.verify_with_daily(self.bars, None)
        self.assertEqual(len(kept), 3)
        self.assertIn("未核對", chk["note"])

    def test_old_mismatch_beyond_window_ignored(self):
        rows = [("2026-10-%02d" % i, 1) for i in range(1, 15)] + [("2026-11-16", 10), ("2026-11-17", 11), ("2026-11-18", 12)]
        old = [B("2026-10-01", 50)] + list(self.bars)
        kept, pend, _ = K.verify_with_daily(old, daily(rows))
        self.assertEqual(len(kept), 4)

    def test_daily_last(self):
        self.assertEqual(K.daily_last(daily([("a", 1), ("b", None)])), "a")
        self.assertIsNone(K.daily_last(None))


class Volume(unittest.TestCase):
    def test_last_same_as_prev_null(self):
        bars = [B("2026-11-17", v=500), B("2026-11-18", v=500)]
        K.fix_last_volume(bars)
        self.assertIsNone(bars[-1][5])
        self.assertEqual(bars[0][5], 500)

    def test_different_kept(self):
        bars = [B("2026-11-17", v=500), B("2026-11-18", v=501)]
        K.fix_last_volume(bars)
        self.assertEqual(bars[-1][5], 501)

    def test_sane(self):
        self.assertTrue(K.sane_bar(B("d", 10, v=None)))
        self.assertFalse(K.sane_bar(["d", 10, 9, 8, 10, 1]))
        bars, pend, prov = K.finalize([["2026-11-17", 10, 9, 8, 10, 1], B("2026-11-18")], set())
        self.assertEqual(len(bars), 1)
        self.assertTrue(pend[0]["reason"].startswith("待確認：開高低收不合理"))


NAN = float("nan")
TZ = ("America/New_York", 16, 0)


def ny(y, m, d, hh, mm):
    from zoneinfo import ZoneInfo
    return dt.datetime(y, m, d, hh, mm, tzinfo=ZoneInfo("America/New_York"))


def info_at(t, **kw):
    base = {"regularMarketTime": int(t.timestamp()), "regularMarketOpen": 10.0, "dayHigh": 12.0, "dayLow": 9.0,
            "regularMarketPrice": 11.0, "regularMarketVolume": 777}
    base.update(kw)
    return base


class Provisional(unittest.TestCase):
    d1, d2 = dt.date(2026, 11, 17), dt.date(2026, 11, 18)

    def raw(self, last):
        return [(self.d1, 10, 11, 9, 10.5, 100), last]

    def test_today_not_done_skipped(self):
        raw = self.raw((self.d2, 10, 11, 9, 10.5, 50))
        bars, prov = K.normalize_rows(raw, ny(2026, 11, 18, 16, 10), TZ, lambda: {})
        self.assertEqual([b[0] for b in bars], ["2026-11-17"])
        bars, prov = K.normalize_rows(raw, ny(2026, 11, 18, 16, 20), TZ, lambda: {})
        self.assertEqual(len(bars), 2)
        self.assertEqual(prov, set())

    def test_close_nan_uses_quote(self):
        now = ny(2026, 11, 18, 17, 0)
        info = info_at(ny(2026, 11, 18, 16, 0))
        bars, prov = K.normalize_rows(self.raw((self.d2, 10, 12, 9, NAN, 777)), now, TZ, lambda: info)
        self.assertEqual(bars[-1][4], 11.0)
        self.assertEqual(prov, {"2026-11-18"})

    def test_close_nan_quote_not_ready(self):
        now = ny(2026, 11, 18, 17, 0)
        info = info_at(ny(2026, 11, 18, 15, 0))   # 盤中報價
        bars, prov = K.normalize_rows(self.raw((self.d2, 10, 12, 9, NAN, 777)), now, TZ, lambda: info)
        self.assertEqual(len(bars), 1)

    def test_full_nan_uses_info(self):
        now = ny(2026, 11, 18, 17, 0)
        info = info_at(ny(2026, 11, 18, 16, 0))
        bars, prov = K.normalize_rows(self.raw((self.d2, NAN, NAN, NAN, NAN, NAN)), now, TZ, lambda: info)
        self.assertEqual(bars[-1], ["2026-11-18", 10.0, 12.0, 9.0, 11.0, 777])
        self.assertEqual(prov, {"2026-11-18"})

    def test_full_nan_missing_field_or_other_day(self):
        now = ny(2026, 11, 18, 17, 0)
        for info in (info_at(ny(2026, 11, 18, 16, 0), regularMarketVolume=None),
                     info_at(ny(2026, 11, 17, 16, 0)), {}):
            bars, prov = K.normalize_rows(self.raw((self.d2, NAN, NAN, NAN, NAN, NAN)), now, TZ, lambda i=info: i)
            self.assertEqual(len(bars), 1)
            self.assertEqual(prov, set())

    def test_old_nan_row_not_filled(self):
        raw = [(self.d1, NAN, NAN, NAN, NAN, NAN), (self.d2, 10, 11, 9, 10.5, 50)]
        called = []
        bars, _ = K.normalize_rows(raw, ny(2026, 11, 18, 17, 0), TZ, lambda: called.append(1) or {})
        self.assertEqual([b[0] for b in bars], ["2026-11-18"])
        self.assertEqual(called, [])

    def test_zero_volume_null(self):
        bars, _ = K.normalize_rows([(self.d1, 10, 11, 9, 10.5, 0)], ny(2026, 11, 18, 17, 0), TZ, lambda: {})
        self.assertIsNone(bars[0][5])

    def test_yesterday_nan_close_with_intraday_today(self):
        # 盤中（今天還沒收）時 Yahoo 已有今天那一列，昨天收盤仍是 NaN：昨天要用收盤後報價補，今天不收
        d0 = dt.date(2026, 11, 16)
        raw = [(d0, 10, 11, 9, 10.5, 100), (self.d1, 10, 12, 9, NAN, 777), (self.d2, 10, 11, 9, 10.2, 50)]
        info = info_at(ny(2026, 11, 17, 16, 0))
        bars, prov = K.normalize_rows(raw, ny(2026, 11, 18, 10, 0), TZ, lambda: info)
        self.assertEqual([b[0] for b in bars], ["2026-11-16", "2026-11-17"])
        self.assertEqual(bars[-1][4], 11.0)
        self.assertEqual(prov, {"2026-11-17"})

    def test_info_zero_volume_null(self):
        b = K.info_to_bar(info_at(ny(2026, 11, 18, 16, 0), regularMarketVolume=0), self.d2, *TZ)
        self.assertIsNotNone(b)
        self.assertIsNone(b[5])

    def test_flag_in_finalize(self):
        bars, pend, prov = K.finalize([B("2026-11-18")], {"2026-11-18"})
        self.assertTrue(prov)


class Need(unittest.TestCase):
    def test_cases(self):
        d = daily([("2026-11-17", 1), ("2026-11-18", 2)])
        self.assertTrue(K.needs_fetch(None, d))
        self.assertTrue(K.needs_fetch({"lastDate": "2026-11-18", "provisional": True}, d))
        self.assertTrue(K.needs_fetch({"lastDate": "2026-11-17"}, d))
        self.assertFalse(K.needs_fetch({"lastDate": "2026-11-18"}, d))
        self.assertFalse(K.needs_fetch({"lastDate": "2026-11-19"}, d))
        self.assertTrue(K.needs_fetch({"lastDate": "2026-11-18"}, None))

    def test_companies(self):
        cfg = {"companies": [{"code": "a", "price": {"yahoo": "A"}}, {"code": "b", "enabled": False, "price": {"yahoo": "B"}},
                             {"code": "c"}, {"code": "d", "enabled": True, "price": {"yahoo": "D"}}]}
        self.assertEqual([c["code"] for c in K.companies(cfg=cfg)], ["a", "d"])
        self.assertEqual([c["code"] for c in K.companies("d", cfg)], ["d"])


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        make_key(self.tmp)
        self.out = os.path.join(self.tmp, "kbar")
        self.meta = {"code": "t", "name": "測試", "yahoo": "T", "currency": "USD", "exchange": "NASDAQ"}
        self.bars = [B("2024-05-01", 5), B("2024-05-02", 6), B("2025-01-02", 7), B("2025-01-03", 8, v=None)]

    def write(self, bars=None, **kw):
        return K.write_files(self.out, self.meta, bars or self.bars, PW, "2025-01-01", key_root=self.tmp, **kw)

    def read(self, name):
        return json.load(open(os.path.join(self.out, name)))

    def test_roundtrip_and_format(self):
        self.write(pending=[{"date": "x", "reason": "待確認：y"}], check={"n": "n", "note": "m"})
        o = self.read("t.enc.json")
        self.assertEqual((o["lastDate"], o["firstDate"], o["bars"], o["pendingCount"], o["provisional"]),
                         ("2025-01-03", "2024-05-01", 4, 1, False))
        self.assertEqual(set(o["hist"]), {"file", "lastDate", "bars", "sha"})
        self.assertEqual(o["hist"]["bars"], 2)
        for k in ("v", "iv", "ct"):
            self.assertIn(k, o)
        p = K.decrypt(o, PW, self.tmp)
        self.assertEqual(p["kind"], "stock")
        self.assertEqual(p["cols"], K.COLS)
        self.assertEqual(p["bars"], self.bars[2:])
        self.assertEqual(p["dp"], 2)
        self.assertEqual(p["exchange"], "NASDAQ")
        self.assertEqual(p["pending"][0]["reason"], "待確認：y")
        self.assertEqual(p["rolls"], [])
        h = K.decrypt(self.read("t.hist.enc.json"), PW, self.tmp)
        self.assertEqual(h, {"code": "t", "cols": K.COLS, "bars": self.bars[:2]})
        with self.assertRaises(Exception):
            K.decrypt(o, "wrong-password-xx", self.tmp)

    def test_hist_not_rewritten_when_sha_same(self):
        self.write()
        hp = os.path.join(self.out, "t.hist.enc.json")
        before = open(hp).read()
        r = self.write(self.bars + [B("2025-01-06", 9)])
        self.assertEqual(r["hist"], "keep")
        self.assertEqual(open(hp).read(), before)

    def test_hist_rewritten_after_password_change(self):   # 換 FUTURES_PASSWORD：明文 sha 沒變也要用新密碼重新加密
        self.write()
        new_pw = "new-password-7890ab"
        r = K.write_files(self.out, self.meta, self.bars + [B("2025-01-06", 9)], new_pw, "2025-01-01", key_root=self.tmp)
        self.assertEqual(r["hist"], "rewrite")
        self.assertEqual(K.decrypt(self.read("t.hist.enc.json"), new_pw, self.tmp)["bars"], self.bars[:2])
        r = K.write_files(self.out, self.meta, self.bars + [B("2025-01-07", 9)], new_pw, "2025-01-01", key_root=self.tmp)
        self.assertEqual(r["hist"], "keep")   # 之後同一個密碼就不再重寫

    def test_hist_rewritten_when_file_broken(self):
        self.write()
        hp = os.path.join(self.out, "t.hist.enc.json")
        open(hp, "w").write('{"code":"t"')   # 半寫的檔
        r = self.write(self.bars + [B("2025-01-06", 9)])
        self.assertEqual(r["hist"], "rewrite")
        self.assertEqual(K.decrypt(self.read("t.hist.enc.json"), PW, self.tmp)["bars"], self.bars[:2])

    def test_hist_sha_stable_through_json(self):   # 解回來的 bars（浮點、None）重算 sha 要一樣，才不會每班重寫
        bars = [["2024-05-01", 0.1 + 0.2, 1234.5678, 1e-4, 3.0, None], ["2024-05-02", 12.3456, 13.0, 11.9999, 12.5, 0]]
        self.assertEqual(K.hist_sha("t", bars), K.hist_sha("t", json.loads(json.dumps(bars))))

    def test_hist_rewritten_after_split(self):
        self.write()
        hp = os.path.join(self.out, "t.hist.enc.json")
        before = open(hp).read()
        adj = [[b[0]] + [p / 2 for p in b[1:5]] + [b[5]] for b in self.bars]
        r = self.write(adj)
        self.assertEqual(r["hist"], "rewrite")
        self.assertNotEqual(open(hp).read(), before)

    def test_no_hist(self):
        r = self.write([B("2025-02-03"), B("2025-02-04")])
        self.assertEqual(r["hist"], "none")
        self.assertIsNone(self.read("t.enc.json")["hist"])
        self.assertFalse(os.path.exists(os.path.join(self.out, "t.hist.enc.json")))

    def test_krw_dp(self):
        self.meta["currency"] = "KRW"
        self.write()
        self.assertEqual(K.decrypt(self.read("t.enc.json"), PW, self.tmp)["dp"], 0)

    def test_new_year_moves_cut_and_rewrites_hist(self):
        self.write()
        o1 = self.read("t.enc.json")
        bars = self.bars + [B("2026-01-02", 9)]
        r = K.write_files(self.out, self.meta, bars, PW, K.cut_date("2027-01-04"), key_root=self.tmp)   # 2027 年：cut 變 2026-01-01
        self.assertEqual(r["hist"], "rewrite")
        o2 = self.read("t.enc.json")
        self.assertNotEqual(o1["hist"]["sha"], o2["hist"]["sha"])
        self.assertEqual((o2["hist"]["bars"], o2["hist"]["lastDate"]), (4, "2025-01-03"))
        self.assertEqual(K.decrypt(o2, PW, self.tmp)["bars"], [bars[-1]])
        self.assertEqual(K.decrypt(self.read("t.hist.enc.json"), PW, self.tmp)["bars"], self.bars)

    def test_no_plaintext_prices(self):
        self.write()
        raw = open(os.path.join(self.out, "t.enc.json")).read()
        self.assertNotIn("2025-01-02", raw)


class Process(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        make_key(self.tmp)
        self.out = os.path.join(self.tmp, "kbar")
        self.dd = os.path.join(self.tmp, "daily")
        os.makedirs(self.dd)
        self.c = {"code": "t", "name": "測試", "price": {"yahoo": "T", "from": "2024-01", "currency": "USD"}}
        self.now = dt.datetime(2026, 11, 18, 22, 30, tzinfo=dt.timezone.utc)   # 紐約 17:30，已收盤

    def fetcher(self, raw, info=None):
        return lambda sym, frm, nd: (raw, lambda: info or {}, "NASDAQ")

    def run_p(self, raw, info=None):
        return K.process(self.c, PW, self.out, daily_dir=self.dd, fetcher=self.fetcher(raw, info), now_utc=self.now, key_root=self.tmp)

    def set_daily(self, rows):
        json.dump({"rows": rows}, open(os.path.join(self.dd, "t.json"), "w"))

    def test_end_to_end_and_skip(self):
        d1, d2 = dt.date(2026, 11, 17), dt.date(2026, 11, 18)
        raw = [(dt.date(2024, 5, 1), 5, 6, 4, 5.5, 10), (d1, 10, 11, 9, 10.5, 100), (d2, 10, 11, 9, 10.8, 100)]
        self.set_daily([["2026-11-17", 10.5], ["2026-11-18", 10.8]])
        self.assertEqual(self.run_p(raw), "written")
        o = json.load(open(os.path.join(self.out, "t.enc.json")))
        self.assertEqual(o["lastDate"], "2026-11-18")
        p = K.decrypt(o, PW, self.tmp)
        self.assertIsNone(p["bars"][-1][5])          # 最新量與前一根相同 → null
        self.assertEqual(o["hist"]["bars"], 1)
        self.assertEqual(self.run_p(raw), "up-to-date")

    def test_provisional_rewritten_until_official(self):
        d1, d2 = dt.date(2026, 11, 17), dt.date(2026, 11, 18)
        from zoneinfo import ZoneInfo
        info = info_at(dt.datetime(2026, 11, 18, 16, 0, tzinfo=ZoneInfo("America/New_York")))
        raw = [(d1, 10, 11, 9, 10.5, 100), (d2, NAN, NAN, NAN, NAN, NAN)]
        self.set_daily([["2026-11-17", 10.5], ["2026-11-18", 11.0]])
        self.assertEqual(self.run_p(raw, info), "written")
        o = json.load(open(os.path.join(self.out, "t.enc.json")))
        self.assertTrue(o["provisional"])
        self.assertTrue(K.decrypt(o, PW, self.tmp)["provisional"])
        raw2 = [(d1, 10, 11, 9, 10.5, 100), (d2, 10, 12, 9, 11.0, 777)]
        self.assertEqual(self.run_p(raw2), "written")      # lastDate 沒變也重抓覆寫
        self.assertFalse(json.load(open(os.path.join(self.out, "t.enc.json")))["provisional"])
        self.assertEqual(self.run_p(raw2), "up-to-date")

    def test_etf_backfill_history(self):
        """ETF 第一次只抓到一個月 → 之後補到完整歷史：lastDate 一樣也要寫（不能判成「沒有新的 K 棒」）。"""
        d1, d2 = dt.date(2026, 11, 17), dt.date(2026, 11, 18)
        self.c = dict(self.c, code="t", dailyDir=self.dd)
        self.set_daily([["2024-01-02", 5.5], ["2026-11-17", 10.5], ["2026-11-18", 10.8]])   # 每日收盤檔是上市以來
        short = [(d1, 10, 11, 9, 10.5, 100), (d2, 10, 11, 9, 10.8, 100)]
        self.assertEqual(self.run_p(short), "written")
        full = [(dt.date(2024, 1, 2), 5, 6, 4, 5.5, 10)] + short
        self.assertEqual(self.run_p(full), "written")
        o = json.load(open(os.path.join(self.out, "t.enc.json")))
        self.assertEqual(o["firstDate"], "2024-01-02")
        self.assertEqual(self.run_p(full), "up-to-date")

    def test_mismatch_goes_pending(self):
        d1, d2 = dt.date(2026, 11, 17), dt.date(2026, 11, 18)
        raw = [(d1, 10, 11, 9, 10.5, 100), (d2, 10, 12, 9, 11.0, 777)]
        self.set_daily([["2026-11-17", 10.5], ["2026-11-18", 10.0]])
        self.run_p(raw)
        o = json.load(open(os.path.join(self.out, "t.enc.json")))
        self.assertEqual((o["lastDate"], o["pendingCount"]), ("2026-11-17", 1))

    def test_stale_list(self):
        self.set_daily([["2026-11-17", 10.5], ["2026-11-18", 10.8]])
        self.assertEqual(K.stale_list([self.c], self.out, self.dd), [("t", "（無檔）", "2026-11-18")])
        os.makedirs(self.out)
        json.dump({"lastDate": "2026-11-18"}, open(os.path.join(self.out, "t.enc.json"), "w"))
        self.assertEqual(K.stale_list([self.c], self.out, self.dd), [])

    def test_log_has_no_prices(self):
        import contextlib, io
        d1, d2 = dt.date(2026, 11, 17), dt.date(2026, 11, 18)
        raw = [(dt.date(2024, 5, 1), 5.4321, 6.4321, 4.4321, 5.9876, 10), (d1, 123.4567, 124.5678, 122.3456, 123.9876, 100),
               (d2, 223.4567, 224.5678, 222.3456, 223.9876, 200)]
        self.set_daily([["2026-11-17", 123.9876], ["2026-11-18", 300.0]])   # 18 日對不上 → pending
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.run_p(raw)
        out = buf.getvalue()
        for p in ("5.4321", "5.9876", "123.4567", "123.9876", "223.9876", "300.0", "223.98", "123.99"):
            self.assertNotIn(p, out)
        self.assertIn("已寫入", out)

    def test_one_company_failure_does_not_stop_others(self):
        from unittest import mock
        seen = []

        def fake(c, pw, out, **kw):
            seen.append(c["code"])
            if c["code"] == "a":
                raise RuntimeError("boom")
            return "written"
        cos = [{"code": "a"}, {"code": "b"}]
        with mock.patch.dict(os.environ, {"FUTURES_PASSWORD": PW}), mock.patch.object(K, "companies", return_value=cos), \
                mock.patch.object(K, "outdir_default", return_value=self.out), mock.patch.object(K, "process", side_effect=fake):
            self.assertEqual(K.main([]), 0)
        self.assertEqual(seen, ["a", "b"])

    def test_short_password_exit1_and_writes_nothing(self):
        from unittest import mock
        with mock.patch.dict(os.environ, {"FUTURES_PASSWORD": "short"}), mock.patch.object(K, "outdir_default", return_value=self.out):
            self.assertEqual(K.main([]), 1)
        self.assertFalse(os.path.exists(self.out))

    def test_no_password_exit1(self):
        old = os.environ.pop("FUTURES_PASSWORD", None)
        try:
            self.assertEqual(K.main(["--company", "nvda"]), 1)
        finally:
            if old is not None:
                os.environ["FUTURES_PASSWORD"] = old


if __name__ == "__main__":
    unittest.main()
