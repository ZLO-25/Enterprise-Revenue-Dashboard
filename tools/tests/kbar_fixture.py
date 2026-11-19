"""看盤頁／個股頁 K 棒的瀏覽器測試用「合成」資料（不是真實行情）。
只寫到你指定的臨時資料夾（絕不寫進 repo 的 data/）：
  <outdir>/data/futures/key.json                  測試用金鑰參數（salt 與 iter 都是假的，iter 很小所以快）
  <outdir>/data/futures/{ym,nq,tx}.enc.json      合成期貨（格式同 tools/futures_update.py）
  <outdir>/data/kbar/<代號>.enc.json／.hist.enc.json  合成個股（用 tools/kbar_update.write_files 產生，格式同真檔）
用法：python3 tools/tests/kbar_fixture.py <outdir>     （測試腳本 tools/tests/kbar_browser.mjs 會自己呼叫）
輸出最後一行是 JSON：{"password": …, "missing": […], "provisional": […], "short": […]}
合成資料的 source.n、check.note 都寫明「合成測試資料」。密碼只用在測試。"""
import base64, datetime as dt, hashlib, json, os, random, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import kbar_update as K          # noqa: E402
import futures_update as FU      # noqa: E402

PASSWORD = "fixture-only-pass-2026"
MISSING = ["rklb"]      # 故意不產生檔：清單那一列要顯示「—」與原因
PROVISIONAL = ["amd"]   # 暫定的最新一根
SHORT = ["spcx"]        # 上市不滿一年：沒有 hist 檔
PENDING = ["csco"]      # 有「待確認」的 K 棒
OLD_PASSWORD = "fixture-old-pass-2025"   # 模擬換過密碼：還沒用新密碼重新產生的檔
STALE_KEY = ["mu"]      # 近期檔還是舊密碼加密：只有那一列顯示原因，不能把整個網站上鎖
STALE_HIST = ["msft"]   # 歷史檔還是舊密碼加密：只顯示近期並標「歷史檔讀不到」，不能上鎖
FUT_NAMES = {"ym": ("小道瓊", "E-mini Dow ($5)", "CBOT YM", 44000, 0), "nq": ("小那指", "E-mini Nasdaq-100 ($20)", "CME NQ", 21000, 2),
             "tx": ("大台指", "TAIEX Futures (TX)", "TAIFEX TX", 23000, 0)}


def weekdays(start, end):
    d = start
    while d <= end:
        if d.weekday() < 5:
            yield d.isoformat()
        d += dt.timedelta(days=1)


def walk(seed, days, base, vol=0.016, with_volume=True):
    rnd = random.Random(int(hashlib.sha1(seed.encode()).hexdigest()[:8], 16))
    px, out = base, []
    for i, d in enumerate(days):
        o = px * (1 + rnd.gauss(0, vol / 3))
        c = o * (1 + rnd.gauss(0.0004, vol))
        h = max(o, c) * (1 + abs(rnd.gauss(0, vol / 2)))
        l = min(o, c) * (1 - abs(rnd.gauss(0, vol / 2)))
        v = int(rnd.uniform(0.6, 1.6) * 1e6) if with_volume and i % 37 else None
        out.append([d, round(o, 4), round(h, 4), round(l, 4), round(c, 4), v])
        px = c
    return out


def currency(yahoo):
    return "KRW" if yahoo.endswith(".KS") else "TWD" if yahoo.endswith((".TW", ".TWO")) else "EUR" if yahoo.endswith(".AS") else "USD"


def last_weekday(today):
    d = today
    while d.weekday() > 4:
        d -= dt.timedelta(days=1)
    return d


def build(outdir, today=None):
    today = today or dt.date.today()
    end = last_weekday(today - dt.timedelta(days=1))
    os.makedirs(os.path.join(outdir, "data", "futures"), exist_ok=True)
    os.makedirs(os.path.join(outdir, "data", "kbar"), exist_ok=True)
    json.dump({"salt": base64.b64encode(b"fixture-salt-0123").decode(), "iter": 1000, "kdf": "PBKDF2-SHA256", "cipher": "AES-256-GCM"},
              open(os.path.join(outdir, "data", "futures", "key.json"), "w"))
    fetched = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    # --- 期貨 ---
    for code, (name, en, ex, base, _dp) in FUT_NAMES.items():
        days = list(weekdays(end - dt.timedelta(days=900), end))
        bars = walk("fut" + code, days, base, 0.009)
        pay = {"code": code, "name": name, "nameEn": en, "exchange": ex, "fetchedAt": fetched, "firstDate": bars[0][0], "lastDate": bars[-1][0],
               "source": {"n": "合成測試資料（不是真實行情）", "url": "https://example.invalid/fixture"},
               "cols": ["date", "open", "high", "low", "close", "volume"], "bars": bars, "rolls": [{"date": bars[len(bars) // 2][0]}], "pending": []}
        if code == "tx":
            pay.update({"market": "TW", "session": "日盤 08:45–13:45", "months": ["202612"] * len(bars)})
        else:
            pay.update({"cross": {"ok": True, "compared": 250, "mismatch": 0, "mismatchInRollWindow": 0, "maxDiffPct": 0.02},
                        "check": {"n": "合成測試資料的核對來源", "url": "https://example.invalid/check"}})
        outer = {"code": code, "name": name, "lastDate": bars[-1][0], "firstDate": bars[0][0], "bars": len(bars), "pendingCount": 0, "fetchedAt": fetched,
                 **K.encrypt(pay, PASSWORD, outdir)}
        json.dump(outer, open(os.path.join(outdir, "data", "futures", code + ".enc.json"), "w"), separators=(",", ":"))
    # --- 個股 ---
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    cut = K.cut_date(today)
    made = []
    for i, c in enumerate(x for x in cfg["companies"] if x.get("enabled") and (x.get("price") or {}).get("yahoo")):
        code, ysym = c["code"], c["price"]["yahoo"]
        if code in MISSING:
            continue
        cur = currency(ysym)
        start = dt.date(today.year, 2, 2) if code in SHORT else dt.date(2023, 1, 2)
        base = {"KRW": 70000, "TWD": 900}.get(cur, 120 + 13 * i)
        bars = walk(code, list(weekdays(start, end)), base)
        pend = [{"date": end.isoformat(), "reason": "待確認：合成測試用的待確認示範（不是真實事件）"}] if code in PENDING else []
        meta = {"code": code, "name": c["name"], "exchange": {"USD": "NASDAQ", "TWD": "TWSE", "KRW": "KOSPI", "EUR": "AMS"}[cur], "yahoo": ysym, "currency": cur,
                "dp": 0 if cur == "KRW" else 2,
                "source": {"n": f"合成測試資料（模仿 Yahoo Finance {ysym} 日線，不是真實行情）", "url": "https://example.invalid/fixture"}}
        K.write_files(os.path.join(outdir, "data", "kbar"), meta, bars, PASSWORD, cut, provisional=code in PROVISIONAL, pending=pend,
                      check={"n": 10, "note": "合成測試資料：沒有與任何來源核對"}, fetched_at=fetched, key_root=outdir)
        kdir = os.path.join(outdir, "data", "kbar")
        if code in STALE_KEY:      # 近期檔換成舊密碼加密（外層不變）
            o = json.load(open(os.path.join(kdir, code + ".enc.json")))
            o.update(K.encrypt(K.decrypt(o, PASSWORD, outdir), OLD_PASSWORD, outdir))
            json.dump(o, open(os.path.join(kdir, code + ".enc.json"), "w"), separators=(",", ":"))
        if code in STALE_HIST:     # 歷史檔換成舊密碼加密（外層與 sha 不變）
            hp = os.path.join(kdir, code + ".hist.enc.json")
            o = json.load(open(hp))
            o.update(K.encrypt(K.decrypt(o, PASSWORD, outdir), OLD_PASSWORD, outdir))
            json.dump(o, open(hp, "w"), separators=(",", ":"))
        made.append(code)
    return {"password": PASSWORD, "missing": MISSING, "provisional": PROVISIONAL, "short": SHORT, "pending": PENDING,
            "staleKey": STALE_KEY, "staleHist": STALE_HIST, "made": made, "asOf": end.isoformat()}


if __name__ == "__main__":
    if len(sys.argv) < 2 or os.path.abspath(sys.argv[1]).startswith(os.path.join(ROOT, "data")):
        sys.exit("用法：python3 tools/tests/kbar_fixture.py <臨時資料夾>（不可在 repo 的 data/ 底下）")
    print(json.dumps(build(sys.argv[1])))
