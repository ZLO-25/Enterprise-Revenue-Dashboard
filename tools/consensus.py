"""市場預期（分析師共識）「事前拍照」：公布前 14 天起，每天存一張當季預估營收與 EPS 的快照（GitHub Actions 跑，不經過 Claude）。

為什麼要拍照：財報一公布，資料網站上的「當季預估」就會被新數字蓋掉，事後補不回來，所以只能在公布前存下來。
規則：
  - 只拍「財報」類公布日（events 的 t 含「財報」或「業績」，不含「月營收」「產量」）前 14 天內；台北時間今天 ≤ 公布日才拍
    （美股盤後公布、台北隔天早上才會看到，台股／韓股在台北下午公布，早上跑還是公布前）。
  - 目標季度 ＝ data 最後一季的下一季。已公布但資料還沒更新（SEC 清單有更新的 8-K 2.02）→ 不拍，避免拍到已滾到下一季的預估。
  - 舊的快照永遠不改、不補、不用今天的預估填過去；同一天重跑只覆蓋當天那張。
  - 幣別和 companies.json 不同 → 不存，寫 why。
輸出 data/consensus/<代號>.json：{"code","snapshots":[{date,period,epsAvg,epsLow,epsHigh,epsN,epsBasis,revAvg,revLow,revHigh,revN,cur}]}
epsBasis：yfinance 的 methodology（normalized＝調整後／非 GAAP，gaap＝GAAP）。營收單位是原幣「元」（顯示時換算成公司單位）。
用法：python3 tools/consensus.py [--dry]    需要 pip install yfinance
"""
import datetime, json, os, re, sys, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOW = 14


def today():
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).date()


def jload(*p, default=None):
    path = os.path.join(ROOT, *p)
    return json.load(open(path, encoding="utf8")) if os.path.exists(path) else default


def next_q(q):
    n, y = int(q[0]), int(q[2:])
    return f"{n + 1}Q{y:02d}" if n < 4 else f"1Q{(y + 1):02d}"


def earnings_event(D, t):
    for e in sorted(D.get("events", []), key=lambda e: e["date"]):
        if re.search("財報|業績", e["t"]) and not re.search("月營收|產量|交車", e["t"]) and e["date"] >= t.isoformat():
            return e
    return None


def num(v):
    try:
        v = float(v)
        return None if v != v else v
    except Exception:  # noqa
        return None


def snap(c, target, t):
    import yfinance as yf
    tk = yf.Ticker(c["price"]["yahoo"])
    ee, re_ = tk.earnings_estimate, tk.revenue_estimate
    if "0q" not in ee.index or "0q" not in re_.index:
        return None, "Yahoo 沒有當季（0q）預估"
    e, r = ee.loc["0q"], re_.loc["0q"]
    cur = str(e.get("currency") or r.get("currency") or "")
    if cur and cur != c["currency"]:
        return None, f"Yahoo 幣別 {cur} 與公司幣別 {c['currency']} 不同"
    return {"date": t.isoformat(), "period": target,
            "epsAvg": num(e.get("avg")), "epsLow": num(e.get("low")), "epsHigh": num(e.get("high")),
            "epsN": int(e["numberOfAnalysts"]) if num(e.get("numberOfAnalysts")) is not None else None, "epsBasis": str(e.get("methodology") or "") or None,
            "revAvg": num(r.get("avg")), "revLow": num(r.get("low")), "revHigh": num(r.get("high")),
            "revN": int(r["numberOfAnalysts"]) if num(r.get("numberOfAnalysts")) is not None else None, "cur": cur or c["currency"]}, None


def main():
    dry = "--dry" in sys.argv
    t = today()
    cfg = jload("companies.json")
    feed = jload("data", "sec-feed.json", default={"companies": {}})
    bad = 0
    for c in cfg["companies"]:
        if not c.get("enabled") or not c.get("price"):
            continue
        D = jload("data", c["code"] + ".json")
        if not D.get("quarters"):
            continue
        ev = earnings_event(D, t)
        if not ev:
            continue
        days = (datetime.date.fromisoformat(ev["date"]) - t).days
        if days > WINDOW:
            continue
        last = D["quarters"][-1]
        f = feed["companies"].get(c["code"])
        if f and f["earnings8k"] and last.get("rd") and f["earnings8k"][0]["date"] > last["rd"]:
            print(c["code"], "已公布（SEC 有新財報 8-K）→ 不拍")
            continue
        target = next_q(last["q"])
        s, why = None, None
        for i in range(3):
            try:
                s, why = snap(c, target, t)
                break
            except Exception as ex:  # noqa
                why = repr(ex)[:120]
                time.sleep(5 * (i + 1))
        if not s or (s["epsAvg"] is None and s["revAvg"] is None):
            print(c["code"], "拍照失敗：", why or "兩個預估都空")
            bad += 1
            continue
        path = os.path.join(ROOT, "data", "consensus", c["code"] + ".json")
        cur = jload("data", "consensus", c["code"] + ".json", default={"code": c["code"], "snapshots": []})
        cur["snapshots"] = [x for x in cur["snapshots"] if not (x["date"] == s["date"] and x["period"] == s["period"])] + [s]
        cur["snapshots"].sort(key=lambda x: (x["period"], x["date"]))
        print(c["code"], target, f"公布日 {ev['date']}（{days} 天後）", "EPS", s["epsAvg"], s["epsBasis"], "營收", s["revAvg"])
        if not dry:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf8") as fh:
                json.dump(cur, fh, ensure_ascii=False, indent=1); fh.write("\n")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
