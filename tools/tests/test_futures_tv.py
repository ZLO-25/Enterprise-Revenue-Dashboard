"""TradingView 匯入：合併規則（只補早期與缺漏、重疊要對得上）與加密往返。數字都是假的測試值。"""
import datetime as dt, json, os, sys, tempfile, unittest, zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import futures_update as F  # noqa: E402
import futures_import as I  # noqa: E402


def days(start, n):
    d, out = dt.date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def yahoo(ds, k=1.0):
    return [[d, 100 * k + i, 102 * k + i, 99 * k + i, 101 * k + i, 10] for i, d in enumerate(ds)]


def tv_from(rows, shift_back=0):
    ts = [int(dt.datetime.fromisoformat(r[0]).replace(tzinfo=dt.timezone.utc).timestamp()) - shift_back * 86400 for r in rows]
    return {"symbol": "CME_MINI:NQ1!", "t": ts, "o": [r[1] for r in rows], "h": [r[2] for r in rows], "l": [r[3] for r in rows], "c": [r[4] for r in rows], "v": [r[5] for r in rows]}


class Merge(unittest.TestCase):
    def setUp(self):
        self.all = days("2000-01-03", 80)
        self.full = yahoo(self.all)

    def test_prepend_early_history(self):
        ya = self.full[30:]
        bars, info, filled = F.merge_tv(ya, tv_from(self.full))
        self.assertEqual(bars[0][0], self.all[0])
        self.assertEqual(info["prepended"], 30)
        self.assertEqual(filled, set())

    def test_fill_missing_day_only_when_neighbours_agree(self):
        ya = [b for b in self.full if b[0] != self.all[50]]
        bars, info, filled = F.merge_tv(ya, tv_from(self.full), bad=[self.all[50]])
        self.assertIn(self.all[50], filled)
        self.assertEqual(info["bad"], [self.all[50]])
        tv = tv_from(self.full)
        tv["c"][49] *= 1.05                        # 前一天對不起來 → 不補
        bars, info, filled = F.merge_tv(ya, tv)
        self.assertNotIn(self.all[50], filled)

    def test_reject_when_levels_differ(self):
        bars, info, filled = F.merge_tv(self.full[30:], tv_from(yahoo(self.all, k=1.1)))
        self.assertIn("rejected", info)
        self.assertEqual(len(bars), 50)

    def test_timestamp_shift_detected(self):
        bars, info, _ = F.merge_tv(self.full[30:], tv_from(self.full, shift_back=1))
        self.assertEqual(info["shift"], 1)
        self.assertEqual(bars[0][0], self.all[0])

    def test_never_overrides_yahoo(self):
        tv = tv_from(self.full); tv["c"][40] = tv["c"][40] * 1.002
        bars, _, _ = F.merge_tv(self.full[30:], tv)
        self.assertEqual({b[0]: b for b in bars}[self.all[40]][4], self.full[40][4])


class Crypto(unittest.TestCase):
    def test_hybrid_roundtrip(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pub = k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        priv = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        body = I.encrypt(zlib.compress(b'{"a":1}'), pub)
        self.assertEqual(json.loads(zlib.decompress(F.decrypt_hybrid(body, priv))), {"a": 1})

    def test_combine_pages(self):
        a = {"t": [3, 1], "o": [3, 1], "h": [3, 1], "l": [3, 1], "c": [3, 1], "v": [0, 0]}
        b = {"result": {"bars": {"t": [2, 3], "o": [2, 3], "h": [2, 3], "l": [2, 3], "c": [2, 3], "v": [0, 0]}}}
        self.assertEqual(I.combine([a, b])["t"], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
