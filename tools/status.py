"""系統健康狀態：把「哪些自動工作有跑、哪些資料過期」算成 data/status/latest.json（網站「系統健康」頁讀它）。

誰會呼叫：GitHub Actions 的 daily-prep（每日檢查一開始會手動觸發它）。不花 Claude token。
紅燈（red）才會開 issue（GitHub 寄信）；黃燈（yellow）只顯示在頁面上；灰燈（gray，不定期工作）不判紅黃、不進 alerts。

工作清單只有一份：data/status/jobs.json（Claude 維護；每個工作的 freq 頻率、method 做法、retry 重試、group 分類）。
  group=actions   排程的 GitHub workflow（在 main）→ 輸出 actions，依 kind 判斷多久沒成功算紅燈
  group=routine   Claude 排程（daily、news、trend、mcap）→ 輸出 routines
  group=check     不是 workflow 的檢查列（sec-feed-file：SEC 清單檔案時間；macro-data：總經資料內容）→ 輸出在 actions
  group=ondemand  不定期工作（ci、bs-fetch、rd-twse、sec-raw、tw-raw）→ 輸出 ondemand，只顯示最近一次執行，燈號固定 gray
每一列都帶 group／freq／method／retry。新增 workflow 或 Claude 排程要同時登記到 jobs.json，tools/tests/test_jobs.py 會擋。
GitHub API 查詢失敗時最多試 3 次（等 2、4 秒）。輸出 version 2（新增 ondemand、group／freq／method／retry）。
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
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "status", "latest.json")
TPE = dt.timedelta(hours=8)

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


def http_json(url, token):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "User-Agent": "status-bot"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def fetch_runs(repo, wf, token, branch=None, tries=3):
    """某個 workflow 最近 10 次已完成的執行。GitHub API 失敗最多試 tries 次（失敗後等 2、4 秒）；branch 只給不在 main 的 workflow（sec-raw、tw-raw）。"""
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{wf}/runs?status=completed&per_page=10" + (f"&branch={branch}" if branch else "")
    for i in range(1, tries + 1):
        try:
            return http_json(url, token).get("workflow_runs", [])
        except Exception:  # noqa: BLE001
            if i >= tries:
                raise
            time.sleep(2 * i)


def jobs_of(group):
    return [j for j in (jload("data", "status", "jobs.json", default={}) or {}).get("jobs", []) if j.get("group") == group]


def check_job(i):
    """group=check：不是 workflow 的檢查列（SEC 清單檔案時間、總經資料內容）；jobs.json 沒有就回「待確認」。"""
    return next((j for j in jobs_of("check") if j["id"] == i), {"group": "check", "label": i, "freq": "待確認", "method": "待確認", "retry": "待確認"})


def info(j):
    """每一列都帶的說明欄位（頻率、做法、重試、分類）。"""
    return {"group": j["group"], "freq": j["freq"], "method": j["method"], "retry": j["retry"]}


def actions_block(now, use_api):
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    rows = []
    for j in jobs_of("actions"):
        wf, kind = j["workflow"], j["kind"]
        row = {"id": wf[:-4], "label": j["label"], "kind": kind, "light": "yellow", "note": "未查詢（沒有 GitHub 權限）", **info(j)}
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
    rows.append(f13_row(jload("data", "13f", "latest.json", default=None), now))
    rows.append(capex_row(now))
    # SEC 清單用檔案時間判斷（由 daily-prep 寫入，比 workflow 紀錄更直接）。放在 sec-feed workflow 那列後面
    feed = jload("data", "sec-feed.json", default={}) or {}
    if feed.get("fetched"):
        ok = parse(feed["fetched"])
        light, note = eval_run_age("daily", ok, None, now)
        at = next((n + 1 for n, r in enumerate(rows) if r["id"] == "sec-feed"), 1)
        rows.insert(at, {"id": "sec-feed-file", "label": check_job("sec-feed-file")["label"], "kind": "daily", "light": light, "note": note, "lastOk": feed["fetched"], **info(check_job("sec-feed-file"))})
    return rows


def ondemand_block(now, use_api):
    """不定期工作：只查 GitHub 最近一次完成的執行。燈號固定 gray，不進 alerts。"""
    repo, token = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_TOKEN")
    rows = []
    for j in jobs_of("ondemand"):
        row = {"id": j["id"], "label": j["label"], "kind": None, "light": "gray", "note": "未查詢（沒有 GitHub 權限）", **info(j)}
        if use_api and repo and token:
            try:
                runs = fetch_runs(repo, j["workflow"], token, branch=j["branch"] if j.get("branch") not in (None, "main") else None)
                if runs:
                    c = runs[0]["conclusion"]
                    row["note"] = f"最近一次 {fmt_tpe(parse(runs[0]['updated_at']))} " + {"success": "成功", "failure": "失敗", "cancelled": "取消"}.get(c, f"結束（{c}）")
                    row["lastRun"] = parse(runs[0]["updated_at"]).strftime("%Y-%m-%dT%H:%MZ")
                    if j["id"] == "ci" and c == "failure":
                        row["note"] += "（PR 檢查，失敗不一定是問題）"
                else:
                    row["note"] = "查不到紀錄"
            except Exception as e:  # noqa: BLE001
                row["note"] = f"查詢失敗：{type(e).__name__}"
        rows.append(row)
    return rows


def f13_row(doc, now):
    """13F 大師持股：季資料，看「最新一季的季末離現在幾天」，不是檔案時間（一季沒新申報不算壞）。
    季末後最多 45 天公開，所以正常情況下最新一季的季末最多約 135 天前；超過 140 天黃燈、155 天紅燈（排程多半壞了）。"""
    cj = check_job("f13-data")
    row = {"id": "f13-data", "label": cj["label"], "kind": "monthly", "light": "yellow", "note": "還沒有資料檔（f13-quarterly 尚未抓過）", **info(cj)}
    ps = [m.get("period") for m in ((doc or {}).get("managers") or {}).values() if m.get("period")]
    if not ps:
        return row
    newest = max(ps)
    age = (now.date() - dt.date.fromisoformat(newest)).days
    row["lastOk"] = doc.get("fetched")
    if age > 155:
        row["light"], row["note"] = "red", f"最新一季是 {newest}（{age} 天前），超過 155 天沒有新一季"
    elif age > 140:
        row["light"], row["note"] = "yellow", f"最新一季是 {newest}（{age} 天前），超過 140 天沒有新一季"
    else:
        row["light"], row["note"] = "green", f"最新一季 {newest}（{age} 天前）"
    return row


def macro_row(doc, now):
    """總經儀表板的資料內容（不是 workflow 有沒有跑，而是抓回來的東西對不對）。
      紅：資料檔超過 10 天沒更新（排程每週兩次＋每天被叫醒一次，10 天沒動代表壞了），或一半以上的序列抓不到
      黃：有序列太久沒有新資料（來源停更、改代號）、有序列這次抓不到、有外部連結 404
    """
    cj = check_job("macro-data")
    row = {"id": "macro-data", "label": cj["label"], "kind": "weekly", "light": "yellow", "note": "還沒有資料檔", **info(cj)}
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


def capex_lagging(entities, now, days=21):
    """純判斷：entities = [(名稱, 季度列表)]；回傳 [「名稱 季別」…]。
    每家取最新一季「有營收」的季度；那一季資本支出是 None，而且財報公布日 rd 早於 now 超過 days 天 → 算落後。
    rd 讀不到（None）就無法判斷，不算落後（不用推算）。"""
    out = []
    for name, Q in entities:
        last = next((q for q in reversed(Q or []) if q.get("rev") is not None), None)
        if not last or last.get("capex") is not None or not last.get("rd"):
            continue
        try:
            rd = dt.datetime.strptime(last["rd"], "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        if (now - rd).days > days:
            out.append(f"{name} {last['q']}")
    return out


def capex_row(now):
    """AI 資本支出鏈（macro 頁）的資料是否跟上財報：只讀各公司財報檔，不抓網路。資料落後只會黃燈（不是系統壞掉），不開紅燈。"""
    cj = check_job("capex-chain")
    row = {"id": "capex-chain", "label": cj["label"], "kind": "daily", "light": "yellow", "note": "尚未計算", **info(cj)}
    try:
        import capex_chain as CH
        out = CH.load()
        ents = [x for x in out["buyerCards"] + [e for e in out["emergingBuyers"] if e.get("enabled")] + out["suppliers"]]
        pairs = []
        for x in ents:
            D = jload("data", x["code"] + ".json", default=None)
            if D:
                pairs.append((x["name"], D.get("quarters") or []))
        lag = capex_lagging(pairs, now)
        last_cq = next((r["cq"] for r in reversed(out["rows"]) if r["total"] is not None), "—")
    except Exception as e:  # noqa: BLE001
        row["note"] = f"資本支出鏈計算失敗：{type(e).__name__}: {e}"
        return row
    if lag:
        row["note"] = f"{len(lag)} 家最新一季還沒有資本支出（公布超過 21 天）：{'、'.join(lag[:3])}{'…' if len(lag) > 3 else ''}"
    else:
        row["light"], row["note"] = "green", f"{len(pairs)} 家都有最新一季資本支出；四大合計到 {last_cq}"
    return row


def routines_block(today):
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import daily
    J = {j["id"]: j for j in jobs_of("routine")}

    def row(i, light, note):
        j = J.get(i) or {"group": "routine", "label": i, "freq": "待確認", "method": "待確認", "retry": "待確認"}
        return {"id": i, "label": j["label"], "light": light, "note": note, **info(j)}
    rows = []
    cal = daily.load_cal()
    ms = daily.missed_days(cal.get("lastSuccess"), today)
    light = "red" if len(ms) >= 2 else ("yellow" if ms else "green")
    rows.append(row("daily", light, f"上次成功 {cal.get('lastSuccess') or '無紀錄'}" + (f"，缺跑 {len(ms)} 天" if ms else "")))
    last = (cal.get("fired") or {}).get("news")
    ref = last or "2026-11-22"   # 第一次預定日（同 daily_brief.NEWS_FIRST）
    days = (today - dt.date.fromisoformat(ref)).days
    rows.append(row("news", "red" if days > 9 else "green",
                    f"上次 {last}（{days} 天前）" if last else ("第一次預定 2026-11-22" if days < 0 else f"從第一次預定日起 {days} 天還沒跑過")))
    ym = today.strftime("%Y-%m")
    if today.day >= 5 and not os.path.exists(os.path.join(ROOT, "reports", "trend", f"{ym}_世界趨勢.md")):
        rows.append(row("trend", "red", f"{ym} 還沒產出"))
    else:
        rows.append(row("trend", "green", "本月已產出或還沒到時間"))
    # 市值檢查（Claude）：2026-11-27 ZL 決定停用，檢查改由 Actions 的 mcap-weekly 跑 mcap_check.py（有問題開 issue），固定灰燈
    rows.append(row("mcap", "gray", "已停用（2026-11-27）：改由 mcap-weekly 抓完自己檢查，有問題才開 issue"))
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
    act, rou, com, ond = actions_block(now, use_api), routines_block(today), companies_block(today), ondemand_block(now, use_api)
    tok_w, tok_r = tokens_block(today)
    alerts = []
    for r in act + rou:
        if r["light"] == "red":
            alerts.append(f"{r['label']}：{r['note']}")
    for r in com:
        if r["light"] == "red":
            alerts.append(f"{r['code']}：{'；'.join(r['problems'])}")
    return {"version": 2, "generated": now.strftime("%Y-%m-%dT%H:%MZ"), "actions": act, "routines": rou, "ondemand": ond, "companies": com,
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
