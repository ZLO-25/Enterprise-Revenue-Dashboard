"""總經儀表板的一週摘要（每週日排程用，見 docs/WEEKLY_NEWS_PROMPT.md）。

  python3 tools/daily.py macro            印出：資料新不新、這一週誰換了燈、觀念提醒的新增與消失、警訊計數、台灣燈號

只讀檔、不抓資料、不計算指標：
  現在 ＝ data/macro/latest.json（只有 GitHub Actions 的 macro-weekly 會寫）
  上週 ＝ git 歷史裡「至少 6 天前」的那一版 latest.json（拿不到就只印現況，並說明沒得比）
燈號、提醒成立與否、警訊計數都是 tools/macro_fetch.py 算好的，這裡只做「兩個版本的差異」。
輸出是公式判斷的事實整理，不是買賣建議，也不判定現在是哪個景氣階段。
"""
import datetime, json, os, subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LATEST = "data/macro/latest.json"
LIGHT = {"worse": "轉差", "better": "轉好", "flat": "持平"}
OLD_DAYS = 10          # 資料檔超過這麼多天沒更新：和系統健康頁的紅燈同一個門檻
MAX_ROWS = 12          # 換燈最多列幾條（轉差排前面），其餘只報數量


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def names(cfg):
    """指標代號 → (名稱, 是不是核心)。美國在 groups，台灣在 tw.series。"""
    out = {}
    for g in cfg.get("groups", []):
        for s in g.get("series", []):
            out[s["key"]] = (s.get("name", s["key"]), bool(s.get("core")))
    for s in cfg.get("tw", {}).get("series", []):
        out[s["key"]] = ("台灣 " + s.get("name", s["key"]), bool(s.get("core")))
    return out


def lights(doc):
    """代號 → 現在的燈（沒有燈的指標不列）。"""
    out = {}
    for src in (doc.get("series") or {}, (doc.get("tw") or {}).get("series") or {}):
        for k, v in src.items():
            l = (v.get("stats") or {}).get("light")
            if l:
                out[k] = l
    return out


def age_days(doc, today):
    try:
        d = datetime.datetime.strptime(doc["updated"], "%Y-%m-%d %H:%M UTC").date()
    except (KeyError, ValueError, TypeError):
        return None
    return (today - d).days


def fmt_val(stats):
    v, d = stats.get("last"), stats.get("lastDate")
    if v is None:
        return ""
    return f"（最新 {v:g}，{d}）" if d else f"（最新 {v:g}）"


def brief(doc, cfg, prev=None, today=None):
    """回傳要印的每一行。doc＝現在的 latest.json，prev＝上週那一版（可以是 None）。"""
    today = today or datetime.date.today()
    nm = names(cfg)
    out = []

    # ① 資料新不新、健康狀態
    age = age_days(doc, today)
    h, lk = doc.get("health") or {}, doc.get("links") or {}
    stale, dead, failed = h.get("stale") or [], lk.get("dead") or [], h.get("failed") or 0
    if age is None:
        out.append("資料：待確認：讀不到 latest.json 的更新時間")
    elif age > OLD_DAYS:
        out.append(f"資料：待確認：總經資料已 {age} 天沒更新（最後 {doc['updated']}），以下可能過時；請手動執行 macro-weekly")
    else:
        out.append(f"資料：{doc['updated']} 更新（{age} 天前）")
    bad = []
    if stale:
        bad.append("停更？" + "、".join(x.get("name", x.get("key", "?")) for x in stale[:5]) + (f" 等 {len(stale)} 個" if len(stale) > 5 else ""))
    if failed:
        bad.append(f"這次抓不到 {failed} 個")
    if dead:
        bad.append(f"連結失效 {len(dead)} 個")
    out.append("健康：" + ("；".join(bad) if bad else "沒有停更、沒有抓不到、沒有失效連結"))

    if prev is None:
        out.append("比較：拿不到一週前的版本，以下只有現況（沒有「這一週的變化」）")
    else:
        out.append(f"比較：對照 {prev.get('updated', '?')} 那一版")

    # ② 這一週誰換了燈
    now_l = lights(doc)
    if prev is not None:
        old_l = lights(prev)
        ch = [(k, old_l[k], now_l[k]) for k in now_l if k in old_l and old_l[k] != now_l[k]]
        order = {"worse": 0, "better": 1, "flat": 2}
        ch.sort(key=lambda x: (order.get(x[2], 9), 0 if nm.get(x[0], ("", False))[1] else 1, x[0]))
        if not ch:
            out.append("換燈：這一週沒有指標換燈")
        else:
            out.append(f"換燈：{len(ch)} 個（★＝核心指標）")
            allstats = dict(doc.get("series") or {}); allstats.update((doc.get("tw") or {}).get("series") or {})
            for k, a, b in ch[:MAX_ROWS]:
                name, core = nm.get(k, (k, False))
                out.append(f"  {'★' if core else '　'}{name}：{LIGHT.get(a, a)} → {LIGHT.get(b, b)}{fmt_val((allstats.get(k) or {}).get('stats') or {})}")
            if len(ch) > MAX_ROWS:
                out.append(f"  其餘 {len(ch) - MAX_ROWS} 個見網站「最近換燈的指標」")
    worse = [nm.get(k, (k, False))[0] for k, l in now_l.items() if l == "worse"]
    out.append(f"目前轉差：{len(worse)} 個" + ("（" + "、".join(worse[:8]) + ("…" if len(worse) > 8 else "") + "）" if worse else ""))

    # ③ 觀念提醒：新出現、消失、持續
    rem = {r["id"]: r for r in cfg.get("reminders", [])}

    def title(i):
        r = rem.get(i)
        return (("留意：" if r.get("level") == "watch" else "觀念：") + r.get("title", i)) if r else i

    now_r = list(doc.get("reminders") or [])
    if prev is not None and "reminders" in prev:
        old_r = list(prev.get("reminders") or [])
        new, gone, keep = [i for i in now_r if i not in old_r], [i for i in old_r if i not in now_r], [i for i in now_r if i in old_r]
        out.append("提醒：新出現 " + (str(len(new)) + " 條" if new else "0 條") + "，消失 " + str(len(gone)) + " 條，持續 " + str(len(keep)) + " 條")
        for i in new:
            out.append("  ＋" + title(i))
        for i in gone:
            out.append("  －" + title(i) + "（條件不再成立）")
        for i in keep:
            out.append("  ＝" + title(i))
    else:
        out.append(f"提醒：目前成立 {len(now_r)} 條" + ("（上週那一版還沒有提醒功能，沒得比）" if prev is not None else ""))
        for i in now_r:
            out.append("  ＝" + title(i))

    # ④ 警訊計數（七大指標亮幾項）與台灣燈號
    items = (doc.get("score") or {}).get("items")
    b = doc.get("boomNow")
    if b is None:
        out.append("警訊計數：待確認：latest.json 沒有 boomNow")
    else:
        s = f"警訊計數：七大指標現在亮 {b} 項" + (f"（共 {items} 項）" if items else "")
        if prev is not None and prev.get("boomNow") is not None:
            pb = prev["boomNow"]
            s += "，和上週相同" if pb == b else f"，上週是 {pb} 項"
        out.append(s)
    tl, pl = (doc.get("tw") or {}).get("light"), ((prev or {}).get("tw") or {}).get("light")
    if tl:
        s = f"台灣景氣燈號：{tl.get('name')}燈（{tl.get('date')}）"
        if pl and (pl.get("name"), pl.get("date")) != (tl.get("name"), tl.get("date")):
            s += f"，上週看到的是 {pl.get('name')}燈（{pl.get('date')}）"
        out.append(s)
    out.append("以上是公式判斷的整理，不是買賣建議；這一頁不判定現在是哪個景氣階段。")
    return out


def prev_doc(today, min_days=6, root=ROOT):
    """git 歷史裡至少 min_days 天前的 latest.json；拿不到（淺層 clone、還沒有那麼舊的版本）回傳 None。"""
    before = (today - datetime.timedelta(days=min_days)).isoformat() + "T23:59:59"
    try:
        sha = subprocess.run(["git", "log", "-1", "--before=" + before, "--format=%H", "--", LATEST],
                             cwd=root, capture_output=True, text=True, timeout=30).stdout.strip()
        if not sha:
            return None
        txt = subprocess.run(["git", "show", f"{sha}:{LATEST}"], cwd=root, capture_output=True, text=True, timeout=30)
        return json.loads(txt.stdout) if txt.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def main(today=None):
    today = today or datetime.date.today()
    try:
        doc = _load(os.path.join(ROOT, LATEST))
        cfg = _load(os.path.join(ROOT, "data", "macro", "config.json"))
    except (OSError, ValueError) as e:
        print(f"總經：待確認：讀不到總經資料檔（{type(e).__name__}）")
        return
    print("【總經一週摘要】https://zlo-25.github.io/Enterprise-Revenue-Dashboard/macro/")
    for line in brief(doc, cfg, prev_doc(today), today):
        print(line)


if __name__ == "__main__":
    main()
