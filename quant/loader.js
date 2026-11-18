/* 量化回測模組的掛載器（手寫；tools/quant_sync.py 不會覆蓋）
 *
 *   sidebar.js 在使用者「第一次」打開量化功能時才載入這支檔案，所以只看財報的人一個 byte 都不會多下載。
 *
 *   mount(container)                    show(tab)                     hide()
 *     ① 載入 quant.css                    依網址 hash 切到對應分頁        離開量化視圖時
 *     ② 抓 view.html 放進容器              （#dca?… 會還原回測參數）       離開時停掉圖表更新（看盤牆已移除）
 *     ③ 載入 Plotly
 *     ④ import js/app.js、js/admin.js（ES module）
 *     ⑤ 等 app.js 初始化完成
 */
(function () {
  "use strict";
  var BASE = (document.currentScript && document.currentScript.src) ? document.currentScript.src.replace(/loader\.js(\?.*)?$/, "") : "quant/";
  var V = (document.currentScript && /\?v=([^&]+)/.exec(document.currentScript.src) || [])[1] || "";
  var q = V ? "?v=" + V : "";
  var ALIAS = { winrate: "rolling", edu: "learn", wall: "dca" };   // 看盤牆已移除：#wall 導到 #dca

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
      container.innerHTML = '<div style="padding:48px 24px;text-align:center;color:#6c6a64">載入量化回測工具…</div>';
      return Promise.all([
        addCss(BASE + "quant.css" + q),
        useRates ? addCss(BASE + "rates.css" + q) : null,
        fetch(BASE + "view.html" + q).then(function (r) { if (!r.ok) throw new Error("view.html " + r.status); return r.text(); }),
        addScript(BASE + "vendor/plotly-basic-2.35.2.min.js")
      ]).then(function (res) {
        container.innerHTML = res[2];
        // 看盤牆已移除（2026-11-18）：view.html 是產生檔不能改，所以載入後把分頁按鈕與內容藏起來（app.js 照常初始化，只是沒有入口）
        var hideWall = document.createElement("style");
        hideWall.textContent = '#tab-wall, [data-tab="wall"] { display: none !important; }';
        container.appendChild(hideWall);
        // 單筆 vs 定期定額：機會成本備註（觀點，意譯，不是原話）
        var dcaTab = container.querySelector("#tab-dca");
        if (dcaTab) {
          var n13 = document.createElement("p"); n13.className = "notice";
          n13.textContent = "觀點（意譯，不是原話）：每個投資都要跟你最好的替代選擇比。對多數人來說，定期買指數就已經很好。這個回測就是在幫你比。";
          dcaTab.insertBefore(n13, dcaTab.firstChild);
        }
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
        container.innerHTML = '<div style="max-width:720px;margin:48px auto;padding:24px;border:1px solid #e34948;border-radius:10px">' +
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
