"""tools/macro_brief.py：總經一週摘要（每週日排程用）。只比兩個版本的 latest.json，不計算指標。"""
import datetime, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import macro_brief as mb

CFG = {
    "groups": [{"series": [{"key": "icsa4", "name": "初領失業金", "core": True}, {"key": "vix", "name": "VIX"}, {"key": "m2", "name": "M2"}]}],
    "tw": {"series": [{"key": "twexp", "name": "出口"}]},
    "reminders": [{"id": "jobs-turn", "level": "watch", "title": "失業金上升"}, {"id": "curve", "level": "calm", "title": "殖利率曲線倒掛中"}],
}
TODAY = datetime.date(2026, 11, 29)


def doc(lights, reminders=None, boom=1, updated="2026-11-28 18:15 UTC", tw=("紅", "2026-09"), stale=(), failed=0, dead=(), twl=None):
    d = {
        "updated": updated,
        "series": {k: {"stats": {"light": v, "last": 1.5, "lastDate": "2026-11-27"}} for k, v in lights.items()},
        "tw": {"series": {k: {"stats": {"light": v}} for k, v in (twl or {}).items()}, "light": {"name": tw[0], "date": tw[1]}},
        "boomNow": boom, "score": {"items": 7},
        "health": {"stale": list(stale), "failed": failed}, "links": {"dead": list(dead)},
    }
    if reminders is not None:
        d["reminders"] = list(reminders)
    return d


class BriefTest(unittest.TestCase):
    def text(self, *a, **k):
        return "\n".join(mb.brief(*a, **k))

    def test_light_changes_worse_first_and_core_marked(self):
        prev = doc({"icsa4": "flat", "vix": "flat", "m2": "flat"}, [])
        now = doc({"icsa4": "worse", "vix": "better", "m2": "flat"}, [])
        lines = mb.brief(now, CFG, prev, TODAY)
        rows = [l for l in lines if "→" in l]
        self.assertEqual(len(rows), 2)
        self.assertIn("★初領失業金：持平 → 轉差", rows[0])
        self.assertIn("VIX：持平 → 轉好", rows[1])
        self.assertIn("換燈：2 個", "\n".join(lines))
        self.assertIn("目前轉差：1 個（初領失業金）", "\n".join(lines))

    def test_no_change(self):
        d = doc({"icsa4": "flat"}, ["curve"])
        t = self.text(d, CFG, d, TODAY)
        self.assertIn("這一週沒有指標換燈", t)
        self.assertIn("新出現 0 條，消失 0 條，持續 1 條", t)
        self.assertIn("和上週相同", t)

    def test_reminders_new_gone_keep(self):
        prev = doc({"icsa4": "flat"}, ["curve"])
        now = doc({"icsa4": "worse"}, ["jobs-turn"], boom=2)
        t = self.text(now, CFG, prev, TODAY)
        self.assertIn("＋留意：失業金上升", t)
        self.assertIn("－觀念：殖利率曲線倒掛中（條件不再成立）", t)
        self.assertIn("七大指標現在亮 2 項（共 7 項），上週是 1 項", t)

    def test_no_prev_only_current(self):
        t = self.text(doc({"vix": "worse"}, ["curve"]), CFG, None, TODAY)
        self.assertIn("拿不到一週前的版本", t)
        self.assertNotIn("換燈：", t)
        self.assertIn("目前成立 1 條", t)

    def test_prev_without_reminders_feature(self):
        prev = doc({"vix": "flat"})                      # 第一版的檔案沒有 reminders
        t = self.text(doc({"vix": "worse"}, ["curve"]), CFG, prev, TODAY)
        self.assertIn("上週那一版還沒有提醒功能", t)
        self.assertIn("VIX：持平 → 轉差", t)

    def test_old_data_is_flagged(self):
        t = self.text(doc({"vix": "flat"}, [], updated="2026-11-10 18:00 UTC"), CFG, None, TODAY)
        self.assertIn("待確認：總經資料已 19 天沒更新", t)

    def test_health_problems_listed(self):
        now = doc({"vix": "flat"}, [], stale=[{"key": "m2", "name": "M2"}], failed=2, dead=[{"url": "x"}])
        t = self.text(now, CFG, None, TODAY)
        self.assertIn("停更？M2", t)
        self.assertIn("這次抓不到 2 個", t)
        self.assertIn("連結失效 1 個", t)

    def test_taiwan_lamp_change_and_tw_series(self):
        prev = doc({}, [], tw=("黃紅", "2026-08"), twl={"twexp": "flat"})
        now = doc({}, [], tw=("紅", "2026-09"), twl={"twexp": "better"})
        t = self.text(now, CFG, prev, TODAY)
        self.assertIn("台灣景氣燈號：紅燈（2026-09），上週看到的是 黃紅燈（2026-08）", t)
        self.assertIn("台灣 出口：持平 → 轉好", t)

    def test_never_gives_advice_or_phase(self):
        t = self.text(doc({"vix": "worse"}, ["jobs-turn"]), CFG, None, TODAY)
        self.assertIn("不是買賣建議", t)
        for w in ("買進", "賣出", "減碼", "加碼"):
            self.assertNotIn(w, t)

    def test_many_changes_are_capped(self):
        keys = {f"k{i}": "flat" for i in range(20)}
        cfg = {"groups": [{"series": [{"key": k, "name": k} for k in keys]}], "reminders": []}
        now = doc({k: "worse" for k in keys}, [])
        lines = mb.brief(now, cfg, doc(keys, []), TODAY)
        self.assertEqual(len([l for l in lines if "→" in l]), mb.MAX_ROWS)
        self.assertIn(f"其餘 {20 - mb.MAX_ROWS} 個", "\n".join(lines))


class PrevDocTest(unittest.TestCase):
    def test_not_a_git_repo_returns_none(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(mb.prev_doc(TODAY, root=d))


if __name__ == "__main__":
    unittest.main()
