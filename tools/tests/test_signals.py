import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import signals as S


def cap(now, thr=30, op="<="):
    return [{"k": "pe", "name": "本益比", "op": op, "thr": thr, "now": now}]


class ThreeState(unittest.TestCase):
    def run_seq(self, vals, **kw):
        st = {"state": {}, "events": []}
        kinds = []
        for i, v in enumerate(vals):
            kinds += [e["kind"] for e in S.update(st, "x", f"2026-01-{i + 1:02d}", cap(v, **kw))]
        return kinds

    def test_first_sight_no_event(self):
        self.assertEqual(self.run_seq([40]), [])
        self.assertEqual(self.run_seq([10]), [])

    def test_rich_needs_15_percent(self):
        self.assertEqual(self.run_seq([30, 34.4]), [])             # 34.4 < 30×1.15 = 34.5
        self.assertEqual(self.run_seq([30, 34.5]), ["rich"])

    def test_cheap_needs_15_percent(self):
        self.assertEqual(self.run_seq([30, 25.6]), [])             # 25.6 > 30×0.85 = 25.5
        self.assertEqual(self.run_seq([30, 25.5]), ["cheap"])

    def test_back_needs_13_percent(self):
        self.assertEqual(self.run_seq([30, 35, 34.0]), ["rich"])           # 34.0 ≥ 30×1.13 = 33.9：還沒回來
        self.assertEqual(self.run_seq([30, 35, 33.8]), ["rich", "back"])
        self.assertEqual(self.run_seq([30, 25, 26.2]), ["cheap", "back"])  # 26.2 > 30×0.87 = 26.1 → 回來
        self.assertEqual(self.run_seq([30, 25, 26.0]), ["cheap"])          # 26.0 還在 −13% 以下

    def test_no_flapping(self):
        self.assertEqual(self.run_seq([30, 35, 34.0, 34.6, 34.2, 34.7]), ["rich"])

    def test_ge_direction(self):
        # 「≥」指標（殖利率）：現值太低＝貴
        self.assertEqual(self.run_seq([3.0, 2.5], thr=3.0, op=">="), ["rich"])      # 2.5 ≤ 3×0.85 = 2.55
        self.assertEqual(self.run_seq([3.0, 3.5], thr=3.0, op=">="), ["cheap"])     # 3.5 ≥ 3×1.15 = 3.45
        self.assertEqual(self.run_seq([3.0, 2.5, 2.6], thr=3.0, op=">="), ["rich"])           # 2.6 ≤ 3×0.87 = 2.61：還沒回來
        self.assertEqual(self.run_seq([3.0, 2.5, 2.7], thr=3.0, op=">="), ["rich", "back"])

    def test_old_state_in_out_is_unknown(self):
        for old in ("in", "out"):
            st = {"state": {"x.pe": old}, "events": []}
            self.assertEqual(S.update(st, "x", "2026-01-01", cap(40)), [])      # 不發訊號
            self.assertEqual(st["state"]["x.pe"], "rich")                        # 但記下新狀態
            self.assertEqual([e["kind"] for e in S.update(st, "x", "2026-01-02", cap(30))], ["back"])

    def test_same_day_dedupe(self):
        st = {"state": {"x.pe": "normal"}, "events": []}
        self.assertEqual(len(S.update(st, "x", "2026-01-01", cap(40))), 1)
        st["state"]["x.pe"] = "normal"
        self.assertEqual(len(S.update(st, "x", "2026-01-01", cap(40))), 0)

    def test_text(self):
        ev = {"code": "aapl", "name": "本益比", "now": 40, "thr": 30, "op": "<=", "kind": "rich"}
        self.assertIn("提醒，不是買賣建議", S.text(ev))
        self.assertIn("貴", S.text(ev))


if __name__ == "__main__":
    unittest.main()
