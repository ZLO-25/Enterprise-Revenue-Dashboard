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
  python3 tools/daily.py watch-done ID [--note 結果]   data/watchlist.json 的日期待辦做完了
  python3 tools/daily.py brief [--wait-prep]  一頁摘要（--wait-prep：先叫醒 GitHub 的每日準備並等它做完，正式排程用；--today 測試模式不叫醒）（清單＋股價＋論點卡轉差＋本益比＋今天要讀哪些附件）
  python3 tools/daily.py save-lights          排程做完時記下論點卡燈號（明天比較轉差）
  python3 tools/daily.py news-scope           每週新聞（週日 06:00）的範圍與公司清單
  python3 tools/daily.py story                各公司核心故事線與類別（寫 milestones 前先對）
  python3 tools/daily.py mark extra|trend|news|newsfire     記下今天已補觸發過（每天最多一次）
  python3 tools/daily.py inbox [CODE…]        SEC 收件匣：Actions 預抓的財報新聞稿＋XBRL 核對表（快報、核對先看這個）
  python3 tools/daily.py trend-facts          世界趨勢月報的事實表（各公司最新一季、四大雲端資本支出、記憶體毛利率）
  python3 tools/daily.py pending              待確認分級（近期／近三年／歷史）統計，寫 reports/pending.md
  python3 tools/daily.py tokens add|report|week   排程 token 用量紀錄（每週統計 → reports/token-usage.md）
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


def sec_hint(f, last_rd, evs, today):
    """SEC 有比上一季 rd 更新的財報 8-K → 可能是新財報。
    例外：公司已公告「未來」的財報日（events 裡有非預估、日期 ≥ 今天的項目），代表這份 8-K 不是財報
    （例：MRVL 2026-11-02 的併購公告 8-K 2.02 沒有數字），不提示，否則會每天誤報到財報日。"""
    if not (f and f.get("earnings8k") and last_rd and f["earnings8k"][0]["date"] > last_rd):
        return False
    return not any(not e.get("est") and e["date"] >= today.isoformat() for e in evs)


def status(today):
    cal = load_cal()
    feed = jload("data", "sec-feed.json", default={"companies": {}})
    print(f"【排程清單 {today}（台北）】")
    ms = missed_days(cal.get("lastSuccess"), today)
    print(f"上次成功：{cal.get('lastSuccess') or '無紀錄'}　缺跑：{('、'.join(ms) + '（要一起補，回報寫明補了哪幾天）') if ms else '無'}")
    if cal.get("lastSuccess"):
        gap = (today - datetime.date.fromisoformat(cal["lastSuccess"])).days
        print("大新聞：每週日 06:00 另有排程（docs/WEEKLY_NEWS_PROMPT.md），每日檢查不搜尋新聞")
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
        if sec_hint(f, last_rd, evs, today) and st["state"] == "waiting":
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
    watch(today, feed)
    print("\n提醒：每家「進行中」或「到期」才開網頁；其餘公司今天不用開網頁（大新聞每週日另跑）。")


def watch(today, feed):
    """data/watchlist.json：要等日期或外部事件的待辦（Anthropic 上市、預估本益比第一次快照…）。"""
    W = jload("data", "watchlist.json", default={"items": []})
    t, rows = today.isoformat(), []
    for w in W["items"]:
        if w.get("done") or w["from"] > t:
            continue
        late = w.get("until") and t > w["until"]
        line = f"  [{w['id']}] {w['what']}" + (f"（期限 {w['until']} 已過：做總結後 watch-done）" if late else "")
        if w.get("auto") == "ipo":
            f = feed["companies"].get(w["code"], {})
            ipo = f.get("ipo", [])
            if not f:
                line += "\n      sec-feed 還沒有這家（等 Actions 的 sec-feed 下一次執行）"
            else:
                priced = [x for x in ipo if x["form"] in ("424B4", "424B1")]
                line += "\n      SEC：" + ("已定價上市 " + priced[0]["date"] + " → 照 how 處理" if priced else
                                         "尚未定價（最近：" + ("、".join(f"{x['form']} {x['date']}" for x in ipo[:3]) or "無") + "）")
                if f.get("earnings8k") or f.get("periodic"):
                    x = (f.get("earnings8k") or f.get("periodic"))[0]
                    line += f"；已有季報申報 {x.get('form', '8-K 2.02')} {x['date']} → 回報置頂，等 ZL 說「繼續 Anthropic」"
        elif w.get("auto") == "forward":
            miss = []
            for c in enabled():
                if not c.get("price"):
                    continue
                P = jload("data", "prices", c["code"] + ".json", default={})
                if not any(x.get("m") == w["month"] for x in P.get("forward", [])):
                    miss.append(c["code"])
            line += "\n      " + (f"還缺 {w['month']} 快照：{'、'.join(miss)}" if miss else f"全部公司都有 {w['month']} 快照 → 回報列出後 watch-done")
        rows.append(line + f"\n      做法：{w['how']}")
    print("\n⑥ 日期待辦（data/watchlist.json）：\n" + ("\n".join(rows) or "  無"))


def add_months(d, n):
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    import calendar
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def cmd_watch_done(wid, note, today):
    p = os.path.join(ROOT, "data", "watchlist.json")
    W = jload("data", "watchlist.json")
    for w in W["items"]:
        if w["id"] == wid:
            if w.get("repeatMonths"):   # 週期待辦：不標 done，把 from 順延 N 個月（until 也順延），並記下這次結果
                n = int(w["repeatMonths"])
                w["lastDone"] = today.isoformat()
                w["from"] = add_months(max(today, datetime.date.fromisoformat(w["from"])), n).isoformat()
                if w.get("until"):
                    w["until"] = add_months(datetime.date.fromisoformat(w["until"]), n).isoformat()
                if note:
                    w["result"] = note
                with open(p, "w", encoding="utf8") as f:
                    json.dump(W, f, ensure_ascii=False, indent=1); f.write("\n")
                print(f"{wid} → 本次完成，下次 {w['from']}"); return
            w["done"] = today.isoformat()
            if note:
                w["result"] = note
            with open(p, "w", encoding="utf8") as f:
                json.dump(W, f, ensure_ascii=False, indent=1); f.write("\n")
            print(f"{wid} → done"); return
    sys.exit(f"找不到 {wid}")


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


def news_days(today):
    """每週新聞要看幾天：從上次 `mark news` 的日期到今天，最長 14 天；沒有紀錄是 7 天。"""
    last = load_cal().get("fired", {}).get("news")
    if not last:
        return 7, None
    return max(1, min(14, (today - datetime.date.fromisoformat(last)).days)), last


def news_scope(today):
    days, last = news_days(today)
    print(f"每週新聞範圍：過去 {days} 天（{(today - datetime.timedelta(days=days)).isoformat()}～{today.isoformat()}）；上次新聞：{last or '無紀錄'}")
    if last == today.isoformat():
        print("今天已經跑過每週新聞 → 回報「本週已完成」後結束，不重搜")
    for c in enabled():
        D = jload("data", c["code"] + ".json")
        ms = [m["d"] for m in D.get("milestones", []) if m.get("d") and m["d"] <= today.isoformat() and m.get("st") != "f"]
        print(f"  {c['code']}\t{c.get('name') or c.get('title') or ''}\tmilestones 最後一筆：{max(ms) if ms else '無'}\t{story_line(D)}")


def story_line(D):
    """核心故事線一行：名稱＋類別（cat 代碼＝中文名）；新增事件時 cat 先對這裡。"""
    S = D.get("story") or {}
    if not S.get("cats"):
        return "核心故事線：（缺，validate 會擋）"
    names = {"contract": "合約", "product": "產品", "listing": "上市", "index": "指數", "profit": "獲利", "ma": "併購",
             "node": "製程", "pkg": "先進封裝", "capacity": "產能", "mgmt": "經營層", "other": "其他", **(D.get("categories") or {})}
    return f"核心故事線：{S.get('t', '')}［" + "、".join(f"{k}={names.get(k, k)}" for k in S["cats"]) + "］"


def story_all():
    for c in enabled():
        D = jload("data", c["code"] + ".json")
        print(f"  {c['code']}\t{story_line(D)}")


def main():
    a = sys.argv[1:]
    today = taipei_today()
    test_mode = "--today" in a
    if "--today" in a:
        i = a.index("--today"); today = datetime.date.fromisoformat(a[i + 1]); del a[i:i + 2]

    def opt(name):
        if name in a:
            i = a.index(name); v = a[i + 1]; del a[i:i + 2]; return v
    target, note = opt("--target"), opt("--note")
    if not a:
        return status(today)
    if a[0] in ("brief", "save-lights"):  # 一頁摘要（見 tools/daily_brief.py）；走 daily.py 是因為排程的權限白名單已允許它
        import daily_brief
        sys.argv = [sys.argv[0]] + (["--today", today.isoformat()] if test_mode else []) + (["--save-lights"] if a[0] == "save-lights" else []) + (["--wait-prep"] if "--wait-prep" in a and not test_mode else [])
        return daily_brief.main()
    if a[0] == "story":  # 核心故事線一覽（新增 milestones 時 cat 先對這裡）
        return story_all()
    if a[0] == "news-scope":  # 每週新聞的範圍與公司清單（見 docs/WEEKLY_NEWS_PROMPT.md）
        return news_scope(today)
    if a[0] == "pending":  # 待確認分級統計＋reports/pending.md（見 tools/pending.py）
        import pending
        return pending.main()
    if a[0] == "tokens":  # 排程 token 用量紀錄（見 tools/token_log.py）
        import token_log
        return token_log.main(today, a[1:])
    if a[0] == "trend-facts":  # 趨勢月報事實表（見 tools/trend_facts.py）
        import trend_facts
        return trend_facts.main()
    if a[0] == "inbox":  # SEC 收件匣：Actions 預抓的新聞稿＋XBRL 核對表（見 tools/sec_inbox.py）
        import sec_inbox
        return sec_inbox.report(a[1:] or None)
    if a[0] == "set":
        return cmd_set(a[1], a[2], target, note, today)
    if a[0] == "try":
        return cmd_try(a[1], note, today)
    if a[0] == "watch-done":
        return cmd_watch_done(a[1], note, today)
    if a[0] == "mark":  # 記錄「今天已補觸發過」：extra（每日排程加跑）、trend（趨勢月報補跑），避免重複觸發
        cal = load_cal(); cal.setdefault("fired", {})[a[1]] = today.isoformat(); save_cal(cal); print(f"fired.{a[1]} =", today); return
    if a[0] == "done":
        cal = load_cal(); cal["lastRun"] = cal["lastSuccess"] = today.isoformat(); save_cal(cal); print("lastSuccess =", today); return
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
