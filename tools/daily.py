"""每日排程的「今天要做什麼」清單與狀態檔（data/calendar.json）。很便宜：不開網頁、不讀財報。

狀態（每家公司一個，記在 data/calendar.json）：
  waiting    等待公布（沒有進行中的事）
  flash      快報完成（數字、書面財測已上線，頁面標「初版」）→ 下一步：補完
  completed  補完完成（電話會議重點、一頁總結已定稿）→ 下一步：核對（等 10-Q／年報，或對 XBRL）
  stuck      連續 5 次沒成功：停止自動重試，首頁標「待更新」，每日回報置頂，等使用者決定
  （核對完成 → `set CODE verified` 會直接回到 waiting）

用法：
  python3 tools/daily.py                      今天的工作清單（含缺跑日期、7 天內公布日、進行中、卡住）
  python3 tools/daily.py set CODE flash --target 3Q27 [--note ...]
  python3 tools/daily.py set CODE completed|verified|waiting|stuck
  python3 tools/daily.py try CODE [--note 原因]   記一次失敗重試（滿 5 次自動轉 stuck）
  python3 tools/daily.py done                  整個排程成功跑完 → 記 lastSuccess ＝ 今天（台北）
  --today YYYY-MM-DD 可指定日期（測試用）
公布日一律從 data/<代號>.json 的 events[] 讀（唯一來源）。events 裡「早於今天」的項目還在，就代表還沒處理。
"""
import datetime, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAL = os.path.join(ROOT, "data", "calendar.json")
STATES = ("waiting", "flash", "completed", "stuck")
MAX_TRIES = 5
RUN_WEEKDAYS = (1, 2, 3, 4, 5)  # 週二～週六（Monday=0）


def taipei_today():
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)).date()


def jload(*p, default=None):
    path = os.path.join(ROOT, *p)
    if not os.path.exists(path):
        return default
    return json.load(open(path, encoding="utf8"))


def load_cal():
    return jload("data", "calendar.json", default={"version": 1, "lastRun": None, "lastSuccess": None, "companies": {}})


def save_cal(c):
    with open(CAL, "w", encoding="utf8") as f:
        json.dump(c, f, ensure_ascii=False, indent=1)
        f.write("\n")


def enabled():
    return [c for c in jload("companies.json")["companies"] if c.get("enabled")]


def missed_days(last_success, today):
    """上次成功之後、今天之前，應該跑卻沒跑的日子（週二～六）。"""
    if not last_success:
        return []
    d = datetime.date.fromisoformat(last_success) + datetime.timedelta(days=1)
    out = []
    while d < today:
        if d.weekday() in RUN_WEEKDAYS:
            out.append(d.isoformat())
        d += datetime.timedelta(days=1)
    return out


def status(today):
    cal = load_cal()
    feed = jload("data", "sec-feed.json", default={"companies": {}})
    print(f"【排程清單 {today}（台北）】")
    ms = missed_days(cal.get("lastSuccess"), today)
    print(f"上次成功：{cal.get('lastSuccess') or '無紀錄'}　缺跑：{('、'.join(ms) + '（要一起補，回報寫明補了哪幾天）') if ms else '無'}")
    if cal.get("lastSuccess"):
        gap = (today - datetime.date.fromisoformat(cal["lastSuccess"])).days
        print(f"新聞檢查範圍：過去 {max(gap, 1)} 天" + ("＋過去一週回顧（週二班）" if today.weekday() == 1 else ""))
    todo, prog, soon, stuck = [], [], [], []
    for c in enabled():
        code = c["code"]
        D = jload("data", code + ".json")
        st = cal["companies"].get(code, {"state": "waiting", "tries": 0})
        last_q = D["quarters"][-1]["q"] if D.get("quarters") else None
        last_rd = D["quarters"][-1].get("rd") if D.get("quarters") else None
        evs = sorted(D.get("events", []), key=lambda e: e["date"])
        # 1) 進行中的事
        if st["state"] == "stuck":
            stuck.append(f"  {code}：{st.get('target')} 卡住（{st.get('note') or ''}）→ 等使用者決定")
        elif st["state"] in ("flash", "completed"):
            nxt = "補完（電話會議重點、一頁總結定稿）" if st["state"] == "flash" else "核對（10-Q／年報、XBRL，解除待確認）"
            prog.append(f"  {code}：{st.get('target')} 已{'快報' if st['state'] == 'flash' else '補完'} → 今天做：{nxt}；第 {st.get('tries', 0) + 1} 次")
        # 2) SEC 新申報提示（只對美股）
        hint = ""
        f = feed["companies"].get(code)
        if f and f["earnings8k"] and last_rd and f["earnings8k"][0]["date"] > last_rd and st["state"] == "waiting":
            hint = f"SEC 已有新的財報 8-K（{f['earnings8k'][0]['date']}）"
        if f and st["state"] == "completed" and f["periodic"] and st.get("flashDate") and f["periodic"][0]["date"] >= st["flashDate"]:
            prog[-1] += f"　（SEC 已有 {f['periodic'][0]['form']} {f['periodic'][0]['date']}）"
        # 3) 到期的公布日（events 早於今天、還在清單裡＝還沒處理）
        if st["state"] == "waiting":
            due = [e for e in evs if e["date"] < today.isoformat()]
            sure = [e for e in due if not e.get("est")]
            est = [e for e in due if e.get("est")]
            if hint and not sure:
                todo.append(f"  {code}：{hint} → 快報（網頁上的公布日是預估，改成實際日期）")
            elif sure:
                todo.append(f"  {code}：{sure[0]['date']} {sure[0]['t'][:30]} → 快報")
            elif est:
                todo.append(f"  {code}：預估日 {est[0]['date']} 已過，{hint or 'SEC 清單沒有新申報'} → 只查公司是否已公告實際日期（不算失敗）")
        for e in evs:
            dd = (datetime.date.fromisoformat(e["date"]) - today).days
            if 0 <= dd <= 7:
                soon.append((e["date"], f"  {e['date']}  {code}  {e['t'][:40]}{'（預估）' if e.get('est') else ''}"))
    print("\n① 今天可能到了／要處理（先查 events 早於今天者）：\n" + ("\n".join(todo) or "  無"))
    print("\n② 進行中（補完／核對）：\n" + ("\n".join(prog) or "  無"))
    print("\n④ 接下來 7 天公布日：\n" + ("\n".join(s for _, s in sorted(soon)) or "  無"))
    print("\n⑤ 卡住（連續 5 次失敗）：\n" + ("\n".join(stuck) or "  無"))
    print("\n提醒：每家「進行中」或「到期」才開網頁；其餘公司只做一次標題層級的新聞搜尋。")


def cmd_set(code, state, target=None, note=None, today=None):
    cal = load_cal()
    if state == "verified":
        cal["companies"].pop(code, None)
    else:
        cur = cal["companies"].get(code, {})
        e = {"state": state, "target": target or cur.get("target"), "tries": 0 if state != "stuck" else cur.get("tries", 0),
             "since": cur.get("since") or today.isoformat()}
        if state == "flash":
            e["flashDate"] = today.isoformat()
        elif cur.get("flashDate"):
            e["flashDate"] = cur["flashDate"]
        if note:
            e["note"] = note
        if state == "waiting":
            e = {"state": "waiting", "tries": 0}
        cal["companies"][code] = e
    save_cal(cal)
    print(f"{code} → {state}")


def cmd_try(code, note, today):
    cal = load_cal()
    e = cal["companies"].setdefault(code, {"state": "waiting", "tries": 0, "since": today.isoformat()})
    e["tries"] = e.get("tries", 0) + 1
    if note:
        e["note"] = note
    if e["tries"] >= MAX_TRIES:
        e["state"] = "stuck"
        print(f"{code} 連續 {e['tries']} 次沒成功 → stuck（停止自動重試，首頁標待更新）")
    else:
        print(f"{code} 第 {e['tries']} 次失敗，明天自動重試")
    save_cal(cal)


def main():
    a = sys.argv[1:]
    today = taipei_today()
    if "--today" in a:
        i = a.index("--today"); today = datetime.date.fromisoformat(a[i + 1]); del a[i:i + 2]

    def opt(name):
        if name in a:
            i = a.index(name); v = a[i + 1]; del a[i:i + 2]; return v
    target, note = opt("--target"), opt("--note")
    if not a:
        return status(today)
    if a[0] == "set":
        return cmd_set(a[1], a[2], target, note, today)
    if a[0] == "try":
        return cmd_try(a[1], note, today)
    if a[0] == "done":
        cal = load_cal(); cal["lastRun"] = cal["lastSuccess"] = today.isoformat(); save_cal(cal); print("lastSuccess =", today); return
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
