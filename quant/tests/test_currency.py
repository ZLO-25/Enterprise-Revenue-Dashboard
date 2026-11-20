"""執行：python -m unittest discover -s quant/tests -p 'test_*.py'
幣別判斷：「財報追蹤公司」群組新增了上櫃、韓股、荷蘭掛牌的代號，金額前綴不能都變成美元。"""
import sys, unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from fetch_data import currency_of  # noqa: E402


class CurrencyTest(unittest.TestCase):
    def test_currency(self):
        for sym, cur in [("2330.TW", "TWD"), ("6187.TWO", "TWD"), ("^TWII", "TWD"), ("0005.HK", "HKD"),
                         ("005930.KS", "KRW"), ("ASML.AS", "EUR"), ("NVDA", "USD"), ("BTC-USD", "USD"), ("^GSPC", "USD")]:
            self.assertEqual(currency_of(sym), cur, sym)


if __name__ == "__main__":
    unittest.main()
