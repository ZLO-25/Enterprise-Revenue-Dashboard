"""從證交所「個股日本益比、殖利率及股價淨值比」（BWIBBU）取得台股財報公布日（GitHub Actions 執行）。

BWIBBU 每天都有一欄「財報年／季」（例如 115/2＝民國 115 年第 2 季），代表證交所當天用哪一季的財報算本益比。
這一欄第一次換成某一季的那一天，就是那一季財報在證交所生效的日期（通常是公司公告財報當天或隔個交易日）。
這是官方資料，但會比公司實際公告日晚 0～數個交易日（偏保守：本益比不會提早用到還沒公布的 EPS）。
輸出：data/rd-sources/<代號>.twse.json（transitions＝每季第一次出現日；monthEnd＝每月最後交易日的官方本益比，之後對照用）
      並同步寫 data/rd-sources/<代號>.txt 的 T 列。
用法：python3 tools/twse_rd.py            # tsmc、delta
"""
import datetime as dt, json, os, re, sys, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = [("tsmc", "2330", "2015-01"), ("delta", "2308", "2019-01")]


def month_rows(stock, ym):
    url = f"https://www.twse.com.tw/exchangeReport/BWIBBU?response=json&date={ym.replace('-', '')}01&stockNo={stock}"
    err = None
    for i in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Enterprise-Revenue-Dashboard research"}), timeout=40) as r:
                j = json.loads(r.read())
            if j.get("stat") != "OK":
                return []
            out = []
            for row in j["data"]:
                m = re.match(r"(\d+)年(\d+)月(\d+)日", row[0])
                d = f"{int(m[1]) + 1911:04d}-{int(m[2]):02d}-{int(m[3]):02d}"
                out.append((d, row[3], row[5]))
            return out
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(6 * (i + 1))
    raise RuntimeError(f"{stock} {ym}: {err}")


def label(fq):
    y, q = fq.split("/")
    return f"{int(q)}Q{(int(y) + 1911) % 100:02d}"


def main():
    today = dt.date.today()
    for code, stock, start in TARGETS:
        y, m = map(int, start.split("-"))
        rows = []
        while (y, m) <= (today.year, today.month):
            rows += month_rows(stock, f"{y:04d}-{m:02d}")
            time.sleep(3.5)
            m += 1
            if m == 13:
                y, m = y + 1, 1
        seen, trans, prev = set(), [], None
        for d, pe, fq in rows:
            if fq != prev:
                if fq not in seen:
                    trans.append({"fq": fq, "q": label(fq), "first": d, "initial": prev is None})
                    seen.add(fq)
                prev = fq
        me = {}
        for d, pe, fq in rows:
            me[d[:7]] = {"m": d[:7], "d": d, "pe": None if pe in ("-", "") else float(pe.replace(",", ""))}
        out = {"source": "TWSE BWIBBU（個股日本益比…以個股月查詢）", "stock": stock, "fetched": today.isoformat(), "transitions": trans, "monthEnd": list(me.values())}
        json.dump(out, open(os.path.join(ROOT, "data", "rd-sources", code + ".twse.json"), "w", encoding="utf8"), ensure_ascii=False, indent=1)
        lines = [f"T {t['q']} {t['first']}" for t in trans if not t["initial"]]
        path = os.path.join(ROOT, "data", "rd-sources", code + ".txt")
        head = ("# 來源：證交所 BWIBBU「財報年／季」欄位第一次換成該季的日期（T＝證交所生效日，通常是公司公告日或其後一個交易日；偏保守）\n"
                "# 詳細資料：data/rd-sources/" + code + ".twse.json\n")
        open(path, "w", encoding="utf8").write(head + "\n".join(lines) + "\n")
        print(code, "月數", len(me), "季轉換", len(trans))


if __name__ == "__main__":
    main()
