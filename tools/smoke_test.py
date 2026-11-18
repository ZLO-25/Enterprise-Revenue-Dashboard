"""網站冒煙測試（CI 用）：用瀏覽器打開首頁、3 個個股頁、市值排名頁、系統健康頁，頁面有 JavaScript 錯誤就失敗；個股頁還要有 #buffett。
用法：python3 tools/smoke_test.py [--shots DIR]   （需要 playwright 與 chromium；先 python3 tools/build.py）
外部字型／CDN 載入失敗不算錯誤（CI 可能沒外網），只看頁面自己的 JavaScript 例外與 console.error。"""
import functools, http.server, os, sys, threading
from playwright.sync_api import sync_playwright

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGES = ["/", "/tsmc/", "/nvda/", "/pltr/", "/mcap/", "/status/", "/calendar/"]
COMPANY_PAGES = ("/tsmc/", "/nvda/", "/pltr/")   # 個股頁（含舊版型台積電、PLTR）必須有巴菲特＋蒙格檢查表 #buffett
IGNORE = ("Failed to load resource", "net::ERR", "fonts.googleapis", "fonts.gstatic")


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
                if w == 390 and over > 2:
                    errs.append(f"手機版有橫向捲動（多 {over}px）")
                if shots:
                    os.makedirs(shots, exist_ok=True)
                    pg.screenshot(path=os.path.join(shots, f"{path.strip('/') or 'home'}-{w}.png"), full_page=False)
                print(("✗" if errs else "✓"), w, path, *errs)
                bad += bool(errs)
        b.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
