import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bs_fetch as B


class CikPrevTest(unittest.TestCase):
    def test_merges_old_and_new_registrant(self):
        data = {
            "NEW": [{"accn": "n1", "start": None, "end": "2026-09-30", "unit": "USD", "val": 3},
                    {"accn": "o1", "start": None, "end": "2025-12-31", "unit": "USD", "val": 2}],
            "OLD": [{"accn": "o1", "start": None, "end": "2025-12-31", "unit": "USD", "val": 2},
                    {"accn": "o0", "start": None, "end": "2024-12-31", "unit": "USD", "val": 1}],
        }
        c = {"cik": "NEW", "cikPrev": ["OLD"]}
        got = B.concept_all(c, "X", fetch=lambda k, n: data[k])
        self.assertEqual(sorted(f["end"] for f in got), ["2024-12-31", "2025-12-31", "2026-09-30"])

    def test_without_prev_is_single_cik(self):
        c = {"cik": "NEW"}
        got = B.concept_all(c, "X", fetch=lambda k, n: [{"accn": "a", "end": "2026-09-30", "unit": "USD"}] if k == "NEW" else [])
        self.assertEqual(len(got), 1)


if __name__ == "__main__":
    unittest.main()
