import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import signals as S


def cap(now, thr=30, op="<="):
    return [{"k": "pe", "name": "本益比", "op": op, "thr": thr, "now": now}]


class Hysteresis(unittest.TestCase):
    def run_seq(self, vals, **kw):
        st = {"state": {}, "events": []}
        kinds = []
        for i, v in enumerate(vals):
            kinds += [e["kind"] for e in S.update(st, "x", f"2026-01-{i + 1:02d}", cap(v, **kw))]
        return kinds

    def test_first_sight_no_event(self):
        self.assertEqual(self.run_seq([40]), [])

    def test_exceed_needs_two_percent(self):
        self.assertEqual(self.run_seq([25, 30.5, 30.6]), [])          # 30.6 < 30*1.02
        self.assertEqual(self.run_seq([25, 30.7]), ["exceed"])        # > 30.6

    def test_back_needs_two_percent(self):
        self.assertEqual(self.run_seq([25, 31, 29.5]), ["exceed"])    # 29.5 > 29.4 → 還沒回來
        self.assertEqual(self.run_seq([25, 31, 29.3]), ["exceed", "back"])

    def test_no_flapping_around_threshold(self):
        self.assertEqual(self.run_seq([25, 31, 30.2, 29.8, 30.4, 29.7]), ["exceed"])

    def test_ge_direction(self):
        self.assertEqual(self.run_seq([40, 29.0], thr=30, op=">="), ["exceed"])
        self.assertEqual(self.run_seq([40, 29.0, 30.5], thr=30, op=">="), ["exceed"])
        self.assertEqual(self.run_seq([40, 29.0, 30.7], thr=30, op=">="), ["exceed", "back"])

    def test_same_day_dedupe(self):
        st = {"state": {"x.pe": "in"}, "events": []}
        self.assertEqual(len(S.update(st, "x", "2026-01-01", cap(40))), 1)
        st["state"]["x.pe"] = "in"
        self.assertEqual(len(S.update(st, "x", "2026-01-01", cap(40))), 0)


if __name__ == "__main__":
    unittest.main()
