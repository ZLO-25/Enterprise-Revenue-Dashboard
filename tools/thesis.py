"""論點卡：燈號由程式算（只用網站已有的數字），論點文字與門檻是人的判斷。

資料：data/thesis/<代號>.json
  {"code","status":"draft|approved","updated":"YYYY-MM-DD","updatedBy":"Claude 草稿|ZL","oneLiner":"…",
   "metrics":[{"k":"revYoy","name":"營收年增（近四季）","op":">=|<=","thr":20,"note":"為什麼是這個門檻","by":"draft|ZL"}],
   "breakWhen":"看到什麼就該重新考慮持有","risks":["…"],"history":[{"q":"3Q26","lights":{"revYoy":"g"}}]}
  **status 不是 approved 的一律不上線**（build.py 只注入 approved；草稿只存在這個檔案，等使用者確認）。
可用的指標 key（來源都是網站已有數字，對應 tools/health.py 與 assets/longterm.js 的定義）：
  revYoy 營收年增（近四季） epsYoy EPS 年增（近四季） gm 毛利率（近四季） om 營業利益率（近四季） fcfRate 自由現金流率（近四季）
  roic roe buybackTtm（近四季回購金額，單位同公司金額） dilYoy 稀釋股數年增 pe 本益比 fpe 預估本益比 peg fcfY 自由現金流殖利率 evS EV/Sales
燈號：g 綠＝最新一點達標；y 黃＝最新一點沒達標、但前一點有達標（或前一點算不出來）；r 紅＝連續兩點都沒達標（季指標看最近兩季、月指標看最近兩個月）；n 灰＝這個指標目前算不出來（寫原因）。
排程只更新燈號與 history，絕不改論點文字或門檻。

用法：python3 tools/thesis.py             列出所有 approved 論點的目前燈號，紅燈置頂
      python3 tools/thesis.py --record 代號  把最新一季的燈號記進 history（每季快報時做一次）
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import health as H, pe as PE  # noqa

KEYS = ("revYoy", "epsYoy", "gm", "om", "fcfRate", "roic", "roe", "buybackTtm", "dilYoy", "pe", "fpe", "peg", "fcfY", "evS")
MONTHLY = ("pe", "fpe", "peg", "fcfY", "evS")


def ttm(Q, k):
    out = []
    for i in range(len(Q)):
        v = [Q[j].get(k) for j in range(i - 3, i + 1)] if i >= 3 else None
        out.append(None if v is None or any(x is None for x in v) else sum(v))
    return out


def series(Q, val, health):
    """回傳 {key: [(label, value|None), …]}。"""
    rev, eps, ni = ttm(Q, "rev"), ttm(Q, "eps"), ttm(Q, "ni")
    lab = [q["q"] for q in Q]
    yoy = lambda a: [(lab[i], (a[i] / a[i - 4] - 1) * 100 if i >= 4 and a[i] and a[i - 4] and a[i] > 0 and a[i - 4] > 0 else None) for i in range(len(a))]
    gm = []
    for i in range(len(Q)):
        w = Q[i - 3:i + 1] if i >= 3 else None
        r = sum(q["rev"] for q in w) if w else 0
        gm.append((lab[i], round(sum(q["gm"] * q["rev"] for q in w) / r, 2) if w and r and all(q.get("gm") is not None for q in w) else None))
    om = []
    for i in range(len(Q)):
        w = Q[i - 3:i + 1] if i >= 3 else None
        r = sum(q["rev"] for q in w) if w else 0
        om.append((lab[i], round(sum(q["om"] * q["rev"] for q in w) / r, 2) if w and r and all(q.get("om") is not None for q in w) else None))
    ocf, cap = ttm(Q, "ocf"), ttm(Q, "capex")
    fcfr = [(lab[i], round((ocf[i] - cap[i]) / rev[i] * 100, 2) if None not in (ocf[i], cap[i], rev[i]) and rev[i] else None) for i in range(len(Q))]
    S = {"revYoy": yoy(rev), "epsYoy": yoy(eps), "gm": gm, "om": om, "fcfRate": fcfr}
    if health:
        S["roic"] = [(x["q"], x["roic"]) for x in health["quarterly"]]
        S["roe"] = [(x["q"], x["roe"]) for x in health["quarterly"]]
        S["buybackTtm"] = [(x["q"], x["buybackTtm"]) for x in health["quarterly"]]
        S["dilYoy"] = [(x["q"], x["dilYoy"]) for x in health["quarterly"]]
        S["peg"] = [(x["m"], x["peg"]) for x in health["monthly"]]
        S["fcfY"] = [(x["m"], x["fcfY"]) for x in health["monthly"]]
        S["evS"] = [(x["m"], x["evS"]) for x in health["monthly"]]
    if val:
        S["pe"] = [(x["m"], x["pe"]) for x in val["monthly"]]
        S["fpe"] = [(x["m"], x["fpe"]) for x in val["monthly"]]
    return S


def meets(v, op, thr):
    return v >= thr if op == ">=" else v <= thr


def lights(th, Q, val, health):
    S = series(Q, val, health)
    out = {}
    for m in th.get("metrics", []):
        s = [p for p in S.get(m["k"], [])]
        if m["k"] in ("dilYoy", "buybackTtm", "roe", "roic"):   # 季度指標：最新一季算不出來時，改取最近算得出來的季度（label 會標明季別）
            while len(s) > 1 and s[-1][1] is None:
                s = s[:-1]
        if not s or s[-1][1] is None:
            out[m["k"]] = {"light": "n", "now": None, "label": s[-1][0] if s else None, "why": "最新一點算不出來（欄位待確認、分母不是正數或沒有資料）"}
            continue
        now, prev = s[-1][1], (s[-2][1] if len(s) > 1 else None)
        ok = meets(now, m["op"], m["thr"])
        pok = prev is not None and meets(prev, m["op"], m["thr"])
        out[m["k"]] = {"light": "g" if ok else ("y" if (pok or prev is None) else "r"), "now": now, "label": s[-1][0], "prev": prev}
    return out


def load_all():
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    for c in cfg["companies"]:
        if not c.get("enabled"):
            continue
        p = os.path.join(ROOT, "data", "thesis", c["code"] + ".json")
        if os.path.exists(p):
            yield c, json.load(open(p, encoding="utf8"))


def context(code):
    D = json.load(open(os.path.join(ROOT, "data", code + ".json"), encoding="utf8"))
    cfg = json.load(open(os.path.join(ROOT, "companies.json"), encoding="utf8"))
    c = next(x for x in cfg["companies"] if x["code"] == code)
    pf = os.path.join(ROOT, "data", "prices", code + ".json")
    prices = json.load(open(pf, encoding="utf8")) if c.get("price") and os.path.exists(pf) else None
    Q = H.normq(D, c.get("schema"))
    val = PE.compute(D["quarters"], prices)
    return D, val, H.compute(Q, val, prices), Q


def main():
    a = sys.argv[1:]
    if a[:1] == ["--record"]:
        code = a[1]
        p = os.path.join(ROOT, "data", "thesis", code + ".json")
        th = json.load(open(p, encoding="utf8"))
        D, val, hl, Q = context(code)
        L = lights(th, Q, val, hl)
        q = D["quarters"][-1]["q"]
        th["history"] = [h for h in th.get("history", []) if h["q"] != q] + [{"q": q, "lights": {k: v["light"] for k, v in L.items()}}]
        json.dump(th, open(p, "w", encoding="utf8"), ensure_ascii=False, indent=1)
        open(p, "a").write("\n")
        print(code, q, {k: v["light"] for k, v in L.items()})
        return
    rows, red = [], []
    for c, th in load_all():
        if th.get("status") != "approved":
            rows.append(f"  {c['code']}：草稿（{th.get('updated')}），等使用者確認，不上線")
            continue
        D, val, hl, Q = context(c["code"])
        L = lights(th, Q, val, hl)
        s = " ".join(f"{k}:{v['light']}" for k, v in L.items())
        rows.append(f"  {c['code']}：{s}")
        red += [f"{c['code']}.{k}" for k, v in L.items() if v["light"] == "r"]
    print("紅燈：" + (("、".join(red)) if red else "無"))
    print("\n".join(rows) or "  還沒有論點卡")


if __name__ == "__main__":
    main()
