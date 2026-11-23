"""tools/vix_update.py：VIX 每日收盤（只有 GitHub Actions 會真的抓；這裡用假資料測解析與計算）。"""
import datetime as dt, json, os, sys, tempfile, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import vix_update as V

UTC = dt.timezone.utc


def series(n=2600, start=dt.date(2016, 1, 4), base=15.0, last=None):
    """n 個交易日（跳過週末）的假收盤，數值在 12～24 之間循環；可以指定最後一筆。"""
    out, d, i = [], start, 0
    while len(out) < n:
        if d.weekday() < 5:
            out.append((d.isoformat(), base + (i % 13) - 3)); i += 1
        d += dt.timedelta(days=1)
    if last is not None:
        out[-1] = (out[-1][0], last)
    return out


def cboe_csv(points):
    return "DATE,OPEN,HIGH,LOW,CLOSE\n" + "\n".join(f"{d[5:7]}/{d[8:10]}/{d[:4]},{c:.6f},{c + 1:.6f},{c - 1:.6f},{c:.6f}" for d, c in points) + "\n"


class ParseTest(unittest.TestCase):
    def test_parse_cboe(self):
        pts = series(300)
        got = V.parse_cboe(cboe_csv(pts))
        self.assertEqual(got[0], pts[0]); self.assertEqual(got[-1], pts[-1]); self.assertEqual(len(got), 300)

    def test_parse_cboe_sorts_and_skips_blank_lines(self):
        pts = series(300)
        text = cboe_csv(list(reversed(pts))) + "\n,,,,\n"
        self.assertEqual(V.parse_cboe(text), pts)

    def test_header_changed_is_rejected(self):
        with self.assertRaises(ValueError):
            V.parse_cboe("Day,Last\n01/02/2020,13.5\n")

    def test_out_of_range_value_rejects_whole_file(self):
        pts = series(300); pts[100] = (pts[100][0], 0.0)
        with self.assertRaises(ValueError):
            V.parse_cboe(cboe_csv(pts))

    def test_too_few_rows_rejected(self):
        with self.assertRaises(ValueError):
            V.check(series(20))

    def test_duplicate_dates_rejected(self):
        pts = series(300)
        with self.assertRaises(ValueError):
            V.check(sorted(pts + [pts[5]]))


class BuildTest(unittest.TestCase):
    def test_build_fields(self):
        pts = series(2600, last=40.0)
        d = V.build(pts, "來源", "https://x", dt.datetime(2026, 1, 1, tzinfo=UTC))
        self.assertEqual(d["last"], {"d": pts[-1][0], "c": 40.0})
        self.assertEqual(d["prev"]["d"], pts[-2][0])
        self.assertEqual(d["chg"], round(40.0 - pts[-2][1], 2))
        self.assertEqual(d["pct10"], 100)                    # 十年裡最高
        self.assertEqual(d["zone"], "tense")
        self.assertEqual(d["hi52"], {"d": pts[-1][0], "c": 40.0})
        self.assertEqual(len(d["points"]), V.KEEP)
        self.assertEqual(d["points"][-1], [pts[-1][0], 40.0])
        self.assertEqual(d["source"], "來源")
        self.assertEqual(d["updated"], "2026-01-01 00:00 UTC")

    def test_percentile_uses_only_last_ten_years(self):
        old = [(f"2000-01-{i + 3:02d}", 80.0) for i in range(5)]        # 十年以前的高值不能算進來
        pts = old + series(2600, last=30.0)
        d = V.build(pts, "s", "u")
        self.assertEqual(d["pct10"], 100)
        self.assertGreater(d["since10"], "2015")

    def test_zones(self):
        self.assertEqual(V.zone_of(12), "calm")
        self.assertEqual(V.zone_of(19.99), "calm")
        self.assertEqual(V.zone_of(20), "mid")
        self.assertEqual(V.zone_of(29.99), "mid")
        self.assertEqual(V.zone_of(30), "tense")

    def test_leap_day(self):
        self.assertEqual(V.minus_years("2024-02-29", 1), "2023-02-28")


class UpdateTest(unittest.TestCase):
    def test_official_wins_a_tie_and_cross_check_ok(self):
        pts = series(300)
        doc, notes = V.update([("官方", "u1", lambda: pts), ("備援", "u2", lambda: list(pts))])
        self.assertEqual(doc["source"], "官方")
        self.assertTrue(doc["xcheck"]["ok"])
        self.assertEqual(len(notes), 3)

    def test_newer_source_is_used(self):
        pts = series(300)
        doc, _ = V.update([("官方", "u1", lambda: pts[:-1]), ("備援", "u2", lambda: pts)])
        self.assertEqual(doc["source"], "備援")
        self.assertEqual(doc["last"]["d"], pts[-1][0])
        self.assertEqual(doc["xcheck"]["d"], pts[-2][0])      # 核對的是兩邊都有的最近一天
        self.assertTrue(doc["xcheck"]["ok"])

    def test_cross_check_mismatch_is_flagged(self):
        a = series(300); b = list(a); b[-1] = (b[-1][0], a[-1][1] * 1.05)
        doc, _ = V.update([("官方", "u1", lambda: a), ("備援", "u2", lambda: b)])
        self.assertFalse(doc["xcheck"]["ok"])
        self.assertTrue(doc["xcheck"]["note"].startswith("待確認："))

    def test_first_source_fails_falls_back(self):
        def boom():
            raise OSError("連不上")
        pts = series(300)
        doc, notes = V.update([("官方", "u1", boom), ("備援", "u2", lambda: pts)])
        self.assertEqual(doc["source"], "備援")
        self.assertNotIn("xcheck", doc)
        self.assertIn("失敗", notes[0])

    def test_update_ex_reports_official_and_points(self):
        pts = series(300)
        _, _, got, official = V.update_ex([("官方", "u1", lambda: pts), ("備援", "u2", lambda: pts[:-1])])
        self.assertTrue(official); self.assertEqual(got, pts)
        _, _, got, official = V.update_ex([("官方", "u1", lambda: pts[:-1]), ("備援", "u2", lambda: pts)])
        self.assertFalse(official)

    def test_all_fail_returns_none(self):
        def boom():
            raise ValueError("壞了")
        doc, notes = V.update([("官方", "u1", boom), ("備援", "u2", boom)])
        self.assertIsNone(doc)
        self.assertEqual(len(notes), 2)


class SessionTest(unittest.TestCase):
    def test_intraday_row_is_dropped_while_us_market_open(self):
        pts = [("2026-11-19", 28.4), ("2026-11-20", 31.0)]
        mid = dt.datetime(2026, 11, 20, 18, 0, tzinfo=UTC)       # 美東 13:00，盤中
        after = dt.datetime(2026, 11, 20, 22, 0, tzinfo=UTC)     # 美東 17:00，已收盤
        self.assertEqual(V.drop_unfinished(pts, mid), pts[:1])
        self.assertEqual(V.drop_unfinished(pts, after), pts)

    def test_weekend_keeps_friday(self):
        pts = [("2026-11-19", 28.4), ("2026-11-20", 31.0)]
        self.assertEqual(V.drop_unfinished(pts, dt.datetime(2026, 11, 21, 15, 0, tzinfo=UTC)), pts)


class HistoryTest(unittest.TestCase):
    def test_ma20_values_and_nulls(self):
        pts = [(f"2020-01-{i + 1:02d}", float(i + 10)) for i in range(25)]     # 10,11,...,34（日期只當標籤）
        ma = V.moving_avg(pts)
        self.assertEqual([r[2] for r in ma[:19]], [None] * 19)
        self.assertEqual(ma[19][2], 19.5)                  # 10..29 的平均
        self.assertEqual(ma[24][2], 24.5)                  # 15..34 的平均
        self.assertEqual(ma[3][:2], ["2020-01-04", 13.0])
        self.assertEqual(V.moving_avg([("a", 1.0 / 3)] * 20)[19][2:], [0.33])    # 四捨五入到小數 2 位

    def test_merge_keeps_old_and_adds_new_dates_only(self):
        old = V.moving_avg(series(300))
        newer = series(305)                                # 多 5 天
        newer = [(d, c + 1) for d, c in newer]             # 重疊日期的值不同
        m = V.merge_history(old, newer, official=False)
        self.assertEqual(len(m), 305)
        self.assertEqual(m[10], (old[10][0], old[10][1]))  # 舊值保留
        self.assertEqual(m[-1], newer[-1])                 # 新日期補上

    def test_official_may_overwrite(self):
        old = V.moving_avg(series(300))
        newer = [(d, c + 1) for d, c in series(300)]
        m = V.merge_history(old, newer, official=True)
        self.assertEqual(m[10][1], old[10][1] + 1)

    def test_merge_never_shrinks_when_source_is_shorter(self):
        long = series(3000)
        old = V.moving_avg(long)
        m = V.merge_history(old, long[-400:])              # Yahoo 只有近期
        self.assertEqual(len(m), 3000)
        self.assertEqual(m[0], long[0])

    def test_merge_rejects_bad_values(self):
        old = V.moving_avg(series(300))
        with self.assertRaises(ValueError):
            V.merge_history(old, [("2099-01-01", 999.0)])

    def test_build_history_fields(self):
        pts = series(300)
        h = V.build_history(pts, "來源", "https://x", dt.datetime(2026, 1, 1, tzinfo=UTC))
        self.assertEqual((h["from"], h["to"], h["n"], h["ma"]), (pts[0][0], pts[-1][0], 300, 20))
        self.assertEqual(len(h["points"]), 300)
        self.assertIsNone(h["points"][18][2]); self.assertIsNotNone(h["points"][19][2])

    def test_write_history_flow(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "vix-history.json")
            full = series(3000)
            t1 = dt.datetime(2026, 1, 1, tzinfo=UTC)
            self.assertTrue(V.write_history(full, True, "Cboe", "u", path, t1))
            first = open(path, encoding="utf-8").read()
            self.assertEqual(first.count("\n"), 1)
            # 沒有變化（時間不同）→ 不重寫
            self.assertFalse(V.write_history(full, True, "Cboe", "u", path, dt.datetime(2026, 1, 2, tzinfo=UTC)))
            self.assertEqual(open(path, encoding="utf-8").read(), first)
            # 只有 Yahoo 近 400 天、多一天 → 補上、不縮水
            nxt = series(3001)
            self.assertTrue(V.write_history(nxt[-400:], False, "Yahoo", "u2", path, t1))
            h = json.load(open(path, encoding="utf-8"))
            self.assertEqual(h["n"], 3001); self.assertEqual(h["from"], full[0][0]); self.assertEqual(h["to"], nxt[-1][0])
            # 抓到的資料壞掉 → 保留舊檔
            before = open(path, encoding="utf-8").read()
            self.assertFalse(V.write_history([("2099-01-01", 0.0)], False, "Yahoo", "u2", path, t1))
            self.assertEqual(open(path, encoding="utf-8").read(), before)


class StaleTest(unittest.TestCase):
    def test_stale(self):
        today = dt.date(2026, 11, 30)
        self.assertTrue(V.is_stale(None, today))
        self.assertTrue(V.is_stale({"last": {"d": "2026-11-20"}}, today))
        self.assertFalse(V.is_stale({"last": {"d": "2026-11-25"}}, today))


if __name__ == "__main__":
    unittest.main()
