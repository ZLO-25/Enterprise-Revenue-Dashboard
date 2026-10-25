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
  首頁另有 {{COMPANIES}}、{{DATASETS}}、{{SITE_TITLE}}、{{REPO}}
新增公司只要補 companies.json、data/<code>.json 與 companies/<code>/SOURCES.md；資料符合 v1 就用 templates/generic.frag.html，不必改本檔。
"""
import json, os, re, sys

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


def js_json(obj):
    # 放進 <script> 內：避免 </script> 提前結束
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


CDN_CHART = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js"></script>'
LOCAL_CHART = '<script src="{rel}assets/vendor/chart.umd.js"></script>'
REQUIRED = ("{{THEME}}", "{{DATA}}", "{{CHARTJS}}", "{{LONGTERM_JS}}")


def fill(frag, pairs):
    for key, val in pairs:
        frag = frag.replace(key, val)
    left = re.findall(r"\{\{[A-Z_]+\}\}", frag)
    assert not left, "模板還有沒填的占位符：" + ", ".join(sorted(set(left)))
    return frag


def page(title, desc, frag):
    return ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
            f"<title>{title}</title><meta name=\"description\" content=\"{desc}\">"
            '<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f"{BASE_STYLE}</head><body>\n{frag}\n</body></html>\n")


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
                       ("{{COMPANIES}}", js_json(companies)), ("{{DATASETS}}", js_json(datasets)),
                       ("{{SITE_TITLE}}", title), ("{{REPO}}", cfg["site"]["repo"])])
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
             '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js"></script>\n'
             "<script>" + SHELL_JS.replace("__VIEWS__", js_json(views)) + "</script>\n")
    write(shell, "dist", "artifacts", "all.html")
    # 相容：舊排程指令仍會發佈 dist/artifacts/<代號>.html 到各公司的 artifact 網址；
    # 這些網址現在都指向合併版，所以內容也一律用合併版，避免單一公司頁蓋掉合併版。
    for c in companies:
        write(shell, "dist", "artifacts", c["code"] + ".html")
    print("dist/artifacts/all.html（合併版 Artifact）")


LONGTERM = ""


def main():
    global LONGTERM
    cfg = json.loads(read("companies.json"))
    theme = read("assets", "theme.css")
    common = read("assets", "common.js")
    LONGTERM = read("assets", "adapters.js") + "\n" + read("assets", "longterm.js")
    pages_url = cfg["site"]["pagesUrl"]
    companies = [c for c in cfg["companies"] if c.get("enabled")]
    datasets = {}
    for c in companies:
        data = json.loads(read("data", c["code"] + ".json"))
        datasets[c["code"]] = data
        frag = read("templates", c["template"] + ".frag.html")
        for key in REQUIRED:
            assert key in frag, f"{c['template']}.frag.html 缺少 {key}"
        depth = c["path"].count("/")
        build = lambda home, chart: fill(frag, [("{{THEME}}", theme), ("{{COMMON_JS}}", common), ("{{LONGTERM_JS}}", LONGTERM),
                                               ("{{CHARTJS}}", chart), ("{{DATA}}", js_json(data)), ("{{HOME}}", home)])
        write(page(c["title"], c["description"], build("../" * depth, LOCAL_CHART.format(rel="../" * depth))), c["path"], "index.html")
        write(f"<title>{c['title']}</title>\n" + build(pages_url, CDN_CHART), "dist", "artifacts", c["code"] + ".html")
        print(f"{c['code']}: {c['path']}index.html（資料截至 {data['asOf']}）")
    home_t = read("templates", "home.frag.html")
    pub = [{k: v for k, v in c.items()} for c in companies]
    home = lambda chart: fill(home_t, [("{{THEME}}", theme), ("{{COMMON_JS}}", common), ("{{LONGTERM_JS}}", LONGTERM), ("{{CHARTJS}}", chart),
                                       ("{{COMPANIES}}", js_json(pub)), ("{{DATASETS}}", js_json(datasets)),
                                       ("{{SITE_TITLE}}", cfg["site"]["title"]), ("{{REPO}}", cfg["site"]["repo"])])
    write(page(cfg["site"]["title"], "多家公司財報與營收追蹤總覽：最新一季、近四季、年化成長、利潤率與自由現金流比較。", home(LOCAL_CHART.format(rel=""))), "index.html")
    write(f"<title>{cfg['site']['title']}</title>\n" + home(CDN_CHART), "dist", "artifacts", "home.html")
    print("index.html（首頁）")
    build_combined(cfg, companies, datasets, theme, common)


if __name__ == "__main__":
    main()
