"""bs_merge：提案沒有值時不可以清掉資料檔原本的值（2026-11-19 PANW 稀釋股數被清空 40 季的修正）。"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import bs_merge as M  # noqa: E402

MARK = M.MARK


def run(D, raw, *flags):
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "data", "bs-raw"))
        for path, obj in ((("data", "t.json"), D), (("data", "bs-raw", "t.json"), raw)):
            with open(os.path.join(d, *path), "w", encoding="utf8") as fh:
                json.dump(obj, fh, ensure_ascii=False)
        old_root, old_argv = M.ROOT, sys.argv
        try:
            M.ROOT, sys.argv = d, ["bs_merge.py", *flags, "t"]
            M.main()
        finally:
            M.ROOT, sys.argv = old_root, old_argv
        with open(os.path.join(d, "data", "t.json"), encoding="utf8") as fh:
            return json.load(fh)


def qrow(q, **kw):
    r = {"q": q, "rev": 100, "ni": 10, "eps": 1.0}
    for k in ("shOut", "dilSh", "cash", "debt", "buyback", "equity", "pretax", "tax", "sbc"):
        r[k] = kw.get(k)
    return r


class KeepOld(unittest.TestCase):
    def test_null_proposal_keeps_existing_value(self):
        D = {"quarters": [qrow("1Q25", dilSh=10.0, cash=5), qrow("2Q25", dilSh=10.0, cash=6), qrow("3Q25")],
             "notes": {"unavailable": []}}
        raw = {"quarters": [{"q": "1Q25", "vals": {"cash": 7}, "why": {"dilSh": "讀不到單季值"}},
                            {"q": "2Q25", "vals": {}, "why": {"*": "淨利對不上"}}]}
        out = run(D, raw)
        self.assertEqual([q["dilSh"] for q in out["quarters"]], [10.0, 10.0, None])   # 舊值保留，新一季照舊 null
        self.assertEqual([q["cash"] for q in out["quarters"]], [7, 6, None])         # 提案有值仍以提案為準
        dil = [x for x in out["notes"]["unavailable"] if "（dilSh）" in x]
        self.assertEqual(len(dil), 1)
        self.assertIn("1 季沒有值（3Q25～3Q25）", dil[0])                             # 只算真的沒值的季度
        self.assertIn("10-Q", dil[0])

    def test_zero_share_count_is_rejected(self):
        D = {"quarters": [qrow("1Q25", shOut=None), qrow("2Q25", shOut=8.0)], "notes": {"unavailable": []}}
        raw = {"quarters": [{"q": "1Q25", "vals": {"shOut": 0}, "why": {}}, {"q": "2Q25", "vals": {"shOut": 0}, "why": {}}]}
        out = run(D, raw)
        self.assertEqual([q["shOut"] for q in out["quarters"]], [None, 8.0])
        line = [x for x in out["notes"]["unavailable"] if "（shOut）" in x][0]
        self.assertIn("0 或負值", line)

    def test_kept_sbc_still_checked(self):
        D = {"quarters": [qrow("1Q25", sbc=90.0), qrow("2Q25", sbc=20.0)], "notes": {"unavailable": []}}
        out = run(D, {"quarters": []}, "--only", "sbc")
        self.assertEqual([q["sbc"] for q in out["quarters"]], [None, 20.0])            # 90/100 > 60% 的舊值不留


class Notes(unittest.TestCase):
    def test_hand_written_line_kept_and_new_quarter_added(self):
        hand = MARK + "有息負債（debt）：1Q25～2Q25 沒有值：這段期間 XBRL 沒有長期借款科目（後來 3Q25 有 3），讀附註前不填"
        D = {"quarters": [qrow("1Q25"), qrow("2Q25"), qrow("3Q25", debt=3), qrow("4Q25")],
             "notes": {"unavailable": ["待確認：別的事", hand]}}
        raw = {"quarters": [{"q": "3Q25", "vals": {"debt": 3}, "why": {}}]}
        un = run(D, raw)["notes"]["unavailable"]
        self.assertEqual(un[:2], ["待確認：別的事", hand])                                # 手寫原文、位置都不動
        new = [x for x in un if "（debt）" in x and x != hand]
        self.assertEqual(len(new), 1)
        self.assertIn("1 季沒有值（4Q25～4Q25）", new[0])                              # 新的沒值季度另外一行

    def test_hand_line_dropped_when_all_its_quarters_filled(self):
        hand = MARK + "有息負債（debt）：1Q25 沒有值：讀不到"
        D = {"quarters": [qrow("1Q25"), qrow("2Q25", debt=2)], "notes": {"unavailable": [hand]}}
        raw = {"quarters": [{"q": "1Q25", "vals": {"debt": 1}, "why": {}}, {"q": "2Q25", "vals": {"debt": 2}, "why": {}}]}
        out = run(D, raw)
        self.assertEqual([q["debt"] for q in out["quarters"]], [1, 2])
        self.assertFalse([x for x in out["notes"]["unavailable"] if "（debt）" in x])

    def test_default_mode_leaves_sbc_line_alone(self):
        sbc = MARK + "股票酬勞（sbc）：1 季沒有值（1Q25～1Q25）：讀不到單季值（1 季）"
        D = {"quarters": [qrow("1Q25", dilSh=10.0)], "notes": {"unavailable": [sbc]}}
        out = run(D, {"quarters": [{"q": "1Q25", "vals": {"dilSh": 10.0}, "why": {}}]})
        self.assertIn(sbc, out["notes"]["unavailable"])                                 # 8 欄位模式不可刪 sbc 的說明

    def test_rerun_is_stable(self):
        D = {"quarters": [qrow("1Q25", dilSh=10.0), qrow("2Q25")], "notes": {"unavailable": []}}
        raw = {"quarters": [{"q": "1Q25", "vals": {}, "why": {"dilSh": "讀不到單季值"}}]}
        once = run(D, raw)
        self.assertEqual(run(once, raw), once)


if __name__ == "__main__":
    unittest.main()
