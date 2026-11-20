"""網站冒煙測試（CI 用）：用瀏覽器打開首頁、3 個個股頁、市值排名頁、系統健康頁，頁面有 JavaScript 錯誤就失敗；個股頁還要有 #buffett，指標小辭典要有新名詞。
量化回測（首頁 #dca）：跑一次預設回測、切三種顯示篩選；再開 #monthly（每月定期投入）、#vol（大跌與回本）各跑一次，線不對或有 JavaScript 錯誤就失敗（quant()）。個股頁要有「回測這檔」連結。
用法：python3 tools/smoke_test.py [--shots DIR]   （需要 playwright 與 chromium；先 python3 tools/build.py）
外部字型／CDN 載入失敗不算錯誤（CI 可能沒外網），只看頁面自己的 JavaScript 例外與 console.error。"""
import functools, http.server, os, sys, threading
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ["/", "/tsmc/", "/nvda/", "/pltr/", "/mcap/", "/status/", "/calendar/", "/futures/"]
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
                if w == 390 and over > 2:
                    errs.append(f"手機版有橫向捲動（多 {over}px）")
                if shots:
                    os.makedirs(shots, exist_ok=True)
                    pg.screenshot(path=os.path.join(shots, f"{path.strip('/') or 'home'}-{w}.png"), full_page=False)
                print(("✗" if errs else "✓"), w, path, *errs)
                bad += bool(errs)
            errs.clear()
            quant(pg, base, w, errs)
            print(("✗" if errs else "✓"), w, "/#dca（量化回測）", *errs)
            bad += bool(errs)
        b.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
