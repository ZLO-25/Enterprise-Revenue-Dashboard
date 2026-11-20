/* 量化回測模組的掛載器（手寫）
 *   2026-11-20 起 view.html、quant.css、js/app.js、js/admin.js、js/engine.js 也改為手寫維護，
 *   所以原本在這裡「載入後補丁」的東西（看盤牆隱藏、機會成本備註）都搬回原始檔了。
 *
 *   sidebar.js 在使用者「第一次」打開量化功能時才載入這支檔案，所以只看財報的人一個 byte 都不會多下載。
 *
 *   mount(container)                    show(tab)                     hide()
 *     ① 載入 quant.css                    依網址 hash 切到對應分頁        離開量化視圖時
 *     ② 抓 view.html 放進容器              （#dca?… 會還原回測參數）       離開時呼叫 app.deactivate()（現在是空函式，保留給側邊欄呼叫）
 *     ③ 載入 Plotly
 *     ④ import js/app.js、js/admin.js（ES module）
 *     ⑤ 等 app.js 初始化完成
 */
(function () {
  "use strict";
  var BASE = (document.currentScript && document.currentScript.src) ? document.currentScript.src.replace(/loader\.js(\?.*)?$/, "") : "quant/";
  var V = (document.currentScript && /\?v=([^&]+)/.exec(document.currentScript.src) || [])[1] || "";
  var q = V ? "?v=" + V : "";
  var ALIAS = { winrate: "rolling", edu: "learn", wall: "dca" };   // 看盤牆已移除（2026-11-20 連程式碼都刪了）：舊連結 #wall 仍導到 #dca

  function addCss(href) {
    return new Promise(function (resolve) {
      var l = document.createElement("link"); l.rel = "stylesheet"; l.href = href;
      l.onload = l.onerror = function () { resolve(); };
      document.head.appendChild(l);
    });
  }
  function addScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script"); s.src = src;
      s.onload = function () { resolve(); }; s.onerror = function () { reject(new Error("載入失敗：" + src)); };
      document.head.appendChild(s);
    });
  }

  // ── 載入失敗自動復原（2026-11-20 事故：GitHub Pages 的檔案 max-age=600，瀏覽器可能同時留著新舊檔）──
  // 量化相關檔案清單。寫死在這裡（不另外抓 json，因為那份也可能是舊的）；
  // quant/tests/test_cache_heal.py 會檢查 quant/js/*.js 都在清單內，新增檔案忘了加就會測試失敗。
  var FILES = ["loader.js", "view.html", "quant.css", "rates.css",
    "js/admin.js", "js/app.js", "js/chart-plus.js", "js/config.js", "js/engine.js",
    "js/rates-core.js", "js/rates.js", "js/theme.js", "js/view-mode.js"];
  var HEAL_KEY = "quant-heal-" + (V || "none");
  function healFlag(set) {
    try { if (set === undefined) return sessionStorage.getItem(HEAL_KEY); if (set) sessionStorage.setItem(HEAL_KEY, "1"); else sessionStorage.removeItem(HEAL_KEY); } catch (e) { /* 無痕模式等：當成沒試過會無限重載，所以讀不到時回傳「已試過」 */ return set === undefined ? "1" : null; }
    return null;
  }
  // 用 cache:"reload" 強制重抓並更新 HTTP 快取：有版本與無版本的網址都抓，再抓目前頁面的 HTML，之後重新整理
  function healAndReload() {
    healFlag(true);
    var urls = [location.href.replace(/#.*$/, "")];
    FILES.forEach(function (f) { urls.push(BASE + f); if (q) urls.push(BASE + f + q); });
    var jobs = urls.map(function (u) { return fetch(u, { cache: "reload" }).catch(function () {}); });
    return Promise.all(jobs).then(function () { location.reload(); return new Promise(function () {}); });
  }

  var app = null;
  window.QuantDCA = {
    mount: function (container, opts) {
      var useRates = !!(opts && opts.rates);   // site.rates 開關（companies.json）：false 時完全不載入升降息週期分頁
      container.innerHTML = '<div style="padding:48px 24px;text-align:center;color:var(--muted)">載入量化回測工具…</div>';
      return Promise.all([
        addCss(BASE + "quant.css" + q),
        useRates ? addCss(BASE + "rates.css" + q) : null,
        fetch(BASE + "view.html" + q).then(function (r) { if (!r.ok) throw new Error("view.html " + r.status); return r.text(); }),
        addScript(BASE + "vendor/plotly-basic-2.35.2.min.js")
      ]).then(function (res) {
        container.innerHTML = res[2];
        // res[0]=quant.css res[1]=rates.css(或 null) res[2]=view.html
        // 升降息週期分頁：要在 app.js 載入「之前」放進去，app.js 才會幫它綁分頁切換與標的選擇器
        var pre = useRates ? import(BASE + "js/rates.js" + q).then(function (m) { m.inject(); }) : Promise.resolve();
        return pre.then(function () { return import(BASE + "js/chart-plus.js" + q); })   // 先載入圖表加強，app.js 畫圖時才找得到
          .then(function () { return Promise.all([import(BASE + "js/app.js" + q), import(BASE + "js/admin.js" + q)]); });
      }).then(function () {
        app = window.__quantApp;
        return app && app.ready;
      }).then(function (r) { healFlag(false); return r; }, function (e) {
        console.error(e);
        if (!healFlag()) return healAndReload();   // 這個分頁、這個版本還沒試過：重抓檔案並重新整理一次
        container.innerHTML = '<div style="max-width:720px;margin:48px auto;padding:24px;border:1px solid var(--neg);border-radius:10px;color:var(--ink)">' +
          "量化回測工具載入失敗：瀏覽器可能留著舊版檔案。請按 Ctrl+F5（Mac：Cmd+Shift+R）強制重新整理；手機請清除此網站的快取。（原始錯誤：" + String(e && e.message || e).replace(/</g, "&lt;") + "）</div>";
      });
    },
    show: function (tab) {
      if (!app) return;
      var h = location.hash.replace(/^#/, ""), name = h.split("?")[0];
      if (ALIAS[name]) history.replaceState(null, "", "#" + ALIAS[name] + h.slice(name.length));   // 別名改成正式名稱
      app.loadHash();
      if (name === "rates" && window.__quantRates) window.__quantRates.activate(location.hash);   // 升降息週期分頁
      setTimeout(function () { window.dispatchEvent(new Event("resize")); }, 50);   // 圖表重新量尺寸
    },
    hide: function () { if (app) app.deactivate(); },
    // 側邊欄底部的「上傳 CSV」「管理標的」
    action: function (what) {
      var el = document.getElementById(what === "csv" ? "csv-upload" : "admin-open");
      if (el) el.click();
    }
  };
})();
