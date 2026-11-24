"""到價提醒＋每日行情報告（tools/alerts.py）的測試。全部用臨時資料夾的合成資料，網路（Yahoo、ntfy、Gmail、Telegram）全部用假的，不碰 repo 的 data/。"""
import base64, datetime as dt, io, json, os, sys, tempfile, unittest
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import alerts as A          # noqa: E402
import kbar_update as K     # noqa: E402

PW = "alerts-test-pass"
CASES = json.load(open(os.path.join(HERE, "alerts_cases.json"), encoding="utf8"))
NOW = dt.datetime(2026, 11, 24, 0, 0, tzinfo=dt.timezone.utc)      # 台北 2026-11-24 08:00
SECRET_WORDS = ("AAA", "BBB", "ETF1", "小那指")                       # log 裡不可出現的代號


def wj(path, obj):
    with open(path, "w", encoding="utf8") as f:
        json.dump(obj, f)


def weekdays(a, b):
    d = a
    while d <= b:
        if d.weekday() < 5:
            yield d.isoformat()
        d += dt.timedelta(days=1)


def mk_bars(days, base, step=0.5):
    out, px = [], base
    for d in days:
        o, c = px, px + step
        out.append([d, o, max(o, c) + 1, min(o, c) - 1, c, 1000])
        px = c
    return out


def build_root(tmp, last="2026-11-23", with_hist=True, spare=()):
    """合成 root：2 檔個股（AAA 科技、BBB 能源）＋1 檔 ETF＋3 檔期貨。"""
    os.makedirs(os.path.join(tmp, "data", "futures"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "data", "kbar"), exist_ok=True)
    os.makedirs(os.path.join(tmp, "data", "etf"), exist_ok=True)
    wj(os.path.join(tmp, "data", "futures", "key.json"), {"salt": base64.b64encode(b"alerts-test-salt").decode(), "iter": 1000})
    wj(os.path.join(tmp, "companies.json"), {"companies": [
        {"code": "aaa", "name": "甲公司", "ticker": "AAA", "sector": "科技", "enabled": True, "price": {"yahoo": "AAA", "currency": "USD"}},
        {"code": "bbb", "name": "乙公司", "ticker": "BBB", "sector": "能源", "enabled": True, "price": {"yahoo": "BBB", "currency": "USD"}},
        {"code": "off", "name": "停用", "ticker": "OFF", "sector": "科技", "enabled": False, "price": {"yahoo": "OFF"}}]})
    wj(os.path.join(tmp, "data", "etf", "config.json"), {"etfs": [{"code": "etf1", "ticker": "ETF1", "name": "Test ETF", "zh": "測試ETF", "yahoo": "ETF1", "currency": "USD"}]})
    end = dt.date.fromisoformat(last)
    cut = K.cut_date(end + dt.timedelta(days=1))
    for code, base in (("aaa", 100), ("bbb", 50), ("etf1", 30)):
        if code in spare:
            continue
        bars = mk_bars(list(weekdays(dt.date(2024, 1, 2), end)), base)
        K.write_files(os.path.join(tmp, "data", "kbar"), {"code": code, "name": code, "yahoo": code.upper(), "currency": "USD"}, bars, PW, cut, key_root=tmp)
    for code, base in (("ym", 44000), ("nq", 21000), ("tx", 23000)):
        pay = {"code": code, "bars": mk_bars(list(weekdays(dt.date(2025, 6, 2), end)), base, 10)}
        outer = {"code": code, **K.encrypt(pay, PW, tmp)}
        wj(os.path.join(tmp, "data", "futures", code + ".enc.json"), outer)
    return A.Paths(tmp)


def rule(**kw):
    r = {"id": "r1", "code": "aaa", "kind": "stock", "name": "甲公司", "p": 9999.0, "dir": "up", "dirAuto": True, "mode": "price", "n": "",
         "on": True, "since": "2026-11-20", "created": "2026-11-20T00:00:00Z", "updated": "2026-11-20T00:00:00Z"}
    r.update(kw)
    return r


def put_rules(paths, rules):
    key = A.derive_key(PW, paths)
    A.write_json(paths.rules, A.enc({"v": 1, "rules": rules, "updated": "2026-11-23T00:00:00Z"}, key))
    return key


def no_net(sym, start):
    return []


class Fake:
    """記錄所有假發送；fail 指定哪些管道要失敗。"""

    def __init__(self, fail=()):
        self.fail, self.calls = set(fail), []

    def __enter__(self):
        self.o = (A.http_post, A.smtp_send)

        def http(url, data, headers=None, timeout=30):
            name = "ntfy" if "ntfy.sh" in url else "Telegram"
            self.calls.append((name, url, data))
            if name in self.fail:
                raise A.SendError("HTTP 500")
            if "getUpdates" in url:
                return 200, json.dumps({"result": [{"message": {"chat": {"id": 4242, "type": "private"}}}]})
            return 200, "{}"

        def smtp(user, pw, msg):
            self.calls.append(("Gmail", user, msg))
            if "Gmail" in self.fail:
                raise A.SendError("SMTPAuthenticationError")
        A.http_post, A.smtp_send = http, smtp
        return self

    def __exit__(self, *a):
        A.http_post, A.smtp_send = self.o

    def names(self):
        return [c[0] for c in self.calls if "getUpdates" not in str(c[1])]


ENV_ALL = {"FUTURES_PASSWORD": PW, "NTFY_TOPIC": "secret-topic-xyz", "GMAIL_USER": "me@example.com", "GMAIL_APP_PASSWORD": "app-pass", "TELEGRAM_BOT_TOKEN": "123:TOKEN"}


def run(paths, env, now=NOW, fetch=no_net, test=False):
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = A.run(paths, env, now, fetch, test)
    return rc, buf.getvalue()


def read_state(paths):
    return A.dec(A.jload(paths.state), A.derive_key(PW, paths))


class HitCases(unittest.TestCase):
    def test_shared_cases(self):
        for c in CASES["hit"]:
            self.assertEqual(A.hit_for(c["rule"], c["bars"]), c["hit"], c["name"])

    def test_valid_cases(self):
        for c in CASES["valid"]:
            self.assertEqual(A.hit_valid(c["rule"], c["hit"]), c["valid"], c["name"])

    def test_pct_price(self):
        for c in CASES["pct"]:
            self.assertAlmostEqual(A.pct_price(c["base"], c["pct"]), c["p"], places=4)

    def test_evaluate_keeps_hit_until_changed(self):
        r = rule(p=110, since="2026-01-02")
        bars = {"aaa": [["2026-01-05", 100, 111, 99, 100, 1], ["2026-01-06", 100, 101, 99, 100, 1]]}
        h = A.evaluate([r], bars, {})
        self.assertEqual(h["r1"]["t"], "2026-01-05")
        h2 = A.evaluate([r], {"aaa": []}, h)                       # K 棒不見了也維持到價（直到關閉或改價）
        self.assertEqual(h2, h)
        self.assertEqual(A.evaluate([dict(r, on=False)], bars, h), {})   # 關閉：清掉
        self.assertEqual(A.evaluate([dict(r, p=120)], {"aaa": []}, h), {})   # 改價：作廢
        self.assertEqual(A.evaluate([dict(r, since="2026-01-05")], {"aaa": []}, h), {})   # 重新開啟：作廢


class Crypto(unittest.TestCase):
    def test_roundtrip_and_wrong_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            key = A.derive_key(PW, paths)
            obj = {"v": 1, "rules": [{"id": "x", "n": "中文備註"}]}
            self.assertEqual(A.dec(A.enc(obj, key), key), obj)
            with self.assertRaises(Exception):
                A.dec(A.enc(obj, key), A.derive_key("wrong", paths))

    def test_compatible_with_kbar_format(self):
        """前端 FUT.decrypt 與 K 棒檔用同一個格式：kbar_update.decrypt 要能解 alerts.enc 的輸出。"""
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            key = A.derive_key(PW, paths)
            self.assertEqual(K.decrypt(A.enc({"a": 1}, key), PW, tmp), {"a": 1})


class Topup(unittest.TestCase):
    def test_only_closed_days(self):
        it = {"code": "aaa", "kind": "stock", "yahoo": "AAA"}
        bars = [["2026-11-20", 1, 2, 1, 1, 1]]
        raw = [(dt.date(2026, 11, 20), 1, 2, 1, 1, 1), (dt.date(2026, 11, 23), 5, 7, 4, 6, 10), (dt.date(2026, 11, 24), 6, 9, 5, 8, 10)]
        # 台北 11/24 08:00 = 美東 11/23 19:00：11/23 已收盤、11/24 還沒開盤
        add = A.topup(it, bars, NOW, lambda s, d: raw)
        self.assertEqual([b[0] for b in add], ["2026-11-23"])
        # 美東 11/23 15:00（收盤前）：11/23 還沒收盤 → 不收
        early = dt.datetime(2026, 11, 23, 20, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(A.topup(it, bars, early, lambda s, d: raw), [])
        # 收盤 16:00 後 20 分鐘才算收完
        self.assertEqual(A.topup(it, bars, dt.datetime(2026, 11, 23, 21, 10, tzinfo=dt.timezone.utc), lambda s, d: raw), [])
        self.assertEqual(len(A.topup(it, bars, dt.datetime(2026, 11, 23, 21, 30, tzinfo=dt.timezone.utc), lambda s, d: raw)), 1)

    def test_taiwan_uses_local_close(self):
        it = {"code": "t", "kind": "stock", "yahoo": "2330.TW"}
        raw = [(dt.date(2026, 11, 24), 5, 7, 4, 6, 10)]
        at = lambda h, m: dt.datetime(2026, 11, 24, h, m, tzinfo=dt.timezone.utc)   # 台北 = UTC+8
        self.assertEqual(A.topup(it, [], at(5, 0), lambda s, d: raw), [])            # 台北 13:00 還沒收
        self.assertEqual(len(A.topup(it, [], at(6, 0), lambda s, d: raw)), 1)         # 台北 14:00 已收（13:30＋20 分）

    def test_futures_ct_rule(self):
        it = {"code": "ym", "kind": "fut", "yahoo": "YM=F"}
        raw = [(dt.date(2026, 11, 23), 1, 2, 1, 1, 1)]
        # 11/23 CT 16:15 = UTC 22:15（11 月是 CST，UTC-6）
        self.assertEqual(A.topup(it, [], dt.datetime(2026, 11, 23, 22, 0, tzinfo=dt.timezone.utc), lambda s, d: raw), [])
        self.assertEqual(len(A.topup(it, [], dt.datetime(2026, 11, 23, 22, 30, tzinfo=dt.timezone.utc), lambda s, d: raw)), 1)

    def test_nan_rows_skipped_and_tx_not_fetched(self):
        it = {"code": "aaa", "kind": "stock", "yahoo": "AAA"}
        nan = float("nan")
        self.assertEqual(A.topup(it, [], NOW, lambda s, d: [(dt.date(2026, 11, 23), nan, nan, nan, nan, None)], lambda s: {}), [])
        self.assertEqual(A.topup({"code": "tx", "kind": "fut", "yahoo": None}, [], NOW, lambda s, d: 1 / 0), [])

    def test_nan_last_day_filled_from_quote(self):
        it = {"code": "aaa", "kind": "stock", "yahoo": "AAA"}
        nan = float("nan")
        raw = [(dt.date(2026, 11, 23), 5, 7, 4, 6, 10), (dt.date(2026, 11, 24), nan, nan, nan, nan, None)]
        # 美東 11/23 16:30 = UTC 21:30
        ts = dt.datetime(2026, 11, 23, 21, 30, tzinfo=dt.timezone.utc).timestamp()
        q = {"regularMarketTime": ts, "regularMarketPrice": 6.5, "regularMarketDayHigh": 7.5, "regularMarketDayLow": 4.5, "regularMarketOpen": 5.5}
        fetched = []
        add = A.topup(it, [], NOW, lambda s, d: [(dt.date(2026, 11, 23), nan, 7.0, 4.0, nan, 10)], lambda s: fetched.append(s) or q)
        self.assertEqual(add, [["2026-11-23", 5.5, 7.0, 4.0, 6.5, 10]])      # 有值的欄位保留，只補 NaN
        self.assertEqual(fetched, ["AAA"])
        # 完整的列不去查報價
        fetched.clear()
        A.topup(it, [], NOW, lambda s, d: raw[:1], lambda s: fetched.append(s) or q)
        self.assertEqual(fetched, [])

    def test_quote_from_other_date_or_before_close_rejected(self):
        it = {"code": "aaa", "kind": "stock", "yahoo": "AAA"}
        nan = float("nan")
        row = lambda s, d: [(dt.date(2026, 11, 23), nan, nan, nan, nan, None)]   # noqa: E731
        mk = lambda y, m, d, h: {"regularMarketTime": dt.datetime(y, m, d, h, 0, tzinfo=dt.timezone.utc).timestamp(), "regularMarketPrice": 6, "regularMarketDayHigh": 7, "regularMarketDayLow": 4, "regularMarketOpen": 5}  # noqa: E731
        self.assertEqual(A.topup(it, [], NOW, row, lambda s: mk(2026, 11, 20, 21)), [])   # 報價是別天的
        self.assertEqual(A.topup(it, [], NOW, row, lambda s: mk(2026, 11, 23, 19)), [])   # 美東 14:00 盤中價
        self.assertEqual(len(A.topup(it, [], NOW, row, lambda s: mk(2026, 11, 23, 21))), 1)

    def test_still_nan_dropped_and_quote_errors_swallowed(self):
        it = {"code": "aaa", "kind": "stock", "yahoo": "AAA"}
        nan = float("nan")
        row = lambda s, d: [(dt.date(2026, 11, 23), nan, nan, nan, nan, None)]   # noqa: E731
        ts = dt.datetime(2026, 11, 23, 21, 30, tzinfo=dt.timezone.utc).timestamp()
        self.assertEqual(A.topup(it, [], NOW, row, lambda s: {"regularMarketTime": ts, "regularMarketPrice": nan}), [])
        self.assertEqual(A.topup(it, [], NOW, row, lambda s: 1 / 0), [])

    def test_topup_failure_does_not_fail_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            put_rules(paths, [rule()])
            def boom(s, d):
                raise RuntimeError("network")
            rc, out = run(paths, {"FUTURES_PASSWORD": PW}, fetch=boom)
            self.assertEqual(rc, 0)
            self.assertIn("補價失敗", out)

    def test_topup_bars_make_hit(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            put_rules(paths, [rule(p=500.0)])
            rc, _ = run(paths, {"FUTURES_PASSWORD": PW}, fetch=lambda s, d: [(dt.date(2026, 11, 24), 400, 520, 399, 450, 1)] if s == "AAA" else [])
            # 台北 11/24 08:00 時美東 11/24 還沒開盤 → 這根不收
            self.assertEqual(read_state(paths)["hits"], {})
            later = dt.datetime(2026, 11, 25, 0, 0, tzinfo=dt.timezone.utc)
            run(paths, {"FUTURES_PASSWORD": PW}, now=later, fetch=lambda s, d: [(dt.date(2026, 11, 24), 400, 520, 399, 450, 1)] if s == "AAA" else [])
            self.assertEqual(read_state(paths)["hits"]["r1"]["t"], "2026-11-24")


class RunFlow(unittest.TestCase):
    def test_no_password_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, _ = run(build_root(tmp), {})
            self.assertEqual(rc, 1)

    def test_no_rules_files_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            self.assertFalse(os.path.exists(paths.rules))
            rc, out = run(paths, {"FUTURES_PASSWORD": PW})
            self.assertEqual(rc, 0)
            self.assertIn("提醒規則 0 條", out)

    def test_hit_from_kbar_and_state_last(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            put_rules(paths, [rule(p=1.0, dir="down", since="2026-11-01"), rule(id="r2", p=9999.0)])
            rc, out = run(paths, {"FUTURES_PASSWORD": PW})
            st = read_state(paths)
            self.assertEqual(rc, 0)
            self.assertEqual(list(st["hits"]), [])        # 價格遠離：沒到價
            put_rules(paths, [rule(p=105.0, dir="up", since="2026-10-01")])
            run(paths, {"FUTURES_PASSWORD": PW})
            st = read_state(paths)
            self.assertIn("r1", st["hits"])
            self.assertEqual(st["hits"]["r1"]["side"], "h")
            self.assertEqual(st["last"]["aaa"]["t"], "2026-11-23")

    def test_send_once_per_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            put_rules(paths, [rule(p=105.0, since="2026-10-01")])
            with Fake() as f:
                self.assertEqual(run(paths, ENV_ALL)[0], 0)
                self.assertEqual(sorted(f.names()), ["Gmail", "Telegram", "ntfy"])
                n = len(f.calls)
                rc, out = run(paths, ENV_ALL, now=NOW + dt.timedelta(hours=2))   # 同一個台北日
                self.assertEqual(len(f.calls), n)
                self.assertIn("今天已經發過", out)
                run(paths, ENV_ALL, now=NOW + dt.timedelta(days=1))              # 隔天又發
                self.assertGreater(len(f.calls), n)
            self.assertEqual(read_state(paths)["lastSent"], "2026-11-25")

    def test_exception_after_send_still_marks_sent_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            put_rules(paths, [rule(p=105.0, since="2026-10-01")])
            with Fake() as f:
                http = A.http_post

                def bad(url, data, headers=None, timeout=30):
                    if "getUpdates" in url:
                        f.calls.append(("Telegram", url, data))
                        return 200, "<<not json>>"          # 非 SendError 的意外
                    return http(url, data, headers, timeout)
                A.http_post = bad
                try:
                    rc, out = run(paths, ENV_ALL)
                    self.assertEqual(rc, 0)
                    self.assertEqual(read_state(paths)["lastSent"], "2026-11-24")
                    self.assertEqual(sorted(f.names()), ["Gmail", "ntfy"])
                    n = len(f.calls)
                    rc, out = run(paths, ENV_ALL, now=NOW + dt.timedelta(hours=1))
                    self.assertEqual((rc, len(f.calls)), (0, n))     # 同一天不重發
                finally:
                    A.http_post = http
            self.assertNotIn("not json", out)

    def test_gmail_daily_even_without_hits_others_only_on_hits(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            put_rules(paths, [rule(p=9999.0)])
            with Fake() as f:
                self.assertEqual(run(paths, ENV_ALL)[0], 0)
                self.assertEqual(f.names(), ["Gmail"])
                msg = f.calls[0][2]
                self.assertIn("每日行情 11/24（提醒 1 條監控中）", msg["Subject"])
                self.assertEqual(msg["To"], "me@example.com")

    def test_no_channels_configured_no_lastsent(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            put_rules(paths, [rule(p=105.0, since="2026-10-01")])
            rc, out = run(paths, {"FUTURES_PASSWORD": PW})
            self.assertEqual(rc, 0)
            self.assertNotIn("lastSent", read_state(paths))

    def test_all_channels_fail_is_red_and_retryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            put_rules(paths, [rule(p=105.0, since="2026-10-01")])
            with Fake(fail=("ntfy", "Gmail", "Telegram")):
                rc, out = run(paths, ENV_ALL)
            self.assertEqual(rc, 1)
            st = read_state(paths)
            self.assertNotIn("lastSent", st)               # 沒記已發：備援班與重試會再試
            self.assertIn("r1", st["hits"])                # 但到價結果有存
            with Fake():
                self.assertEqual(run(paths, ENV_ALL)[0], 0)

    def test_partial_failure_still_records_lastsent(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            put_rules(paths, [rule(p=105.0, since="2026-10-01")])
            with Fake(fail=("ntfy",)):
                rc, out = run(paths, ENV_ALL)
            self.assertEqual(rc, 0)
            self.assertIn("ntfy：失敗", out)
            st = read_state(paths)
            self.assertEqual(st["lastSent"], "2026-11-24")
            self.assertEqual(sorted(st["sent"][-1]["ch"]), ["Gmail", "Telegram"])

    def test_log_has_no_tickers_prices_or_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            put_rules(paths, [rule(p=105.0, since="2026-10-01", n="秘密備註")])
            with Fake(fail=("Telegram",)):
                rc, out = run(paths, ENV_ALL)
            for w in SECRET_WORDS + ("secret-topic-xyz", "app-pass", "123:TOKEN", "me@example.com", "秘密備註", "甲公司", "105", PW):
                self.assertNotIn(w, out)

    def test_ntfy_has_no_prices(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            put_rules(paths, [rule(p=105.5, since="2026-10-01", n="備註"), rule(id="r2", code="nq", kind="fut", name="小那指", dir="down", p=30000, since="2026-10-01")])
            with Fake() as f:
                run(paths, ENV_ALL)
            body = json.loads([c for c in f.calls if c[0] == "ntfy"][0][2])
            self.assertEqual(body["topic"], "secret-topic-xyz")
            self.assertEqual(body["click"], A.ALERTS_URL)
            self.assertIn("甲公司 漲破", body["message"])
            self.assertIn("小那指 跌破", body["message"])
            for w in ("105", "30,000", "30000", "備註"):
                self.assertNotIn(w, body["message"] + body["title"])

    def test_telegram_chat_id_autodiscovery_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            put_rules(paths, [rule(p=105.0, since="2026-10-01")])
            with Fake() as f:
                run(paths, ENV_ALL)
            sent = [c for c in f.calls if c[0] == "Telegram" and "sendMessage" in c[1]]
            self.assertEqual(json.loads(sent[0][2])["chat_id"], "4242")
            self.assertEqual(read_state(paths)["tg"], 4242)
            # 第二天不再呼叫 getUpdates
            with Fake() as f2:
                run(paths, ENV_ALL, now=NOW + dt.timedelta(days=1))
            self.assertFalse(any("getUpdates" in str(c[1]) for c in f2.calls))

    def test_test_mode_sends_to_each_channel_and_keeps_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            with Fake() as f:
                rc, out = run(paths, ENV_ALL, test=True)
            self.assertEqual(rc, 0)
            self.assertEqual(sorted(f.names()), ["Gmail", "Telegram", "ntfy"])
            self.assertFalse(os.path.exists(paths.state))
            with Fake(fail=("ntfy", "Gmail", "Telegram")):
                self.assertEqual(run(paths, ENV_ALL, test=True)[0], 1)
            with Fake() as f3:
                self.assertEqual(run(paths, {"FUTURES_PASSWORD": PW, "NTFY_TOPIC": "x"}, test=True)[0], 0)
                self.assertEqual(f3.names(), ["ntfy"])

    def test_wrong_password_rules_fail_clearly(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp)
            put_rules(paths, [rule()])
            rc, out = run(paths, {"FUTURES_PASSWORD": "another"})
            self.assertEqual(rc, 1)
            self.assertIn("解不開", out)


class Report(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.paths = build_root(self.tmp.name)
        self.key = A.derive_key(PW, self.paths)

    def tearDown(self):
        self.tmp.cleanup()

    def market(self):
        rows = []
        for it in A.universe(self.paths):
            bars, ok = A.load_bars(it, self.key, self.paths)
            if bars:
                rows.append(A.market_row(it, bars, ok, dt.date(2026, 11, 24)))
        return rows

    def test_universe_groups_and_order(self):
        its = A.universe(self.paths)
        self.assertEqual([i["code"] for i in its], ["aaa", "bbb", "etf1", "ym", "nq", "tx"])      # 停用公司不在
        self.assertEqual([s for s, _ in A.groups(self.market())], ["科技", "能源", "ETF", "指數期貨"])

    def test_ath_uses_recent_and_hist_files(self):
        it = [i for i in A.universe(self.paths) if i["code"] == "aaa"][0]
        recent_only = A.load_bars(it, self.key, self.paths, want_hist=False)[0]
        full, ok = A.load_bars(it, self.key, self.paths)
        self.assertTrue(ok)
        self.assertGreater(len(full), len(recent_only))               # 2024 的資料只在歷史檔
        row = A.market_row(it, full, ok, dt.date(2026, 11, 24))
        self.assertEqual(row["ath"], max(b[2] for b in full))
        self.assertEqual(row["athT"], max(full, key=lambda b: b[2])[0])
        self.assertAlmostEqual(row["fromAth"], (full[-1][4] / row["ath"] - 1) * 100)
        self.assertFalse(row["old"])

    def test_hist_unreadable_marks_not_full(self):
        os.remove(os.path.join(self.tmp.name, "data", "kbar", "aaa.hist.enc.json"))
        it = [i for i in A.universe(self.paths) if i["code"] == "aaa"][0]
        bars, ok = A.load_bars(it, self.key, self.paths)
        self.assertFalse(ok)
        row = A.market_row(it, bars, ok, dt.date(2026, 11, 24))
        self.assertIn("只含近期資料", A.table_text([row]))

    def test_futures_ath_uses_all_bars(self):
        it = [i for i in A.universe(self.paths) if i["code"] == "ym"][0]
        bars, ok = A.load_bars(it, self.key, self.paths)
        row = A.market_row(it, bars, ok, dt.date(2026, 11, 24))
        self.assertEqual(row["ath"], max(b[2] for b in bars))
        self.assertEqual(row["ccy"], "點")

    def test_stale_marker_boundary(self):
        it = [i for i in A.universe(self.paths) if i["code"] == "bbb"][0]
        bars, ok = A.load_bars(it, self.key, self.paths)
        self.assertFalse(A.market_row(it, bars, ok, dt.date(2026, 11, 27))["old"])
        self.assertTrue(A.market_row(it, bars, ok, dt.date(2026, 11, 28))["old"])
        row = A.market_row(it, bars, ok, dt.date(2026, 11, 30))
        self.assertIn("資料較舊", A.table_text([row]))
        self.assertIn("資料較舊", A.build_html([], [], [row], dt.date(2026, 11, 30)))

    def lines(self, rules, hits):
        market = {r["code"]: r for r in self.market()}
        return A.rule_lines(rules, hits, market), market

    def test_rule_sorting(self):
        rules = [rule(id="far", p=5000.0), rule(id="near", p=150.0), rule(id="hit1", p=105.0, since="2026-10-01"), rule(id="off", on=False)]
        hits = {"hit1": {"t": "2026-11-10", "px": 106.0, "side": "h", "p": 105.0}}
        (h, o, off), _ = self.lines(rules, hits)
        self.assertEqual([x["rule"]["id"] for x in h], ["hit1"])
        self.assertEqual([x["rule"]["id"] for x in o], ["near", "far"])          # 距目標近的在前
        self.assertEqual([x["rule"]["id"] for x in off], ["off"])

    def test_html_and_text_sections(self):
        rules = [rule(id="hit1", p=105.0, since="2026-10-01", n="注意追高"), rule(id="w", code="nq", kind="fut", name="小那指", p=25000.0, mode="pct", pct=-10, base={"t": "2026-11-20", "c": 28000.0}, dir="down")]
        hits = {"hit1": {"t": "2026-11-10", "px": 106.0, "side": "h", "p": 105.0}}
        (h, o, _), market = self.lines(rules, hits)
        rows = list(market.values())
        html_s = A.build_html(h, o, rows, dt.date(2026, 11, 24))
        txt = A.build_text(h, o, rows, dt.date(2026, 11, 24))
        # 順序：提醒在最上面（已到價 → 監控中），之後才是總表
        self.assertLess(html_s.index("已到價"), html_s.index("監控中"))
        self.assertLess(html_s.index("監控中"), html_s.index("追蹤標的總表"))
        self.assertLess(txt.index("【已到價"), txt.index("【監控中"))
        self.assertLess(txt.index("【監控中"), txt.index("追蹤標的總表"))
        self.assertIn("基準 28,000", html_s)                # 百分比模式附 −10% 與基準
        self.assertIn("−10%", html_s)
        self.assertIn("注意追高", html_s)
        self.assertIn("距目標", html_s)
        for sec in ("科技", "能源", "ETF", "指數期貨"):
            self.assertIn(sec, html_s)
        self.assertIn(A.ALERTS_URL, html_s)
        self.assertIn("prefers-color-scheme:dark", html_s)
        self.assertIn("viewport", html_s)
        self.assertIn("已依股票分割調整", html_s)

    def test_no_rules_line(self):
        market = self.market()
        self.assertIn("目前沒有設定提醒", A.build_html([], [], market, dt.date(2026, 11, 24)))
        self.assertIn("目前沒有設定提醒", A.build_text([], [], market, dt.date(2026, 11, 24)))

    def test_subject(self):
        d = dt.date(2026, 11, 24)
        self.assertEqual(A.subject(2, 5, d), "🔔 到價 2 檔｜每日行情 11/24")
        self.assertEqual(A.subject(0, 5, d), "每日行情 11/24（提醒 5 條監控中）")

    def test_table_columns(self):
        rows = self.market()
        t = A.table_text(rows)
        self.assertIn("甲公司（AAA）", t)
        self.assertIn("距高點", t)
        self.assertIn("資料 11/23", t)

    def test_group_order_matches_website(self):
        rows = [dict(sector=s) for s in ("能源", "指數期貨", "ETF", "科技", "能源")]
        self.assertEqual([s for s, _ in A.groups(rows)], ["能源", "科技", "ETF", "指數期貨"])

    def test_missing_files_skipped_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = build_root(tmp, spare=("bbb",))
            put_rules(paths, [rule(code="bbb", p=10.0)])
            rc, out = run(paths, {"FUTURES_PASSWORD": PW})
            self.assertEqual(rc, 0)
            self.assertEqual(read_state(paths)["hits"], {})


if __name__ == "__main__":
    unittest.main()
