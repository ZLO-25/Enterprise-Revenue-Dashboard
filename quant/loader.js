/* 量化回測模組的掛載器（手寫；tools/quant_sync.py 不會覆蓋）
 *
 *   sidebar.js 在使用者「第一次」打開量化功能時才載入這支檔案，所以只看財報的人一個 byte 都不會多下載。
 *
 *   mount(container)                    show(tab)                     hide()
 *     ① 載入 quant.css                    依網址 hash 切到對應分頁        離開量化視圖時
 *     ② 抓 view.html 放進容器              （#dca?… 會還原回測參數）       停掉看盤牆的自動輪播
 *     ③ 載入 Plotly
 *     ④ import js/app.js、js/admin.js（ES module）
 *     ⑤ 等 app.js 初始化完成
 */
(function () {
  "use strict";
  var BASE = (document.currentScript && document.currentScript.src) ? document.currentScript.src.replace(/loader\.js(\?.*)?$/, "") : "quant/";
  var V = (document.currentScript && /\?v=([^&]+)/.exec(document.currentScript.src) || [])[1] || "";
  var q = V ? "?v=" + V : "";
  var ALIAS = { winrate: "rolling", edu: "learn" };

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

  var app = null;
  window.QuantDCA = {
    mount: function (container) {
      container.innerHTML = '<div style="padding:48px 24px;text-align:center;color:#6c6a64">載入量化回測工具…</div>';
      return Promise.all([
        addCss(BASE + "quant.css" + q),
        fetch(BASE + "view.html" + q).then(function (r) { if (!r.ok) throw new Error("view.html " + r.status); return r.text(); }),
        addScript(BASE + "vendor/plotly-basic-2.35.2.min.js")
      ]).then(function (res) {
        container.innerHTML = res[1];
        return Promise.all([import(BASE + "js/app.js" + q), import(BASE + "js/admin.js" + q)]);
      }).then(function () {
        app = window.__quantApp;
        return app && app.ready;
      }).catch(function (e) {
        console.error(e);
        container.innerHTML = '<div style="max-width:720px;margin:48px auto;padding:24px;border:1px solid #e34948;border-radius:10px">' +
          "量化回測工具載入失敗，請重新整理頁面。（" + String(e && e.message || e).replace(/</g, "&lt;") + "）</div>";
      });
    },
    show: function (tab) {
      if (!app) return;
      var h = location.hash.replace(/^#/, ""), name = h.split("?")[0];
      if (ALIAS[name]) history.replaceState(null, "", "#" + ALIAS[name] + h.slice(name.length));   // 別名改成正式名稱
      app.loadHash();
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
