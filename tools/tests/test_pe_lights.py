import os, sys, unittest, datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pe as PE
import daily_brief as B


class Noisy(unittest.TestCase):
    def test_threshold(self):
        self.assertFalse(PE.pe_noisy(200))
        self.assertTrue(PE.pe_noisy(200.1))
        self.assertFalse(PE.pe_noisy(None))

    def test_text(self):
        self.assertEqual(PE.pe_text(25.04), "25.0")
        self.assertIn("不適用", PE.pe_text(5489.5))
        self.assertEqual(PE.pe_text(None), "—")


class LightsSplit(unittest.TestCase):
    def test_split_biz_val(self):
        lights = {"a": {"om": "r", "pe": "r"}, "b": {"pe": "y"}}
        groups = {"a": {"om": "biz", "pe": "val"}, "b": {"pe": "val"}}
        out = "\n".join(B.lights_part(lights, groups))
        self.assertIn("體質紅燈 1：a.om", out)
        self.assertIn("估值紅燈 1（附錄）：a.pe", out)


if __name__ == "__main__":
    unittest.main()
