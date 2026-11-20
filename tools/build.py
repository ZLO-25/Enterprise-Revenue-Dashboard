"""由 companies.json + data/<code>.json + templates/ 產生網站。

用法：python3 tools/build.py [--root 目錄]
輸出：
  <path>/index.html            各公司頁面（GitHub Pages 用，單檔自足；Chart.js 用 repo 內的 assets/vendor/ 副本）
  index.html                   首頁總覽
  dist/artifacts/<code>.html   給 Claude Artifact 發佈用的頁面片段（不進 git；Chart.js 改用 jsDelivr CDN）
  dist/artifacts/all.html      合併版 Artifact：總覽＋各公司分頁，單一檔案（不進 git）

模板占位符：
  {{THEME}}        assets/theme.css
  {{COMMON_JS}}    assets/common.js（共用前端函式）
  {{LONGTERM_JS}}  assets/adapters.js + assets/longterm.js（資料轉接層＋長期指標；所有模板都要有）
  {{DATA}}         data/<code>.json
  {{CHARTJS}}      <script src=…chart.umd.js>（Pages 用本地副本，Artifact 用 CDN）
  {{HOME}}         回首頁的連結
  {{FUTURES_JS}}   assets/futures.js（指數期貨：解密、指標、首頁小卡、K 棒頁）
  {{KBAR_JS}}      assets/kbar.js（看盤頁：個股＋期貨；個股頁的 K 棒檢視由 daily.js 延遲載入同一支檔）
  {{FUT_BASE}}     加密期貨資料的資料夾網址；{{FUT_LINK}} K 棒頁網址；{{LWC}} Lightweight Charts（首頁與 K 棒頁）
  首頁另有 {{COMPANIES}}、{{DATASETS}}、{{SITE_TITLE}}、{{REPO}}
新增公司只要補 companies.json、data/<code>.json 與 companies/<code>/SOURCES.md；資料符合 v1 就用 templates/generic.frag.html，不必改本檔。
"""
import json, os, re, sys, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pe as PE
import health as HEALTH
import thesis as THESIS
import buffett as BUFFETT
import daily_calc as DAILY

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if "--root" in sys.argv:
    ROOT = os.path.abspath(sys.argv[sys.argv.index("--root") + 1])

BASE_STYLE = ("<style>:root{color-scheme:light;box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);"
              "padding-bottom:env(safe-area-inset-bottom,0px)}html{scroll-padding-top:env(safe-area-inset-top,0px)}"
              "body{margin:0;padding:0;font:14px -apple-system,BlinkMacSystemFont,sans-serif;background:#faf9f5;color:#141413}"
              "img{max-width:100%}[hidden]:not([hidden=until-found i]){display:none!important}</style>")


def read(*p):
    with open(os.path.join(ROOT, *p), encoding="utf8") as f:
        return f.read()


def write(text, *p):
    path = os.path.join(ROOT, *p)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf8") as f:
        f.write(text)


# 首頁只讀這幾個欄位（用 Proxy 記錄首頁所有互動實際讀到的欄位得出；做法見 tools/perf/README.md）。
# 其餘（health、notes、annual、milestones、thesis、summary、sources…）只有個股頁用，不放進首頁，首頁因此小一半。
# 新增首頁功能若要讀別的欄位，把欄位名加進來（companies.json site.homeSlim=false 可整個關掉瘦身）。
HOME_KEYS = ("asOf", "quarters", "events", "valuation", "profile", "segments", "monthly", "pltr", "analysis", "buffett")
# 巴菲特＋蒙格指標在首頁只帶精簡欄位（記分板「盈餘殖利率減公債」欄與「選擇權」小標）；十年成績單、月序列等只放個股頁
HOME_BUFFETT_EY = ("ey", "pe", "m", "spread", "why", "bondWhy")
# 公司分析在首頁只帶精簡欄位（展開列的「結論＋重點」）；全文 full 很大，只放個股頁，首頁用連結過去
HOME_ANALYSIS = ("q", "date", "mode", "verdict", "conclusion", "points")


def check_home_keys():
    # 防呆：首頁範本裡讀到的欄位（D.xxx、DATA[...].xxx）都必須在 HOME_KEYS 內，否則瘦身會「靜默」把它拿掉
    src = read("templates", "home.frag.html")
    used = set(re.findall(r"(?<!\w)D\.(\w+)", src)) | set(re.findall(r"DATA\[[^\]]+\]\.(\w+)", src))
    missing = sorted(k for k in used if k not in HOME_KEYS)
    assert not missing, "首頁讀了 HOME_KEYS 沒有的欄位：" + ", ".join(missing) + "（加進 tools/build.py 的 HOME_KEYS，或把 companies.json 的 site.homeSlim 設 false）"


def home_data(datasets, slim):
    if not slim:
        return datasets
    check_home_keys()
    out = {}
    for c, d in datasets.items():
        h = {k: v for k, v in d.items() if k in HOME_KEYS}
        if "analysis" in h:   # 另外縮成精簡版；複製一份，不能改到個股頁共用的 datasets
            h["analysis"] = {k: v for k, v in h["analysis"].items() if k in HOME_ANALYSIS}
        if h.get("buffett"):   # 同樣另外縮成精簡版（複製，不改到個股頁共用的 datasets）
            b = h["buffett"]
            h["buffett"] = {"type": b.get("type"), "ey": dict({k: v for k, v in b["ey"].items() if k in HOME_BUFFETT_EY},
                                                              bond=(b["ey"].get("bond") or {}).get("v"), ref=(b["ey"].get("ref") or {}).get("v"), currency=b["ey"].get("currency"))}
        out[c] = h
    assert not any("full" in (h.get("analysis") or {}) for h in out.values()), "首頁不能帶分析全文 analysis.full"
    return out


def js_json(obj):
    # 放進 <script> 內：避免 </script> 提前結束
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


CDN_CHART = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js"></script>'
LOCAL_CHART = '<script src="{rel}assets/vendor/chart.umd.js"></script>'
LOCAL_LWC = '<script src="assets/vendor/lightweight-charts.standalone.production.js"></script>'
CDN_LWC = '<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.js"></script>'
REQUIRED = ("{{THEME}}", "{{DATA}}", "{{CHARTJS}}", "{{LONGTERM_JS}}")


def fill(frag, pairs):
    for key, val in pairs:
        frag = frag.replace(key, val)
    left = re.findall(r"\{\{[A-Z_]+\}\}", frag)
    assert not left, "模板還有沒填的占位符：" + ", ".join(sorted(set(left)))
    return frag


def icon_links(rel):
    # 分頁圖示（favicon）：SVG 為主，PNG 與 apple-touch-icon 備援；rel 是回到網站根目錄的相對路徑
    d = rel + "assets/icons/"
    return (f'<link rel="icon" type="image/svg+xml" href="{d}favicon.svg">'
            f'<link rel="icon" type="image/png" sizes="32x32" href="{d}favicon-32.png">'
            f'<link rel="apple-touch-icon" href="{d}apple-touch-icon.png">')


# 左側全域導覽欄（App Shell）：companies.json 的 site.sidebar 為 true 才注入。
# false（或沒有這個欄位）時 page() 的輸出跟加入側邊欄以前一個 byte 都不差 → 這就是 rollback 開關。
EARLY_SB = ('<script>try{if(localStorage.getItem("erd.sidebar.open")==="1"&&matchMedia("(min-width:1280px)").matches)'
            'document.documentElement.classList.add("sb-push","sb-open")}catch(e){}</script>')
SPEC_RULES = ('<script type="speculationrules">{"prerender":[{"where":{"selector_matches":"#sb-panel a[data-co]:not([aria-current])"},'
              '"eagerness":"moderate"}]}</script>')
PRERENDER = False   # main() 依 companies.json 的 site.prerender 設定
SIDEBAR = None   # main() 依 companies.json 設定；None = 不注入


def asset_ver(*p):
    # 靜態檔的版本號（內容雜湊），改檔後瀏覽器才不會一直用舊的快取
    import hashlib
    path = os.path.join(ROOT, *p)
    return hashlib.sha1(open(path, "rb").read()).hexdigest()[:8] if os.path.exists(path) else ""


# quant/js 模組之間的相對 import（from "./x.js"、import "./x.js"、import("./x.js"），含已帶 ?v= 的）
QUANT_IMPORT = re.compile(r"""(\bfrom\s*|\bimport\s*\(?\s*)(["'])(\.{1,2}/[^"'?]+\.js)(?:\?v=[0-9a-f]*)?\2""")


def _quant_js_norm(data):
    # 算版本號時把 ?v=… 拿掉，否則「版本號寫進檔案、檔案又影響版本號」會每次 build 都變
    return QUANT_IMPORT.sub(lambda m: m.group(1) + m.group(2) + m.group(3) + m.group(2), data.decode("utf8")).encode("utf8")


def quant_ver():
    # quant/ 底下所有檔案一起算一個版本號：任何一個改了，瀏覽器就會重新下載
    import hashlib
    h, base = hashlib.sha1(), os.path.join(ROOT, "quant")
    for d, dirs, files in os.walk(base):   # 不能寫 sorted(os.walk())：那樣會先走完全部，下面的排除就失效
        dirs[:] = sorted(x for x in dirs if x not in ("data", "__pycache__"))   # 價格資料每天變，不算進程式版本號
        for f in sorted(files):
            raw = open(os.path.join(d, f), "rb").read()
            if f.endswith(".js") and os.path.basename(d) == "js":
                raw = _quant_js_norm(raw)
            h.update(f.encode()); h.update(raw)
    return h.hexdigest()[:8] if os.path.isdir(base) else ""


def stamp_quant_imports(qv):
    # 把 quant/js/*.js 的內部 import 改寫成 "./x.js?v=<qv>"（和 loader.js 動態 import 的網址形式完全相同，
    # 所以每個模組只會有一份實例）。瀏覽器 HTTP 快取是「每個網址」各管各的：沒有版本號的 ./engine.js
    # 可能留著舊版，新版 app.js 就會 import 到舊 engine（2026-11-20 事故，見 docs/QUANT.md）。冪等：連跑兩次結果相同。
    jsdir = os.path.join(ROOT, "quant", "js")
    if not qv or not os.path.isdir(jsdir):
        return
    for f in sorted(os.listdir(jsdir)):
        if not f.endswith(".js"):
            continue
        path = os.path.join(jsdir, f)
        old = open(path, encoding="utf8").read()
        new = QUANT_IMPORT.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}?v={qv}{m.group(2)}", old)
        if new != old:
            open(path, "w", encoding="utf8", newline="").write(new)


def page(title, desc, frag, rel="", kind=None, code=""):
    head, tail = "", ""
    if SIDEBAR is not None and kind:
        cfg = dict(SIDEBAR, root=rel, page=kind, code=code)
        head = f'<link rel="stylesheet" href="{rel}assets/sidebar.css?v={asset_ver("assets", "sidebar.css")}">'
        if SIDEBAR.get("early"):
            # 寬螢幕且上次是展開的：在第一次繪製前就套用展開狀態，內容不會先全寬再被推窄（少一次版面跳動）
            head += EARLY_SB
        if PRERENDER and kind == "company":
            # 游標停在（或按下）側邊欄公司連結時，Chrome／Edge 先在背景載入那一頁，點下去幾乎立刻出現。
            # Safari、Firefox 不支援，會直接忽略（等於沒做）；用 moderate：只在 hover/按下時才預載，一次一頁
            head += SPEC_RULES
        tail = (f'\n<script id="sb-cfg" type="application/json">{js_json(cfg)}</script>'
                f'<script src="{rel}assets/sidebar.js?v={asset_ver("assets", "sidebar.js")}"></script>')
        if kind == "home":
            # 首頁兩個平行視圖：原主站整包放進 #main-dashboard-view（display:contents，排版不受影響）
            frag = ('<div id="main-dashboard-view">\n' + frag + '\n</div>\n'
                    '<div id="quant-dca-view" hidden></div>')
    return ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
            f"<title>{title}</title><meta name=\"description\" content=\"{desc}\">"
            '<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f"{icon_links(rel)}{BASE_STYLE}{head}</head><body>\n{frag}{tail}\n</body></html>\n")


SHELL_CSS = """
.tabbar{position:sticky;top:env(safe-area-inset-top,0px);z-index:20;background:var(--page);border-bottom:1px solid var(--line);margin-inline:-16px;padding-inline:16px}
.tabbar .in{max-width:1180px;margin-inline:auto;display:flex;gap:6px;overflow-x:auto;padding-block:8px;scrollbar-width:none}
.tabbar .in::-webkit-scrollbar{display:none}
.tabbar button{flex:none;font:inherit;font-size:.92rem;font-weight:600;border:1px solid var(--line);background:var(--surface);color:var(--ink-2);padding:8px 16px;border-radius:999px;cursor:pointer}
.tabbar button[aria-selected="true"]{background:var(--chip-bg);color:var(--chip-ink);border-color:transparent}
.tabbar button:hover{color:var(--ink)}
.view[hidden]{display:none!important}
.view .homelink{display:none!important}
.view .secnav{top:calc(env(safe-area-inset-top,0px) + 52px)!important}
.view section{scroll-margin-top:112px}
"""

SHELL_JS = r"""
const VIEWS = __VIEWS__;
const stage = document.getElementById('stage'), bar = document.getElementById('tabs');
const scoped = (root) => new Proxy(document, { get(t, k) {
  if (k === 'querySelector') return (s) => root.querySelector(s);
  if (k === 'querySelectorAll') return (s) => root.querySelectorAll(s);
  if (k === 'getElementById') return (id) => root.querySelector('#' + id);
  const v = t[k]; return typeof v === 'function' ? v.bind(t) : v;
} });
window.__scoped = {};
const roots = {}, mounted = {};
function mount(v) {
  const root = document.createElement('div'); root.className = 'view'; root.id = 'view-' + v.id; root.hidden = true;
  root.innerHTML = v.html; stage.appendChild(root); roots[v.id] = root;
  root.addEventListener('click', (e) => {
    const a = e.target.closest('a[href^="#"]'); if (a && a.getAttribute('href').length > 1) {
      const t = root.querySelector(a.getAttribute('href')); if (t) { e.preventDefault(); t.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    }
    const go = e.target.closest('a.go'); if (go) {
      const hit = VIEWS.find(x => x.path && go.getAttribute('href') === x.path); if (hit) { e.preventDefault(); show(hit.id); }
    }
  });
  window.__scoped[v.id] = scoped(root);
  mounted[v.id] = true;
  return root;
}
function runScript(v) {
  const el = document.createElement('script');
  el.textContent = '(function(document){\n' + v.code + '\n})(window.__scoped[' + JSON.stringify(v.id) + ']);';
  stage.appendChild(el);
}
function show(id) {
  const v = VIEWS.find(x => x.id === id) || VIEWS[0];
  VIEWS.forEach(x => { if (roots[x.id]) roots[x.id].hidden = x.id !== v.id; });
  if (!mounted[v.id]) { mount(v); roots[v.id].hidden = false; try { runScript(v); } catch (e) { console.error(e); } }
  bar.querySelectorAll('button').forEach(b => b.setAttribute('aria-selected', String(b.dataset.id === v.id)));
  window.scrollTo(0, 0);
  window.dispatchEvent(new Event('resize'));
}
bar.innerHTML = VIEWS.map(v => '<button type="button" role="tab" data-id="' + v.id + '" aria-selected="false">' + v.label + '</button>').join('');
bar.addEventListener('click', (e) => { const b = e.target.closest('button'); if (b) show(b.dataset.id); });
const h = (location.hash || '').replace('#', '');
show(VIEWS.some(v => v.id === h) ? h : VIEWS[0].id);
"""


def split_frag(text):
    """把公司頁片段拆成 (標記, 程式碼)：腳本改由合併版外殼以隔離範圍執行。"""
    text = re.sub(r"<link[^>]*>\s*", "", text)
    text = re.sub(r"<script src=[^>]*></script>\s*", "", text)
    m = re.search(r"<script>(.*?)</script>", text, re.S)
    assert m, "找不到內嵌腳本"
    return text[:m.start()] + text[m.end():], m.group(1)


def build_combined(cfg, companies, datasets, theme, common):
    title = cfg["site"]["title"]
    views = []
    home = read("templates", "home.frag.html")
    home = fill(home, [("{{THEME}}", theme), ("{{COMMON_JS}}", common), ("{{LONGTERM_JS}}", LONGTERM), ("{{CHARTJS}}", CDN_CHART),
                       ("{{COMPANIES}}", js_json(companies)), ("{{DATASETS}}", js_json(home_data(datasets, cfg["site"].get("homeSlim")))),
                       ("{{SITE_TITLE}}", title), ("{{REPO}}", cfg["site"]["repo"]), ("{{FUTURES_JS}}", FUTJS),
                       ("{{FUT_BASE}}", cfg["site"]["pagesUrl"] + "data/futures/"), ("{{FUT_LINK}}", cfg["site"]["pagesUrl"] + "futures/"), ("{{LWC}}", CDN_LWC),
                       ("{{CAL_LINK}}", cfg["site"]["pagesUrl"] + "calendar/"), ("{{STATUS_LINK}}", cfg["site"]["pagesUrl"] + "status/")])
    html, code = split_frag(home)
    views.append({"id": "overview", "label": "總覽", "html": html, "code": code, "path": ""})
    for c in companies:
        frag = read("templates", c["template"] + ".frag.html")
        frag = fill(frag, [("{{THEME}}", theme), ("{{COMMON_JS}}", common), ("{{LONGTERM_JS}}", LONGTERM), ("{{CHARTJS}}", CDN_CHART),
                           ("{{DATA}}", js_json(datasets[c["code"]])), ("{{HOME}}", "#")])
        html, code = split_frag(frag)
        views.append({"id": c["code"], "label": c["name"], "html": html, "code": code, "path": c["path"]})
    shell = (f"<title>{title}</title>\n"
             '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
             '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
             '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600;700&family=Noto+Sans+TC:wght@400;500;700&display=swap">\n'
             f"<style>\n{theme}\n{SHELL_CSS}</style>\n"
             '<div class="tabbar" role="navigation" aria-label="公司"><div class="in" id="tabs" role="tablist"></div></div>\n'
             '<div id="stage"></div>\n'
             '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js"></script>\n' + CDN_LWC + '\n'
             "<script>" + SHELL_JS.replace("__VIEWS__", js_json(views)) + "</script>\n")
    write(shell, "dist", "artifacts", "all.html")
    # 相容：舊排程指令仍會發佈 dist/artifacts/<代號>.html 到各公司的 artifact 網址；
    # 這些網址現在都指向合併版，所以內容也一律用合併版，避免單一公司頁蓋掉合併版。
    for c in companies:
        write(shell, "dist", "artifacts", c["code"] + ".html")
    print("dist/artifacts/all.html（合併版 Artifact）")


LONGTERM = ""
FUTJS = ""


def main():
    global LONGTERM, FUTJS, KBARJS, SIDEBAR, PRERENDER
    PRERENDER = False
    cfg = json.loads(read("companies.json"))
    PRERENDER = bool(cfg["site"].get("prerender"))
    # 有價格資料可回測的代號（quant/tickers.json）：個股頁只有在這裡找得到才放「回測這檔」連結
    QUANT_SYMS = {t["symbol"] for g in json.loads(read("quant", "tickers.json"))["groups"] for t in g["tickers"]}
    if cfg["site"].get("sidebar"):
        QV = quant_ver()
        stamp_quant_imports(QV)
        SIDEBAR = {"title": cfg["site"]["title"], "qv": QV, "early": bool(cfg["site"].get("perf")),
                   "rates": bool(cfg["site"].get("rates")),   # 回測的「🏦 升降息週期」分頁；false 或沒有這個欄位 = 完全不出現
                   "companies": [{"code": c["code"], "name": c["name"], "ticker": c.get("ticker", ""), "sector": c["sector"], "path": c["path"]}
                                 for c in cfg["companies"] if c.get("enabled")]}
    theme = read("assets", "theme.css")
    common = read("assets", "common.js")
    LONGTERM = read("assets", "adapters.js") + "\n" + read("assets", "longterm.js") + "\n" + read("assets", "summary.js") + "\n" + read("assets", "thesis.js") + "\n" + read("assets", "buffett.js") + "\n" + read("assets", "analysis.js") + "\n" + read("assets", "health.js") + "\n" + read("assets", "valuation.js") + "\n" + read("assets", "daily.js") + "\n" + read("assets", "today.js")
    if cfg["site"].get("perf"):
        # 效能開關（companies.json site.perf）：圖表延後到捲近才畫、關進場動畫。false 或沒有這個欄位 = 舊行為
        LONGTERM = "window.__PERF = true;\n" + LONGTERM
    FUTJS = read("assets", "futures.js")
    KBARJS = read("assets", "kbar.js")
    pages_url = cfg["site"]["pagesUrl"]
    companies = [c for c in cfg["companies"] if c.get("enabled")]
    datasets = {}
    for c in companies:
        data = json.loads(read("data", c["code"] + ".json"))
        pf = os.path.join(ROOT, "data", "prices", c["code"] + ".json")
        prices = json.load(open(pf, encoding="utf8")) if (c.get("price") and os.path.exists(pf)) else None
        data["valuation"] = PE.compute(data["quarters"], prices)   # 本益比只在建置時算，不存檔
        data["health"] = HEALTH.compute(HEALTH.normq(data, c.get("schema")), data["valuation"], prices)   # ROIC、ROE、FCF 殖利率…只在建置時算，不存檔
        tp = os.path.join(ROOT, "data", "thesis", c["code"] + ".json")
        if os.path.exists(tp):
            th = json.load(open(tp, encoding="utf8"))
            if th.get("status") == "approved":          # 草稿永遠不上線，使用者確認（approved）後才放進頁面
                th["lights"] = THESIS.lights(th, HEALTH.normq(data, c.get("schema")), data["valuation"], data["health"])
                data["thesis"] = th
        try:
            data["buffett"] = BUFFETT.compute(c, data, HEALTH.normq(data, c.get("schema")), data["valuation"], data["health"], prices, BUFFETT.load_rates(), BUFFETT.load_index_prices(), data.get("thesis"))
        except Exception as e:  # noqa: BLE001  算不出來就不顯示檢查表，不讓整個建置失敗；訊息留在輸出
            print(f"{c['code']}: buffett 指標計算失敗 {type(e).__name__}: {e}")
            data["buffett"] = None
        dp = os.path.join(ROOT, "data", "daily", c["code"] + ".json")
        if c.get("price") and os.path.exists(dp):
            # 每日收盤價（Actions 每天寫 data/daily/<代號>.json）：建置時用現在的財報重算一次放進頁面當備援；
            # 頁面打開時另外讀 dailyUrl 的最新檔，取比較新的（所以每天更新收盤價不必重建網站）
            dd = json.load(open(dp, encoding="utf8"))
            data["daily"] = DAILY.compute(HEALTH.normq(data, c.get("schema")), data["quarters"], dd, prices, data["valuation"],
                                          data.get("thesis") if (data.get("thesis") or {}).get("status") == "approved" else None)
        ap = os.path.join(ROOT, "data", "analysis", c["code"] + ".json")
        if os.path.exists(ap):
            # 公司分析（觀點）：個股頁標題下方的「結論＋重點」，more 展開全文。首頁展開列只帶精簡版（HOME_ANALYSIS）
            data["analysis"] = json.load(open(ap, encoding="utf8"))
        pp = os.path.join(ROOT, "data", "profile", c["code"] + ".json")
        if os.path.exists(pp):
            # 主力產品／痛點／護城河：草稿也放進首頁展開列，但頁面會標「草稿・待 ZL 確認」（status:"approved" 才拿掉標籤）
            data["profile"] = json.load(open(pp, encoding="utf8"))
        datasets[c["code"]] = data
        frag = read("templates", c["template"] + ".frag.html")
        for key in REQUIRED:
            assert key in frag, f"{c['template']}.frag.html 缺少 {key}"
        depth = c["path"].count("/")
        build = lambda home, chart: fill(frag, [("{{THEME}}", theme), ("{{COMMON_JS}}", common), ("{{LONGTERM_JS}}", LONGTERM),
                                               ("{{CHARTJS}}", chart), ("{{DATA}}", js_json(data)), ("{{HOME}}", home)])
        if c.get("price"):
            data["dailyUrl"] = "../" * depth + "data/daily/" + c["code"] + ".json"
            # 個股頁「今日股價與估值」的 K 棒檢視：選到 K 棒且區塊進入畫面時才動態載入這三支 script（不內嵌，公司頁維持輕量）
            rel = "../" * depth
            data["kbar"] = {"lwc": rel + "assets/vendor/lightweight-charts.standalone.production.js",
                            "js": [rel + "assets/futures.js?v=" + asset_ver("assets", "futures.js"), rel + "assets/kbar.js?v=" + asset_ver("assets", "kbar.js")],
                            "base": rel + "data/kbar/", "futBase": rel + "data/futures/", "link": rel + "futures/", "code": c["code"], "name": c["name"], "ticker": c.get("ticker", "")}
        site_frag = build("../" * depth, LOCAL_CHART.format(rel="../" * depth))
        ysym = (c.get("price") or {}).get("yahoo")
        if SIDEBAR is not None and ysym in QUANT_SYMS:
            # 「回測這檔」：個股頁標題區底下兩個低調的文字連結，帶到首頁量化分頁並預填這檔的代號（只放在站內頁面，Artifact／合併版沒有量化功能，不放）
            q = urllib.parse.quote(ysym, safe=".")
            r = "../" * depth
            link = (f'<p class="bt-link"><span>回測這檔</span><a href="{r}#monthly?t={q}">每月定期投入</a>'
                    f'<a href="{r}#dca?t={q}">單筆 vs 定期定額</a></p>\n  ')
            assert site_frag.count("</header>") == 1, f"{c['template']}.frag.html 的 </header> 不是剛好一個"
            site_frag = site_frag.replace("</header>", link + "</header>", 1)
        write(page(c["title"], c["description"], site_frag, "../" * depth, "company", c["code"]), c["path"], "index.html")
        if c.get("price"):
            data["dailyUrl"] = pages_url + "data/daily/" + c["code"] + ".json"   # Artifact／合併版：讀 GitHub Pages 上的檔（讀不到就用建置時的版本）
            data["kbar"] = None   # Artifact 不能載入站內 script：K 棒按鈕改成連到網站的看盤頁
            data["kbarLink"] = pages_url + "futures/?s=" + c["code"]
        write(f"<title>{c['title']}</title>\n" + build(pages_url, CDN_CHART), "dist", "artifacts", c["code"] + ".html")
        print(f"{c['code']}: {c['path']}index.html（資料截至 {data['asOf']}）")
    home_t = read("templates", "home.frag.html")
    import pending as PEND
    pend = PEND.counts(PEND.scan())          # 待確認分級（近期／近三年／歷史），首頁「資料新鮮度」表用
    pub = [dict({k: v for k, v in c.items()}, pending=pend.get(c["code"])) for c in companies]
    home = lambda chart: fill(home_t, [("{{THEME}}", theme), ("{{COMMON_JS}}", common), ("{{LONGTERM_JS}}", LONGTERM), ("{{CHARTJS}}", chart),
                                       ("{{COMPANIES}}", js_json(pub)), ("{{DATASETS}}", js_json(home_data(datasets, cfg["site"].get("homeSlim")))),
                                       ("{{SITE_TITLE}}", cfg["site"]["title"]), ("{{REPO}}", cfg["site"]["repo"]), ("{{FUTURES_JS}}", FUTJS),
                                       ("{{FUT_BASE}}", fb), ("{{FUT_LINK}}", fl), ("{{LWC}}", lwc),
                                       ("{{CAL_LINK}}", fl.replace("futures/", "calendar/")), ("{{STATUS_LINK}}", fl.replace("futures/", "status/"))])
    fb, fl, lwc = "data/futures/", "futures/", LOCAL_LWC
    write(page(cfg["site"]["title"], "多家公司財報與營收追蹤總覽：最新一季、近四季、年化成長、利潤率與自由現金流比較。", home(LOCAL_CHART.format(rel="")), "", "home"), "index.html")
    fb, fl, lwc = pages_url + "data/futures/", pages_url + "futures/", CDN_LWC
    write(f"<title>{cfg['site']['title']}</title>\n" + home(CDN_CHART), "dist", "artifacts", "home.html")
    # 指數期貨 K 棒頁（資料加密；頁面本身公開，解鎖後才有內容）
    kb_cos = [{"code": c["code"], "name": c["name"], "ticker": c.get("ticker", ""), "sector": c.get("sector") or "其他", "href": "../" + c["path"]}
              for c in companies if (c.get("price") or {}).get("yahoo")]   # 清單順序＝companies.json 的順序（產業依第一次出現的順序）
    ft = fill(read("templates", "futures.frag.html"), [("{{THEME}}", theme), ("{{COMMON_JS}}", common), ("{{FUTURES_JS}}", FUTJS), ("{{KBAR_JS}}", KBARJS),
              ("{{LWC}}", '<script src="../assets/vendor/lightweight-charts.standalone.production.js"></script>'),
              ("{{HOME}}", "../"), ("{{FUT_BASE}}", "../data/futures/"), ("{{KB_BASE}}", "../data/kbar/"), ("{{KB_COMPANIES}}", js_json(kb_cos))])
    write(page("看盤 K 棒", "指數期貨與追蹤中個股的日 K、週 K、月 K，搭配均線、扣抵值、KD 與成交量；資料加密，解鎖後顯示。", ft, "../", "futures"), "futures", "index.html")
    print("futures/index.html（看盤 K 棒頁）")
    # 市值排名頁（資料 data/mcap/latest.json 由 Actions 每週寫入；頁面執行時才讀，所以每週更新不必重建網站）
    mt = fill(read("templates", "mcap.frag.html"), [("{{THEME}}", theme), ("{{HOME}}", "../"), ("{{MCAP_BASE}}", "../data/mcap/")])
    write(page("市值排名", "全球公司、美國公司、全球資產（黃金、白銀、比特幣、公司）市值前 30 名，每週更新。", mt, "../", "mcap"), "mcap", "index.html")
    print("mcap/index.html（市值排名頁）")
    # 系統健康頁（資料 data/status/latest.json 由 daily-prep 每天寫入；頁面執行時才讀）
    st = fill(read("templates", "status.frag.html"), [("{{THEME}}", theme), ("{{HOME}}", "../"), ("{{STATUS_BASE}}", "../data/status/")])
    write(page("系統健康", "自動工作、Claude 排程與各公司資料有沒有過期；紅燈會開 GitHub issue。", st, "../", "status"), "status", "index.html")
    print("status/index.html（系統健康頁）")
    # 財報行事曆頁：事件來自各公司 events[]（建置時內嵌；「今天」與分週在瀏覽時用台北日期算，所以不需要另外排程）
    cal_ev, cal_recent = [], []
    for c in companies:
        D = datasets[c["code"]]
        for e in D.get("events", []):
            cal_ev.append({"d": e["date"], "code": c["code"], "name": c["name"], "sector": c.get("sector") or "其他", "path": c["path"], "t": e["t"], "est": bool(e.get("est"))})
        Q = D.get("quarters") or []
        if Q and Q[-1].get("rd"):
            cal_recent.append({"code": c["code"], "name": c["name"], "path": c["path"], "q": Q[-1]["q"], "rd": Q[-1]["rd"]})
    ct = fill(read("templates", "calendar.frag.html"), [("{{THEME}}", theme), ("{{HOME}}", "../"), ("{{TODAY_JS}}", read("assets", "today.js")),
              ("{{EVENTS}}", js_json(cal_ev)), ("{{RECENT}}", js_json(cal_recent))])
    write(page("財報行事曆", "未來 90 天各公司的財報與營收公布日：已公告與預估分開標示，依週分組。", ct, "../", "calendar"), "calendar", "index.html")
    print("calendar/index.html（財報行事曆頁）")
    print("index.html（首頁）")
    build_combined(cfg, companies, datasets, theme, common)


if __name__ == "__main__":
    main()
