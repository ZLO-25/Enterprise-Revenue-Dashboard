"""排程的 token 用量紀錄（每週統計）。從 `python3 tools/daily.py tokens ...` 呼叫（排程的權限白名單已允許 daily.py）。

為什麼這樣記：排程的 session 結束前，用 get_session（不帶 session_id）可以讀到「到目前為止的累計用量」
（external_metadata.usage：input_tokens、cache_read_tokens、cache_write_tokens、output_tokens、cost_usd）。
每個排程在最後一步把這幾個數字記進 data/token-usage.json，一週的統計就從這個檔算出來。
數字是「結束前一刻」的累計，會比實際少最後一兩個回合（回報與 push），誤差很小；這是估計值，不是帳單。

用法：
  python3 tools/daily.py tokens add <排程名> --session S --model M --input N --cache-read N --cache-write N --output N --cost X
  python3 tools/daily.py tokens report        重寫 reports/token-usage.md（每週一張表）
  python3 tools/daily.py tokens week          印最近 7 天各排程用量
排程名固定：daily（每日檢查）、weekly-news（每週新聞）、trend（趨勢月報）、mcap（市值檢查）、daily-shadow（新版測試）
"""
import datetime, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "data", "token-usage.json")
REPORT = os.path.join(ROOT, "reports", "token-usage.md")
NAMES = {"daily": "每日檢查", "weekly-news": "每週新聞", "trend": "趨勢月報", "mcap": "市值檢查", "daily-shadow": "新版測試"}


def load():
    if os.path.exists(P):
        with open(P, encoding="utf8") as f:
            return json.load(f)
    return {"version": 1, "note": "排程 token 用量（估計值，結束前一刻的累計）。只用 python3 tools/daily.py tokens add 改。", "runs": []}


def save(d):
    with open(P, "w", encoding="utf8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1); f.write("\n")


def total(r):
    return r["input"] + r["cacheRead"] + r["cacheWrite"] + r["output"]


def week_start(date):
    d = datetime.date.fromisoformat(date)
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


def fmt(n):
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"


def add(today, a):
    name = a[0]
    o = {}
    i = 1
    while i < len(a):
        o[a[i].lstrip("-")] = a[i + 1]; i += 2
    run = {"date": today.isoformat(), "routine": name, "session": o.get("session", ""), "model": o.get("model", ""),
           "input": int(o.get("input", 0)), "cacheRead": int(o.get("cache-read", 0)),
           "cacheWrite": int(o.get("cache-write", 0)), "output": int(o.get("output", 0)),
           "costUsd": round(float(o.get("cost", 0)), 2)}
    d = load()
    d["runs"] = [r for r in d["runs"] if not (run["session"] and r["session"] == run["session"])] + [run]
    save(d)
    print(f"記錄 {name} {run['date']}：總 {fmt(total(run))} tokens（讀快取 {fmt(run['cacheRead'])}、輸出 {fmt(run['output'])}）約 ${run['costUsd']}")


def weekly(runs):
    W = {}
    for r in runs:
        w = W.setdefault(week_start(r["date"]), {})
        s = w.setdefault(r["routine"], {"n": 0, "tot": 0, "cr": 0, "out": 0, "usd": 0.0})
        s["n"] += 1; s["tot"] += total(r); s["cr"] += r["cacheRead"]; s["out"] += r["output"]; s["usd"] += r["costUsd"]
    return W


def report():
    d = load()
    W = weekly(d["runs"])
    L = ["# 排程 token 用量（每週）", "",
         "> 由 `python3 tools/daily.py tokens report` 產生，**不要手改**。數字是各排程結束前一刻的累計（估計值，比實際少最後一兩個回合，不是帳單）。",
         "> 「總 token」＝ 輸入＋快取讀取＋快取寫入＋輸出；快取讀取佔 9 成以上是正常的（每個回合都重讀前面的內容），所以「步驟數」才是省 token 的關鍵。",
         "> 費用是按公開牌價換算，只用來比較，不代表實際扣款。", ""]
    if not W:
        L.append("還沒有紀錄。")
    for ws in sorted(W, reverse=True):
        we = (datetime.date.fromisoformat(ws) + datetime.timedelta(days=6)).isoformat()
        tot = sum(s["tot"] for s in W[ws].values()); usd = sum(s["usd"] for s in W[ws].values())
        L += [f"## {ws} ～ {we}　合計 {fmt(tot)} tokens（約 ${usd:.2f}）", "",
              "| 排程 | 次數 | 總 token | 每次平均 | 快取讀取 | 輸出 | 約 USD |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for k, s in sorted(W[ws].items(), key=lambda x: -x[1]["tot"]):
            L.append(f"| {NAMES.get(k, k)} | {s['n']} | {fmt(s['tot'])} | {fmt(s['tot'] // s['n'])} | {fmt(s['cr'])} | {fmt(s['out'])} | {s['usd']:.2f} |")
        L.append("")
    with open(REPORT, "w", encoding="utf8") as f:
        f.write("\n".join(L).rstrip() + "\n")
    print(f"已寫 reports/token-usage.md（{len(W)} 週）")


def week(today):
    since = (today - datetime.timedelta(days=7)).isoformat()
    rs = [r for r in load()["runs"] if r["date"] > since]
    if not rs:
        print("最近 7 天沒有紀錄"); return
    for k, s in sorted(weekly(rs).get(week_start(rs[-1]["date"]), {}).items()):
        pass
    by = {}
    for r in rs:
        by.setdefault(r["routine"], []).append(total(r))
    for k, v in by.items():
        print(f"{NAMES.get(k, k)}：{len(v)} 次，合計 {fmt(sum(v))}，平均 {fmt(sum(v) // len(v))}")


def main(today, a):
    if not a:
        sys.exit(__doc__)
    if a[0] == "add":
        return add(today, a[1:])
    if a[0] == "report":
        return report()
    if a[0] == "week":
        return week(today)
    sys.exit(__doc__)
