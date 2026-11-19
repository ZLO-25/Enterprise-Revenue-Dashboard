"""大台指（TX）：期交所 CSV 解析、近月選擇、換月日、台灣休市判斷、落後判斷。數字都是假的測試值。"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import futures_update as F  # noqa: E402

HEAD = ['交易日期', '契約', '到期月份(週別)', '開盤價', '最高價', '最低價', '收盤價', '漲跌價', '漲跌%', '成交量', '結算價',
        '未沖銷契約數', '最後最佳買價', '最後最佳賣價', '歷史最高價', '歷史最低價', '是否因訊息面暫停交易', '交易時段', '價差對單式委託成交量']


def row(d, m, o, h, l, c, v, sess='一般'):
    return [d, 'TX', m, o, h, l, c, '', '', v, '', '', '', '', '', '', '', sess, '']


class TaifexParse(unittest.TestCase):
    def test_near_month_day_session_only(self):
        rows = [HEAD,
                row('2026/11/18', '202611', '100', '110', '95', '105', '50'),
                row('2026/11/18', '202612', '200', '210', '195', '205', '9'),
                row('2026/11/18', '202611/202612', '1', '1', '1', '1', '3'),     # 價差：不要
                row('2026/11/18', '202611W4', '7', '7', '7', '7', '1'),         # 週契約：不要
                row('2026/11/18', '202611', '900', '990', '850', '950', '70', '盤後'),  # 夜盤：不要
                row('2026/11/19', '202612', '206', '220', '200', '215', '60')]
        out, miss = F.parse_taifex(rows)
        self.assertEqual(out['2026-11-18'], ('202611', ['2026-11-18', 100, 110, 95, 105, 50]))
        self.assertEqual(out['2026-11-19'][0], '202612')
        self.assertEqual(miss, [])

    def test_near_month_without_trades_is_missing_not_replaced(self):
        rows = [HEAD, row('2026/11/18', '202611', '-', '-', '-', '-', '0'), row('2026/11/18', '202612', '200', '210', '195', '205', '9')]
        out, miss = F.parse_taifex(rows)
        self.assertNotIn('2026-11-18', out)
        self.assertEqual(miss, ['2026-11-18'])

    def test_old_format_without_session_column(self):
        h = HEAD[:17]
        rows = [h, row('1998/07/21', '199808', '100', '110', '95', '105', '5')[:17]]
        out, _ = F.parse_taifex(rows)
        self.assertEqual(out['1998-07-21'][1][4], 105)

    def test_unexpected_header_raises(self):
        with self.assertRaises(RuntimeError):
            F.parse_taifex([['日期', '價格'], ['2026/11/18', '1']])

    def test_rolls_are_actual_contract_changes(self):
        r = F.tx_rolls([('2026-11-17', '202611'), ('2026-11-18', '202611'), ('2026-11-19', '202612')])
        self.assertEqual(r, [{'date': '2026-11-19', 'from': '202611', 'to': '202612'}])

    def test_month_ranges_at_most_one_month(self):
        rs = list(F.month_ranges(dt.date(2026, 1, 15), dt.date(2026, 3, 2)))
        self.assertEqual(rs[0], (dt.date(2026, 1, 15), dt.date(2026, 1, 31)))
        self.assertEqual(rs[-1], (dt.date(2026, 3, 1), dt.date(2026, 3, 2)))
        self.assertTrue(all((b - a).days <= 31 for a, b in rs))


class TwCalendar(unittest.TestCase):
    T = F.TPE

    def test_expected_date(self):
        self.assertEqual(F.tw_expected_date(dt.datetime(2026, 11, 19, 10, 0, tzinfo=self.T)), '2026-11-18')
        self.assertEqual(F.tw_expected_date(dt.datetime(2026, 11, 19, 17, 0, tzinfo=self.T)), '2026-11-19')
        self.assertEqual(F.tw_expected_date(dt.datetime(2026, 11, 23, 8, 0, tzinfo=self.T)), '2026-11-20')  # 週一早上 → 上週五

    def test_holiday_only_after_next_morning(self):
        self.assertFalse(F.tw_assume_closed('2026-11-18', dt.datetime(2026, 11, 18, 20, 0, tzinfo=self.T)))
        self.assertTrue(F.tw_assume_closed('2026-11-18', dt.datetime(2026, 11, 19, 7, 30, tzinfo=self.T)))

    def test_behind_uses_checked_for(self):
        now = dt.datetime(2026, 11, 19, 8, 30, tzinfo=self.T)
        ok_us = {'lastDate': '2026-11-18'}
        meta = {'ym': ok_us, 'nq': ok_us, 'tx': {'lastDate': '2026-11-17'}}
        self.assertEqual(F.behind_list(meta, now), ['tx'])
        meta['tx']['checkedFor'] = '2026-11-18'      # 已確認 11/18 休市
        self.assertEqual(F.behind_list(meta, now), [])


if __name__ == '__main__':
    unittest.main()
