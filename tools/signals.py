"""估值訊號：論點卡「估值（val）」門檻與現值差太多時記一筆（只提醒，不是買賣建議；每週彙整呈現，不在每天提醒）。

規則（三態 cheap／normal／rich，±15%）：
  · 只看已核准論點卡的估值門檻（daily_calc 算出的 calc.latest.caps[]，每筆有 k／op／thr／now）
  · 「≤ 門檻」的指標（本益比、EV/Sales）：現值 ≥ 門檻×1.15 → rich（比門檻貴）；現值 ≤ 門檻×0.85 → cheap（比門檻便宜）
    「≥ 門檻」的指標（自由現金流殖利率）方向相反：現值 ≤ 門檻×0.85 → rich；現值 ≥ 門檻×1.15 → cheap
  · 回到 normal 要越過 ±13%（保留 2 個百分點的緩衝，避免在 ±15% 邊緣來回洗版）；中間地帶維持原狀態
  · 第一次看到某個指標：只記狀態，不發訊號；舊版狀態檔的 in／out 視為未知：重新判定、不發訊號
  · 狀態與事件存 data/daily/_signals.json：{"state": {"code.k": "cheap|normal|rich"}, "events": [{d, code, k, name, kind: rich|cheap|back, now, thr, op}]}
  · 每週彙整：docs/WEEKLY_NEWS_PROMPT.md「本週估值訊號」讀這個檔最近 7 天的事件
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data", "daily", "_signals.json")
EDGE = 0.15   # 進入 rich／cheap 的距離
BACK = 0.13   # 回到 normal 要越過的距離（比 EDGE 小 2 個百分點的緩衝）
STATES = ("cheap", "normal", "rich")
KEEP = 200  # 最多留幾筆事件


def load():
    if os.path.exists(PATH):
        with open(PATH, encoding="utf8") as f:
            return json.load(f)
    return {"version": 2, "note": "估值訊號狀態與事件（tools/signals.py 寫；提醒，不是買賣建議）", "state": {}, "events": []}


def save(S):
    with open(PATH, "w", encoding="utf8") as f:
        json.dump(S, f, ensure_ascii=False, indent=1); f.write("\n")


def judge(prev, op, thr, now):
    """回傳新狀態 cheap／normal／rich。prev 不是三態之一（第一次、或舊檔的 in／out）時，直接用 ±15% 判定。"""
    d = round(now / thr - 1, 9)           # 四捨五入避免 34.5/30−1 這類邊界值被浮點誤差擠到另一邊
    s = d if op == "<=" else -d          # s > 0：比門檻貴
    if prev == "rich" and s >= BACK:
        return "rich"
    if prev == "cheap" and s <= -BACK:
        return "cheap"
    if s >= EDGE:
        return "rich"
    if s <= -EDGE:
        return "cheap"
    return "normal"


def update(S, code, date, caps):
    """caps = calc.latest.caps；回傳這次新增的事件。同一天同一指標只處理一次。"""
    new = []
    for c in caps or []:
        if c.get("now") is None or c.get("thr") is None or c["thr"] <= 0:
            continue
        key = f"{code}.{c['k']}"
        prev = S["state"].get(key)
        known = prev in STATES
        cur = judge(prev if known else None, c["op"], c["thr"], c["now"])
        S["state"][key] = cur
        if known and cur != prev:
            kind = "back" if cur == "normal" else cur
            ev = {"d": date, "code": code, "k": c["k"], "name": c["name"], "kind": kind, "now": c["now"], "thr": c["thr"], "op": c["op"]}
            if not any(e["d"] == date and e["code"] == code and e["k"] == c["k"] and e["kind"] == ev["kind"] for e in S["events"]):
                S["events"].append(ev); new.append(ev)
    S["events"] = S["events"][-KEEP:]
    return new


WORD = {"rich": "比門檻貴 15% 以上", "cheap": "比門檻便宜 15% 以上", "back": "回到門檻附近（±13% 內）", "exceed": "超出估值範圍（舊紀錄）"}


def text(ev):
    return f"{ev['code'].upper()} {ev['name']} {ev['now']}（門檻 {ev['op']} {ev['thr']}）{WORD.get(ev['kind'], ev['kind'])}。提醒，不是買賣建議"
