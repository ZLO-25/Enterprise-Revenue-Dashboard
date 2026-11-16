#!/usr/bin/env python3
"""市值排名：每週抓一次，寫 data/mcap/latest.json（只在 GitHub Actions 跑；Claude 的容器連不到這些網站）

    python3 tools/mcap_fetch.py --check   只確認這週是否已抓過（寫 stale=true/false 到 GITHUB_OUTPUT）
    python3 tools/mcap_fetch.py           抓資料、核對、寫檔（失敗不覆蓋舊檔，exit 1 → 紅燈）

  三張榜（各取前 30）：
    global  全球公司   主來源 companiesmarketcap（CSV）      核對 Yahoo（yfinance，換成美元）
    us      美國公司   主來源 companiesmarketcap（美國 CSV）  核對 Yahoo
    assets  全球資產   主來源 companiesmarketcap 資產頁       核對：公司→Yahoo、黃金→WGC 存量×金價、加密貨幣→CoinGecko

  兩個來源差超過 config.tolerancePct（預設 10%）→ 該列標「待確認」，數字照主來源顯示，不自己改。
  只有一個來源（例如白銀，沒有官方地上存量）→ 標「單一來源」。
"""
import csv, datetime as dt, io, json, os, re, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, "data", "mcap")
LATEST = os.path.join(DIR, "latest.json")
TPE = dt.timezone(dt.timedelta(hours=8))
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
CMC = {
    "global": "https://companiesmarketcap.com/?download=csv",
    "us": "https://companiesmarketcap.com/usa/largest-companies-in-the-usa-by-market-cap/?download=csv",
    "assets": "https://companiesmarketcap.com/assets-by-market-cap/",
}
METALS = {"GOLD": "貴金屬", "SILVER": "貴金屬", "PLATINUM": "貴金屬", "PALLADIUM": "貴金屬", "COPPER": "金屬"}
CRYPTO = {"BTC": "bitcoin", "ETH": "ethereum", "USDT": "tether", "XRP": "ripple", "BNB": "binancecoin", "SOL": "solana", "USDC": "usd-coin"}


def now_tpe():
    return dt.datetime.now(TPE)


def last_saturday(d):
    return d - dt.timedelta(days=(d.weekday() - 5) % 7)


def check():
    stale = True
    if os.path.exists(LATEST):
        run = dt.date.fromisoformat(json.load(open(LATEST, encoding="utf8"))["runDate"])
        stale = run < last_saturday(now_tpe().date())
        print(f"上次抓取 {run}；本週六 {last_saturday(now_tpe().date())} → {'需要更新' if stale else '已是最新，不抓'}")
    if os.environ.get("GITHUB_OUTPUT"):
        open(os.environ["GITHUB_OUTPUT"], "a").write(f"stale={'true' if stale else 'false'}\n")


def get(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            return urllib.request.urlopen(req, timeout=40).read().decode("utf8", "replace")
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"{url}: {err}")


def num(s):
    try:
        return float(str(s).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None


def cmc_csv(url):
    rows = []
    for r in csv.DictReader(io.StringIO(get(url))):
        cap = num(r.get("marketcap"))
        if cap and r.get("Name"):
            rows.append({"name": r["Name"].strip(), "symbol": (r.get("Symbol") or "").strip(), "country": (r.get("country") or "").strip(),
                         "cap": cap, "price": num(r.get("price (USD)"))})
    rows.sort(key=lambda x: -x["cap"])
    if len(rows) < 30:
        raise RuntimeError(f"{url}: 只讀到 {len(rows)} 列（網站格式可能改了）")
    return rows


def cmc_assets(html):
    """解析資產頁：每列 <tr> 取 company-name、company-code、data-sort 數字（排名、市值、價格）"""
    rows = []
    for tr in re.split(r"<tr[\s>]", html)[1:]:
        nm = re.search(r'class="company-name"[^>]*>(.*?)</div>', tr, re.S)
        cd = re.search(r'class="company-code"[^>]*>(?:<[^>]+>)*\s*([^<]*?)\s*<', tr, re.S)
        sorts = [num(x) for x in re.findall(r'data-sort="([-0-9.eE]+)"', tr)]
        sorts = [x for x in sorts if x is not None]
        if not nm or len(sorts) < 2:
            continue
        caps = [x for x in sorts if x > 1e10]   # 市值一定 > 100 億美元（前幾百名），排名、價格都比這小
        if not caps:
            continue
        name = re.sub(r"<[^>]+>", "", nm.group(1)).strip()
        code = (cd.group(1).strip() if cd else "").upper()
        rows.append({"name": name, "symbol": code, "cap": caps[0]})
    rows.sort(key=lambda x: -x["cap"])
    if len(rows) < 30:
        raise RuntimeError(f"資產頁只讀到 {len(rows)} 列（網站格式可能改了）")
    return rows


# ---------- 核對來源 ----------
_fx = {}


def yahoo_caps(symbols):
    import yfinance as yf
    out = {}
    for s in symbols:
        try:
            fi = yf.Ticker(s).fast_info
            cap, cur = fi["marketCap"], fi["currency"]
            if not cap:
                continue
            if cur and cur.upper() != "USD":
                c, div = cur.upper(), 1.0
                if cur == "GBp":          # 倫敦股價以便士計
                    c, div = "GBP", 100.0
                if c not in _fx:
                    _fx[c] = yf.Ticker(f"{c}USD=X").fast_info.last_price
                cap = cap / div * _fx[c]
            out[s] = cap
        except Exception as e:  # noqa: BLE001
            print(f"  Yahoo {s} 讀不到：{e}")
    return out


def coingecko(ids):
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=" + ",".join(ids)
    return {r["id"]: r["market_cap"] for r in json.loads(get(url)) if r.get("market_cap")}


def gold_price():
    import yfinance as yf
    return yf.Ticker("GC=F").fast_info.last_price   # COMEX 黃金期貨近月，美元／金衡盎司


def metals(cfg, assets_all):
    """AI 相關金屬：每週收盤（近 1 年）＋ 1 週／4 週／52 週漲跌；市值有在 companiesmarketcap 資產頁才附上"""
    import yfinance as yf
    caps = {r["symbol"]: r["cap"] for r in (assets_all or [])}
    out = []
    for m in cfg["metals"]["items"]:
        row = {k: m[k] for k in ("code", "name", "unit", "why", "yahoo")}
        try:
            h = yf.Ticker(m["yahoo"]).history(period="1y", interval="1wk", auto_adjust=False)["Close"].dropna()
            pts = [[i.strftime("%Y-%m-%d"), round(float(v), 4)] for i, v in h.items()]
        except Exception as e:  # noqa: BLE001
            pts = []
            print(f"  Yahoo {m['yahoo']} 讀不到：{e}")
        if len(pts) >= 2:
            last = pts[-1][1]
            ch = lambda n: round((last / pts[-1 - n][1] - 1) * 100, 1) if len(pts) > n else None
            row.update(last=last, lastDate=pts[-1][0], w1=ch(1), w4=ch(4), w52=round((last / pts[0][1] - 1) * 100, 1), closes=pts)
        else:
            row.update(last=None, flag="待確認：Yahoo 這週讀不到價格")
        cap = caps.get(m["code"])
        row["cap"] = round(cap) if cap else None
        row["capSrc"] = "companiesmarketcap（估算：價格 × 地上存量）" if cap else "companiesmarketcap 資產頁沒有這項，只看價格"
        out.append(row)
    return out


SECTOR_ZH = {"Technology": "科技硬體", "Financial Services": "金融", "Healthcare": "醫療保健", "Consumer Cyclical": "非必需消費",
             "Consumer Defensive": "必需消費", "Communication Services": "通訊服務", "Energy": "能源", "Industrials": "工業",
             "Basic Materials": "原物料", "Real Estate": "房地產", "Utilities": "公用事業"}


def category(sector, industry):
    """Yahoo 的 sector／industry → 頁面的中文類別。科技再拆成 半導體／軟體／科技硬體，因為這個網站最關心這三塊。"""
    ind = industry or ""
    if "Semiconductor" in ind:
        return "半導體"
    if sector == "Technology" and ind.startswith("Software"):
        return "軟體"
    return SECTOR_ZH.get(sector)


def sectors(symbols):
    """產業分類很少變：存在 data/mcap/sectors.json，只查快取沒有的或超過 180 天的代號"""
    import yfinance as yf
    path = os.path.join(DIR, "sectors.json")
    cache = json.load(open(path, encoding="utf8")) if os.path.exists(path) else {}
    today = now_tpe().date()
    for sym in symbols:
        c = cache.get(sym)
        if c and c.get("sector") and (today - dt.date.fromisoformat(c["checked"])).days < 180:
            continue
        try:
            info = yf.Ticker(sym).info
            cache[sym] = {"sector": info.get("sector"), "industry": info.get("industry"), "checked": today.isoformat()}
        except Exception as e:  # noqa: BLE001
            print(f"  Yahoo 分類 {sym} 讀不到：{e}")
            cache.setdefault(sym, {"sector": None, "industry": None, "checked": today.isoformat()})
    open(path, "w", encoding="utf8").write(json.dumps(dict(sorted(cache.items())), ensure_ascii=False, indent=1) + "\n")
    return cache


def mark(row, chk_src, chk_cap, tol):
    row["chk"] = {"src": chk_src, "cap": round(chk_cap) if chk_cap else None}
    if not chk_cap:
        row["flag"] = f"待確認：{chk_src} 讀不到這一筆，只有一個來源"
        return
    diff = (chk_cap - row["cap"]) / row["cap"] * 100
    row["chk"]["diff"] = round(diff, 1)
    if abs(diff) > tol:
        row["flag"] = f"待確認：{chk_src} 為 {chk_cap/1e12:.2f} 兆美元，與主來源差 {diff:+.1f}%（股數或股別口徑可能不同）"


def main():
    cfg = json.load(open(os.path.join(DIR, "config.json"), encoding="utf8"))
    top, tol = cfg["top"], cfg["tolerancePct"]
    warn, assets_asof = [], None
    g = cmc_csv(CMC["global"])
    us = cmc_csv(CMC["us"])
    try:
        assets = cmc_assets(get(CMC["assets"]))
    except Exception as e:  # noqa: BLE001
        assets = None
        warn.append(f"待確認：全球資產榜讀不到 companiesmarketcap 資產頁（{e}），本週資產榜沿用上週")

    lists = {"global": g[:top], "us": us[:top]}
    for k in lists:
        for i, r in enumerate(lists[k]):
            r.update(rank=i + 1, type="公司", src="companiesmarketcap")
    syms = sorted({r["symbol"] for k in lists for r in lists[k] if r["symbol"]})
    yc = yahoo_caps(syms)
    for k in lists:
        for r in lists[k]:
            mark(r, "Yahoo", yc.get(r["symbol"]), tol)

    if assets:
        comp = {r["symbol"]: r for r in g}
        lst = assets[:top + 25]   # 多拿幾列：拿掉 ETF 後還要湊滿
        cg_ids = [CRYPTO[r["symbol"]] for r in lst if r["symbol"] in CRYPTO]
        cg = coingecko(cg_ids) if cg_ids else {}
        gp = gold_price()
        more = yahoo_caps([r["symbol"] for r in lst if r["symbol"] in comp and r["symbol"] not in yc])
        yc.update(more)
        for i, r in enumerate(lst):
            r.update(rank=i + 1, src="companiesmarketcap")
            s = r["symbol"]
            if s == "GOLD":
                r["type"] = "貴金屬"
                gs = cfg["goldStock"]
                own = gs["tonnes"] * 32150.7466 * gp if gp else None   # 1 公噸 = 32,150.7466 金衡盎司
                mark(r, f"WGC 地上存量 {gs['tonnes']:,} 公噸（{gs['label']}）× COMEX 金價", own, tol)
                r["est"] = "估算：價格 × 地上存量"
            elif s in METALS:
                r["type"] = METALS[s]
                r["est"] = "估算：價格 × 地上存量（companiesmarketcap 自行估計）"
                r["chk"] = None
                r["flag"] = "單一來源：沒有官方地上存量數字可核對"
            elif s in CRYPTO:
                r["type"] = "加密貨幣"
                mark(r, "CoinGecko", cg.get(CRYPTO[s]), tol)
            elif s in comp:
                r["type"] = "公司"
                r["country"] = comp[s]["country"]
                mark(r, "Yahoo", yc.get(s), tol)
            else:
                r["type"] = "ETF"     # 下面拿掉：ETF 持有的就是榜上的公司，放進來等於重複計算
        lst = [r for r in lst if r["type"] != "ETF"]
        for i, r in enumerate(lst):
            r["rank"] = i + 1
        lists["assets"] = lst[:top]
    else:
        old = json.load(open(LATEST, encoding="utf8")) if os.path.exists(LATEST) else {}
        if old.get("lists", {}).get("assets"):
            lists["assets"] = old["lists"]["assets"]
            assets_asof = old.get("runDate")
        else:
            lists["assets"] = []

    # 合理性檢查：沒過就不寫檔（舊檔保留），讓 Actions 紅燈
    for k in ("global", "us"):
        caps = [r["cap"] for r in lists[k]]
        assert len(caps) == top, f"{k} 只有 {len(caps)} 列"
        assert caps == sorted(caps, reverse=True), f"{k} 沒有依市值排序"
        assert 5e11 < caps[0] < 5e13, f"{k} 第一名市值 {caps[0]:.3g} 不合理"
    bad = sum(1 for k in ("global", "us") for r in lists[k] if r.get("flag"))
    if bad > top // 2:
        raise SystemExit(f"兩來源對不起來的列數太多（{bad} 列），可能有一邊壞掉，不寫檔")

    t = now_tpe()
    prev = json.load(open(LATEST, encoding="utf8")).get("runDate") if os.path.exists(LATEST) else None
    out = {
        "runDate": t.date().isoformat(),
        "fetchedAt": t.strftime("%Y-%m-%d %H:%M") + "（台北）",
        "catSource": "Yahoo Finance 的 sector／industry（科技再拆成半導體、軟體、科技硬體）",
        "basis": "抓取當下的最新報價；週六台北清晨抓 → 美股為週五收盤、加密貨幣為抓取當下",
        "sources": {"companiesmarketcap": "https://companiesmarketcap.com/", "Yahoo": "https://finance.yahoo.com/（yfinance）",
                    "CoinGecko": "https://www.coingecko.com/", "WGC": cfg["goldStock"]["url"]},
        "tolerancePct": tol,
        "prev": prev if prev != t.date().isoformat() else None,   # 上一次的檔名（history/<prev>.json），頁面用來算「比上週」
        "links": cfg["links"],
        "metals": metals(cfg, assets),
        "warnings": warn,
        "assetsAsOf": assets_asof,   # 不是 None ＝ 資產榜這週讀不到，沿用這一天的
        "lists": lists,
    }
    # 產業分類（只有公司有；貴金屬、加密貨幣用 type 當類別）
    co_syms = sorted({r["symbol"] for k in ("global", "us", "assets") for r in lists.get(k) or [] if r.get("type") == "公司" and r["symbol"]})
    sec = sectors(co_syms)
    for k in ("global", "us", "assets"):
        for r in lists.get(k) or []:
            if r.get("type") == "公司":
                c = sec.get(r["symbol"]) or {}
                r["cat"] = category(c.get("sector"), c.get("industry")) or "待確認"
                r["industry"] = c.get("industry")
                if r["cat"] == "待確認":
                    r["catNote"] = "待確認：Yahoo 沒有這家公司的產業分類"
            else:
                r["cat"] = r.get("type")
    for k in ("global", "us", "assets"):
        for r in lists.get(k) or []:
            r["cap"] = round(r["cap"])
            if r.get("price") is not None:
                r["price"] = round(r["price"], 2)
    os.makedirs(os.path.join(DIR, "history"), exist_ok=True)
    s = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    open(LATEST, "w", encoding="utf8").write(s + "\n")
    open(os.path.join(DIR, "history", out["runDate"] + ".json"), "w", encoding="utf8").write(s + "\n")
    print(f"寫入 latest.json：全球 {len(lists['global'])}、美國 {len(lists['us'])}、資產 {len(lists['assets'])} 列；待確認／單一來源 "
          f"{sum(1 for k in ('global','us','assets') for r in lists.get(k) or [] if r.get('flag'))} 列；警告 {len(warn)}")
    for w in warn:
        print("  ⚠", w)


if __name__ == "__main__":
    if "--check" in sys.argv:
        check()
    else:
        main()
