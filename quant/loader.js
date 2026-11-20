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
      }).catch(function (e) {
        console.error(e);
        container.innerHTML = '<div style="max-width:720px;margin:48px auto;padding:24px;border:1px solid var(--neg);border-radius:10px;color:var(--ink)">' +
          "量化回測工具載入失敗，請重新整理頁面。（" + String(e && e.message || e).replace(/</g, "&lt;") + "）</div>";
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
