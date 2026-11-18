"""估值訊號：論點卡「估值（val）」門檻被穿越時記一筆（只提醒，不是買賣建議）。

規則（和 docs 規劃 ④ 一致）：
  · 只看已核准論點卡的估值門檻（daily_calc 算出的 calc.latest.caps[]，每筆有 k／op／thr／now）
  · 磁滯 ±2%：op「<=」時，現值 > 門檻×1.02 才算「超出」，< 門檻×0.98 才算「回到範圍內」，中間不動（避免在門檻邊緣來回洗版）
  · 第一次看到某個指標：只記狀態，不發訊號
  · 狀態與事件存 data/daily/_signals.json：{"state": {"code.k": "in|out"}, "events": [{d, code, k, name, kind, now, thr}]}
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, "data", "daily", "_signals.json")
BAND = 0.02
KEEP = 200  # 最多留幾筆事件


def load():
    if os.path.exists(PATH):
        with open(PATH, encoding="utf8") as f:
            return json.load(f)
    return {"version": 1, "note": "估值訊號狀態與事件（tools/signals.py 寫；提醒，不是買賣建議）", "state": {}, "events": []}


def save(S):
    with open(PATH, "w", encoding="utf8") as f:
        json.dump(S, f, ensure_ascii=False, indent=1); f.write("\n")


def judge(prev, op, thr, now):
    """回傳新狀態 'in'／'out'（磁滯）。prev 是 None（第一次）時用有沒有超過門檻決定。"""
    hi, lo = thr * (1 + BAND), thr * (1 - BAND)
    if op == "<=":
        beyond, inside = now > hi, now < lo
    else:
        beyond, inside = now < lo, now > hi
    if prev is None:
        return "out" if (now > thr if op == "<=" else now < thr) else "in"
    if beyond:
        return "out"
    if inside:
        return "in"
    return prev


def update(S, code, date, caps):
    """caps = calc.latest.caps；回傳這次新增的事件。同一天同一指標只處理一次。"""
    new = []
    for c in caps or []:
        if c.get("now") is None or c.get("thr") is None:
            continue
        key = f"{code}.{c['k']}"
        prev = S["state"].get(key)
        cur = judge(prev, c["op"], c["thr"], c["now"])
        S["state"][key] = cur
        if prev is not None and cur != prev:
            ev = {"d": date, "code": code, "k": c["k"], "name": c["name"], "kind": "exceed" if cur == "out" else "back", "now": c["now"], "thr": c["thr"], "op": c["op"]}
            if not any(e["d"] == date and e["code"] == code and e["k"] == c["k"] and e["kind"] == ev["kind"] for e in S["events"]):
                S["events"].append(ev); new.append(ev)
    S["events"] = S["events"][-KEEP:]
    return new


def text(ev):
    word = "超出" if ev["kind"] == "exceed" else "回到"
    return f"{ev['code'].upper()} {ev['name']} {ev['now']}（門檻 {ev['op']} {ev['thr']}）{word}估值範圍"
