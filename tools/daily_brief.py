#!/usr/bin/env python3
"""每日排程的「一頁摘要」：一個指令印出今天要知道的全部事情，讓 Claude 少走很多步。

    python3 tools/daily_brief.py                 印摘要（只讀檔，不連網、不改檔）
    python3 tools/daily_brief.py --save-lights   排程做完時執行：記下今天的論點卡燈號，明天用來比「轉黃／轉紅」
    --today YYYY-MM-DD                           指定日期（測試用）

為什麼有這支：每日排程原本要一個一個跑 daily.py、prices_update.py --check、thesis.py、
讀 consensus 快照、算本益比……每多一步，Claude 就要把前面的內容重讀一次（token 隨步驟數增加）。
這支把「固定規則就能決定的事」一次做完，Claude 只讀這一頁，再決定要不要深入。

輸出 ⑩「補跑與優先順序」（缺跑、積壓時才出現）與 ⑪「今天要讀的指令附件」告訴 Claude 要開 docs/schedule/ 的哪幾份；安靜日一份都不用開。
"""
import contextlib, datetime, io, json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import daily  # noqa: E402

LIGHTS = os.path.join(ROOT, "data", "brief-lights.json")
# 公司分析 hook 從這天起生效：最新一季公布日（rd）在這天以後、還沒有該季分析的公司，列進「分析待寫」。
# 更早的季度不回補（要補由 ZL 指定），免得第一次就一口氣寫 20 家。
ANALYSIS_FROM = "2026-11-17"


def jload(*p, default=None):
    path = os.path.join(ROOT, *p)
    if not os.path.exists(path):
        return default
    return json.load(open(path, encoding="utf8"))


def calendar_part(today):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        daily.status(today)
    txt = buf.getvalue()
    # 最後一行「提醒」由下面的附件清單取代
    lines = [l for l in txt.splitlines() if not l.startswith("提醒：")]
    return "\n".join(lines).rstrip()


def stages(today):
    """依 daily.status 同一套規則，判斷今天有哪些階段（決定要讀哪些附件）。"""
    cal = daily.load_cal()
    feed = jload("data", "sec-feed.json", default={"companies": {}})
    need = {"flash": [], "complete": [], "verify": [], "est": [], "stuck": [], "analysis": []}
    for c in daily.enabled():
        code = c["code"]
        D = jload("data", code + ".json")
        st = cal["companies"].get(code, {"state": "waiting"})
        q_last = D["quarters"][-1] if D.get("quarters") else {}
        A = jload("data", "analysis", code + ".json", default={}) or {}
        # 分析待寫：補完之後（completed／waiting），或補完卡了 3 次以上（用快報資料先寫）
        if (q_last.get("rd") or "") >= ANALYSIS_FROM and A.get("q") != q_last.get("q") and \
                (st["state"] in ("completed", "waiting") or (st["state"] == "flash" and st.get("tries", 0) >= 3)):
            need["analysis"].append(code + " " + q_last.get("q", ""))
        if st["state"] == "stuck":
            need["stuck"].append(code); continue
        if st["state"] == "flash":
            need["complete"].append(code); continue
        if st["state"] == "completed":
            need["verify"].append(code); continue
        last_rd = D["quarters"][-1].get("rd") if D.get("quarters") else None
        f = feed["companies"].get(code)
        hint = bool(f and f.get("earnings8k") and last_rd and f["earnings8k"][0]["date"] > last_rd)
        due = [e for e in D.get("events", []) if e["date"] < today.isoformat()]
        if hint or any(not e.get("est") for e in due):
            dates = [e["date"] for e in due if not e.get("est")] + ([f["earnings8k"][0]["date"]] if hint else [])
            need["flash"].append((min(dates), code))
        elif due:
            need["est"].append(code)
    need["flash"] = [c for _, c in sorted(need["flash"])]  # 最早到期的先做
    return need


# 每次排程最多處理幾家（積壓時分次做；剩下的留給下一次，狀態檔會記得）
CAPS = {"flash": 2, "complete": 2, "verify": 3}
TRIGGERS = {"daily": "trig_01CpC7MUpPAfrWAZfS4yxSxW", "trend": "trig_014e4JKi6EaLkTFUV2aAVc4U"}


def missed_detail(today):
    """缺跑的每一天各發生了什麼（公布日、SEC 財報 8-K），安靜的日子只寫一行「無事」。
    週日、週一的事件歸到它之後第一個缺跑日。"""
    cal = daily.load_cal()
    last = cal.get("lastSuccess")
    ms = daily.missed_days(last, today)
    if not ms:
        return []
    feed = jload("data", "sec-feed.json", default={"companies": {}})
    hit = {d: [] for d in ms}

    def put(date, text):
        if not (last < date < today.isoformat()):
            return
        for d in ms:
            if d >= date:
                hit[d].append(text); return

    for c in daily.enabled():
        code = c["code"]
        D = jload("data", code + ".json")
        for e in D.get("events", []):
            put(e["date"], f"{code} {e['t'][:14]}{'（預估）' if e.get('est') else ''}")
        for x in (feed["companies"].get(code) or {}).get("earnings8k", []):
            put(x["date"], f"{code} SEC 財報 8-K")
    return [f"{d[5:]}：" + ("、".join(sorted(set(v))) if v else "無事") for d, v in hit.items()]


def plan_part(today, need):
    cal = daily.load_cal()
    fired = cal.get("fired", {})
    out, left = [], []
    for k, label in (("flash", "快報"), ("complete", "補完"), ("verify", "核對")):
        xs = need[k]
        now, later = xs[:CAPS[k]], xs[CAPS[k]:]
        if now:
            out.append(f"{label}：今天做 {'、'.join(now)}" + (f"；留到下一次 {'、'.join(later)}" if later else ""))
        left += later
    if need["est"]:
        out.append("預估日已過、只查是否公告：" + "、".join(need["est"]))
    md = missed_detail(today)
    lines = []
    if md:
        lines.append(f"缺跑 {len(md)} 天（每天一行，回報 ② 照抄；新聞檢查範圍已自動涵蓋）：")
        lines += ["  " + x for x in md]
    if out:
        lines.append("優先順序（快報 → 補完 → 核對 → 新聞 → 日期待辦；同一類最早到期的先做）：")
        lines += ["  " + x for x in out]
    if left:
        if fired.get("extra") == today.isoformat():
            lines.append(f"  積壓還有 {len(left)} 件，今天已加跑過一次 → 留給明天的排程")
        else:
            lines.append(f"  積壓還有 {len(left)} 件 → 全部做完並 push 後，fire_trigger {TRIGGERS['daily']} 一次，並 python3 tools/daily.py mark extra（每天最多加跑一次）")
    # 世界趨勢月報：每月 2 日的排程沒跑成功（例如額度用完）時，由每日排程補觸發一次
    ym = today.strftime("%Y-%m")
    if today.day >= 3 and not os.path.exists(os.path.join(ROOT, "reports", "trend", f"{ym}_世界趨勢.md")):
        last = fired.get("trend")
        if last and (today - datetime.date.fromisoformat(last)).days < 3:
            lines.append(f"趨勢月報 {ym} 還沒產出（{last} 已補觸發過，3 天內不重複）")
        else:
            lines.append(f"趨勢月報 {ym} 還沒產出 → fire_trigger {TRIGGERS['trend']} 一次，並 python3 tools/daily.py mark trend；回報 ⑤ 寫一行")
    return lines


def prices_part():
    """股價檔最後一個月是不是上個月（同 prices_update.py --check 的規則，但只讀檔）。"""
    today = datetime.date.today()
    first = today.replace(day=1)
    want = (first - datetime.timedelta(days=1)).strftime("%Y-%m")
    stale = []
    for c in daily.enabled():
        if not c.get("price"):
            continue
        P = jload("data", "prices", c["code"] + ".json", default=None)
        last = P["monthly"][-1]["m"] if P and P.get("monthly") else None
        if last is None or last < want:
            stale.append(f"{c['code']}（最後 {last}）")
    if stale:
        return f"✗ 股價檔沒到 {want}：" + "、".join(stale) + " → 手動觸發 prices-monthly 一次並在回報說明（不可自己填）"
    return f"股價檔都已到 {want}"


def daily_part():
    """每日收盤價（Actions prices-daily 寫 data/daily/<代號>.json）：只讀檔，落後也不用 Claude 處理。"""
    today = daily.taipei_today()
    rows, late = [], []
    for c in daily.enabled():
        if not c.get("price"):
            continue
        X = (jload("data", "daily", c["code"] + ".json", default=None) or {}).get("calc") or {}
        L = X.get("latest") or {}
        if not L.get("d"):
            late.append(f"{c['code']}（還沒有檔）")
            continue
        lim = 12 if c["price"]["yahoo"].endswith((".TW", ".TWO", ".KS")) else 4
        if (today - datetime.date.fromisoformat(L["d"])).days > lim:
            late.append(f"{c['code']}（最後 {L['d']}）")
        pe = f"{L['pe']:.1f}" if L.get("pe") is not None else "—"
        rows.append(f"{c['code']} {L['d'][5:]} {L['c']} PE {pe}")
    head = ("✗ 每日收盤價落後：" + "、".join(late) + "（prices-daily 每天多班會自己補，21:12 那班仍落後會寄信；不要自己抓或填）") if late else "每日收盤價都是最新"
    return head, rows


def valuation_and_lights():
    """各公司最新本益比、預估本益比，與論點卡燈號（approved 才算）。"""
    import thesis as T
    pe_rows, lights = [], {}
    approved = {c["code"]: th for c, th in T.load_all() if th.get("status") == "approved"}
    for c in daily.enabled():
        code = c["code"]
        if not c.get("price"):
            pe_rows.append(f"{code} —（未設股價）")
            continue
        try:
            D, val, hl, Q = T.context(code)
        except Exception as e:  # noqa: BLE001
            pe_rows.append(f"{code} 待確認（計算失敗：{type(e).__name__}）")
            continue
        st = (val or {}).get("stats", {})
        pe = f"{st['latest']:.1f}" if st.get("latest") is not None else "—"
        fpe = f"{st['fpeLatest']:.1f}（{st['fpeM']}）" if st.get("fpeLatest") is not None else "待確認：無快照"
        pe_rows.append(f"{code} {pe}／{fpe}")
        if code in approved:
            L = T.lights(approved[code], Q, val, hl)
            lights[code] = {k: v["light"] for k, v in L.items()}
    return pe_rows, lights


def lights_part(lights):
    old = jload("data", "brief-lights.json", default={}).get("lights", {})
    order = {"g": 0, "y": 1, "r": 2}
    worse, red = [], []
    for code, L in lights.items():
        for k, v in L.items():
            if v == "r":
                red.append(f"{code}.{k}")
            o = old.get(code, {}).get(k)
            if o and order.get(v, 0) > order.get(o, 0):
                worse.append(f"{code}.{k} {o}→{v}")
    out = ["論點卡：" + ("今天轉差 " + "、".join(worse) + "（回報 ⑤ 置頂）" if worse else ("今天沒有轉黃／轉紅" if old else "第一次記錄，明天起比較"))]
    out.append("目前紅燈：" + ("、".join(red) if red else "無"))
    return out


def save_lights(today):
    _, lights = valuation_and_lights()
    with open(LIGHTS, "w", encoding="utf8") as f:
        json.dump({"date": today.isoformat(), "lights": lights}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"已記錄 {len(lights)} 家論點卡燈號 → data/brief-lights.json")


def main():
    a = sys.argv[1:]
    today = daily.taipei_today()
    if "--today" in a:
        i = a.index("--today"); today = datetime.date.fromisoformat(a[i + 1]); del a[i:i + 2]
    if a[:1] == ["--save-lights"]:
        return save_lights(today)

    print(calendar_part(today))
    need = stages(today)
    pe_rows, lights = valuation_and_lights()
    print("\n⑦ 股價：" + prices_part())
    dh, drows = daily_part()
    print("   " + dh + ("\n   收盤／每日本益比：" + "；".join(drows) if drows else ""))
    print("\n⑧ " + "\n   ".join(lights_part(lights)))
    print("\n⑨ 本益比／預估本益比（回報附錄照抄）：\n  " + "；".join(pe_rows))

    plan = plan_part(today, need)
    if plan:
        print("\n⑩ 補跑與優先順序：\n  " + "\n  ".join(plan))
    for k in CAPS:
        need[k] = need[k][:CAPS[k]]
    files = []
    if need["flash"] or need["est"]:
        files.append("docs/schedule/flash.md（" + "、".join(need["flash"] + need["est"]) + "）")
    if need["complete"]:
        files.append("docs/schedule/complete.md（" + "、".join(need["complete"]) + "）")
    if need["verify"]:
        files.append("docs/schedule/verify.md（" + "、".join(need["verify"]) + "；用年度申報核對時再讀 docs/schedule/profile.md）")
    if need["analysis"]:
        files.append("docs/schedule/analysis.md（分析待寫：" + "、".join(need["analysis"]) + "）")
    quiet = not (need["flash"] or need["est"] or need["complete"] or need["verify"] or need["analysis"])
    print("\n⑪ 今天要讀的指令附件：" + ("無（安靜日：只做 ④ 大新聞 → 回報 → done）" if quiet else ""))
    for f in files:
        print("  · " + f)
    if need["stuck"]:
        print("  · 卡住的公司（" + "、".join(need["stuck"]) + "）只在回報置頂，不處理")
    print("\n資料誠實：讀不到就 null＋「待確認」；validate 沒過不發佈。")


if __name__ == "__main__":
    main()
