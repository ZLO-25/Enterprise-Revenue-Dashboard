"""個股日 K（OHLCV）每日更新（GitHub Actions 的 prices-daily 一併執行，不經過 Claude）。

流程：
  1. companies.json 啟用且有 price.yahoo 的公司 → Yahoo 日線（auto_adjust=False：已依分割調整、不扣股利，
     口徑與 tools/prices_daily.py 相同；起點用 price.from）
  2. 還沒收盤的當天不收；收盤後數小時內 Yahoo 日線常是 NaN → 用報價補（標 provisional，下一班重抓覆寫）
  3. 與 data/daily/<代號>.json（同一個 job 剛更新、台股已對過證交所／櫃買）核對最近 10 個交易日收盤
  4. 切成「近期檔」（前一年 1/1 起，每天改）與「歷史檔」（更早，內容沒變就不重寫），AES-256-GCM 加密
     → data/kbar/<代號>.enc.json、data/kbar/<代號>.hist.enc.json
密碼放在 GitHub Secret FUTURES_PASSWORD（與期貨共用）、金鑰參數用 data/futures/key.json；沒有密碼就停止，絕不寫出明文。
執行紀錄（公開 repo 的 Actions log）只印筆數、日期、核對結果，不印任何價格。
資料誠實規則：價格只來自來源原值，不估計、不內插；對不起來的 K 棒不放，寫進 pending（待確認）。

用法：
  FUTURES_PASSWORD=... python3 tools/kbar_update.py [--company <代號>]
  python3 tools/kbar_update.py --stale-check     # 有公司 K 棒落後 data/daily 最新收盤日 → 列出並結束碼 1
"""
import contextlib, datetime as dt, hashlib, base64, json, os, sys, time, zlib
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import futures_update as FU   # noqa: E402  pack / sane / encrypt_password 不複製
import prices_daily as PD     # noqa: E402  exch / 收盤時間規則

COLS = ["date", "open", "high", "low", "close", "volume"]
TOL = 0.005          # 與 data/daily 收盤價容許差距 0.5%
CHECK_DAYS = 10      # 核對最近幾個交易日
SRC_URL = "https://finance.yahoo.com/quote/{}/history"
CHECK_N = "每日收盤價（data/daily；台股最新一天已對證交所／櫃買中心）"


def log(*a):
    print(*a, flush=True)


def jload(path, default=None):
    try:
        with open(path, encoding="utf8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def outdir_default():
    return os.path.join(ROOT, "data", "kbar")


# ---------- 公司清單 ----------
def companies(only=None, cfg=None):
    """公司（companies.json）＋ ETF（data/etf/config.json；只在讀真正的設定檔時加入）。
    ETF 的核對用 data/etf/daily/<代號>.json（tools/etf_update.py 同一個 job 先寫好），所以帶 dailyDir。"""
    real = cfg is None
    cfg = cfg or jload(os.path.join(ROOT, "companies.json"))
    out = [c for c in cfg["companies"] if c.get("enabled") is not False and (c.get("price") or {}).get("yahoo")
           and (not only or c["code"] == only)]
    if real:
        ecfg = jload(os.path.join(ROOT, "data", "etf", "config.json")) or {}
        out += [etf_item(e) for e in ecfg.get("etfs") or [] if not only or e["code"] == only]
    return out


def etf_item(e):
    return {"code": e["code"], "name": e["name"], "dailyDir": os.path.join(ROOT, "data", "etf", "daily"),
            "price": {"yahoo": e["yahoo"], "currency": e.get("currency"), "from": e.get("from")}}


# ---------- 切檔與 sha ----------
def cut_date(today):
    """近期檔起點：前一年 1/1。today 可為 date 或 'YYYY-MM-DD'。"""
    y = today.year if isinstance(today, dt.date) else int(str(today)[:4])
    return f"{y - 1}-01-01"


def split_bars(bars, cut):
    """回傳 (hist, recent)：hist＝日期 < cut，recent＝其餘（日期字串比較）。"""
    return [b for b in bars if b[0] < cut], [b for b in bars if b[0] >= cut]


def plain_bytes(obj):
    """與 futures_update.pack 壓縮前相同的 JSON bytes（sha 用）。"""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf8")


def hist_sha(code, bars):
    return hashlib.sha256(plain_bytes({"code": code, "cols": COLS, "bars": bars})).hexdigest()


def hist_decision(prev_outer, hist_file_exists, code, hist):
    """決定歷史檔怎麼處理。回傳 (action, sha, reason)；action: none（沒有歷史）／keep（不重寫）／rewrite。"""
    if not hist:
        return "none", None, ""
    sha = hist_sha(code, hist)
    ph = (prev_outer or {}).get("hist")
    if ph and ph.get("sha") == sha and hist_file_exists:
        return "keep", sha, ""
    if not ph:
        why = "第一次建立歷史檔"
    elif ph.get("sha") != sha:
        why = f"歷史內容改變（跨年、分割或來源修正）：{ph.get('bars')} → {len(hist)} 根，到 {hist[-1][0]}"
    else:
        why = "歷史檔不存在，重建"
    return "rewrite", sha, why


# ---------- 與 data/daily 核對 ----------
def daily_last(daily):
    """data/daily 最後一個收盤非 null 的日期；沒有檔或沒有任何收盤 → None。"""
    for r in reversed((daily or {}).get("rows") or []):
        if r[1] is not None:
            return r[0]
    return None


def verify_with_daily(bars, daily, n=CHECK_DAYS, tol=TOL):
    """回傳 (bars, pending, check)。bars 需依日期排序、價格為原值。不印價格。
    - 晚於 daily 最後有效收盤日的 K 棒不收
    - 最近 n 個交易日：daily 收盤 null，或與 K 棒收盤差 > tol → 從那天起都先不放，寫 pending
    - 沒有 daily 檔 → 照收，check.note 寫未核對"""
    if not daily or not daily.get("rows"):
        return list(bars), [], {"n": CHECK_N, "note": "未核對：沒有 data/daily 的每日收盤價可對"}
    last = daily_last(daily)
    pending = []
    if last is None:
        return [], [{"date": bars[0][0] if bars else None, "reason": "待確認：每日收盤價檔沒有任何有效收盤，K 棒先不放"}], \
            {"n": CHECK_N, "note": "未通過：每日收盤價沒有有效收盤"}
    by_date = {b[0]: b for b in bars}
    kept = [b for b in bars if b[0] <= last]
    bad = None
    compared = 0
    for r in (daily["rows"])[-n:]:
        d, dc = r[0], r[1]
        b = by_date.get(d)
        if b is None:
            continue
        if dc is None:
            bad = (d, "每日收盤價那天沒有通過官方核對（null），K 棒先不放")
            break
        compared += 1
        diff = abs(b[4] - dc) / dc
        if diff > tol:
            bad = (d, f"K 棒收盤與每日收盤價差 {diff * 100:.2f}%（超過 {tol * 100:.1f}%），從這天起先不放")
            break
    if bad:
        kept = [b for b in kept if b[0] < bad[0]]
        pending.append({"date": bad[0], "reason": "待確認：" + bad[0] + " " + bad[1]})
        note = f"未通過：{bad[0]} 起暫不發佈（見待確認）"
    else:
        note = f"最近 {compared} 個交易日收盤與每日收盤價一致（差距 ≤ {tol * 100:.1f}%）；最新一天另由每日收盤價對過官方來源" \
            if (daily.get("check") or {}).get("src") else f"最近 {compared} 個交易日收盤與每日收盤價一致（差距 ≤ {tol * 100:.1f}%）"
    return kept, pending, {"n": CHECK_N, "note": note}


# ---------- 需要抓嗎／落後 ----------
def needs_fetch(prev_outer, daily):
    """不上網判斷：沒有舊檔、舊檔是 provisional、K 棒落後 data/daily 最新有效收盤日、或沒有 daily 可比 → 抓。"""
    if not prev_outer or prev_outer.get("provisional"):
        return True
    dl = daily_last(daily)
    if dl is None:
        return True
    return (prev_outer.get("lastDate") or "") < dl


def stale_list(cos, outdir=None, daily_dir=None):
    out = []
    for c in cos:
        daily = jload(os.path.join(c.get("dailyDir") or daily_dir or os.path.join(ROOT, "data", "daily"), c["code"] + ".json"))
        dl = daily_last(daily)
        if dl is None:
            continue
        prev = jload(os.path.join(outdir or outdir_default(), c["code"] + ".enc.json"))
        have = (prev or {}).get("lastDate") or ""
        if have < dl:
            out.append((c["code"], have or "（無檔）", dl))
    return out


# ---------- 把 Yahoo 原始列整理成 K 棒（純函式） ----------
def _nan(x):
    return x is None or x != x


def _num(x):
    return None if _nan(x) else float(x)


def info_to_bar(info, d, tz, hh, mm):
    """Ticker.info → 當天 K 棒；regularMarketTime 要是同一天且已過收盤，任何一個欄位缺就回 None。"""
    if not info:
        return None
    t = info.get("regularMarketTime")
    if not t:
        return None
    lt = dt.datetime.fromtimestamp(t, ZoneInfo(tz))
    if lt.date() != d or lt.hour * 60 + lt.minute < hh * 60 + mm - 1:
        return None
    o = info.get("regularMarketOpen")
    h = info.get("dayHigh", info.get("regularMarketDayHigh"))
    l = info.get("dayLow", info.get("regularMarketDayLow"))
    c = info.get("regularMarketPrice")
    v = info.get("regularMarketVolume")
    if any(_nan(x) for x in (o, h, l, c, v)):
        return None
    return [d.isoformat(), round(float(o), 4), round(float(h), 4), round(float(l), 4), round(float(c), 4), int(v) or None]   # 0 → null


def info_close(info, d, tz, hh, mm):
    """只要收盤：同 prices_daily.closing_quote 的規則（報價時間同一天、已過收盤），但不在 log 印價格。"""
    if not info or info.get("regularMarketPrice") is None or not info.get("regularMarketTime"):
        return None
    lt = dt.datetime.fromtimestamp(info["regularMarketTime"], ZoneInfo(tz))
    if lt.date() != d or lt.hour * 60 + lt.minute < hh * 60 + mm - 1:
        return None
    return float(info["regularMarketPrice"])


def normalize_rows(raw, now_local, tz_close, info_fn):
    """raw：[(date, o, h, l, c, v)]（可含 NaN，依日期排序，date 為 date 物件）。
    now_local：交易所當地現在時間；tz_close：(tz, hh, mm)；info_fn：() → Ticker.info（延遲呼叫，網路在這裡）。
    回傳 (bars, provisional_dates)。"""
    tz, hh, mm = tz_close
    done_today = now_local.hour * 60 + now_local.minute >= hh * 60 + mm + 20
    today = now_local.date()
    closed = lambda d: d < today or (d == today and done_today)
    # 「最新一天」只看已收盤的列：盤中那根（今天還沒收）不算，否則昨天收盤 NaN 時就補不到
    last_df = max((r[0] for r in raw if closed(r[0])), default=None)
    bars, prov = [], set()
    for d, o, h, l, c, v in raw:
        if not closed(d):
            continue                                   # 還沒收盤：盤中價不收
        o, h, l, c, v = (_num(x) for x in (o, h, l, c, v))
        recent = d == today or d == last_df
        if o is None and h is None and l is None and c is None:
            if not recent:
                continue
            b = info_to_bar(info_fn(), d, tz, hh, mm)
            if b is None:
                continue                               # 缺任何一個就不收，下一班再試
            bars.append(b)
            prov.add(d.isoformat())
            continue
        if c is None and None not in (o, h, l):
            if not recent:
                continue
            c = info_close(info_fn(), d, tz, hh, mm)
            if c is None:
                continue
            prov.add(d.isoformat())
        elif None in (o, h, l, c):
            continue                                   # 殘缺列：不補
        bars.append([d.isoformat(), round(o, 4), round(h, 4), round(l, 4), round(c, 4),
                     int(v) if v else None])           # 0 或沒有 → null
    return bars, prov


def sane_bar(b):
    """FU.sane 的成交量可為 None 版本。"""
    return FU.sane(b[:5] + [b[5] or 0])


def finalize(bars, prov):
    """sane 過濾、最新量重複→null。回傳 (bars, pending, provisional)。"""
    pending = [{"date": b[0], "reason": "待確認：開高低收不合理（最高價低於開/收盤或最低價高於開/收盤），沒有採用"}
               for b in bars if not sane_bar(b)]
    bars = [b for b in bars if sane_bar(b)]
    fix_last_volume(bars)
    return bars, pending, bool(bars) and bars[-1][0] in prov


def fix_last_volume(bars):
    """Yahoo 最新一根成交量常還沒更新（和前一根完全一樣）→ 標成未知，之後重抓會補。"""
    if len(bars) > 1 and bars[-1][5] is not None and bars[-1][5] == bars[-2][5]:
        bars[-1][5] = None
    return bars


# ---------- 加解密與寫檔 ----------
@contextlib.contextmanager
def _key_root(root):
    """futures_update.encrypt_password 固定讀 ROOT/data/futures/key.json；測試用臨時 key 時暫時換 ROOT。"""
    old = FU.ROOT
    FU.ROOT = root or old
    try:
        yield
    finally:
        FU.ROOT = old


def encrypt(obj, password, key_root=None):
    with _key_root(key_root):
        return FU.encrypt_password(FU.pack(obj), password)


def decrypt(outer, password, key_root=None):
    """解回密文內容（dict）。測試與前端 fixture 用；網站上由瀏覽器解。"""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
    kp = jload(os.path.join(key_root or ROOT, "data", "futures", "key.json"))
    key = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=base64.b64decode(kp["salt"]), iterations=kp["iter"]).derive(password.encode("utf8"))
    plain = AESGCM(key).decrypt(base64.b64decode(outer["iv"]), base64.b64decode(outer["ct"]), None)
    return json.loads(zlib.decompress(plain))


def hist_readable(path, sha, password, key_root=None):
    """現有歷史檔能用目前的密碼解開，而且明文 sha 與外層記的相同。"""
    try:
        h = decrypt(jload(path), password, key_root)
        return hist_sha(h["code"], h["bars"]) == sha
    except Exception:  # noqa: BLE001  解不開、檔案壞掉都算讀不到
        return False


def _dump(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(obj, f, separators=(",", ":"))


def write_files(outdir, meta, bars, password, cut, *, provisional=False, pending=(), check=None,
                fetched_at=None, key_root=None, prev_outer=None):
    """把一組 bars 切成「近期檔」與「歷史檔」並加密寫到 outdir。回傳 {"recent": bool, "hist": 'none'|'keep'|'rewrite'}。
    meta 需要：code, name；可選 exchange, yahoo, currency, dp, source。
    歷史檔明文 sha 與 prev_outer.hist.sha 相同（且檔案在）→ 不重寫（加密每次 iv 不同，重寫會讓 repo 變大）。
    bars 需依日期排序、每根 [date,o,h,l,c,v]。前端 fixture 直接呼叫這個函式即可。"""
    code = meta["code"]
    fetched_at = fetched_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    hist, recent = split_bars(bars, cut)
    hpath = os.path.join(outdir, code + ".hist.enc.json")
    if prev_outer is None:
        prev_outer = jload(os.path.join(outdir, code + ".enc.json"))
    action, sha, why = hist_decision(prev_outer, os.path.exists(hpath), code, hist)
    if action == "keep" and not hist_readable(hpath, sha, password, key_root):
        # 明文沒變，但現有檔用目前的密碼解不開（換過 FUTURES_PASSWORD）或內容對不上 sha：不重寫的話前端永遠讀不到歷史
        action, why = "rewrite", "現有歷史檔用目前的密碼解不開或內容與 sha 不符（換過密碼？），重新加密"
    href = None
    if action != "none":
        href = {"file": code + ".hist.enc.json", "lastDate": hist[-1][0], "bars": len(hist), "sha": sha}
        if action == "rewrite":
            _dump(hpath, {"code": code, "lastDate": hist[-1][0], "bars": len(hist), "sha": sha,
                          **encrypt({"code": code, "cols": COLS, "bars": hist}, password, key_root)})
            log(f"  歷史檔重寫：{why}")
    elif os.path.exists(hpath):
        os.remove(hpath)
    payload = {
        "code": code, "name": meta["name"], "kind": "stock",
        "exchange": meta.get("exchange") or meta.get("yahoo"), "yahoo": meta.get("yahoo"), "currency": meta.get("currency"),
        "dp": meta.get("dp", 0 if meta.get("currency") == "KRW" else 2),
        "source": meta.get("source") or {"n": f"Yahoo Finance（{meta.get('yahoo')}，日線，已依股票分割調整、不含股利調整）",
                                         "url": SRC_URL.format(meta.get("yahoo"))},
        "check": check, "fetchedAt": fetched_at, "firstDate": bars[0][0], "lastDate": bars[-1][0],
        "cols": COLS, "bars": recent, "rolls": [], "pending": list(pending), "provisional": bool(provisional),
    }
    outer = {"code": code, "name": meta["name"], "lastDate": bars[-1][0], "firstDate": bars[0][0], "bars": len(bars),
             "pendingCount": len(payload["pending"]), "fetchedAt": fetched_at, "provisional": bool(provisional),
             "hist": href, **encrypt(payload, password, key_root)}
    _dump(os.path.join(outdir, code + ".enc.json"), outer)
    return {"recent": True, "hist": action}


# ---------- 網路（只有這一段上網） ----------
def fetch_raw(sym, frm, now_date):
    """回傳 (raw rows, info_fn, exchange)。raw：[(date, o, h, l, c, v)]，可含 NaN。"""
    import yfinance as yf
    err = None
    for i in range(4):
        try:
            t = yf.Ticker(sym)
            df = t.history(start=(frm + "-01") if frm else None, end=(now_date + dt.timedelta(days=2)).isoformat(),
                           interval="1d", auto_adjust=False, actions=False)
            if df is None or df.empty:
                raise RuntimeError("沒有日線資料")
            raw = [(ts.date(), r["Open"], r["High"], r["Low"], r["Close"], r["Volume"]) for ts, r in df.iterrows()]
            if frm:
                raw = [r for r in raw if r[0].isoformat() >= frm + "-01"]   # 上市月之前（SPAC 時期）不收
            ex = None
            try:
                md = t.history_metadata or {}
                ex = md.get("fullExchangeName") or md.get("exchangeName")
            except Exception:  # noqa: BLE001
                pass
            cache = {}

            def info_fn():
                if "i" not in cache:
                    try:
                        cache["i"] = t.info
                    except Exception as e:  # noqa: BLE001
                        log(f"   {sym} 報價讀取失敗：{type(e).__name__}")
                        cache["i"] = {}
                return cache["i"]
            return raw, info_fn, ex
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(10 * (i + 1))
    raise RuntimeError(f"{sym} 抓取失敗：{type(err).__name__}")


def process(c, password, outdir, *, daily_dir=None, fetcher=fetch_raw, now_utc=None, key_root=None):
    """單一公司：判斷要不要抓 → 抓 → 整理 → 核對 daily → 寫檔。回傳狀態字串（up-to-date／written／unchanged／empty）。"""
    code, pc = c["code"], c["price"]
    daily = jload(os.path.join(c.get("dailyDir") or daily_dir or os.path.join(ROOT, "data", "daily"), code + ".json"))
    path = os.path.join(outdir, code + ".enc.json")
    prev = jload(path)
    if not needs_fetch(prev, daily):
        log(f"[{code}] 已是最新")
        return "up-to-date"
    tz, hh, mm = PD.exch(pc["yahoo"])
    now = (now_utc or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo(tz))
    raw, info_fn, ex = fetcher(pc["yahoo"], pc.get("from"), now.date())
    bars, prov = normalize_rows(raw, now, (tz, hh, mm), info_fn)
    bars, pend_sane, _ = finalize(bars, prov)
    bars, pend_daily, check = verify_with_daily(bars, daily)
    fix_last_volume(bars)
    pending = pend_sane + pend_daily
    if not bars:
        log(f"[{code}] 沒有可用的 K 棒（待確認 {len(pending)} 項），保留舊檔")
        return "empty"
    provisional = bars[-1][0] in prov
    if prev and not provisional and not prev.get("provisional") and prev.get("lastDate") == bars[-1][0] \
            and prev.get("pendingCount", 0) == len(pending):
        log(f"[{code}] 沒有新的 K 棒，不更新檔案")
        return "unchanged"
    meta = {"code": code, "name": c["name"], "yahoo": pc["yahoo"], "currency": pc.get("currency"),
            "exchange": ex or pc["yahoo"]}
    res = write_files(outdir, meta, bars, password, cut_date(now.date()), provisional=provisional, pending=pending,
                      check=check, key_root=key_root, prev_outer=prev)
    log(f"[{code}] 已寫入：共 {len(bars)} 根，{bars[0][0]} ~ {bars[-1][0]}；"
        f"{'暫定（收盤價待日線確認）；' if provisional else ''}待確認 {len(pending)} 項；歷史檔 {res['hist']}")
    return "written"


def main(argv=None):
    a = list(sys.argv[1:] if argv is None else argv)
    only = a[a.index("--company") + 1] if "--company" in a else None
    cos = companies(only)
    if "--stale-check" in a:
        late = stale_list(cos)
        log("個股 K 棒落後每日收盤價的最新日期：" + ("、".join(f"{c}（K 棒 {h}，收盤價 {d}）" for c, h, d in late) if late else "無"))
        return 1 if late else 0
    pw = os.environ.get("FUTURES_PASSWORD", "")
    if len(pw) < 12:
        log("沒有設定 FUTURES_PASSWORD（或少於 12 字），停止：不會寫出未加密的資料。")
        return 1
    out = outdir_default()
    os.makedirs(out, exist_ok=True)
    fails = []
    for c in cos:
        try:
            process(c, pw, out)
        except Exception as e:  # noqa: BLE001
            log(f"[{c['code']}] 失敗：{type(e).__name__}：{str(e)[:120]}；保留舊檔")
            fails.append(c["code"])
    if fails:
        log("失敗：" + "、".join(fails))
    return 0


if __name__ == "__main__":
    sys.exit(main())
