"""新增公司的腳手架：一行指令產生所有必要檔案，之後只要填資料。

用法：
  python3 tools/new_company.py <代號> --name 中文名 --name-en EnglishName --ticker NVDA \
      --exchange "Nasdaq NVDA" --sector 半導體 --currency USD [--unit 百萬美元] [--eps-unit 美元] \
      [--yahoo NVDA --price-from 2009-02 [--twse 2330] | --no-price] [--source-name "SEC EDGAR"] [--source-url https://...] [--enable]

會建立／修改：
  data/<代號>.json               由 templates/_skeleton/data.v1.json 產生的空殼（所有數字為 null）
  companies/<代號>/SOURCES.md    由 templates/_skeleton/SOURCES.md 產生，請補完來源與欄位說明
  companies.json                 加一筆設定，template 用 generic（通用頁面），預設 enabled:false
不會動到 assets/、tools/build.py、其他公司的任何檔案。
填完資料後：python3 tools/validate.py <代號> && python3 tools/build.py
"""
import argparse, datetime, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UNITS = {"USD": ("百萬美元", "美元"), "TWD": ("百萬元新台幣", "元"), "JPY": ("百萬日圓", "日圓"), "EUR": ("百萬歐元", "歐元"), "HKD": ("百萬港元", "港元"), "CNY": ("百萬人民幣", "人民幣")}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("code", help="小寫英數字代號，同時是網址路徑，例：nvda")
    ap.add_argument("--name", required=True, help="中文名稱，例：輝達")
    ap.add_argument("--name-en", required=True, help="英文名稱，例：NVIDIA")
    ap.add_argument("--ticker", required=True, help="股票代號，例：NVDA 或 2330")
    ap.add_argument("--exchange", required=True, help="交易所與代號，例：'Nasdaq NVDA'、'TWSE 2330'")
    ap.add_argument("--sector", required=True, help="產業（首頁分頁籤）：優先沿用 companies.json 已有的產業名稱；沒有合適的才取新名稱，首頁會自動多一個分頁")
    ap.add_argument("--currency", required=True, help="幣別代碼：USD、TWD、JPY…")
    ap.add_argument("--unit", help="金額單位中文（預設依幣別：百萬美元／百萬元新台幣…）")
    ap.add_argument("--eps-unit", help="每股單位（預設依幣別：美元／元…）")
    ap.add_argument("--source-name", default="SEC EDGAR（10-Q、10-K、8-K）")
    ap.add_argument("--source-url", default="https://www.sec.gov/edgar/search/")
    ap.add_argument("--frequency", default="quarterly", choices=["quarterly", "monthly+quarterly"])
    ap.add_argument("--yahoo", help="Yahoo Finance 代碼（主要掛牌地普通股，例：NVDA、2330.TW、005930.KS）。有上市就必填")
    ap.add_argument("--price-from", help="股價起點 YYYY-MM（第一季資料的季度起始月或上市當月，取較晚者）")
    ap.add_argument("--twse", help="台股才填：證交所股票代號（會做證交所收盤價交叉核對），例：2330")
    ap.add_argument("--cik", help="美股才填：SEC CIK（10 位數，例 0001045810）。填了每日排程才能用 SEC 新申報清單判斷是否已公布財報")
    ap.add_argument("--tz", default=None, choices=["US", "TW", "KR", "JP", "EU"], help="公布時區（預設：有 cik 為 US，其餘請指定）")
    ap.add_argument("--no-price", action="store_true", help="尚未上市：companies.json 的 price 寫 null")
    ap.add_argument("--enable", action="store_true", help="直接 enabled:true（預設 false，填完資料並通過核對再開）")
    a = ap.parse_args()
    if not a.no_price and not (a.yahoo and a.price_from):
        sys.exit("本益比需要股價：請填 --yahoo <代碼> --price-from YYYY-MM（台股再加 --twse <代號>）；尚未上市請改用 --no-price")
    code = a.code.lower()
    if not code.isalnum():
        sys.exit("代號只能是小寫英數字")
    unit, eps_unit = UNITS.get(a.currency.upper(), ("百萬" + a.currency, a.currency))
    unit, eps_unit = a.unit or unit, a.eps_unit or eps_unit
    today = datetime.date.today()
    nxt = today + datetime.timedelta(days=60)
    vals = {"{{CODE}}": code, "{{NAME}}": a.name, "{{NAME_EN}}": a.name_en, "{{TICKER}}": a.ticker, "{{EXCHANGE}}": a.exchange,
            "{{CURRENCY}}": a.currency.upper(), "{{UNIT}}": unit, "{{EPS_UNIT}}": eps_unit, "{{ASOF}}": today.isoformat(),
            "{{NEXT_EVENT}}": nxt.isoformat(), "{{SOURCE_NAME}}": a.source_name, "{{SOURCE_URL}}": a.source_url, "{{TEMPLATE}}": "generic"}

    def render(rel):
        with open(os.path.join(ROOT, "templates", "_skeleton", rel), encoding="utf8") as f:
            s = f.read()
        for k, v in vals.items():
            s = s.replace(k, v)
        return s

    def put(text, *p):
        path = os.path.join(ROOT, *p)
        if os.path.exists(path):
            print(f"  已存在，略過：{'/'.join(p)}")
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf8") as f:
            f.write(text)
        print(f"  建立：{'/'.join(p)}")

    print(f"新增公司 {a.name}（{code}）")
    json.loads(render("data.v1.json"))  # 確認是合法 JSON
    put(render("data.v1.json"), "data", code + ".json")
    put(render("SOURCES.md"), "companies", code, "SOURCES.md")
    cfg_path = os.path.join(ROOT, "companies.json")
    cfg = json.load(open(cfg_path, encoding="utf8"))
    if any(c["code"] == code for c in cfg["companies"]):
        print("  companies.json 已有這個代號，略過")
    else:
        cfg["companies"].append({
            "code": code, "name": a.name, "nameEn": a.name_en, "ticker": a.ticker, "exchange": a.exchange,
            "sector": a.sector.strip(), "currency": a.currency.upper(), "frequency": a.frequency, "path": code + "/", "schema": "v1", "template": "generic",
            "title": f"{a.name}財報追蹤板", "description": f"{a.name}（{a.ticker}）每季營收、利潤率、EPS、現金流、財測與重要事件追蹤。",
            "price": None if a.no_price else dict({"yahoo": a.yahoo, "from": a.price_from, "currency": a.currency.upper()}, **({"twse": a.twse} if a.twse else {})),
            "primarySource": {"n": a.source_name, "url": a.source_url}, "tz": a.tz or ("US" if a.cik else "US"), "artifact": cfg["site"].get("artifact"), "enabled": bool(a.enable),
        })
        if a.cik:
            cfg["companies"][-1]["cik"] = a.cik
        with open(cfg_path, "w", encoding="utf8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2); f.write("\n")
        print("  companies.json 已加入設定" + ("（enabled:true）" if a.enable else "（enabled:false，填完資料再改成 true）"))
    if not a.no_price:
        print("  提醒：每一季要填 rd（財報公布日）；設定 price 後請手動觸發 GitHub Actions 的 prices-monthly 並等它完成，再抽查 3 個月股價")
    print("\n下一步：\n  1. 照 companies/%s/SOURCES.md 蒐集資料，填進 data/%s.json（取不到的欄位留 null）\n  2. python3 tools/validate.py %s\n  3. companies.json 把 enabled 改成 true → python3 tools/build.py\n  4. 用無頭瀏覽器檢查 /%s/，再 commit、push" % (code, code, code, code))


if __name__ == "__main__":
    main()
