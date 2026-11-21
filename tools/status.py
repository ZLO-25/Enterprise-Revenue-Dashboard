"""系統健康狀態：把「哪些自動工作有跑、哪些資料過期」算成 data/status/latest.json（網站「系統健康」頁讀它）。

誰會呼叫：GitHub Actions 的 daily-prep（每日檢查一開始會手動觸發它）。不花 Claude token。
紅燈（red）才會開 issue（GitHub 寄信）；黃燈（yellow）只顯示在頁面上。
用法：
  python3 tools/status.py              算完寫 data/status/latest.json，印摘要；有紅燈也不報錯（issue 由 workflow 開）
  python3 tools/status.py --no-api     不查 GitHub 執行紀錄（本機測試用；沒有 GITHUB_TOKEN 也會自動略過）
  python3 tools/status.py --alerts     只印紅燈標題（一行一個，給 workflow 用）
  python3 tools/status.py --now 2026-11-18T01:00:00Z   指定現在時間（測試用）
"""
import datetime as dt
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "status", "latest.json")
TPE = dt.timedelta(hours=8)

# 自動工作：file＝workflow 檔名；kind＝多久該跑一次（daily／weekly／monthly）；label＝頁面上的中文名
WORKFLOWS = [
    ("daily-prep.yml", "daily", "每日準備（SEC、預估、股價、期貨）"),
    ("prices-daily.yml", "daily", "每日收盤價與本益比"),
    ("futures-daily.yml", "daily", "指數期貨 K 棒"),
    ("quant-prices.yml", "daily", "回測用股價"),
    ("mcap-weekly.yml", "weekly", "市值排名"),
    ("rates-weekly.yml", "weekly", "升降息資料"),
    ("macro-weekly.yml", "weekly", "總經儀表板資料"),
    ("prices-monthly.yml", "monthly", "每月股價"),
]
LIMIT_H = {"daily": 36, "weekly": 8.5 * 24, "monthly": 35 * 24}


def jload(*p, default=None):
    path = os.path.join(ROOT, *p)
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf8") as f:
        return json.load(f)


def parse(ts):
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def weekend_allow_h(now):
    """排程只在台北週二～六跑：週日、週一、週二（尚未跑之前）多給 48 小時，避免週末誤報。"""
    return 48 if (now + TPE).weekday() in (6, 0, 1) else 0


def eval_run_age(kind, last_ok, last_done, now):
    """依最後成功時間與最後一次完成的結果，判斷燈號。回傳 (燈, 說明)。"""
    if last_ok is None:
        return "yellow", "查不到成功紀錄"
    age_h = (now - last_ok).total_seconds() / 3600
    lim = LIMIT_H[kind] + (weekend_allow_h(now) if kind == "daily" else 0)
    if last_done and last_done["conclusion"] == "failure" and last_done["at"] > last_ok:
        return "red", f"最近一次失敗（{fmt_tpe(last_done['at'])}），最後成功在 {age_h:.0f} 小時前"
    if age_h > lim:
        return "red", f"已 {age_h:.0f} 小時沒有成功（上限 {lim:.0f}）"
    return "green", f"{age_h:.0f} 小時前成功"


def fmt_tpe(t):
    return (t + TPE).strftime("%m/%d %H:%M")


def fetch_runs(repo, wf, token):
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{wf}/runs?status=completed&per_page=10"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "status-bot"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("workflow_runs", [])


def actions_block(now, use_api):
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    rows = []
    for wf, kind, label in WORKFLOWS:
        row = {"id": wf[:-4], "label": label, "kind": kind, "light": "yellow", "note": "未查詢（沒有 GitHub 權限）"}
        if use_api and repo and token:
            try:
                runs = fetch_runs(repo, wf, token)
                ok = next((parse(r["updated_at"]) for r in runs if r["conclusion"] == "success"), None)
                done = {"conclusion": runs[0]["conclusion"], "at": parse(runs[0]["updated_at"])} if runs else None
                row["light"], row["note"] = eval_run_age(kind, ok, done, now)
                row["lastOk"] = ok.strftime("%Y-%m-%dT%H:%MZ") if ok else None
            except Exception as e:  # noqa: BLE001
                row["note"] = f"查詢失敗：{type(e).__name__}"
        rows.append(row)
    rows.append(macro_row(jload("data", "macro", "latest.json", default=None), now))
    # SEC 清單用檔案時間判斷（由 daily-prep 寫入，比 workflow 紀錄更直接）
    feed = jload("data", "sec-feed.json", default={}) or {}
    if feed.get("fetched"):
        ok = parse(feed["fetched"])
        light, note = eval_run_age("daily", ok, None, now)
        rows.insert(1, {"id": "sec-feed", "label": "SEC 新申報清單（檔案時間）", "kind": "daily", "light": light, "note": note, "lastOk": feed["fetched"]})
    return rows


def macro_row(doc, now):
    """總經儀表板的資料內容（不是 workflow 有沒有跑，而是抓回來的東西對不對）。
      紅：資料檔超過 10 天沒更新（排程每週兩次＋每天被叫醒一次，10 天沒動代表壞了），或一半以上的序列抓不到
      黃：有序列太久沒有新資料（來源停更、改代號）、有序列這次抓不到、有外部連結 404
    """
    row = {"id": "macro-data", "label": "總經資料（內容檢查：停更、抓不到、連結失效）", "kind": "weekly", "light": "yellow", "note": "還沒有資料檔"}
    if not doc or not doc.get("updated"):
        return row
    at = dt.datetime.strptime(doc["updated"], "%Y-%m-%d %H:%M UTC").replace(tzinfo=dt.timezone.utc)
    age_d = (now - at).total_seconds() / 86400
    row["lastOk"] = at.strftime("%Y-%m-%dT%H:%MZ")
    stale = (doc.get("health") or {}).get("stale") or []
    failed = [u for u in doc.get("unavailable") or []]
    dead = (doc.get("links") or {}).get("dead") or []
    total = len(doc.get("series") or {}) or 1
    if age_d > 10:
        row["light"], row["note"] = "red", f"資料檔已 {age_d:.0f} 天沒有更新"
    elif len(failed) > total / 2:
        row["light"], row["note"] = "red", f"{len(failed)} 條序列抓不到（共 {total} 條），來源可能改了格式"
    elif stale or failed or dead:
        parts = ([f"{len(stale)} 條太久沒有新資料（{'、'.join(x['name'] for x in stale[:3])}{'…' if len(stale) > 3 else ''}）"] if stale else []) + \
                ([f"{len(failed)} 條這次抓不到"] if failed else []) + ([f"{len(dead)} 個外部連結 404"] if dead else [])
        row["light"], row["note"] = "yellow", "；".join(parts) + "。細節在總經儀表板頁尾"
    else:
        row["light"], row["note"] = "green", f"{age_d:.0f} 天前更新，{total} 條序列都正常"
    return row


def routines_block(today):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import daily
    rows = []
    cal = daily.load_cal()
    ms = daily.missed_days(cal.get("lastSuccess"), today)
    light = "red" if len(ms) >= 2 else ("yellow" if ms else "green")
    rows.append({"id": "daily", "label": "每日檢查（Claude 排程）", "light": light,
                 "note": f"上次成功 {cal.get('lastSuccess') or '無紀錄'}" + (f"，缺跑 {len(ms)} 天" if ms else "")})
    last = (cal.get("fired") or {}).get("news")
    ref = last or "2026-11-22"   # 第一次預定日（同 daily_brief.NEWS_FIRST）
    days = (today - dt.date.fromisoformat(ref)).days
    rows.append({"id": "news", "label": "每週新聞（週日 06:00）", "light": "red" if days > 9 else "green",
                 "note": f"上次 {last}（{days} 天前）" if last else ("第一次預定 2026-11-22" if days < 0 else f"從第一次預定日起 {days} 天還沒跑過")})
    ym = today.strftime("%Y-%m")
    if today.day >= 5 and not os.path.exists(os.path.join(ROOT, "reports", "trend", f"{ym}_世界趨勢.md")):
        rows.append({"id": "trend", "label": "世界趨勢月報", "light": "red", "note": f"{ym} 還沒產出"})
    else:
        rows.append({"id": "trend", "label": "世界趨勢月報", "light": "green", "note": "本月已產出或還沒到時間"})
    return rows


def companies_block(today):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import daily
    import pending
    PEND = pending.counts(pending.scan())
    cal = daily.load_cal()
    rows = []
    for c in daily.enabled():
        code = c["code"]
        D = jload("data", code + ".json") or {}
        Q = D.get("quarters") or []
        st = cal["companies"].get(code, {"state": "waiting"})
        evs = sorted(D.get("events", []), key=lambda e: e["date"])
        nxt = next((e for e in evs if e["date"] >= today.isoformat()), None)
        X = ((jload("data", "daily", code + ".json", default={}) or {}).get("calc") or {}).get("latest") or {}
        mon = None
        if c.get("price"):
            P = jload("data", "prices", code + ".json", default=None)
            mon = P["monthly"][-1]["m"] if P and P.get("monthly") else None
        problems, light = [], "green"
        if st["state"] == "stuck":
            problems.append("卡住（連續 5 次失敗）"); light = "red"
        # 已確定的公布日過了 3 天還沒進入快報
        sure_due = [e for e in evs if not e.get("est") and e["date"] < (today - dt.timedelta(days=3)).isoformat()]
        if sure_due and st["state"] == "waiting":
            problems.append(f"公布日 {sure_due[0]['date']} 已過 3 天還沒更新"); light = "red"
        if c.get("price") and X.get("d"):
            lim = 12 if c["price"]["yahoo"].endswith((".TW", ".TWO", ".KS")) else 4
            late = (today - dt.date.fromisoformat(X["d"])).days
            if late > lim:
                problems.append(f"收盤價落後 {late} 天"); light = "red"
        pc = PEND.get(code)
        rows.append({"code": code, "name": c.get("name") or c.get("title") or code, "quarter": Q[-1]["q"] if Q else None, "stage": st["state"],
                     "close": X.get("d"), "priceMonth": mon, "next": ({"d": nxt["date"], "t": nxt["t"][:24], "est": bool(nxt.get("est"))} if nxt else None),
                     "pending": pc, "light": light, "problems": problems})
    return rows


def signals_block(today):
    S = jload("data", "daily", "_signals.json", default={"events": []}) or {"events": []}
    cut = (today - dt.timedelta(days=30)).isoformat()
    return [e for e in S.get("events", []) if e["d"] >= cut][-40:]


def tokens_block(today):
    """最近 4 週：每週合計（token、費用）＋每次明細（含是否為執行結算）。資料只來自 data/token-usage.json。"""
    T = jload("data", "token-usage.json", default={"runs": []}) or {"runs": []}
    cut = (today - dt.timedelta(days=28)).isoformat()
    names = {"daily": "每日檢查", "weekly-news": "每週新聞", "trend": "趨勢月報", "mcap": "市值檢查", "daily-shadow": "新版測試"}
    weeks, runs = {}, []
    for r in T["runs"]:
        if r["date"] < cut:
            continue
        n = r["input"] + r["cacheRead"] + r["cacheWrite"] + r["output"]
        d = dt.date.fromisoformat(r["date"])
        w = (d - dt.timedelta(days=d.weekday())).isoformat()
        s = weeks.setdefault(w, {"week": w, "tokens": 0, "usd": 0.0, "runs": 0})
        s["tokens"] += n; s["usd"] = round(s["usd"] + r.get("costUsd", 0), 2); s["runs"] += 1
        runs.append({"date": r["date"], "routine": names.get(r["routine"], r["routine"]), "tokens": n, "usd": r.get("costUsd", 0),
                     "turns": r.get("turns"), "exact": bool(r.get("exact"))})
    return [weeks[w] for w in sorted(weeks)], runs[::-1][:30]


def build(now, use_api=True):
    today = (now + TPE).date()
    act, rou, com = actions_block(now, use_api), routines_block(today), companies_block(today)
    tok_w, tok_r = tokens_block(today)
    alerts = []
    for r in act + rou:
        if r["light"] == "red":
            alerts.append(f"{r['label']}：{r['note']}")
    for r in com:
        if r["light"] == "red":
            alerts.append(f"{r['code']}：{'；'.join(r['problems'])}")
    return {"version": 1, "generated": now.strftime("%Y-%m-%dT%H:%MZ"), "actions": act, "routines": rou, "companies": com,
            "signals": signals_block(today), "tokens": tok_w, "tokenRuns": tok_r, "alerts": alerts}


def main():
    a = sys.argv[1:]
    now = parse(a[a.index("--now") + 1]) if "--now" in a else dt.datetime.now(dt.timezone.utc)
    S = build(now, "--no-api" not in a)
    if "--alerts" in a:
        print("\n".join(S["alerts"]))
        return 0
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf8") as f:
        json.dump(S, f, ensure_ascii=False, indent=1); f.write("\n")
    print(f"狀態已寫入 data/status/latest.json（{S['generated']}）；紅燈 {len(S['alerts'])} 個")
    for x in S["alerts"]:
        print("  紅燈：" + x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
