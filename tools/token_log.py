"""排程的 token 用量紀錄（每週統計＋系統健康頁）。從 `python3 tools/daily.py tokens ...` 呼叫（排程的權限白名單已允許 daily.py）。

為什麼改成這樣（2026-11-20）：
  原本叫排程最後一步用 get_session 讀 external_metadata.usage，但那個欄位根本不存在，所以 11/12 起一筆都沒記到。
  現在有兩個來源：

  ┌─ ① 工作階段紀錄檔（自動，排程最後一步）──────────────────────────────┐
  │ ~/.claude/projects/*/<CLAUDE_CODE_SESSION_ID>.jsonl（主對話）         │
  │   ＋ <同名資料夾>/subagents/*.jsonl（子代理，例如讀網頁的 haiku）      │
  │ 每則回覆都附 usage，加總就是 token 數；`tokens auto <排程名>` 一行完成 │
  │ 費用：用過去「實際結算」的每百萬 token 單價估（exact=false）           │
  └──────────────────────────────────────────────────────────────────────┘
  ┌─ ② 執行結算（實際數字，事後補）──────────────────────────────────────┐
  │ list_events(session, kinds=["result"]) 的 modelUsage／total_cost_usd │
  │ 排程結束後才有，所以由下一次每週新聞排程用 `tokens fill` 列出要補的，  │
  │ 再 `tokens exact <session> --cost X ...` 把估計換成實際（exact=true）  │
  └──────────────────────────────────────────────────────────────────────┘

用法：
  python3 tools/daily.py tokens auto <排程名>    讀本工作階段紀錄檔，記一筆（排程最後一步用這個）
  python3 tools/daily.py tokens add <排程名> --session S --input N --cache-read N --cache-write N --output N --cost X [--exact] [--turns N] [--date D]
  python3 tools/daily.py tokens exact <session> --cost X [--input N --cache-read N --cache-write N --output N --turns N]
  python3 tools/daily.py tokens fill             列出還是估計值、需要用 list_events 補實際結算的 session
  python3 tools/daily.py tokens report           重寫 reports/token-usage.md（每週一張表）
  python3 tools/daily.py tokens week             印最近 7 天各排程用量
排程名固定：daily（每日檢查）、weekly-news（每週新聞）、trend（趨勢月報）、mcap（市值檢查）、daily-shadow（新版測試）
"""
import datetime, glob, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
P = os.path.join(ROOT, "data", "token-usage.json")
REPORT = os.path.join(ROOT, "reports", "token-usage.md")
NAMES = {"daily": "每日檢查", "weekly-news": "每週新聞", "trend": "趨勢月報", "mcap": "市值檢查", "daily-shadow": "新版測試"}
FIELDS = ("input", "cacheRead", "cacheWrite", "output")
# 沒有任何實際結算可參考時的保底單價（美元／每百萬「總 token」），只用來估；2026-11 實測 Opus 約 0.45、Haiku 約 0.03
FALLBACK_RATE = {"opus": 0.45, "sonnet": 0.3, "haiku": 0.03, "fable": 0.45}


def load():
    if os.path.exists(P):
        with open(P, encoding="utf8") as f:
            return json.load(f)
    return {"version": 2, "note": "排程 token 用量。exact=true 是執行結算（list_events）的實際數字；false 是工作階段紀錄檔加總、費用為估計。只用 python3 tools/daily.py tokens 改。", "runs": []}


def save(d):
    d["version"] = 2
    with open(P, "w", encoding="utf8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1); f.write("\n")


def total(r):
    return sum(int(r.get(k, 0)) for k in FIELDS)


def week_start(date):
    d = datetime.date.fromisoformat(date)
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


def fmt(n):
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"


def norm_session(s):
    """cse_X（環境變數）與 session_X（list_events 用）是同一個工作階段，統一存 session_X。"""
    s = (s or "").strip()
    return "session_" + s[4:] if s.startswith("cse_") else s


def family(model):
    m = (model or "").lower()
    for k in FALLBACK_RATE:
        if k in m:
            return k
    return "opus"


# ── ① 工作階段紀錄檔 ──────────────────────────────────────────────

def transcript_files(session_uuid, home=None):
    home = home or os.path.expanduser("~")
    main = glob.glob(os.path.join(home, ".claude", "projects", "*", session_uuid + ".jsonl"))
    subs = glob.glob(os.path.join(home, ".claude", "projects", "*", session_uuid, "subagents", "*.jsonl"))
    return main, subs


def sum_transcript(paths):
    """同一則回覆會分成好幾行寫入（串流），用 message.id 去重、每個欄位取最大值。回傳 {model: {欄位…, turns}}。"""
    msgs = {}
    for p in paths:
        with open(p, encoding="utf8") as f:
            for line in f:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if o.get("type") != "assistant":
                    continue
                m = o.get("message") or {}
                u = m.get("usage") or {}
                if not u:
                    continue
                key = (p, m.get("id") or o.get("uuid"))
                cur = msgs.setdefault(key, {"model": m.get("model") or "", "input": 0, "cacheRead": 0, "cacheWrite": 0, "output": 0})
                for src, dst in (("input_tokens", "input"), ("cache_read_input_tokens", "cacheRead"),
                                 ("cache_creation_input_tokens", "cacheWrite"), ("output_tokens", "output")):
                    cur[dst] = max(cur[dst], int(u.get(src) or 0))
    out = {}
    for v in msgs.values():
        if v["model"] in ("", "<synthetic>"):
            continue
        s = out.setdefault(v["model"], {"input": 0, "cacheRead": 0, "cacheWrite": 0, "output": 0, "turns": 0})
        for k in FIELDS:
            s[k] += v[k]
        s["turns"] += 1
    return out


def rates(runs):
    """從實際結算（exact）的紀錄算各模型每百萬 token 的單價；沒有就用保底單價。"""
    acc = {}
    for r in runs:
        if not r.get("exact"):
            continue
        for m, s in (r.get("models") or {}).items():
            if s.get("costUsd") is None:
                continue
            a = acc.setdefault(family(m), [0.0, 0])
            a[0] += s["costUsd"]; a[1] += total(s)
    R = dict(FALLBACK_RATE)
    for k, (usd, tok) in acc.items():
        if tok > 0:
            R[k] = usd / tok * 1e6
    return R


def estimate(models, runs):
    R = rates(runs)
    return round(sum(total(s) / 1e6 * R[family(m)] for m, s in models.items()), 2)


def put(d, run):
    d["runs"] = [r for r in d["runs"] if not (run["session"] and r.get("session") == run["session"])] + [run]
    d["runs"].sort(key=lambda r: (r["date"], r.get("routine", "")))


def auto(today, a, env=None, home=None):
    env = env if env is not None else os.environ
    if not a:
        sys.exit("用法：tokens auto <排程名>")
    name = a[0]
    uuid = env.get("CLAUDE_CODE_SESSION_ID", "")
    if not uuid:
        sys.exit("讀不到 CLAUDE_CODE_SESSION_ID：不是在 Claude Code 工作階段裡執行，無法自動記錄")
    main, subs = transcript_files(uuid, home)
    if not main:
        sys.exit(f"找不到工作階段紀錄檔（{uuid}.jsonl）")
    models = sum_transcript(main + subs)
    if not models:
        sys.exit("紀錄檔裡沒有任何用量")
    d = load()
    R = rates(d["runs"])
    for m, s in models.items():
        s["costUsd"] = round(total(s) / 1e6 * R[family(m)], 4)
    run = {"date": today.isoformat(), "routine": name, "session": norm_session(env.get("CLAUDE_CODE_REMOTE_SESSION_ID", "")) or uuid,
           "model": max(models, key=lambda m: total(models[m])),
           **{k: sum(s[k] for s in models.values()) for k in FIELDS},
           "turns": sum(s["turns"] for s in models.values()), "subagentFiles": len(subs),
           "costUsd": round(sum(s["costUsd"] for s in models.values()), 2), "exact": False, "src": "transcript",
           "models": models}
    put(d, run); save(d)
    print(f"記錄 {name} {run['date']}：總 {fmt(total(run))} tokens（讀快取 {fmt(run['cacheRead'])}、輸出 {fmt(run['output'])}、"
          f"{run['turns']} 次回覆、子代理 {len(subs)} 個）約 ${run['costUsd']}（估計，之後由每週排程換成實際結算）")
    return run


# ── ② 手動／實際結算 ──────────────────────────────────────────────

def opts(a):
    o, i = {}, 0
    while i < len(a):
        k = a[i].lstrip("-")
        if i + 1 < len(a) and not a[i + 1].startswith("--"):
            o[k] = a[i + 1]; i += 2
        else:
            o[k] = True; i += 1
    return o


def add(today, a):
    name, o = a[0], opts(a[1:])
    run = {"date": o.get("date") or today.isoformat(), "routine": name, "session": norm_session(o.get("session", "")),
           "model": o.get("model", ""), "input": int(o.get("input", 0)), "cacheRead": int(o.get("cache-read", 0)),
           "cacheWrite": int(o.get("cache-write", 0)), "output": int(o.get("output", 0)),
           "costUsd": round(float(o.get("cost", 0)), 2), "exact": bool(o.get("exact")), "src": "result" if o.get("exact") else "manual"}
    if o.get("turns"):
        run["turns"] = int(o["turns"])
    if o.get("note"):
        run["note"] = o["note"]
    d = load(); put(d, run); save(d)
    print(f"記錄 {name} {run['date']}：總 {fmt(total(run))} tokens 約 ${run['costUsd']}{'（實際結算）' if run['exact'] else ''}")


def exact(a):
    sid, o = norm_session(a[0]), opts(a[1:])
    d = load()
    hit = [r for r in d["runs"] if r.get("session") == sid]
    if not hit:
        sys.exit(f"沒有 {sid} 的紀錄")
    r = hit[0]
    r["costUsd"] = round(float(o["cost"]), 2)
    for src, dst in (("input", "input"), ("cache-read", "cacheRead"), ("cache-write", "cacheWrite"), ("output", "output"), ("turns", "turns")):
        if src in o:
            r[dst] = int(o[src])
    r["exact"], r["src"] = True, "result"
    save(d)
    print(f"{r['date']} {r['routine']} 換成實際結算：{fmt(total(r))} tokens、${r['costUsd']}")


def fill():
    rs = [r for r in load()["runs"] if not r.get("exact") and r.get("session", "").startswith("session_")]
    if not rs:
        print("沒有需要補實際結算的紀錄"); return
    print("用 list_events(session_id=<下列 id>, kinds=[\"result\"], limit=100) 讀「第一筆」result 的 total_cost_usd 與 modelUsage，"
          "再 tokens exact <id> --cost X --input … --cache-read … --cache-write … --output … --turns <num_turns>：")
    for r in rs[-7:]:
        print(f"  {r['session']}  {r['date']} {NAMES.get(r['routine'], r['routine'])}  目前估計 ${r['costUsd']}")


# ── 報表 ─────────────────────────────────────────────────────────

def weekly(runs):
    W = {}
    for r in runs:
        w = W.setdefault(week_start(r["date"]), {})
        s = w.setdefault(r["routine"], {"n": 0, "tot": 0, "cr": 0, "out": 0, "usd": 0.0, "est": 0})
        s["n"] += 1; s["tot"] += total(r); s["cr"] += r["cacheRead"]; s["out"] += r["output"]; s["usd"] += r["costUsd"]
        s["est"] += 0 if r.get("exact") else 1
    return W


def report():
    d = load()
    W = weekly(d["runs"])
    L = ["# 排程 token 用量（每週）", "",
         "> 由 `python3 tools/daily.py tokens report` 產生，**不要手改**。",
         "> 「總 token」＝ 輸入＋快取讀取＋快取寫入＋輸出（含子代理）；快取讀取佔 9 成以上是正常的（每個回合都重讀前面的內容），所以「回覆次數」才是省 token 的關鍵。",
         "> 費用是公開牌價換算（list），只用來比較，不代表實際扣款；標 * 的含估計值（還沒換成執行結算）。", ""]
    if not W:
        L.append("還沒有紀錄。")
    for ws in sorted(W, reverse=True):
        we = (datetime.date.fromisoformat(ws) + datetime.timedelta(days=6)).isoformat()
        tot = sum(s["tot"] for s in W[ws].values()); usd = sum(s["usd"] for s in W[ws].values())
        L += [f"## {ws} ～ {we}　合計 {fmt(tot)} tokens（約 ${usd:.2f}）", "",
              "| 排程 | 次數 | 總 token | 每次平均 | 快取讀取 | 輸出 | 約 USD |", "| --- | --- | --- | --- | --- | --- | --- |"]
        for k, s in sorted(W[ws].items(), key=lambda x: -x[1]["tot"]):
            L.append(f"| {NAMES.get(k, k)} | {s['n']} | {fmt(s['tot'])} | {fmt(s['tot'] // s['n'])} | {fmt(s['cr'])} | {fmt(s['out'])} | {s['usd']:.2f}{'*' if s['est'] else ''} |")
        L.append("")
    L += ["## 每次明細（最近 30 筆）", "", "| 日期 | 排程 | 總 token | 回覆次數 | 約 USD | 來源 |", "| --- | --- | --- | --- | --- | --- |"]
    for r in d["runs"][-30:][::-1]:
        L.append(f"| {r['date']} | {NAMES.get(r['routine'], r['routine'])} | {fmt(total(r))} | {r.get('turns', '—')} | {r['costUsd']:.2f} | {'執行結算' if r.get('exact') else '紀錄檔（估計）'} |")
    with open(REPORT, "w", encoding="utf8") as f:
        f.write("\n".join(L).rstrip() + "\n")
    print(f"已寫 reports/token-usage.md（{len(W)} 週）")


def week(today):
    since = (today - datetime.timedelta(days=7)).isoformat()
    rs = [r for r in load()["runs"] if r["date"] > since]
    if not rs:
        print("最近 7 天沒有紀錄"); return
    by = {}
    for r in rs:
        by.setdefault(r["routine"], []).append(r)
    for k, v in by.items():
        t = [total(r) for r in v]
        print(f"{NAMES.get(k, k)}：{len(v)} 次，合計 {fmt(sum(t))}，平均 {fmt(sum(t) // len(t))}，約 ${sum(r['costUsd'] for r in v):.2f}")


def main(today, a):
    if not a:
        sys.exit(__doc__)
    cmd = a[0]
    if cmd == "auto":
        auto(today, a[1:]); return report()
    if cmd == "add":
        add(today, a[1:]); return report()
    if cmd == "exact":
        exact(a[1:]); return report()
    if cmd == "fill":
        return fill()
    if cmd == "report":
        return report()
    if cmd == "week":
        return week(today)
    sys.exit(__doc__)
