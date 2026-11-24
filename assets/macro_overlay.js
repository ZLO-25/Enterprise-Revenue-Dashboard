/* 總經頁「美元・利率・通膨對照圖」：TradingView 式疊圖（左軸美元指數 K 棒、右軸 %）。
   資料 data/macro/overlay.json 只由 GitHub Actions（macro-weekly，tools/macro_overlay.py）寫入；這支只畫，不算任何數字。
   捲到這一區才下載圖表工具與資料（不拖慢總經頁其他部分）。 */
(function () {
  'use strict';
  var KEY_ON = 'erd-mxo-on', KEY_RG = 'erd-mxo-range';
  /* 每條線：k＝overlay.json 的 key、scale＝價格軸（left＝美元、right＝%、其他＝自己一條看不見的軸）、on＝預設顯示 */
  var LINES = [
    { k: 'fedfunds', label: '聯邦基金有效利率', unit: '%', c: '--s1', scale: 'right', on: true, w: 2 },
    { k: 'cpi', label: 'CPI 年增率', unit: '%', c: '--s3', scale: 'right', on: true, w: 2 },
    { k: 'target', label: '聯準會目標區間', unit: '%', c: '--s1', scale: 'right', on: true, w: 1, band: true },
    { k: 'dgs2', label: '2 年期公債殖利率', unit: '%', c: '--s4', scale: 'right', on: false, w: 2 },
    { k: 'dfii10', label: '10 年期實質利率', unit: '%', c: '--s7', scale: 'right', on: false, w: 2 },
    { k: 'wti', label: '西德州原油', unit: '美元', c: '--s2', scale: 'wti', on: false, w: 1.5 },
    { k: 'spy', label: 'SPY', unit: '美元', c: '--s5', scale: 'spy', on: false, w: 1.5 }
  ];
  var RANGES = [['1', '1 年'], ['3', '3 年'], ['5', '5 年'], ['10', '10 年'], ['all', '全部']];
  var ls = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) { /* 私密視窗等：不記也能用 */ } }
  };
  function T(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function dstr(d) { return d ? d.replace(/-/g, '/') : '—'; }
  function f2(v, d) { return v == null || isNaN(v) ? '—' : Number(v).toFixed(d == null ? 2 : d); }
  function ymdAgo(last, years) { var d = new Date(last + 'T00:00:00Z'); d.setUTCFullYear(d.getUTCFullYear() - years); return d.toISOString().slice(0, 10); }
  /* 某一天的值：找「那一天或之前最近的一筆」（月資料在月中也顯示當月值）；超過 maxGap 天就當成沒有 */
  function at(pts, t, maxGap) {
    var lo = 0, hi = pts.length - 1, i = -1;
    while (lo <= hi) { var m = (lo + hi) >> 1; if (pts[m][0] <= t) { i = m; lo = m + 1; } else hi = m - 1; }
    if (i < 0) return null;
    if (maxGap && (Date.parse(t) - Date.parse(pts[i][0])) / 864e5 > maxGap) return null;
    return pts[i];
  }

  function init(root, o) {
    var D = null, chart = null, S = {}, on = {}, range = ls.get(KEY_RG) || '3';
    var saved = null; try { saved = JSON.parse(ls.get(KEY_ON) || 'null'); } catch (e) { saved = null; }
    LINES.forEach(function (L) { on[L.k] = saved && L.k in saved ? !!saved[L.k] : L.on; });
    var $ = function (s) { return root.querySelector(s); };
    var box = $('.dx-chart'), leg = $('.dx-leg'), note = $('.dx-note'), bar = $('.dx-bar');

    function drawBar() {
      bar.innerHTML = '<span class="grp" role="group" aria-label="期間">' + RANGES.map(function (r) {
        return '<button type="button" data-rg="' + r[0] + '" aria-pressed="' + (range === r[0]) + '">' + r[1] + '</button>';
      }).join('') + '</span><span class="grp dx-tg" role="group" aria-label="要顯示哪些線">' + LINES.map(function (L) {
        var s = D && D.series[L.k];
        return '<label' + (s ? '' : ' class="off" title="這條目前沒有資料"') + '><input type="checkbox" data-k="' + L.k + '"' + (on[L.k] ? ' checked' : '') + (s ? '' : ' disabled') + '>' +
          '<i style="background:' + T(L.c) + (L.band ? ';opacity:.45' : '') + '"></i>' + esc(L.label) + '</label>';
      }).join('') + '</span>';
    }
    bar.addEventListener('click', function (e) {
      var b = e.target.closest('button[data-rg]'); if (!b) return;
      range = b.dataset.rg; ls.set(KEY_RG, range); drawBar(); setRange();
    });
    bar.addEventListener('change', function (e) {
      var k = e.target.dataset && e.target.dataset.k; if (!k) return;
      on[k] = e.target.checked; ls.set(KEY_ON, JSON.stringify(on));
      (S[k] || []).forEach(function (s) { s.applyOptions({ visible: on[k] }); });
      legend(null);
    });

    function setRange() {
      if (!chart || !D.series.dxy) return;
      var bars = D.series.dxy.bars, last = bars[bars.length - 1][0];
      if (range === 'all') { chart.timeScale().fitContent(); return; }
      chart.timeScale().setVisibleRange({ from: ymdAgo(last, +range), to: last });
    }

    /* 圖例：滑鼠指到哪一天就顯示那一天的值；沒指的時候顯示最新值 */
    function legend(t) {
      var x = D.series, dx = x.dxy, rows = [];
      var b = dx ? (t ? at(dx.bars, t, 7) : dx.bars[dx.bars.length - 1]) : null;
      var day = t || (b && b[0]);
      rows.push('<span class="d">' + dstr(day) + '</span>');
      if (b) {
        var up = b[4] >= b[1];
        rows.push('<span><b>美元指數</b> 開 ' + f2(b[1], 3) + ' 高 ' + f2(b[2], 3) + ' 低 ' + f2(b[3], 3) + ' 收 <b class="' + (up ? 'kup' : 'kdn') + '">' + f2(b[4], 3) + '</b></span>');
      }
      LINES.forEach(function (L) {
        var s = x[L.k]; if (!s || !on[L.k]) return;
        var v;
        if (L.band) {
          var st = at(s.steps, day || s.steps[s.steps.length - 1][0]);
          v = st ? (st[1] === st[2] ? f2(st[1]) : f2(st[1]) + '～' + f2(st[2])) + '%' : '—';
        } else {
          var mon = L.k === 'fedfunds' || L.k === 'cpi';
          var p = t ? at(s.pts, t, mon ? 75 : 7) : s.pts[s.pts.length - 1];   // 沒指的時候：每條自己最新的一筆（月資料比美元晚一兩個月是正常的）
          v = p ? f2(p[1]) + (L.unit === '%' ? '%' : ' ' + L.unit) + (mon ? '<small>（' + p[0].slice(0, 7).replace('-', '/') + '）</small>' : '') : '—';
        }
        rows.push('<span><i style="background:' + T(L.c) + '"></i>' + esc(L.label) + ' <b>' + v + '</b></span>');
      });
      leg.innerHTML = rows.join('');
    }

    function draw() {
      var LW = window.LightweightCharts, x = D.series;
      if (chart) { chart.remove(); chart = null; S = {}; }
      box.innerHTML = '';
      var grid = T('--grid'), up = T('--kup'), dn = T('--kdn');
      chart = LW.createChart(box, {
        autoSize: true,
        layout: { background: { color: 'transparent' }, textColor: T('--tick'), fontFamily: 'IBM Plex Mono, Noto Sans TC, monospace', fontSize: 12, attributionLogo: true },
        grid: { vertLines: { color: grid }, horzLines: { color: grid } },
        leftPriceScale: { visible: true, borderColor: T('--axis') },
        rightPriceScale: { visible: true, borderColor: T('--axis') },
        timeScale: { borderColor: T('--axis'), rightOffset: 4, minBarSpacing: 0.05 },
        crosshair: { mode: 0 },
        localization: { locale: 'zh-TW', timeFormatter: function (t) { return typeof t === 'string' ? dstr(t) : t.year + '/' + String(t.month).padStart(2, '0') + '/' + String(t.day).padStart(2, '0'); } }
      });
      if (x.dxy) {
        var c = chart.addSeries(LW.CandlestickSeries, { priceScaleId: 'left', upColor: up, downColor: dn, borderUpColor: up, borderDownColor: dn, wickUpColor: up, wickDownColor: dn, priceLineVisible: false, priceFormat: { type: 'price', precision: 2, minMove: 0.01 } });
        c.setData(x.dxy.bars.map(function (b) { return { time: b[0], open: b[1], high: b[2], low: b[3], close: b[4] }; }));
        S.dxy = [c];
      }
      LINES.forEach(function (L) {
        var s = x[L.k]; if (!s) return;
        var base = { priceScaleId: L.scale, color: T(L.c), lineWidth: L.w, priceLineVisible: false, visible: on[L.k], lastValueVisible: L.scale === 'right', crosshairMarkerVisible: !L.band, priceFormat: { type: 'price', precision: 2, minMove: 0.01 } };
        if (L.band) {      // 目標區間：上下限兩條階梯虛線（2008 年以前是單一目標，兩條重疊）
          var last = x.dxy ? x.dxy.bars[x.dxy.bars.length - 1][0] : s.through;
          var mk = function (i) {
            var d = s.steps.map(function (r) { return { time: r[0], value: r[i] }; });
            if (last > s.steps[s.steps.length - 1][0]) d.push({ time: last, value: s.steps[s.steps.length - 1][i] });   // 畫到今天（目標沒變就延續）
            var ser = chart.addSeries(LW.LineSeries, Object.assign({}, base, { lineType: 1, lineStyle: 2, color: T(L.c) + '99', lastValueVisible: false }));
            ser.setData(d); return ser;
          };
          S[L.k] = [mk(1), mk(2)];
          return;
        }
        var ser = chart.addSeries(LW.LineSeries, base);
        ser.setData(s.pts.map(function (p) { return { time: p[0], value: p[1] }; }));
        if (L.scale !== 'left' && L.scale !== 'right') chart.priceScale(L.scale).applyOptions({ scaleMargins: { top: 0.1, bottom: 0.1 } });
        S[L.k] = [ser];
      });
      chart.subscribeCrosshairMove(function (p) {
        var t = p && p.time; legend(t ? (typeof t === 'string' ? t : t.year + '-' + String(t.month).padStart(2, '0') + '-' + String(t.day).padStart(2, '0')) : null);
      });
      setRange();
      legend(null);
    }

    function notes() {
      var x = D.series, parts = [], pend = [];
      [['dxy', '美元指數']].concat(LINES.map(function (L) { return [L.k, L.label]; })).forEach(function (r) {
        var s = x[r[0]]; if (!s) return;
        parts.push(esc(r[1]) + '：<a href="' + esc(s.url) + '" target="_blank" rel="noopener">' + esc(s.src) + '</a>' + (s.formula ? '（' + esc(s.formula) + '）' : '') + '，資料到 ' + dstr(s.through) + (s.single ? '<span class="unc-chip" title="沒有第二個免費來源可以核對">單一來源</span>' : ''));
        (s.pending || []).forEach(function (p) { pend.push(esc(r[1]) + ' ' + dstr(p.date) + '：' + esc(p.reason)); });
      });
      note.innerHTML = '<b>來源：</b>' + parts.join('；') + '。資料更新：' + esc(D.updated) + '（平日每天一次，和上面的指標同一班）。' +
        (pend.length || (D.unavailable || []).length ? '<br><b>待確認：</b>' + pend.concat((D.unavailable || []).map(esc)).join('；') : '');
    }

    function loadScript(src) {
      return new Promise(function (ok, bad) {
        if (window.LightweightCharts) return ok();
        var s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = function () { bad(new Error('圖表工具載入失敗')); }; document.head.appendChild(s);
      });
    }
    function start() {
      Promise.all([loadScript(o.lwc), fetch(o.base + 'overlay.json', { cache: 'no-cache' }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })])
        .then(function (r) {
          D = r[1];
          if (!D.series || !D.series.dxy) throw new Error('還沒有美元指數資料');
          drawBar(); draw(); notes();
          new MutationObserver(function () { drawBar(); draw(); }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
          if (window.matchMedia) { var mq = window.matchMedia('(prefers-color-scheme: dark)'); if (mq.addEventListener) mq.addEventListener("change", function () { drawBar(); draw(); }); }
          root.dataset.ready = '1';
        })
        .catch(function (e) {
          box.innerHTML = '<p class="mx-warn" style="padding:16px">對照圖資料還沒準備好（' + esc(e.message) + '）。資料由每天的自動工作產生，第一次上線後最晚隔天就會出現。</p>';
          root.dataset.ready = 'err';
        });
    }
    if ('IntersectionObserver' in window) {
      var io = new IntersectionObserver(function (es) { if (es.some(function (e) { return e.isIntersecting; })) { io.disconnect(); start(); } }, { rootMargin: '400px' });
      io.observe(root);
    } else start();
  }
  window.MXO = { init: init, _at: at };
})();
