"""到價提醒瀏覽器測試用的「合成」資料（不是真實行情，也不是真實提醒）。
先用 tools/tests/kbar_fixture.py 產生同一個臨時資料夾的合成 K 棒，再由本檔：
  1. 複製 companies.json、data/etf/config.json 到臨時資料夾（tools/alerts.py 的標的清單要讀）
  2. 寫一組合成提醒規則（已到價 / 監控中 / 已關閉）並加密 → 輸出給測試的假 GitHub（不寫進臨時資料夾的 data/alerts/rules.enc.json，
     因為測試用真的 Worker 核心 worker/core.js＋假 GitHub 來讀寫）
  3. 用 tools/alerts.py 的 run() 真的跑一次判斷到價（不上網、不發訊息）→ 臨時資料夾的 data/alerts/state.enc.json
  4. 輸出 ALERT_KEY（Worker 用的金鑰）、規則檔、每日行情報告 HTML（螢幕截圖用）
只寫到你指定的臨時資料夾（絕不寫進 repo 的 data/）。
用法：python3 tools/tests/alerts_fixture.py <臨時資料夾>      最後一行輸出 JSON。"""
import base64, datetime as dt, io, json, os, shutil, sys
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, HERE)
import alerts as A            # noqa: E402
import kbar_fixture as KF     # noqa: E402


def build(tmp):
    pw = KF.PASSWORD
    shutil.copy(os.path.join(ROOT, "companies.json"), os.path.join(tmp, "companies.json"))
    os.makedirs(os.path.join(tmp, "data", "etf"), exist_ok=True)
    shutil.copy(os.path.join(ROOT, "data", "etf", "config.json"), os.path.join(tmp, "data", "etf", "config.json"))
    paths = A.Paths(tmp)
    key = A.derive_key(pw, paths)
    items = {i["code"]: i for i in A.universe(paths)}

    def bars_of(code):
        return A.load_bars(items[code], key, paths)[0]

    nv, ym, vo = bars_of("nvda"), bars_of("ym"), bars_of("etf_voo")
    last_nv, last_ym, last_vo = nv[-1], ym[-1], vo[-1]
    since_nv = nv[-31][0]
    low30 = min(b[3] for b in nv[-30:])
    now = "2026-11-20T00:00:00Z"
    base = {"dirAuto": True, "n": "", "on": True, "created": now, "updated": now, "offAt": None}
    rules = [
        # 已到價：往下跌破，起算日 30 根前，目標價放在這 30 根最低價上方一點 → 一定到價
        dict(base, id="hit1", code="nvda", kind="stock", name="輝達", p=round(low30 + 0.5, 2), dir="down", mode="price", since=since_nv, n="跌破就要看財報", base={"t": since_nv, "c": nv[-31][4]}),
        # 監控中：漲破，最新收盤上方 8%
        dict(base, id="on1", code="nvda", kind="stock", name="輝達", p=round(last_nv[4] * 1.08, 2), dir="up", mode="price", since=last_nv[0], base={"t": last_nv[0], "c": last_nv[4]}),
        # 監控中：百分比模式 −10%（小道瓊期貨）
        dict(base, id="on2", code="ym", kind="fut", name="小道瓊", p=round(last_ym[4] * 0.9), dir="down", mode="pct", pct=-10, since=last_ym[0], n="大跌再加碼", base={"t": last_ym[0], "c": last_ym[4]}),
        # 已關閉
        dict(base, id="off1", code="nvda", kind="stock", name="輝達", p=round(last_nv[4] * 0.85, 2), dir="down", mode="price", since=last_nv[0], on=False, offAt="2026-11-21T00:00:00Z", base={"t": last_nv[0], "c": last_nv[4]}),
        dict(base, id="off2", code="etf_voo", kind="etf", name="先鋒標普 500", p=round(last_vo[4] * 1.2, 2), dir="up", mode="price", since=last_vo[0], on=False, offAt="2026-11-21T00:00:00Z", base={"t": last_vo[0], "c": last_vo[4]}),
    ]
    rules_file = A.enc({"v": 1, "rules": rules, "updated": now}, key)
    # 用真的 tools/alerts.py 判斷到價，產生 state.enc.json（不上網、不發訊息）
    os.makedirs(paths.alerts, exist_ok=True)
    A.write_json(paths.rules, rules_file)
    buf = io.StringIO()
    with redirect_stdout(buf):
        A.run(paths, {"FUTURES_PASSWORD": pw}, dt.datetime(2026, 11, 24, 0, 0, tzinfo=dt.timezone.utc), lambda s, d: [])
    os.remove(paths.rules)         # 規則改由測試的假 GitHub 提供
    # 每日行情報告（螢幕截圖用）
    st = A.dec(A.jload(paths.state), key)
    market, rows = {}, []
    today = dt.date(2026, 11, 24)
    for it in items.values():
        bars, ok = A.load_bars(it, key, paths)
        if bars:
            r = A.market_row(it, bars, ok, today)
            rows.append(r)
            market[it["code"]] = r
    hit_l, on_l, _ = A.rule_lines(rules, st["hits"], market)
    html_s = A.build_html(hit_l, on_l, rows, today, [c for c in items if c not in market])
    return {"alertKey": base64.b64encode(key).decode(), "rules": rules_file, "hitIds": sorted(st["hits"]), "lastNvda": {"t": last_nv[0], "c": last_nv[4]},
            "reportHtml": html_s, "subject": A.subject(len(hit_l), len(on_l), today), "ruleCount": len(rules)}


if __name__ == "__main__":
    if len(sys.argv) < 2 or os.path.abspath(sys.argv[1]).startswith(os.path.join(ROOT, "data")):
        sys.exit("用法：python3 tools/tests/alerts_fixture.py <臨時資料夾>（不可在 repo 的 data/ 底下；要先跑 kbar_fixture.py）")
    print(json.dumps(build(sys.argv[1])))
