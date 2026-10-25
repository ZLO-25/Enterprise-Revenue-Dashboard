"""由 companies.json + data/<code>.json + templates/ 產生網站。

用法：python3 tools/build.py [--root 目錄]
輸出：
  <path>/index.html            各公司頁面（GitHub Pages 用，單檔自足）
  index.html                   首頁總覽
  dist/artifacts/<code>.html   給 Claude Artifact 發佈用的頁面片段（不進 git）
新增公司只要補 companies.json、data/<code>.json 與 templates/<template>.frag.html，不必改本檔。
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


def page(title, desc, frag):
    return ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
            f"<title>{title}</title><meta name=\"description\" content=\"{desc}\">"
            '<meta name=viewport content="width=device-width,initial-scale=1,viewport-fit=cover">'
            f"{BASE_STYLE}</head><body>\n{frag}\n</body></html>\n")


def main():
    cfg = json.loads(read("companies.json"))
    theme = read("assets", "theme.css")
    common = read("assets", "common.js")
    pages_url = cfg["site"]["pagesUrl"]
    companies = [c for c in cfg["companies"] if c.get("enabled")]
    datasets = {}
    for c in companies:
        data = json.loads(read("data", c["code"] + ".json"))
        datasets[c["code"]] = data
        frag = read("templates", c["template"] + ".frag.html")
        for key, val in (("{{THEME}}", theme), ("{{DATA}}", js_json(data))):
            assert key in frag, f"{c['template']}.frag.html 缺少 {key}"
        build = lambda home: (frag.replace("{{THEME}}", theme).replace("{{COMMON_JS}}", common)
                              .replace("{{DATA}}", js_json(data)).replace("{{HOME}}", home))
        write(page(c["title"], c["description"], build("../")), c["path"], "index.html")
        write(f"<title>{c['title']}</title>\n" + build(pages_url), "dist", "artifacts", c["code"] + ".html")
        print(f"{c['code']}: {c['path']}index.html（資料截至 {data['asOf']}）")
    home = read("templates", "home.frag.html")
    pub = [{k: v for k, v in c.items()} for c in companies]
    home = (home.replace("{{THEME}}", theme).replace("{{COMMON_JS}}", common).replace("{{COMPANIES}}", js_json(pub))
            .replace("{{DATASETS}}", js_json(datasets)).replace("{{SITE_TITLE}}", cfg["site"]["title"]))
    write(page(cfg["site"]["title"], "多家公司財報與營收追蹤總覽。", home), "index.html")
    write(f"<title>{cfg['site']['title']}</title>\n" + home, "dist", "artifacts", "home.html")
    print("index.html（首頁）")


if __name__ == "__main__":
    main()
