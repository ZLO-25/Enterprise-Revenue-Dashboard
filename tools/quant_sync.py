"""把「單筆 vs 定期定額」回測站（github.com/ZLO-25/Lump-Sum-v.s.-DCA）的前端搬進 quant/。

用法：python3 tools/quant_sync.py <Lump-Sum-v.s.-DCA 的本機路徑>

為什麼要用程式搬、不手動複製？
  回測站之後還會繼續改。這支程式把「原始檔 → 主站版本」的每一個改動都寫死在下面，
  並且檢查每個改動都剛好套用到 1 次；原始檔改到對不上時會直接報錯，不會默默搬錯。
  以後回測站有更新，重新跑一次這支程式就好。

    Lump-Sum-v.s.-DCA/                         Enterprise-Revenue-Dashboard/quant/
      index.html  <body> 內容 ───────────────▶ view.html（放進首頁的 #quant-dca-view）
      assets/css/style.css ─── 加上作用域 ───▶ quant.css（每條規則都限定在 #quant-dca-view 內）
      assets/js/engine.js ──── 原封不動 ─────▶ js/engine.js
      assets/js/app.js ─────── 6 處小改 ─────▶ js/app.js
      assets/js/admin.js ───── 3 處小改 ─────▶ js/admin.js
      assets/vendor/plotly* ── 原封不動 ─────▶ vendor/
    手寫、不會被覆蓋：quant/loader.js（掛載與切換）、quant/js/config.js（資料從哪裡讀）
"""
import os, re, shutil, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "quant")
SCOPE = "#quant-dca-view"


def rd(src, *p):
    with open(os.path.join(src, *p), encoding="utf8") as f:
        return f.read()


def wr(text, *p):
    path = os.path.join(OUT, *p)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf8") as f:
        f.write(text)


def patch(text, pairs, name):
    for old, new in pairs:
        n = text.count(old)
        assert n == 1, f"{name}：找不到（或不只一處）要修改的片段：{old[:60]!r}（出現 {n} 次）"
        text = text.replace(old, new)
    return text


# ---------------- CSS 作用域 ----------------
def scope_selector(sel):
    s = sel.strip()
    if s in ("html", "body", "html, body", ":root"):
        return SCOPE
    if s.startswith(":root"):
        # :root:not([data-theme="light"]) / :root[data-theme="dark"] → 祖先條件 + 容器
        return s + " " + SCOPE
    if s == "*":
        return SCOPE + " *"
    return SCOPE + " " + s


def scope_css(css):
    out, i, n = [], 0, len(css)
    while i < n:
        j = css.find("{", i)
        if j < 0:
            out.append(css[i:]); break
        head = css[i:j]
        # 找對應的右括號
        depth, k = 1, j + 1
        while depth:
            if css[k] == "{": depth += 1
            elif css[k] == "}": depth -= 1
            k += 1
        body = css[j + 1:k - 1]
        # 前面的註解保持原樣
        m = re.match(r"(\s*(?:/\*.*?\*/\s*)*)(.*)$", head, re.S)
        lead, sel = m.group(1), m.group(2)
        if sel.strip().startswith("@media") or sel.strip().startswith("@supports"):
            out.append(lead + sel + "{" + scope_css(body) + "}")
        elif sel.strip().startswith("@keyframes"):
            out.append(lead + sel.replace("@keyframes spin", "@keyframes quant-spin") + "{" + body + "}")
        else:
            sels = ", ".join(dict.fromkeys(scope_selector(x) for x in sel.split(",")))
            out.append(lead + sels + " {" + body + "}")
        i = k
    return "".join(out)


# 主站 theme.css 有一些「元素」樣式（p、h1~h3、section、table、th、td…）會滲進量化視圖；
# 在量化視圖裡先把它們還原成瀏覽器預設，再套回測站自己的樣式（下面的規則會覆蓋這些）。
RESET = f"""/* ===== 由 tools/quant_sync.py 產生，請不要手改；要改就改回測站原始檔後重跑 ===== */
/* 1. 擋住主站元素樣式滲入（只作用在量化視圖內） */
{SCOPE} p {{ margin: 1em 0; }}
{SCOPE} h1, {SCOPE} h2, {SCOPE} h3 {{ text-wrap: wrap; font-family: inherit; }}
{SCOPE} section {{ display: block; gap: normal; scroll-margin-top: 0; }}
{SCOPE} table {{ font-size: inherit; font-variant-numeric: normal; width: auto; }}
{SCOPE} th, {SCOPE} td {{ padding: 1px; text-align: inherit; white-space: normal; border-bottom: 0; color: inherit;
  background: none; position: static; font-family: inherit; font-weight: inherit; }}
{SCOPE} th {{ font-weight: bold; text-align: center; }}
{SCOPE} footer {{ font-size: inherit; color: inherit; }}
/*   主站也有同名的 class（.controls .card .chip）：先還原成沒有樣式的狀態 */
{SCOPE} .controls {{ display: block; flex-wrap: nowrap; gap: normal; align-items: normal; }}
{SCOPE} .card {{ background: none; border: 0; border-radius: 0; padding: 0; display: block; gap: normal; min-width: auto; align-content: normal; }}
{SCOPE} .chip {{ justify-self: auto; font-size: inherit; font-weight: inherit; padding: 0; border-radius: 0; background: none; color: inherit; }}
/* 2. 回測站原本的樣式（每條都加上 {SCOPE} 前綴） */
"""


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = os.path.abspath(sys.argv[1])

    # view.html
    html = rd(src, "index.html")
    body = html.split("<body>", 1)[1].split('<script type="module"', 1)[0]
    wr("<!-- 由 tools/quant_sync.py 從 Lump-Sum-v.s.-DCA/index.html 產生，請不要手改 -->\n" + body.strip() + "\n", "view.html")

    # quant.css
    css = rd(src, "assets", "css", "style.css")
    css = css.replace("animation: spin ", "animation: quant-spin ")
    # 3. 容器本身：滿版（抵銷主站 body 左右 16px 留白）
    tail = f"\n/* 3. 量化視圖容器 */\n{SCOPE} {{ display: block; margin: 0 -16px; min-height: 100vh; }}\n"
    wr(RESET + scope_css(css) + tail, "quant.css")

    # engine.js：原封不動
    os.makedirs(os.path.join(OUT, "js"), exist_ok=True)
    shutil.copyfile(os.path.join(src, "assets", "js", "engine.js"), os.path.join(OUT, "js", "engine.js"))

    # app.js
    app = rd(src, "assets", "js", "app.js")
    app = patch(app, [
        # ① 資料位置與量化容器
        ('} from "./engine.js";\n',
         '} from "./engine.js";\nimport { DATA_BASE } from "./config.js";\n'
         '// [主站] 所有選取都限定在量化容器內，不會選到主站的元素\n'
         'const QROOT = document.getElementById("quant-dca-view") || document;\n'),
        # ② $ / $$ 預設只在量化容器內找
        ("const $ = (sel, root = document) =>", "const $ = (sel, root = QROOT) =>"),
        ("const $$ = (sel, root = document) =>", "const $$ = (sel, root = QROOT) =>"),
        # ③ 價格資料從 config.js 指定的位置讀
        ("fetch(`data/manifest.json?", "fetch(`${DATA_BASE}manifest.json?"),
        ("fetch(`data/${m.file}?", "fetch(`${DATA_BASE}${m.file}?"),
        # ④ 圖表配色：CSS 變數現在掛在量化容器上
        ("getComputedStyle(document.documentElement)", "getComputedStyle(QROOT === document ? document.documentElement : QROOT)"),
        ("getComputedStyle(document.body).fontFamily", "getComputedStyle(QROOT === document ? document.body : QROOT).fontFamily"),
        # ⑤ 監看的是量化容器裡的 <main>，不是主站的 <main>
        ('.observe(document.querySelector("main"),', '.observe($("main"),'),
        # ⑥ 內部分頁切換時通知側邊欄；初始化完成後提供給 loader 使用
        ('history.replaceState(null, "", `#${b.dataset.tab}`);\n',
         'history.replaceState(null, "", `#${b.dataset.tab}`);\n'
         '  window.dispatchEvent(new CustomEvent("quant:tab", { detail: b.dataset.tab }));\n'),
        ("\ninit();\n", "\n// [主站] loader.js 用：等初始化完成、依網址切分頁、離開時停掉看盤牆\n"
                        "const ready = init();\nwindow.__quantApp = { ready, loadHash, showTab, deactivate: () => Wall.deactivate() };\n"),
    ], "app.js")
    wr("// 由 tools/quant_sync.py 從 Lump-Sum-v.s.-DCA/assets/js/app.js 產生（標 [主站] 的是改動處），請不要手改\n" + app, "js", "app.js")

    # admin.js
    adm = rd(src, "assets", "js", "admin.js")
    adm = patch(adm, [
        ('export const REPO = { owner: "ZLO-25", repo: "Lump-Sum-v.s.-DCA", branch: "main" };',
         'import { ADMIN } from "./config.js";\nexport const REPO = ADMIN.repo;   // [主站] 由 config.js 決定'),
        ('const KEY_PATH = "config/admin-key.json";', "const KEY_PATH = ADMIN.keyUrl;   // [主站]"),
        ('const TICKERS_PATH = "scripts/tickers.json";', "const TICKERS_PATH = ADMIN.tickersPath;   // [主站]"),
    ], "admin.js")
    wr("// 由 tools/quant_sync.py 從 Lump-Sum-v.s.-DCA/assets/js/admin.js 產生（標 [主站] 的是改動處），請不要手改\n" + adm, "js", "admin.js")

    # Plotly
    os.makedirs(os.path.join(OUT, "vendor"), exist_ok=True)
    for f in os.listdir(os.path.join(src, "assets", "vendor")):
        shutil.copyfile(os.path.join(src, "assets", "vendor", f), os.path.join(OUT, "vendor", f))
    print("quant/ 已更新：view.html、quant.css、js/{app,admin,engine}.js、vendor/")


if __name__ == "__main__":
    main()
