"""SEC 新申報清單（GitHub Actions 每天跑，不經過 Claude）。

讀 companies.json 每家有 `cik` 的公司，從 data.sec.gov/submissions 取最近的 8-K（含 Item 2.02＝財報新聞稿）與 10-Q／10-K，
寫入 data/sec-feed.json。每日排程用它判斷「公司是不是已經公布財報」，不必開網頁搜尋。
用法：python3 tools/sec_feed.py        （--check 只印結果、不寫檔）
"""
import datetime, json, os, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "Enterprise-Revenue-Dashboard research contact@example.com"  # SEC 要求 User-Agent 含聯絡方式；探測時用這個格式讀得到


def get(url):
    for i in range(2):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20) as r:
                return json.load(r)
        except Exception as e:  # noqa
            print("  重試", url, e)
            time.sleep(3 * (i + 1))
    return None


def main():
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    out = {"fetched": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"), "source": "SEC EDGAR submissions API", "companies": {}}
    bad = 0
    for c in cfg["companies"]:
        if not c.get("cik") or not c.get("enabled"):
            continue
        d = get(f"https://data.sec.gov/submissions/CIK{c['cik']}.json")
        if not d:
            print(c["code"], "讀取失敗"); bad += 1; continue
        r = d["filings"]["recent"]
        e = {"earnings8k": [], "periodic": []}
        for i, form in enumerate(r["form"]):
            items = r["items"][i] or ""
            acc = r["accessionNumber"][i]
            row = {"date": r["filingDate"][i], "acc": acc, "doc": r["primaryDocument"][i]}
            if form == "8-K" and "2.02" in items and len(e["earnings8k"]) < 3:
                e["earnings8k"].append(row)
            elif form in ("10-Q", "10-K") and len(e["periodic"]) < 3:
                e["periodic"].append(dict(row, form=form, period=r["reportDate"][i]))
            if len(e["earnings8k"]) >= 3 and len(e["periodic"]) >= 3:
                break
        out["companies"][c["code"]] = e
        print(c["code"], "8-K 2.02:", [x["date"] for x in e["earnings8k"]], "10-Q/K:", [x["date"] for x in e["periodic"]])
        time.sleep(0.3)
    if "--check" not in sys.argv:
        with open(os.path.join(ROOT, "data", "sec-feed.json"), "w", encoding="utf8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1); f.write("\n")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
