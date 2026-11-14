/* 左側全域導覽欄（App Shell）
 *
 *   每一頁（首頁、個股頁、期貨 K 棒頁）都由 tools/build.py 在頁尾注入：
 *     <script id="sb-cfg" type="application/json">{root, page, code, companies…}</script>
 *     <script src="assets/sidebar.js">
 *   companies.json 的 site.sidebar = false 時 build.py 什麼都不注入，網站回到原狀（rollback 開關）。
 *
 *   首頁才有兩個視圖：
 *     #main-dashboard-view   原本的企業財報追蹤板（內容不動）
 *     #quant-dca-view        量化回測（第一次打開才載入 quant/）
 *   網址 hash 決定顯示哪一個：
 *     #dca #rolling #alloc #vol #wall #learn（＋別名 #winrate #edu）→ 量化視圖
 *     其他（沒有 hash、#companies 這類錨點）                        → 原主站
 *
 *   只新增 DOM，不改原本頁面的任何元素；所有狀態都寫在 <html> 的 class 上。
 */
(function () {
  "use strict";
  var cfgEl = document.getElementById("sb-cfg");
  if (!cfgEl) return;
  var CFG;
  try { CFG = JSON.parse(cfgEl.textContent); } catch (e) { return; }
  var ROOT = CFG.root || "", PAGE = CFG.page || "", HTML = document.documentElement;
  var KEY = "erd.sidebar.open";
  var WIDE = window.matchMedia("(min-width: 1280px)");

  // ---- 量化分頁：hash 名稱與舊回測站相同（舊分享連結繼續有效）
  var QUANT = [
    { id: "dca", ico: "📈", label: "單筆 vs 定期定額" },
    { id: "rolling", ico: "🎲", label: "勝率分析" },
    { id: "alloc", ico: "💼", label: "資產配置" },
    { id: "vol", ico: "⚡", label: "波動與風險" },
    { id: "wall", ico: "🖥️", label: "看盤牆" },
    { id: "learn", ico: "📚", label: "觀念教室" }
  ];
  var ALIAS = { winrate: "rolling", edu: "learn" };
  function quantTab(hash) {
    var t = (hash || "").replace(/^#/, "").split("?")[0];
    t = ALIAS[t] || t;
    for (var i = 0; i < QUANT.length; i++) if (QUANT[i].id === t) return t;
    return null;
  }
  // 首頁內部快速錨點（只列首頁真的有的區塊）
  var ANCHORS = [["futures", "指數期貨"], ["companies", "公司列表"], ["score", "長期體質記分板"], ["compare", "跨公司比較"], ["freshness", "資料新鮮度"]];

  // ---- localStorage（無痕模式可能丟例外，一律包起來）
  function load() { try { return localStorage.getItem(KEY) === "1"; } catch (e) { return false; } }
  function save(v) { try { localStorage.setItem(KEY, v ? "1" : "0"); } catch (e) { /* 忽略 */ } }

  function esc(s) { return String(s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  var ICON_MENU = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>';
  var ICON_CLOSE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>';

  // ---- 組側邊欄 HTML
  var isHome = PAGE === "home";
  function homeHref(hash) { return isHome ? (hash ? "#" + hash : "./") : ROOT + (hash ? "#" + hash : ""); }
  var companies = CFG.companies || [];
  var sectors = [];
  companies.forEach(function (c) { if (sectors.indexOf(c.sector) < 0) sectors.push(c.sector); });
  var coList = sectors.map(function (s) {
    return '<div class="sb-sector">' + esc(s) + "</div>" + companies.filter(function (c) { return c.sector === s; }).map(function (c) {
      var cur = PAGE === "company" && CFG.code === c.code;
      return '<a class="sb-item" data-co="' + esc(c.code + " " + c.name + " " + (c.ticker || "")).toLowerCase() + '" href="' + esc(ROOT + c.path) + '"' + (cur ? ' aria-current="page"' : "") + ">" + esc(c.name) + (c.ticker ? ' <small style="color:var(--muted)">' + esc(c.ticker) + "</small>" : "") + "</a>";
    }).join("");
  }).join("");

  var html =
    '<div class="sb-head"><div class="sb-brand"><small>導覽</small>' + esc(CFG.title || "企業財報追蹤板") + "</div>" +
      '<button type="button" class="sb-btn" data-sb="close" aria-label="收合側邊欄" title="收合">' + ICON_CLOSE + "</button></div>" +
    '<nav class="sb-scroll" aria-label="網站導覽">' +
      '<div class="sb-group"><div class="sb-label">企業基本面</div>' +
        '<a class="sb-item" data-view="main" href="' + homeHref("") + '"><span class="sb-ico">📊</span>企業財報追蹤板</a>' +
        '<div class="sb-sub">' + ANCHORS.map(function (a) { return '<a class="sb-item" data-anchor="' + a[0] + '" href="' + homeHref(a[0]) + '">' + a[1] + "</a>"; }).join("") + "</div>" +
        '<details' + (PAGE === "company" ? " open" : "") + '><summary class="sb-item"><span class="sb-ico">🏢</span>個股深度頁</summary>' +
          '<div class="sb-sub"><input class="sb-filter" type="search" placeholder="搜尋公司…" aria-label="搜尋公司">' + coList + "</div></details>" +
      "</div>" +
      '<div class="sb-group"><div class="sb-label">量化回測與配置</div>' +
        QUANT.map(function (q) { return '<a class="sb-item" data-quant="' + q.id + '" href="' + homeHref(q.id) + '"><span class="sb-ico">' + q.ico + "</span>" + q.label + "</a>"; }).join("") +
      "</div>" +
    "</nav>" +
    '<div class="sb-foot" hidden>' +
      '<button type="button" class="sb-item" data-act="csv"><span class="sb-ico">📂</span>上傳 CSV</button>' +
      '<button type="button" class="sb-item" data-act="admin"><span class="sb-ico">⚙️</span>管理標的</button>' +
    "</div>";

  var panel = document.createElement("aside");
  panel.className = "sb-panel"; panel.id = "sb-panel"; panel.setAttribute("aria-label", "側邊導覽欄");
  panel.innerHTML = html;
  var backdrop = document.createElement("div"); backdrop.className = "sb-backdrop"; backdrop.setAttribute("data-sb", "close");
  var fab = document.createElement("button");
  fab.type = "button"; fab.className = "sb-btn sb-fab"; fab.setAttribute("data-sb", "open"); fab.setAttribute("aria-label", "展開側邊欄"); fab.title = "選單"; fab.innerHTML = ICON_MENU;
  var mini = fab.cloneNode(true); mini.className = "sb-btn sb-mini";
  var topbar = document.createElement("div"); topbar.className = "sb-topbar";
  topbar.innerHTML = '<button type="button" class="sb-btn" data-sb="open" aria-label="展開側邊欄">' + ICON_MENU + "<span>選單</span></button><span>財報追蹤・量化回測</span>";
  [fab, mini, panel, backdrop].forEach(function (el) { el.setAttribute("aria-controls", "sb-panel"); document.body.appendChild(el); });
  document.body.insertBefore(topbar, document.body.firstChild);
  HTML.classList.add("sb-push");

  // ---- 展開 / 收合
  function setOpen(v, remember) {
    HTML.classList.toggle("sb-open", v);
    [fab, mini].concat([].slice.call(topbar.querySelectorAll("[data-sb]"))).forEach(function (b) { b.setAttribute("aria-expanded", String(v)); });
    if (remember) save(v);
    // 寬螢幕推擠內容後，讓圖表重新量尺寸
    setTimeout(function () { window.dispatchEvent(new Event("resize")); }, 230);
  }
  // 窄螢幕是抽屜：不記住「展開」，每次進來都收著，避免蓋住內容
  setOpen(WIDE.matches && load(), false);
  WIDE.addEventListener && WIDE.addEventListener("change", function (e) { setOpen(e.matches && load(), false); });

  document.addEventListener("click", function (e) {
    var b = e.target.closest && e.target.closest("[data-sb]");
    if (b) { var open = b.getAttribute("data-sb") === "open"; setOpen(open, WIDE.matches); if (open && !WIDE.matches) panel.querySelector(".sb-item").focus(); }
  });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && HTML.classList.contains("sb-open") && !WIDE.matches) setOpen(false, false); });
  var lastY = -1;
  window.addEventListener("scroll", function () {
    var y = window.scrollY > 120;
    if (y !== lastY) { HTML.classList.toggle("sb-scrolled", y); lastY = y; }
  }, { passive: true });

  // ---- 個股搜尋
  var filter = panel.querySelector(".sb-filter");
  filter.addEventListener("input", function () {
    var q = filter.value.trim().toLowerCase();
    panel.querySelectorAll("a[data-co]").forEach(function (a) { a.hidden = q && a.getAttribute("data-co").indexOf(q) < 0; });
  });

  // 點側邊欄的連結後，窄螢幕自動收起抽屜
  panel.addEventListener("click", function (e) {
    if (e.target.closest("a") && !WIDE.matches) setOpen(false, false);
  });

  // 底部快捷：交給量化模組（第三步）處理
  panel.querySelectorAll("[data-act]").forEach(function (b) {
    b.addEventListener("click", function () {
      if (window.QuantDCA && window.QuantDCA.action) window.QuantDCA.action(b.getAttribute("data-act"));
      if (!WIDE.matches) setOpen(false, false);
    });
  });

  if (!isHome) {
    // 個股頁、期貨頁：只有側邊欄；量化連結會帶到首頁的 #dca 等
    return;
  }

  // ================= 首頁：兩個視圖切換 =================
  var mainView = document.getElementById("main-dashboard-view");
  var quantView = document.getElementById("quant-dca-view");
  if (!mainView || !quantView) return;
  var mainScroll = 0, current = "main";

  function mark(tab) {
    panel.querySelectorAll("[data-view],[data-quant]").forEach(function (a) {
      var on = tab ? a.getAttribute("data-quant") === tab : a.hasAttribute("data-view");
      a.classList.toggle("sb-on", on);
      if (on) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    panel.querySelector(".sb-foot").hidden = !tab;
  }

  var quantLoading = null;
  function ensureQuant() {
    // 第三步會由 quant/loader.js 提供 window.QuantDCA.mount(container)
    if (quantLoading) return quantLoading;
    quantLoading = new Promise(function (resolve) {
      var s = document.createElement("script");
      s.src = ROOT + "quant/loader.js" + (CFG.qv ? "?v=" + CFG.qv : "");
      s.onload = function () { resolve(window.QuantDCA || null); };
      s.onerror = function () { resolve(null); };
      document.head.appendChild(s);
    }).then(function (Q) {
      if (Q && Q.mount) return Promise.resolve(Q.mount(quantView, { root: ROOT })).then(function () { return Q; });
      quantView.innerHTML = '<div class="sb-placeholder"><h2>量化回測（建置中）</h2><p>這裡會放入「單筆 vs 定期定額」回測工具的 6 個分頁。</p></div>';
      return null;
    });
    return quantLoading;
  }

  function route() {
    var tab = quantTab(location.hash);
    if (tab) {
      if (current === "main") mainScroll = window.scrollY;
      mainView.hidden = true; quantView.hidden = false; current = tab; HTML.classList.add("sb-quant");
      mark(tab);
      document.title = (QUANT.filter(function (q) { return q.id === tab; })[0].label) + "｜量化回測｜" + (CFG.title || "");
      ensureQuant().then(function (Q) { if (Q && Q.show) Q.show(tab, location.hash); });
      window.scrollTo(0, 0);
    } else {
      var wasQuant = current !== "main";
      if (wasQuant && window.QuantDCA && window.QuantDCA.hide) window.QuantDCA.hide();   // 停掉看盤牆輪播
      quantView.hidden = true; mainView.hidden = false; current = "main"; HTML.classList.remove("sb-quant");
      mark(null);
      document.title = CFG.title || document.title;
      if (wasQuant) {
        window.dispatchEvent(new Event("resize"));     // 被隱藏過的圖表重新量尺寸
        var id = location.hash.replace(/^#/, ""), t = id && document.getElementById(id);
        if (t) t.scrollIntoView({ block: "start" }); else window.scrollTo(0, mainScroll);
      }
    }
  }
  var BASE_TITLE = document.title; CFG.title = CFG.title || BASE_TITLE;

  // 「📊 企業財報追蹤板」：回到主站並捲回剛剛的位置
  panel.querySelector("[data-view]").addEventListener("click", function (e) {
    e.preventDefault();
    if (current === "main") { window.scrollTo({ top: 0, behavior: "smooth" }); return; }
    history.pushState(null, "", location.pathname + location.search);
    route();
  });
  // 首頁錨點：量化視圖時先切回主站再捲動
  panel.querySelectorAll("[data-anchor]").forEach(function (a) {
    a.addEventListener("click", function (e) {
      var t = document.getElementById(a.getAttribute("data-anchor"));
      if (!t) return;
      e.preventDefault();
      if (current !== "main") { history.pushState(null, "", "#" + a.getAttribute("data-anchor")); route(); }
      else { history.pushState(null, "", "#" + a.getAttribute("data-anchor")); t.scrollIntoView({ behavior: "smooth", block: "start" }); }
    });
  });
  // 量化工具內部的分頁按鈕被點時，同步側邊欄的亮起項目
  window.addEventListener("quant:tab", function (e) {
    if (current === "main") return;
    current = e.detail; mark(e.detail);
    var q = QUANT.filter(function (x) { return x.id === e.detail; })[0];
    if (q) document.title = q.label + "｜量化回測｜" + (CFG.title || "");
  });
  window.addEventListener("hashchange", route);
  window.addEventListener("popstate", route);
  route();
})();
