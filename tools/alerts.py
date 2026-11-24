"""到價提醒＋每日行情報告（GitHub Actions 的 alerts-daily 執行，不經過 Claude）。

流程：
  1. 讀 data/alerts/rules.enc.json（只有 Cloudflare Worker 會寫）與 state.enc.json（只有本程式寫）。
     兩個檔都用「看盤密碼」推導的 AES-256-GCM 金鑰加密（格式同 data/kbar、data/futures）。檔案不存在＝沒有提醒／沒有到價紀錄。
  2. 讀全部追蹤標的（個股＋ETF＋期貨）的日 K（data/kbar、data/futures），再用 Yahoo 補「最後一根之後、已收盤」的日線。
  3. 判斷到價（當天最高價／最低價碰到就算），更新 state.hits、state.last。
  4. 台北今天還沒寄過（state.lastSent）就發：
       Gmail：每天都寄「每日行情報告」（提醒在最上方＋追蹤標的總表）
       ntfy、Telegram：只在「有到價中的提醒」時發
  5. log 只印數量與管道結果，不印代號、價格、金鑰（公開 repo 的 Actions log 誰都看得到）。

用法：
  FUTURES_PASSWORD=... python3 tools/alerts.py            # 正常執行
  FUTURES_PASSWORD=... python3 tools/alerts.py --test     # 每個已設定的管道發一則測試訊息（不改 state）
  FUTURES_PASSWORD=... python3 tools/alerts.py --derive-key   # 印出 Worker 要用的 ALERT_KEY（只給部署 workflow 用，輸出不可進 log）
環境變數：FUTURES_PASSWORD（必要）、NTFY_TOPIC、GMAIL_USER、GMAIL_APP_PASSWORD、TELEGRAM_BOT_TOKEN、TELEGRAM_CHAT_ID（都選用，有設才發）。
"""
import base64, datetime as dt, html, json, math, os, smtplib, ssl, sys, urllib.error, urllib.request, zlib
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

TPE = ZoneInfo("Asia/Taipei")
SITE = "https://zlo-25.github.io/Enterprise-Revenue-Dashboard/"
ALERTS_URL = SITE + "alerts/"
FUT_NAMES = {"ym": "小道瓊", "nq": "小那指", "tx": "大台指"}
FUT_YAHOO = {"ym": "YM=F", "nq": "NQ=F"}           # tx（大台指）Yahoo 沒有，不補
FUT_DP = {"ym": 0, "nq": 2, "tx": 0}
STALE_DAYS = 4                                      # 超過 4 天沒新 K 棒標「資料較舊」（與前端 FUT.fresh 同一個門檻）
KEEP_SENT = 30


def log(*a):
    print(*a, flush=True)


class Paths:
    """所有檔案位置集中在這裡，測試用臨時資料夾換掉 root 即可（不會碰 repo 的 data/）。"""

    def __init__(self, root=ROOT):
        self.root = root
        self.alerts = os.path.join(root, "data", "alerts")
        self.kbar = os.path.join(root, "data", "kbar")
        self.fut = os.path.join(root, "data", "futures")
        self.rules = os.path.join(self.alerts, "rules.enc.json")
        self.state = os.path.join(self.alerts, "state.enc.json")


def jload(path, default=None):
    try:
        with open(path, encoding="utf8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


# ---------- 加解密（格式同 tools/futures_update.py：明文 = zlib(JSON)，AES-256-GCM，{"iv","ct"} base64） ----------
def derive_key(password, paths=None):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    paths = paths or Paths()
    kp = jload(os.path.join(paths.fut, "key.json"))
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(kp["salt"]), iterations=kp["iter"]).derive(password.encode("utf8"))


def enc(obj, key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    iv = os.urandom(12)
    plain = zlib.compress(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf8"), 9)
    return {"v": 1, "iv": base64.b64encode(iv).decode(), "ct": base64.b64encode(AESGCM(key).encrypt(iv, plain, None)).decode()}


def dec(file, key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return json.loads(zlib.decompress(AESGCM(key).decrypt(base64.b64decode(file["iv"]), base64.b64decode(file["ct"]), None)))


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf8") as f:
        json.dump(obj, f, separators=(",", ":"))


# ---------- 到價判斷（與 assets/alerts.js 的 hitFor 同一套；共用案例 tools/tests/alerts_cases.json） ----------
def num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def hit_for(rule, bars):
    """bars：[[t,o,h,l,c,v]…] 依日期排序。t > since 的第一根滿足條件的 K 棒：
    dir=up：h ≥ p；dir=down：l ≤ p。回傳 {t, px, side, p}；沒有回 None。缺 h／l 的 K 棒略過。"""
    since = rule.get("since") or ""
    p = rule.get("p")
    if not num(p):
        return None
    up = rule.get("dir") == "up"
    for b in bars:
        if b[0] <= since:
            continue
        v = b[2] if up else b[3]
        if not num(v):
            continue
        if (v >= p) if up else (v <= p):
            return {"t": b[0], "px": v, "side": "h" if up else "l", "p": p}
    return None


def hit_valid(rule, hit):
    """state 裡的到價紀錄是否仍然有效：改價、重新開啟（since 往後）、改方向都會作廢。"""
    if not hit or not rule.get("on"):
        return False
    since = rule.get("since") or ""
    side_ok = hit.get("side") == ("h" if rule.get("dir") == "up" else "l")
    return hit.get("t", "") > since and hit.get("p") == rule.get("p") and side_ok


def evaluate(rules, bars_by_code, old_hits):
    """回傳新的 hits dict（只含仍有效、且啟用中的提醒）。已到價的提醒維持到價（直到使用者關閉或改價）。"""
    hits = {}
    for r in rules:
        if not r.get("on"):
            continue
        old = (old_hits or {}).get(r["id"])
        if hit_valid(r, old):
            hits[r["id"]] = old
            continue
        h = hit_for(r, bars_by_code.get(r["code"]) or [])
        if h:
            hits[r["id"]] = h
    return hits


def pct_price(base_c, pct):
    return round(base_c * (1 + pct / 100.0), 4)


# ---------- 標的清單 ----------
def universe(paths=None):
    """全部追蹤標的，依網站分類：個股（companies.json sector 順序）→ ETF → 期貨。
    每項：{code, name, ticker, kind, sector, ccy, yahoo, dp}"""
    paths = paths or Paths()
    cfg = jload(os.path.join(paths.root, "companies.json"), {"companies": []})
    out = []
    for c in cfg["companies"]:
        y = (c.get("price") or {}).get("yahoo")
        if c.get("enabled") is False or not y:
            continue
        out.append({"code": c["code"], "name": c["name"], "ticker": c.get("ticker") or c["code"].upper(), "kind": "stock",
                    "sector": c.get("sector") or "其他", "ccy": (c.get("price") or {}).get("currency") or c.get("currency") or "", "yahoo": y,
                    "dp": 0 if y.endswith(".KS") else 2})
    ecfg = jload(os.path.join(paths.root, "data", "etf", "config.json"), {"etfs": []})
    for e in ecfg.get("etfs") or []:
        out.append({"code": e["code"], "name": e.get("zh") or e["name"], "ticker": e["ticker"], "kind": "etf", "sector": "ETF",
                    "ccy": e.get("currency") or "", "yahoo": e["yahoo"], "dp": 2})
    for code in ("ym", "nq", "tx"):
        out.append({"code": code, "name": FUT_NAMES[code], "ticker": code.upper(), "kind": "fut", "sector": "指數期貨", "ccy": "點",
                    "yahoo": FUT_YAHOO.get(code), "dp": FUT_DP[code]})
    return out


# ---------- 讀 K 棒 ----------
def load_bars(item, key, paths, want_hist=True):
    """回傳 (bars, hist_ok)。bars 依日期排序、去重。股票／ETF：近期檔＋歷史檔；期貨：單一檔。
    檔案不存在或解不開 → ([], False)。hist_ok=False 表示歷史檔讀不到（歷史最高只能用近期資料，要標出來）。"""
    code = item["code"]
    if item["kind"] == "fut":
        f = jload(os.path.join(paths.fut, code + ".enc.json"))
        if not f:
            return [], False
        try:
            return dec(f, key)["bars"], True
        except Exception:  # noqa: BLE001
            return [], False
    f = jload(os.path.join(paths.kbar, code + ".enc.json"))
    if not f:
        return [], False
    try:
        recent = dec(f, key)["bars"]
    except Exception:  # noqa: BLE001
        return [], False
    hist, ok = [], True
    h = f.get("hist")
    if want_hist and h and h.get("file"):
        try:
            hist = dec(jload(os.path.join(paths.kbar, h["file"])), key)["bars"]
        except Exception:  # noqa: BLE001
            ok = False
    seen = {b[0] for b in recent}
    bars = sorted([b for b in hist if b[0] not in seen] + list(recent), key=lambda b: b[0])
    return bars, ok


# ---------- Yahoo 補價（只補已收盤的日 K） ----------
def closed_through(item, now_utc):
    """已經收盤的最新交易日（日期字串）。股票／ETF：交易所當地收盤＋20 分鐘後才算今天；期貨：CT 16:15 後才算今天（同 futures_update）。"""
    import futures_update as FU
    import prices_daily as PD
    if item["kind"] == "fut":
        return FU.last_closed_date(now_utc.astimezone(FU.CT)).isoformat()
    tz, hh, mm = PD.exch(item["yahoo"])
    now = now_utc.astimezone(ZoneInfo(tz))
    done = now.hour * 60 + now.minute >= hh * 60 + mm + 20
    return (now.date() if done else now.date() - dt.timedelta(days=1)).isoformat()


def yahoo_fetch(sym, start):
    """真正上網的那一小段：回傳 [(date, o, h, l, c, v)]（可含 NaN）。測試用假的取代。"""
    import yfinance as yf
    df = yf.Ticker(sym).history(start=start, end=(dt.date.today() + dt.timedelta(days=2)).isoformat(), auto_adjust=False, actions=False)
    if df is None or df.empty:
        return []
    return [(ts.date(), float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"]), r.get("Volume")) for ts, r in df.iterrows()]


def topup(item, bars, now_utc, fetch=yahoo_fetch):
    """回傳要補在 bars 後面的新 K 棒（t > 最後一根、t ≤ 已收盤的最新交易日、o/h/l/c 都是有限數字）。沒有 Yahoo 代號回 []。丟錯＝補價失敗。"""
    if not item.get("yahoo"):
        return []
    last = bars[-1][0] if bars else "1990-01-01"
    start = (dt.date.fromisoformat(last) - dt.timedelta(days=3)).isoformat()
    limit = closed_through(item, now_utc)
    out = []
    for d, o, h, l, c, v in fetch(item["yahoo"], start):
        ds = d.isoformat() if hasattr(d, "isoformat") else str(d)
        if ds <= last or ds > limit or not all(num(x) for x in (o, h, l, c)):
            continue
        out.append([ds, round(o, 4), round(h, 4), round(l, 4), round(c, 4), int(v) if num(v) and v else None])
    return out


# ---------- 報告資料 ----------
def market_row(item, bars, hist_ok, today):
    """一檔的行情摘要：最新收盤、日漲跌、歷史最高（附日期）、資料日期、是否過舊。沒有 K 棒回 None。"""
    if not bars:
        return None
    b, p = bars[-1], (bars[-2] if len(bars) > 1 else None)
    top = max((x for x in bars if num(x[2])), key=lambda x: x[2], default=None)
    age = (today - dt.date.fromisoformat(b[0])).days
    r = {"code": item["code"], "name": item["name"], "ticker": item["ticker"], "kind": item["kind"], "sector": item["sector"], "ccy": item["ccy"], "dp": item["dp"],
         "t": b[0], "c": b[4], "chg": (b[4] / p[4] - 1) * 100 if p and num(p[4]) and p[4] else None,
         "ath": top[2] if top else None, "athT": top[0] if top else None, "athFull": hist_ok, "old": age > STALE_DAYS}
    r["fromAth"] = (b[4] / r["ath"] - 1) * 100 if r["ath"] else None
    return r


def fmt(v, dp=2):
    return "—" if v is None else f"{v:,.{dp}f}"


def sgn(v, dp=2):
    return "—" if v is None else ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):.{dp}f}%"


def mdd(t):
    return t[5:].replace("-", "/") if t else ""


def dir_word(r):
    return "漲破" if r.get("dir") == "up" else "跌破"


def rule_lines(rules, hits, market):
    """提醒分三組。回傳 (已到價, 監控中, 已關閉)；每筆是 dict（含 rule、hit、last、dist%）。
    已到價依到價日新到舊；監控中依「距目標 %」絕對值由近到遠。"""
    hit_l, on_l, off_l = [], [], []
    for r in rules:
        m = market.get(r["code"])
        last = m["c"] if m else None
        dist = (r["p"] / last - 1) * 100 if last else None
        row = {"rule": r, "hit": hits.get(r["id"]), "m": m, "last": last, "dist": dist}
        if not r.get("on"):
            off_l.append(row)
        elif row["hit"]:
            hit_l.append(row)
        else:
            on_l.append(row)
    hit_l.sort(key=lambda x: x["hit"]["t"], reverse=True)
    on_l.sort(key=lambda x: abs(x["dist"]) if x["dist"] is not None else 1e9)
    return hit_l, on_l, off_l


def px(rule, m, v):
    dp = (m or {}).get("dp", 2)
    return fmt(v, dp)


def target_text(r, m):
    s = px(r, m, r["p"])
    if r.get("mode") == "pct" and r.get("pct") is not None and r.get("base"):
        b = r["base"]
        s += f"（{sgn(r['pct'], 1 if abs(r['pct']) % 1 else 0)}，基準 {px(r, m, b['c'])}，{mdd(b['t'])}）"
    return s


def row_text(x):
    r, h, m = x["rule"], x["hit"], x["m"]
    s = f"{r['name']} {dir_word(r)} {target_text(r, m)}"
    if h:
        s += f"｜到價 {mdd(h['t'])}，當天{'最高' if h['side'] == 'h' else '最低'} {px(r, m, h['px'])}"
    s += f"｜最新收盤 {px(r, m, x['last'])}" if x["last"] is not None else "｜最新收盤 —（沒有 K 棒資料）"
    if x["dist"] is not None:
        s += f"，距目標 {sgn(x['dist'])}（價差 {px(r, m, abs(r['p'] - x['last']))}）"
    if r.get("n"):
        s += f"｜{r['n']}"
    return s


def subject(hit_n, on_n, today):
    d = f"{today.month:02d}/{today.day:02d}"
    return f"🔔 到價 {hit_n} 檔｜每日行情 {d}" if hit_n else f"每日行情 {d}（提醒 {on_n} 條監控中）"


def alert_section_text(hit_l, on_l):
    if not hit_l and not on_l:
        return "到價提醒\n目前沒有設定提醒\n"
    out = ["到價提醒"]
    if hit_l:
        out.append(f"【已到價 {len(hit_l)} 檔】")
        out += ["・" + row_text(x) for x in hit_l]
    if on_l:
        out.append(f"【監控中 {len(on_l)} 條（依距目標由近到遠）】")
        out += ["・" + row_text(x) for x in on_l]
    return "\n".join(out) + "\n"


def groups(rows):
    """依網站分類分組：個股的 sector 順序＝出現順序，ETF、期貨放最後。"""
    order, by = [], {}
    for x in rows:
        if x["sector"] not in by:
            by[x["sector"]] = []
            order.append(x["sector"])
        by[x["sector"]].append(x)
    tail = [s for s in ("ETF", "指數期貨") if s in by]
    order = [s for s in order if s not in tail] + tail
    return [(s, by[s]) for s in order]


def table_text(rows):
    out = ["追蹤標的總表（最新收盤｜日漲跌｜距歷史最高）"]
    for sector, arr in groups(rows):
        out.append(f"【{sector}】")
        for x in arr:
            cur = f" {x['ccy']}" if x["ccy"] else ""
            ath = f"{sgn(x['fromAth'])}（高 {fmt(x['ath'], x['dp'])}，{x['athT']}{'' if x['athFull'] else '，只含近期資料'}）" if x["ath"] else "—"
            out.append(f"・{x['name']}（{x['ticker']}） {fmt(x['c'], x['dp'])}{cur}｜{sgn(x['chg'])}｜距高點 {ath}｜資料 {mdd(x['t'])}" + ("｜資料較舊" if x["old"] else ""))
    return "\n".join(out) + "\n"


FOOT_TEXT = ("管理提醒：" + ALERTS_URL + "\n資料來源：Yahoo 日線（已依股票分割調整、不含股利）與本站每日 K 棒；延遲資料，只供研究，不構成投資建議。\n")


def build_text(hit_l, on_l, rows, today, missing=()):
    t = alert_section_text(hit_l, on_l) + "\n" + table_text(rows)
    if missing:
        t += f"\n沒有 K 棒資料的標的：{len(missing)} 檔（略過）\n"
    return t + "\n" + FOOT_TEXT


# ---------- HTML 信（行動裝置：單欄、窄表格、行內樣式＋深色模式） ----------
def esc(s):
    return html.escape(str(s), quote=True)


STYLE = """<style>
.w{max-width:640px;margin:0 auto;font:14px/1.5 -apple-system,'Segoe UI','Noto Sans TC',sans-serif;color:#141413}
.w h2{font-size:16px;margin:18px 0 6px}.w h3{font-size:13px;margin:14px 0 4px;color:#4f4e4a}
.w table{border-collapse:collapse;width:100%}.w td{padding:6px 4px;border-bottom:1px solid #e4e3dc;vertical-align:top}
.w .n{font-weight:600}.w .s{font-size:12px;color:#6c6a64}.w .r{text-align:right;white-space:nowrap}
.w .hit{background:#fdecea}.w .up{color:#c62828}.w .dn{color:#138a52}.w .old{color:#b26a00;font-size:12px}
@media (prefers-color-scheme:dark){.w{color:#f6f6f3}.w h3,.w .s{color:#a3a197}.w td{border-color:#2c2c2a}.w .hit{background:#3a1d1d}.w .up{color:#f06a6a}.w .dn{color:#2fbf7f}.w .old{color:#e0a040}}
</style>"""


def html_rule_rows(items, hit):
    out = []
    for x in items:
        r, h, m = x["rule"], x["hit"], x["m"]
        sub = f"目標 {esc(target_text(r, m))}"
        if h:
            sub += f"<br>到價 {mdd(h['t'])}，當天{'最高' if h['side'] == 'h' else '最低'} {esc(px(r, m, h['px']))}"
        if r.get("n"):
            sub += f"<br>{esc(r['n'])}"
        last = esc(px(r, m, x["last"])) if x["last"] is not None else "—"
        dist = ""
        if x["dist"] is not None:
            dist = f"<br><span class=\"s\">距目標 {esc(sgn(x['dist']))}<br>價差 {esc(px(r, m, abs(r['p'] - x['last'])))}</span>"
        cls = ' class="hit"' if hit else ""
        out.append(f"<tr{cls}><td><span class=\"n\">{'🔔 ' if hit else ''}{esc(r['name'])} {dir_word(r)}</span><br><span class=\"s\">{sub}</span></td>"
                   f"<td class=\"r\">{last}{dist}</td></tr>")
    return "".join(out)


def build_html(hit_l, on_l, rows, today, missing=()):
    p = [STYLE, '<div class="w">', "<h2>到價提醒</h2>"]
    if not hit_l and not on_l:
        p.append("<p>目前沒有設定提醒</p>")
    if hit_l:
        p.append(f"<h3 class=\"up\">已到價（{len(hit_l)} 檔）</h3><table>{html_rule_rows(hit_l, True)}</table>")
    if on_l:
        p.append(f"<h3>監控中（{len(on_l)} 條，依距目標由近到遠）</h3><table>{html_rule_rows(on_l, False)}</table>")
    p.append("<h2>追蹤標的總表</h2>")
    for sector, arr in groups(rows):
        p.append(f"<h3>{esc(sector)}（{len(arr)}）</h3><table>")
        for x in arr:
            cur = f" {esc(x['ccy'])}" if x["ccy"] else ""
            cls = "up" if (x["chg"] or 0) > 0 else "dn" if (x["chg"] or 0) < 0 else ""
            ath = ""
            if x["ath"]:
                ath = f"高 {esc(fmt(x['ath'], x['dp']))}（{esc(x['athT'])}）" + ("" if x["athFull"] else "，只含近期資料")
            old = f"<br><span class=\"old\">資料較舊（{mdd(x['t'])}）</span>" if x["old"] else ""
            p.append(f"<tr><td><span class=\"n\">{esc(x['name'])}</span> <span class=\"s\">{esc(x['ticker'])}</span><br><span class=\"s\">{ath}</span>{old}</td>"
                     f"<td class=\"r\">{esc(fmt(x['c'], x['dp']))}<span class=\"s\">{cur}</span><br><span class=\"{cls}\">{esc(sgn(x['chg']))}</span>"
                     f"<br><span class=\"s\">距高點 {esc(sgn(x['fromAth']))}</span></td></tr>")
        p.append("</table>")
    if missing:
        p.append(f"<p class=\"s\">沒有 K 棒資料的標的：{len(missing)} 檔（略過）</p>")
    p.append(f"<p class=\"s\"><a href=\"{ALERTS_URL}\">管理提醒</a>　資料來源：Yahoo 日線（已依股票分割調整、不含股利）與本站每日 K 棒；延遲資料，只供研究，不構成投資建議。</p></div>")
    return "<!doctype html><html lang=\"zh-Hant\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"></head><body>" + "".join(p) + "</body></html>"


# ---------- 通知內容 ----------
def ntfy_text(hit_l):
    """只寫名稱與方向，不寫價格（主題名稱等於密碼，外洩時影響最小）。"""
    names = [f"{x['rule']['name']} {dir_word(x['rule'])}" for x in hit_l]
    shown = "、".join(names[:10]) + (f" …等 {len(names)} 檔" if len(names) > 10 else "")
    return f"到價提醒 {len(hit_l)} 檔：{shown}"


def telegram_text(hit_l, on_l):
    return (alert_section_text(hit_l, on_l) + "\n管理提醒：" + ALERTS_URL)[:4000]


# ---------- 發送（各管道一個函式；測試用假的取代 http_post、smtp_send） ----------
class SendError(Exception):
    pass


def http_post(url, data, headers=None, timeout=30):
    """回傳 (status, body 文字)。錯誤只丟 SendError，訊息不含網址（網址裡可能有 bot token）。"""
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf8", "replace")
    except urllib.error.HTTPError as e:
        raise SendError(f"HTTP {e.code}")
    except Exception as e:  # noqa: BLE001
        raise SendError(type(e).__name__)


def smtp_send(user, password, msg):
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as s:
            s.login(user, password)
            s.send_message(msg)
    except Exception as e:  # noqa: BLE001
        raise SendError(type(e).__name__)


def send_ntfy(topic, title, message):
    body = json.dumps({"topic": topic, "title": title, "message": message, "click": ALERTS_URL, "tags": ["bell"]}, ensure_ascii=False).encode("utf8")
    st, _ = http_post("https://ntfy.sh/", body, {"Content-Type": "application/json"})
    if st >= 300:
        raise SendError(f"HTTP {st}")


def send_gmail(user, password, subj, text, html_body):
    from email.message import EmailMessage
    m = EmailMessage()
    m["Subject"], m["From"], m["To"] = subj, user, user
    m.set_content(text)
    m.add_alternative(html_body, subtype="html")
    smtp_send(user, password, m)


def telegram_chat(token, env_chat, state):
    """chat id：環境變數 > state.tg > getUpdates 找最新的私訊（先在 Telegram 對 bot 說一句話）。找不到回 None。"""
    if env_chat:
        return str(env_chat)
    if state.get("tg"):
        return str(state["tg"])
    st, body = http_post(f"https://api.telegram.org/bot{token}/getUpdates", None)
    for u in reversed(json.loads(body).get("result") or []):
        ch = (u.get("message") or {}).get("chat") or {}
        if ch.get("type") == "private" and ch.get("id") is not None:
            state["tg"] = ch["id"]
            return str(ch["id"])
    return None


def send_telegram(token, chat, text):
    body = json.dumps({"chat_id": chat, "text": text, "disable_web_page_preview": True}, ensure_ascii=False).encode("utf8")
    st, _ = http_post(f"https://api.telegram.org/bot{token}/sendMessage", body, {"Content-Type": "application/json"})
    if st >= 300:
        raise SendError(f"HTTP {st}")


def configured(env):
    """已設定的管道（有 secret 才算）。"""
    ch = []
    if env.get("NTFY_TOPIC"):
        ch.append("ntfy")
    if env.get("GMAIL_USER") and env.get("GMAIL_APP_PASSWORD"):
        ch.append("Gmail")
    if env.get("TELEGRAM_BOT_TOKEN"):
        ch.append("Telegram")
    return ch


def deliver(plan, env, state):
    """plan：{"ntfy": (title, msg) | None, "Gmail": (subj, text, html) | None, "Telegram": text | None}。
    回傳 {管道: True/False}（只含有設定且 plan 有內容的）。log 只印成功／失敗與錯誤類型。"""
    res = {}
    for name in ("ntfy", "Gmail", "Telegram"):
        if name not in configured(env) or not plan.get(name):
            continue
        try:
            if name == "ntfy":
                send_ntfy(env["NTFY_TOPIC"], *plan[name])
            elif name == "Gmail":
                send_gmail(env["GMAIL_USER"], env["GMAIL_APP_PASSWORD"], *plan[name])
            else:
                chat = telegram_chat(env["TELEGRAM_BOT_TOKEN"], env.get("TELEGRAM_CHAT_ID"), state)
                if not chat:
                    raise SendError("找不到 chat id（請先在 Telegram 對 bot 傳一句話）")
                send_telegram(env["TELEGRAM_BOT_TOKEN"], chat, plan[name])
            res[name] = True
            log(f"  {name}：成功")
        except SendError as e:
            res[name] = False
            log(f"  {name}：失敗（{e}）")
    return res


# ---------- 主流程 ----------
def run(paths=None, env=None, now_utc=None, fetch=yahoo_fetch, test=False):
    """回傳結束碼。paths／env／now_utc／fetch 都可換成測試用的。"""
    paths = paths or Paths()
    env = os.environ if env is None else env
    now_utc = now_utc or dt.datetime.now(dt.timezone.utc)
    pw = env.get("FUTURES_PASSWORD")
    if not pw:
        log("沒有 FUTURES_PASSWORD，停止（絕不寫出明文）")
        return 1
    key = derive_key(pw, paths)
    chans = configured(env)
    if test:
        log(f"測試訊息：已設定的管道 {len(chans)} 個")
        plan = {"ntfy": ("到價提醒測試", "測試訊息：到價提醒設定成功"),
                "Gmail": ("到價提醒測試", "測試訊息：到價提醒設定成功\n管理提醒：" + ALERTS_URL, "<p>測試訊息：到價提醒設定成功</p>"),
                "Telegram": "測試訊息：到價提醒設定成功"}
        res = deliver(plan, env, {})
        return 1 if chans and not any(res.values()) else 0

    rd = jload(paths.rules)
    try:
        rules = dec(rd, key).get("rules", []) if rd else []
    except Exception:  # noqa: BLE001
        log("提醒規則檔解不開（密碼換過？Worker 的 ALERT_KEY 要重新部署）")
        return 1
    sd = jload(paths.state)
    try:
        state = dec(sd, key) if sd else {}
    except Exception:  # noqa: BLE001
        log("到價紀錄檔解不開，當成沒有紀錄重新開始")
        state = {}
    state.setdefault("hits", {})
    state.setdefault("sent", [])
    today = now_utc.astimezone(TPE).date()
    today_s = today.isoformat()
    on_rules = [r for r in rules if r.get("on")]
    log(f"提醒規則 {len(rules)} 條（啟用中 {len(on_rules)} 條）")

    # 1) 全部標的的 K 棒（報告要用）＋ Yahoo 補價
    items = universe(paths)
    bars_by, rows, missing, fail = {}, [], [], 0
    for it in items:
        bars, hist_ok = load_bars(it, key, paths)
        try:
            add = topup(it, bars, now_utc, fetch)
            if add:
                bars = bars + add
        except Exception:  # noqa: BLE001
            fail += 1
        if not bars:
            missing.append(it["code"])
            continue
        bars_by[it["code"]] = bars
        rows.append(market_row(it, bars, hist_ok, today))
    if fail:
        log(f"補價失敗 {fail} 檔（只用檔案裡的 K 棒）")
    log(f"標的 {len(items)} 檔，有 K 棒 {len(rows)} 檔")
    market = {r["code"]: r for r in rows}

    # 2) 到價判斷
    hits = evaluate(rules, bars_by, state.get("hits"))
    state["hits"] = hits
    state["last"] = {r["code"]: {"t": market[r["code"]]["t"], "c": market[r["code"]]["c"]} for r in rules if r["code"] in market}
    state["asOf"] = now_utc.isoformat(timespec="seconds")
    state["v"] = 1
    log(f"到價 {len(hits)} 條")
    hit_l, on_l, _off = rule_lines(rules, hits, market)
    write_json(paths.state, enc(state, key))     # 先存到價結果；發送失敗也不會丟

    # 3) 通知（一天一次）
    if state.get("lastSent") == today_s:
        log("今天已經發過，不重發")
        return 0
    plan = {}
    if hit_l:
        plan["ntfy"] = ("到價提醒", ntfy_text(hit_l))
        plan["Telegram"] = telegram_text(hit_l, on_l)
    plan["Gmail"] = (subject(len(hit_l), len(on_l), today), build_text(hit_l, on_l, rows, today, missing), build_html(hit_l, on_l, rows, today, missing))
    todo = [c for c in chans if plan.get(c)]
    if not todo:
        log("今天沒有可發的管道（沒設定管道，或沒有到價且沒設定 Gmail）")
        return 0
    res = deliver(plan, env, state)
    if not any(res.values()):
        log("全部管道都失敗")
        write_json(paths.state, enc(state, key))
        return 1
    state["lastSent"] = today_s
    state["sent"] = (state["sent"] + [{"d": today_s, "t": now_utc.isoformat(timespec="seconds"), "n": len(hit_l), "ch": [k for k, v in res.items() if v]}])[-KEEP_SENT:]
    write_json(paths.state, enc(state, key))
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--derive-key" in argv:
        pw = os.environ.get("FUTURES_PASSWORD")
        if not pw:
            return 1
        print(base64.b64encode(derive_key(pw)).decode())
        return 0
    return run(test="--test" in argv)


if __name__ == "__main__":
    sys.exit(main())
