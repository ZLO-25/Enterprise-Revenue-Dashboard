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
import pe as PE  # noqa: E402

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
        hint = daily.sec_hint(f, last_rd, D.get("events", []), today)
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
TRIGGERS = {"daily": "trig_01CpC7MUpPAfrWAZfS4yxSxW", "trend": "trig_014e4JKi6EaLkTFUV2aAVc4U", "news": "trig_01RyLx6r8GG3Zj8MJuboqA8L"}
NEWS_FIRST = "2026-11-22"  # 每週新聞排程第一次該跑的日子（週日）；沒有紀錄時從這天起算


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
        lines.append(f"缺跑 {len(md)} 天（每天一行，回報 ② 照抄）：")
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
    # 每週新聞（週日 06:00）超過 9 天沒跑（額度用完等）→ 由每日排程補觸發一次
    ref = fired.get("news") or NEWS_FIRST
    days = (today - datetime.date.fromisoformat(ref)).days
    if days > 9:
        last = fired.get("newsfire")
        if last and (today - datetime.date.fromisoformat(last)).days < 3:
            lines.append(f"每週新聞已 {days} 天沒跑（{last} 已補觸發過，3 天內不重複）")
        else:
            lines.append(f"每週新聞已 {days} 天沒跑 → fire_trigger {TRIGGERS['news']} 一次，並 python3 tools/daily.py mark newsfire；回報 ⑤ 寫一行")
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
        pe = PE.pe_text(L.get("pe"))
        rows.append(f"{c['code']} {L['d'][5:]} {L['c']} PE {pe}")
    head = ("✗ 每日收盤價落後：" + "、".join(late) + "（prices-daily 每天多班會自己補，21:12 那班仍落後會寄信；不要自己抓或填）") if late else "每日收盤價都是最新"
    return head, rows


def valuation_and_lights():
    """各公司最新本益比、預估本益比，與論點卡燈號（approved 才算）。"""
    import thesis as T
    pe_rows, lights, groups = [], {}, {}
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
        pe = PE.pe_text(st.get("latest"))
        fpe = f"{PE.pe_text(st['fpeLatest'])}（{st['fpeM']}）" if st.get("fpeLatest") is not None else "待確認：無快照"
        pe_rows.append(f"{code} {pe}／{fpe}")
        if code in approved:
            L = T.lights(approved[code], Q, val, hl)
            lights[code] = {k: v["light"] for k, v in L.items()}
            groups[code] = {m["k"]: ("aux" if m.get("role") == "aux" else m.get("group", "biz")) for m in approved[code].get("metrics", [])}   # biz＝核心體質、val＝估值、aux＝輔助觀察
    return pe_rows, lights, groups


def lights_part(lights, groups):
    """核心體質（biz）、估值（val）、輔助（aux）分開：只有核心體質轉差才置頂（那是公司變差了）；估值轉差與輔助指標轉差只放附錄（股價變貴，或成長指標單獨變動，都不是論點破了）。"""
    old = jload("data", "brief-lights.json", default={}).get("lights", {})
    order = {"g": 0, "y": 1, "r": 2}
    worse = {"biz": [], "val": []}
    red = {"biz": [], "val": []}   # val 在這裡包含估值與輔助
    for code, L in lights.items():
        for k, v in L.items():
            g = "val" if groups.get(code, {}).get(k) in ("val", "aux") else "biz"
            if v == "r":
                red[g].append(f"{code}.{k}")
            o = old.get(code, {}).get(k)
            if o and order.get(v, 0) > order.get(o, 0):
                worse[g].append(f"{code}.{k} {o}→{v}")
    if not old:
        out = ["論點卡：第一次記錄，明天起比較"]
    else:
        out = ["論點卡體質：" + ("今天轉差 " + "、".join(worse["biz"]) + "（回報 ⑤ 置頂）" if worse["biz"] else "今天沒有轉黃／轉紅")]
        out.append("論點卡估值與輔助：" + ("今天轉差 " + "、".join(worse["val"]) + "（只放回報附錄，不置頂；是股價變貴或輔助指標變動，不是論點破了）" if worse["val"] else "今天沒有轉黃／轉紅"))
    out.append(f"體質紅燈 {len(red['biz'])}：" + ("、".join(red["biz"]) or "無"))
    out.append(f"估值與輔助紅燈 {len(red['val'])}（附錄）：" + ("、".join(red["val"]) or "無"))
    return out


def signals_part(today):
    """最近 7 天的估值訊號只留一行計數（內容改由每週彙整，見 docs/WEEKLY_NEWS_PROMPT.md「本週估值訊號」）。提醒，不是買賣建議。"""
    S = jload("data", "daily", "_signals.json", default={"events": []}) or {"events": []}
    cut = (today - datetime.timedelta(days=7)).isoformat()
    n = sum(1 for e in S["events"] if e["d"] >= cut)
    return f"估值訊號：最近 7 天 {n} 則（只計數，不展開；每週彙整再看。提醒，不是買賣建議）"


def save_lights(today):
    _, lights, _g = valuation_and_lights()
    # 燈號變化記進 data/lights-log.json（日期、公司、指標、從、到），之後回頭看哪個指標什麼時候轉差
    old = jload("data", "brief-lights.json", default={}).get("lights", {})
    log = jload("data", "lights-log.json", default={"version": 1, "note": "論點卡燈號變化紀錄（daily_brief.py --save-lights 寫）", "changes": []})
    have = {(c["d"], c["code"], c["k"]) for c in log["changes"]}
    import thesis as T
    meta = {c["code"]: {m["k"]: ("aux" if m.get("role") == "aux" else m.get("group", "biz"), m["name"]) for m in th.get("metrics", [])} for c, th in T.load_all()}
    for code, L in lights.items():
        for k, v in L.items():
            o = old.get(code, {}).get(k)
            if o and o != v and (today.isoformat(), code, k) not in have:
                g, nm = meta.get(code, {}).get(k, ("biz", k))
                log["changes"].append({"d": today.isoformat(), "code": code, "k": k, "name": nm, "g": g, "from": o, "to": v})
    with open(os.path.join(ROOT, "data", "lights-log.json"), "w", encoding="utf8") as f:
        json.dump(log, f, ensure_ascii=False, indent=1); f.write("\n")
    with open(LIGHTS, "w", encoding="utf8") as f:
        json.dump({"date": today.isoformat(), "lights": lights}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(f"已記錄 {len(lights)} 家論點卡燈號 → data/brief-lights.json")


def _git(*args, timeout=60):
    import subprocess
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def prep_fresh(max_min=20):
    """origin/main 上的 data/status/latest.json 是不是 max_min 分鐘內產生的（daily-prep 最後一步寫的）。"""
    r = _git("show", "origin/main:data/status/latest.json")
    if r.returncode:
        return False
    try:
        g = datetime.datetime.strptime(json.loads(r.stdout)["generated"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=datetime.timezone.utc)
    except Exception:  # noqa: BLE001
        return False
    return (datetime.datetime.now(datetime.timezone.utc) - g).total_seconds() < max_min * 60


def wait_prep(max_s=240):
    """每日檢查當鬧鐘：觸發 GitHub Actions 的 daily-prep（SEC 清單、預估、股價、期貨、健康狀態），等它做完再 pull。
    只在 main 分支執行；測試模式（--today）不會呼叫這裡。回傳要印在摘要最前面的一行。"""
    import subprocess, time
    if _git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() != "main":
        return "（不在 main 分支，略過等待每日準備）"
    _git("fetch", "-q", "origin", "main")
    mark = os.path.join(ROOT, ".git", "daily-prep-dispatched")   # 15 分鐘內觸發過就不重複觸發（同一次排程重跑這個指令時）
    recent = os.path.exists(mark) and time.time() - os.path.getmtime(mark) < 15 * 60
    if prep_fresh():
        note = "每日準備：20 分鐘內已跑過，直接用"
    else:
        ok = recent
        if not recent:
            try:
                r = subprocess.run(["gh", "workflow", "run", "daily-prep.yml", "--ref", "main"], cwd=ROOT, capture_output=True, text=True, timeout=30)
                ok = r.returncode == 0
            except Exception:  # noqa: BLE001
                ok = False
            if ok:
                open(mark, "w").close()
        if not ok:
            return "✗ 每日準備觸發失敗（gh 不可用）：SEC 清單可能是舊的 → 若有 GitHub 工具，用 actions_run_trigger 觸發 daily-prep.yml（ref main）後再跑一次 brief --wait-prep"
        t0 = time.time()
        note = None
        while time.time() - t0 < max_s:
            time.sleep(10)
            _git("fetch", "-q", "origin", "main")
            if prep_fresh():
                note = f"每日準備：已觸發並完成（等了 {int(time.time() - t0)} 秒）"
                break
        if note is None:
            return f"✗ 每日準備 {max_s} 秒內沒完成：SEC 清單是舊的（回報 ⑤ 寫一行；它會自己跑完，明天就會是新的）"
    m = _git("merge", "--ff-only", "origin/main")
    if m.returncode:
        return note + "；但 pull 失敗（" + (m.stderr.strip()[:80] or "?") + "）→ 用 git pull --rebase 處理"
    return note + "，已 pull 最新資料"


def main():
    a = sys.argv[1:]
    today = daily.taipei_today()
    if "--today" in a:
        i = a.index("--today"); today = datetime.date.fromisoformat(a[i + 1]); del a[i:i + 2]
    if a[:1] == ["--save-lights"]:
        return save_lights(today)
    if "--wait-prep" in a:
        print(wait_prep() + "\n")

    print(calendar_part(today))
    need = stages(today)
    pe_rows, lights, groups = valuation_and_lights()
    print("\n⑦ 股價：" + prices_part())
    dh, drows = daily_part()
    print("   " + dh + ("\n   收盤／每日本益比：" + "；".join(drows) if drows else ""))
    print("\n⑧ " + "\n   ".join(lights_part(lights, groups) + [signals_part(today)]))
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
    print("\n⑪ 今天要讀的指令附件：" + ("無（安靜日：不讀附件，直接回報 → done）" if quiet else ""))
    for f in files:
        print("  · " + f)
    if need["stuck"]:
        print("  · 卡住的公司（" + "、".join(need["stuck"]) + "）只在回報置頂，不處理")
    print("\n資料誠實：讀不到就 null＋「待確認」；validate 沒過不發佈。")


if __name__ == "__main__":
    main()
