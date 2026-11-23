"""網站冒煙測試（CI 用）：用瀏覽器打開首頁、3 個個股頁、市值排名頁、系統健康頁，頁面有 JavaScript 錯誤就失敗；個股頁還要有 #buffett，指標小辭典要有新名詞。
量化回測（首頁 #dca）：跑一次預設回測、切三種顯示篩選；再開 #monthly（每月定期投入）、#vol（大跌與回本）各跑一次，線不對或有 JavaScript 錯誤就失敗（quant()）。個股頁要有「回測這檔」連結。
用法：python3 tools/smoke_test.py [--shots DIR]   （需要 playwright 與 chromium；先 python3 tools/build.py）
外部字型／CDN 載入失敗不算錯誤（CI 可能沒外網），只看頁面自己的 JavaScript 例外與 console.error。"""
import functools, http.server, os, re, sys, threading
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ["/", "/tsmc/", "/nvda/", "/pltr/", "/mcap/", "/etf/", "/status/", "/calendar/", "/futures/", "/macro/"]
COMPANY_PAGES = ("/tsmc/", "/nvda/", "/pltr/")   # 個股頁（含舊版型台積電、PLTR）必須有巴菲特＋蒙格檢查表 #buffett
IGNORE = ("Failed to load resource", "net::ERR", "fonts.googleapis", "fonts.gstatic")


def quant(pg, base, w, errs):
    """量化回測（首頁 #dca）：載入、用預設參數跑一次回測、切「兩者／只看單筆／只看定期定額」，檢查畫出來的線對不對。
    價格資料（quant/data/）與 Plotly（quant/vendor/）都在 repo 裡，不需要外網。"""
    try:
        pg.goto(base + "/#dca", wait_until="load")
        pg.wait_for_selector("#form-dca button[type=submit]", timeout=20000)
        pg.wait_for_function("document.querySelectorAll('[data-picker=dca] .chip').length > 0", timeout=20000)
        pg.click("#form-dca button[type=submit]")
        pg.wait_for_selector("#chart-dca-value .main-svg", timeout=30000)
    except Exception as e:   # 載入或回測逾時
        errs.append(f"量化回測沒有畫出資產價值圖：{str(e).splitlines()[0]}")
        return
    # 線名是「代號 單筆」「代號 定期定額」（app.js／view-mode.js）
    for v, want in (("ls", ("單筆",)), ("dca", ("定期定額",)), ("both", ("單筆", "定期定額"))):
        try:
            pg.click(f"#dca-view-seg button[data-v={v}]", timeout=5000)
        except Exception:
            errs.append(f"找不到顯示篩選按鈕 {v}（#dca-view-seg）")
            return
        pg.wait_for_timeout(500)
        got = pg.evaluate("""() => ({
            names: document.querySelector('#chart-dca-value').data.map((t) => t.name.split(' ').slice(1).join(' ')),
            pressed: document.querySelector('#dca-view-seg button[aria-pressed=true]')?.dataset.v,
            buys: !!document.querySelector('#chart-dca-buys') })""")
        if not got["names"] or set(got["names"]) != set(want):
            errs.append(f"顯示篩選 {v}：資產價值圖的線是 {sorted(set(got['names']))}，應該是 {list(want)}")
        if got["pressed"] != v:
            errs.append(f"顯示篩選 {v}：按鈕 aria-pressed 是 {got['pressed']}")
        if got["buys"] != (v != "ls"):
            errs.append(f"顯示篩選 {v}：扣款紀錄面板{'不該' if v == 'ls' else '應該'}出現")
    over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    if w == 390 and over > 2:
        errs.append(f"量化回測手機版有橫向捲動（多 {over}px）")
    # 每月定期投入（#monthly）：用網址參數（只帶標的）開頁，自動跑一次；要有資產價值圖、每檔 4 張卡片
    try:
        pg.goto(base + "/#monthly?t=SPY,QQQ", wait_until="load")
        pg.wait_for_selector("#chart-monthly-value .main-svg", timeout=30000)
        pg.wait_for_selector("#chart-monthly-pnl .main-svg", timeout=30000)
    except Exception as e:
        errs.append(f"每月定期投入沒有畫出圖：{str(e).splitlines()[0]}")
        return
    got = pg.evaluate("""() => ({ cards: document.querySelectorAll('#out-monthly .cards .card').length,
        lines: document.querySelector('#chart-monthly-value').data.map((t) => t.name) })""")
    if got["cards"] != 8:
        errs.append(f"每月定期投入：2 檔應有 8 張卡片，實際 {got['cards']}")
    # 「最難熬的時候」：每檔一張卡片，裡面要有「資產從高點回落最多的一次」
    worst = pg.evaluate("""() => [...document.querySelectorAll('#out-monthly .q-worst')].map((e) => e.textContent.includes('資產從高點回落最多的一次'))""")
    if len(worst) != 2 or not all(worst):
        errs.append(f"每月定期投入：最難熬的時候應有 2 張卡片、各含「資產從高點回落最多的一次」，實際 {worst}")
    if not any("投入本金" in n for n in got["lines"]):
        errs.append(f"每月定期投入：圖上沒有投入本金線（{got['lines']}）")
    over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    if w == 390 and over > 2:
        errs.append(f"每月定期投入手機版有橫向捲動（多 {over}px）")
    # 波動與風險（#vol）：大跌與回本表要出現，換門檻會重畫
    try:
        pg.goto(base + "/#vol?t=SPY,QQQ", wait_until="load")
        pg.wait_for_selector("#vol-dd-body table.data", timeout=30000)
        pg.click("#vol-dd-seg button[data-d='30']", timeout=5000)
        pg.wait_for_timeout(500)
        txt = pg.text_content("#vol-dd-body") or ""
        if "跌 30% 以上共" not in txt:
            errs.append("波動與風險：換成 30% 門檻後，大跌與回本摘要沒有更新")
    except Exception as e:
        errs.append(f"波動與風險沒有畫出大跌與回本：{str(e).splitlines()[0]}")
        return
    over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    if w == 390 and over > 2:
        errs.append(f"波動與風險手機版有橫向捲動（多 {over}px）")


def stale_cache(b, base):
    """「舊檔混新檔」（2026-11-20 事故）：GitHub Pages 檔案 max-age=600，使用者瀏覽器可能留著舊的 engine.js 或 view.html。
    用 route 攔截模擬 HTTP 快取：指定的檔案一直回舊版，直到 loader.js 開始自動復原（Playwright 看不到 cache:"reload" 的標頭，
    所以用「有人用 fetch 去抓 loader.js」當作復原開始的訊號；正常載入 loader.js 是 <script>，不是 fetch）。
    舊版內容在測試內自己做（拿現在的檔案改壞），不依賴 git 歷史。回傳錯誤清單。"""
    engine = open(os.path.join(ROOT, "quant/js/engine.js"), encoding="utf8").read()
    view = open(os.path.join(ROOT, "quant/view.html"), encoding="utf8").read()
    old_engine = re.sub(r"export function drawdownEpisodes\b", "function drawdownEpisodes_old", engine)   # 少了一個 export
    old_view = view.replace('id="form-monthly"', 'id="form-monthly-old"')                                  # 少了 #form-monthly
    assert old_engine != engine and old_view != view
    errs = []

    def run(name, stale, heals, expect_ok, expect_navs, init=None):
        """stale：{路徑: (舊內容, content-type, 只有無 ?v= 的網址才舊)}；heals：被強制重抓後是否換回新版；expect_navs：頁面主文件載入次數（含自動重新整理）"""
        ctx = b.new_context()
        if init:
            ctx.add_init_script(init)
        pg = ctx.new_page()
        healed, navs, fetched = [False], [0], set()
        pg.on("request", lambda r: navs.__setitem__(0, navs[0] + 1) if r.resource_type == "document" and r.frame == pg.main_frame else None)

        def route(r):
            req = r.request
            u = re.match(r"https?://[^/]+/([^?#]*)(\?[^#]*)?", req.url)
            path, query = u.group(1), u.group(2) or ""
            if req.resource_type == "fetch" and path.startswith("quant/"):
                fetched.add(path + ("?v" if "v=" in query else ""))
                if path == "quant/loader.js" and heals:
                    healed[0] = True   # 復原開始：之後所有請求都拿到新檔（模擬強制重抓更新了快取）
            if path in stale and req.resource_type != "document" and not healed[0]:
                body, ctype, unversioned_only = stale[path]
                if not (unversioned_only and "v=" in query):
                    return r.fulfill(body=body, content_type=ctype)
            r.continue_()
        ctx.route("**/*", route)
        try:
            pg.goto(base + "/#dca", wait_until="load")
            pg.wait_for_timeout(500)
            if expect_ok:
                pg.wait_for_selector("#form-dca button[type=submit]", timeout=20000)
                pg.wait_for_function("document.querySelectorAll('[data-picker=dca] .chip').length > 0", timeout=20000)
                pg.click("#form-dca button[type=submit]")
                pg.wait_for_selector("#chart-dca-value .main-svg", timeout=30000)
            else:
                pg.wait_for_function("document.getElementById('quant-dca-view').innerText.includes('Ctrl+F5')", timeout=20000)
                pg.wait_for_timeout(1500)   # 再等一下，確認沒有繼續重新載入
        except Exception as e:
            errs.append(f"舊檔混新檔「{name}」：{str(e).splitlines()[0]}")
        if heals and expect_navs > 1:   # 復原要同時重抓有版本與無版本的網址
            for path in stale:
                for want in (path, path + "?v"):
                    if want not in fetched:
                        errs.append(f"舊檔混新檔「{name}」：自動復原沒有重抓 {want}")
        if navs[0] != expect_navs:
            errs.append(f"舊檔混新檔「{name}」：頁面載入 {navs[0]} 次，應該是 {expect_navs} 次（自動復原只能重新整理一次）")
        ctx.close()

    js = lambda t: (t, "application/javascript", False)
    # (a) 舊的、沒有版本號的 engine.js 還在快取：新版 app.js 的 import 帶 ?v=，根本不會用到它 → 不需要重新整理
    run("a 無版本舊 engine.js", {"quant/js/engine.js": (old_engine, "application/javascript", True)}, True, True, 1)
    # (b) 連帶 ?v= 的 engine.js 都是舊的（快取卡在同一個網址）：第一次載入失敗 → 強制重抓 → 重新整理一次後正常
    run("b 舊 engine.js 自動復原", {"quant/js/engine.js": js(old_engine)}, True, True, 2)
    # (c) view.html 是舊的：新 app.js 找不到新元素 → 同上
    run("c 舊 view.html 自動復原", {"quant/view.html": (old_view, "text/html", False)}, True, True, 2)
    # (d) 永遠是舊的（強制重抓也救不了）：只重新整理一次，然後顯示 Ctrl+F5 的說明，不會無限重載
    run("d 救不回來時不無限重載", {"quant/js/engine.js": js(old_engine)}, False, False, 2)
    # (e) sessionStorage 可讀不可寫（舊版 Safari 無痕）：旗標寫不進去就不重新整理，直接顯示說明（否則會無限重載）
    run("e 旗標寫不進去時不重載", {"quant/js/engine.js": js(old_engine)}, True, False, 1,
        init="Storage.prototype.setItem = function () { throw new Error('QuotaExceededError'); };")
    return errs


def main():
    shots = sys.argv[sys.argv.index("--shots") + 1] if "--shots" in sys.argv else None
    class Q(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a, **k):
            pass
    H = functools.partial(Q, directory=ROOT)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    bad = 0
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": os.environ["PW_CHROMIUM"]} if os.environ.get("PW_CHROMIUM") else {}))
        for w, h in ((1280, 900), (390, 800)):
            pg = b.new_page(viewport={"width": w, "height": h})
            errs = []
            pg.on("pageerror", lambda e: errs.append(f"例外：{e}"))
            pg.on("console", lambda m: errs.append("console.error：" + m.text) if m.type == "error" and not any(x in m.text for x in IGNORE) else None)
            for path in PAGES:
                errs.clear()
                pg.goto(base + path, wait_until="load")
                pg.wait_for_timeout(1200)
                over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                if path in COMPANY_PAGES and not pg.query_selector("#buffett"):
                    errs.append("個股頁沒有 #buffett（巴菲特＋蒙格檢查表）")
                if path in COMPANY_PAGES and len(pg.query_selector_all(".bt-link a")) != 2:
                    errs.append("個股頁沒有「回測這檔」的兩個連結（.bt-link）")
                if path in COMPANY_PAGES and "盈餘殖利率" not in (pg.text_content("#gloss") or ""):
                    errs.append("個股頁的指標小辭典沒有巴菲特＋蒙格的新名詞（BUFFETT.GLOSS）")
                if path == "/status/":
                    # 自動工作、Claude 排程、不定期工作三張表：欄位（頻率）、做法、重試都要有；不定期工作要有灰點
                    for tid in ("stAct", "stRou", "stOnd"):
                        txt = pg.text_content("#" + tid) or ""
                        if "頻率" not in txt or "做法：" not in txt or "重試：" not in txt:
                            errs.append(f"系統健康頁 #{tid} 缺少頻率／做法／重試欄位")
                    if not pg.query_selector("#ondemand .st-dot.gray"):
                        errs.append("系統健康頁沒有「不定期工作」區塊的灰點")
                if w == 390 and over > 2:
                    errs.append(f"手機版有橫向捲動（多 {over}px）")
                if shots:
                    os.makedirs(shots, exist_ok=True)
                    pg.screenshot(path=os.path.join(shots, f"{path.strip('/') or 'home'}-{w}.png"), full_page=False)
                print(("✗" if errs else "✓"), w, path, *errs)
                bad += bool(errs)
            errs.clear()
            quant(pg, base, w, errs)
            print(("✗" if errs else "✓"), w, "/#dca、#monthly、#vol（量化回測）", *errs)
            bad += bool(errs)
        errs = stale_cache(b, base)
        print(("✗" if errs else "✓"), "量化回測：舊檔混新檔（快取事故）自動復原", *errs)
        bad += bool(errs)
        b.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
