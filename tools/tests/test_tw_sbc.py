"""台股股票酬勞（tools/tw_sbc.py）：現金流量表累計數拆單季、沒有這一行不當成 0、較新報表的重編數優先。"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import tw_sbc as T  # noqa: E402

CF = "<tr><td>AAAA</td><td>營業活動之淨現金流入（流出）</td><td>1</td><td>1</td></tr>"


def new(cur, prev):
    return (f"<table>{CF}<tr><td>A21900</td><td><span class='zh'>股份基礎給付酬勞成本</span> Share-based payments</td>"
            f"<td>{cur}</td><td>{prev}</td></tr></table>")


def old(cur, prev):
    return f"<table>{CF}<tr><td>　　股份基礎給付酬勞成本</td><td>{cur}</td><td>{prev}</td></tr></table>"


NOLINE = f"<table>{CF}<tr><td>A29900</td><td>其他項目</td><td>17,873</td><td>90,654</td></tr></table>"


class ReadRow(unittest.TestCase):
    def test_new_and_old_format(self):
        self.assertEqual(T.read_row(new("324,131", "15,000")), (324131.0, 15000.0))
        self.assertEqual(T.read_row(old("38,980", "0")), (38980.0, 0.0))
        self.assertEqual(T.read_row(new("( 1,200 )", "0")), (-1200.0, 0.0))

    def test_missing_line_is_none_and_notes_do_not_match(self):
        self.assertIsNone(T.read_row(NOLINE))
        note = "<table><tr><td>股份基礎給付</td><td>0</td><td>0</td></tr><tr><td>N1</td><td>股份基礎給付 Share-based payments</td><td>5,568</td></tr></table>"
        self.assertIsNone(T.read_row(note))


class Build(unittest.TestCase):
    def q(self, Q):
        return {r["q"]: r for r in Q}

    def test_ytd_to_quarter(self):
        files = {(2026, 1): new("10,000", "0"), (2026, 2): new("68,041", "0"), (2026, 3): new("324,131", "15,000")}
        _, Q = T.build(files)
        q = self.q(Q)
        self.assertEqual(q["1Q26"]["vals"]["sbc"], 10.0)
        self.assertEqual(q["2Q26"]["vals"]["sbc"], 58.041)
        self.assertEqual(q["3Q26"]["vals"]["sbc"], 256.09)

    def test_missing_line_never_becomes_zero(self):
        # 第一季沒有這一行：第一季不填；第二季因為上一季累計不明也不填；第三季＝9 個月 − 6 個月 可以算
        files = {(2026, 1): NOLINE, (2026, 2): new("68,041", "0"), (2026, 3): new("324,131", "15,000")}
        q = self.q(T.build(files)[1])
        self.assertNotIn("sbc", q["1Q26"]["vals"])
        self.assertIn("沒有列", q["1Q26"]["why"]["sbc"])
        self.assertNotIn("sbc", q["2Q26"]["vals"])
        self.assertIn("上一季", q["2Q26"]["why"]["sbc"])
        self.assertEqual(q["3Q26"]["vals"]["sbc"], 256.09)

    def test_prior_year_column_fills_and_printed_zero_counts(self):
        # 2025 年的報表都沒有這一行，但 2026 年報表的「去年同期」欄印了 0 與 15,000 → 3Q25 ＝ 15
        files = {(2025, 2): NOLINE, (2025, 3): NOLINE, (2026, 2): new("68,041", "0"), (2026, 3): new("324,131", "15,000")}
        q = self.q(T.build(files)[1])
        self.assertEqual(q["3Q25"]["vals"]["sbc"], 15.0)
        self.assertNotIn("sbc", q["2Q25"]["vals"])

    def test_newer_report_wins_on_restatement(self):
        files = {(2025, 1): new("5,000", "0"), (2026, 1): new("9,000", "6,000")}
        ytd, Q = T.build(files)
        self.assertEqual(ytd[(2025, 1)]["v"], 6000.0)
        self.assertEqual(ytd[(2025, 1)]["restated"], 5000.0)
        self.assertEqual(self.q(Q)["1Q25"]["vals"]["sbc"], 6.0)

    def test_sign_flip_between_reports_is_a_conflict(self):
        files = {(2022, 3): new("61,481", "0"), (2022, 4): new("( 74,885 )", "0"), (2023, 4): new("45,869", "74,885")}
        q = self.q(T.build(files)[1])
        self.assertNotIn("sbc", q["4Q22"]["vals"])
        self.assertIn("正負號相反", q["4Q22"]["why"]["sbc"])

    def test_report_without_cashflow_is_skipped(self):
        self.assertEqual(T.build({(2026, 1): "<table></table>"})[1], [])


if __name__ == "__main__":
    unittest.main()
