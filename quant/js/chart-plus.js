// 量化回測圖表的「好用度」加強（手寫）
//
//   app.js 的 plot() 畫完圖後會呼叫 window.__quantChartPlus.after(el, traces, colors)：
//
//   ① 提示框看得清楚：背景用卡片色、字用正文色（原本深色模式是白底淺字，幾乎看不到）
//   ② 時間軸圖表加「1年／3年／5年／10年／全部」快速縮放鈕（HTML 的 .seg 膠囊按鈕，長相跟主站一致；不再用 Plotly 內建的 rangeselector）
//   ③ 資產類圖表加「金額／報酬率％／對數」切換：
//        金額     原始數字
//        報酬率％  每條線 ÷ 自己的起點 − 1 → 不同幣別、不同金額也能放在一起比
//        對數     縱軸改對數刻度 → 漲很多的那條不會把其他線壓成一條平線
//      選擇記在瀏覽器（localStorage），下次打開沿用
//   ④ 圖表下方一行小提示：點圖例隱藏、雙擊只看那一條、拖曳框選放大、雙擊圖面還原
//   ⑤ 「單筆 vs 定期定額」主圖下方加一張「帳面損益」小圖：每條線 − 總投入金額
//        > 0 帳面賺、< 0 帳面賠；主圖縮放時小圖跟著縮放
//   ⑥ 比較 2 檔以上時，圖上方一排「標的開關」：按一下把那一檔的所有線（單筆＋定期定額）一起收起來
//   ⑦ 提示框「一檔一行」：同一檔的單筆、定期定額合併成一行（主圖和帳面損益小圖都是）
//        SPY   單筆 123,456 ｜ 定期定額 118,900
//      做法：單筆那條線的提示文字同時帶出定期定額的數字，定期定額那條線不另外列；
//      如果單筆那條被隱藏，定期定額那條自己列一行，數字不會消失
//   （每月定期投入的 chart-monthly-value：縱軸只有「金額／對數」，沒有「報酬率 %」；線名「代號 資產價值」「代號 投入本金」，標的開關用第一個詞分組）
//   ⑧ 只看單筆／只看定期定額時（app.js 只畫所選策略的線），提示框退回「一線一行」、帳面損益說明不提沒畫出來的線
//   （手機版圖表加高寫在 quant.css）
const VALUE_CHARTS = new Set(["chart-dca-value", "chart-alloc", "chart-monthly-value"]);
const MODES = [["value", "金額"], ["pct", "報酬率 %"], ["log", "對數"]];
// 每月定期投入的資產線會一直有新錢進來，「相對起點的報酬率」沒有意義：只給「金額／對數」
const NO_PCT = new Set(["chart-monthly-value"]);
const modesOf = (id) => (NO_PCT.has(id) ? MODES.filter((m) => m[0] !== "pct") : MODES);
const KEY = "quant.chart.mode.";
const PNL_CHARTS = new Set(["chart-dca-value"]);   // 有「總投入金額」那條水平線的圖
const isDate = (v) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v);
// 日期軸一律用 yyyy/mm（拉近到一個月內才顯示日），不要英文月份；提示框的日期顯示 yyyy/mm/dd
const TICKFMT = [{ dtickrange: [null, 86400000 * 28], value: "%Y/%m/%d" }, { dtickrange: [86400000 * 28, null], value: "%Y/%m" }];

function loadMode(id) { try { return localStorage.getItem(KEY + id) || "value"; } catch { return "value"; } }
function saveMode(id, m) { try { localStorage.setItem(KEY + id, m); } catch { /* 無痕模式 */ } }

// ② 區間快速鈕：算出「最後一天往前 N 年」，用 relayout 設定時間軸範圍（拖曳、雙擊還原時按鈕狀態跟著清掉）
const RANGES = [["1年", 1], ["3年", 3], ["5年", 5], ["10年", 10], ["全部", 0]];
const addYears = (iso, n) => `${+iso.slice(0, 4) - n}${iso.slice(4, 10)}`;
function dataSpan(traces) {
  let lo = null, hi = null;
  traces.forEach((t) => {
    if (!Array.isArray(t.x) || !t.x.length || !isDate(t.x[0])) return;
    const a = String(t.x[0]).slice(0, 10), b = String(t.x[t.x.length - 1]).slice(0, 10);
    if (lo === null || a < lo) lo = a;
    if (hi === null || b > hi) hi = b;
  });
  return [lo, hi];
}
function rangeBar(el, traces) {
  let bar = el.parentNode.querySelector(".qplus-range");
  if (!bar) {
    bar = document.createElement("div");
    bar.className = "qplus-bar qplus-range";
    bar.innerHTML = `<span class="qplus-lab">區間</span><span class="seg">` + RANGES.map(([t, n]) => `<button type="button" data-y="${n}">${t}</button>`).join("") + `</span>`;
    el.parentNode.insertBefore(bar, el);
    bar.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-y]"); if (!b || !el.__qSpan) return;
      const n = +b.dataset.y, [lo, hi] = el.__qSpan;
      const from = n ? addYears(hi, n) : lo;
      window.Plotly.relayout(el, n && from > lo ? { "xaxis.range": [from, hi] } : { "xaxis.autorange": true });
      bar.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    });
  }
  el.__qSpan = dataSpan(traces);
  bar.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.y === "0")));
  if (!el.__qRangeSync) {   // 使用者自己拖曳或雙擊還原：按鈕不再代表目前範圍
    el.__qRangeSync = true;
    el.on("plotly_relayout", (ev) => {
      if (ev["xaxis.autorange"]) { bar.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.y === "0"))); return; }
      if (ev["xaxis.range[0]"] !== undefined && !el.__qRangeBusy) bar.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", "false"));
    });
  }
}

// 依模式改寫 y 值：原始值存在 el.__qOrig，切換時都從原始值算，不會越算越歪
function applyMode(el, mode, c) {
  const orig = el.__qOrig;
  if (!orig) return;
  const ys = orig.y.map((y) => {
    if (mode !== "pct") return y;
    const base = y.find((v) => v != null && isFinite(v) && v !== 0);
    return y.map((v) => (v == null || !base ? v : v / base - 1));
  });
  const shapes = (orig.shapes || []).map((s) => (mode === "pct" && s.y0 === s.y1 ? { ...s, y0: 0, y1: 0 } : s));
  window.Plotly.restyle(el, { y: ys, hovertemplate: orig.y.map((_, i) => (mode === "pct" ? "%{y:+.1%}" : orig.ht[i])) });
  el.__qFmt = mode === "pct" ? "+.1%" : ",.0f";
  pairHover(el);
  window.Plotly.relayout(el, {
    "yaxis.type": mode === "log" ? "log" : "linear",
    "yaxis.tickformat": mode === "pct" ? "+.0%" : orig.tickformat,
    "yaxis.title.text": mode === "pct" ? "報酬率（相對起點）" : orig.title,
    "yaxis.autorange": true,
    shapes,
  });
}

function toolbar(el, c) {
  const id = el.id;
  let bar = el.parentNode.querySelector(".qplus-mode");
  if (!bar) {
    bar = document.createElement("div");
    bar.className = "qplus-bar qplus-mode";
    bar.innerHTML = `<span class="qplus-lab">縱軸</span><span class="seg">` + modesOf(id).map(([m, t]) =>
      `<button type="button" data-m="${m}">${t}</button>`).join("") + `</span>`;
    el.parentNode.insertBefore(bar, el);
    bar.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-m]"); if (!b) return;
      saveMode(id, b.dataset.m); mark(bar, b.dataset.m); applyMode(el, b.dataset.m, c);
    });
  }
  let m = loadMode(id); if (!modesOf(id).some((x) => x[0] === m)) m = "value";
  mark(bar, m);
  if (m !== "value") applyMode(el, m, c);
}
function mark(bar, m) { bar.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.m === m))); }

function tip(el) {
  let t = el.nextElementSibling;
  if (t && t.classList.contains("qplus-tip")) return;
  t = document.createElement("div"); t.className = "qplus-tip";
  t.textContent = "小技巧：點圖例可隱藏該線、雙擊圖例只看那一條；在圖上拖曳框選可放大，雙擊圖面還原。";
  el.parentNode.insertBefore(t, el.nextSibling);
}

// ⑥ 標的開關：線的名稱是「SPY 單筆」「SPY 定期定額」，用第一個詞分組
const groupOf = (name) => String(name || "").split(" ")[0];
function setVisible(el, hidden) {
  const vis = el.data.map((t) => (hidden.has(groupOf(t.name)) ? "legendonly" : true));
  window.Plotly.restyle(el, { visible: vis });   // 小圖會透過 plotly_restyle 事件跟著
}
function tickerBar(el, traces) {
  const groups = [];
  traces.forEach((t) => {
    const g = groupOf(t.name);
    if (!groups.some((x) => x.g === g)) groups.push({ g, color: (t.line && t.line.color) || "" });
  });
  let bar = el.parentNode.querySelector(".qplus-tick");
  if (groups.length < 2) { if (bar) bar.remove(); return; }
  if (!bar) {
    bar = document.createElement("div");
    bar.className = "qplus-bar qplus-tick";
    el.parentNode.insertBefore(bar, el);
    bar.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-g]"); if (!b) return;
      const h = el.__qHidden;
      h.has(b.dataset.g) ? h.delete(b.dataset.g) : h.add(b.dataset.g);
      b.setAttribute("aria-pressed", String(!h.has(b.dataset.g)));
      setVisible(el, h);
    });
  }
  el.__qHidden = new Set();   // 重新回測 = 全部重新顯示
  const esc = (x) => x.replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
  bar.innerHTML = `<span class="qplus-lab">標的</span><span class="seg">` + groups.map(({ g, color }) =>
    `<button type="button" class="qplus-t" data-g="${esc(g)}" aria-pressed="true"><i class="qplus-sw" style="background:${esc(color)}"></i>${esc(g)}</button>`).join("") + `</span>`;
}

// ⑦ 提示框一檔一行：找出「X 單筆」「X 定期定額」成對的線
const LS = " 單筆", DCA = " 定期定額";
const shown = (t) => t.visible !== false && t.visible !== "legendonly";
function pairs(data) {
  const out = [];
  data.forEach((t, i) => {
    const n = String(t.name || "");
    if (!n.endsWith(LS)) return;
    const g = n.slice(0, -LS.length);
    const j = data.findIndex((u) => u.name === g + DCA);
    if (j >= 0) out.push({ g, i, j });
  });
  return out;
}
// el.__qFmt：數字格式（d3-format）；el.__qBase：帳面損益小圖的總投入金額，有的話每個數字後面再帶（報酬率％）
function pairHover(el) {
  const data = el.data; if (!data || !data.length) return;
  const P = pairs(data); if (!P.length) return;
  const fmt = el.__qFmt || ",.0f";
  // 手機（圖寬 < 560px）一行放不下「金額＋％」，帳面損益小圖只列金額，避免提示框超出螢幕被切掉
  const base = el.clientWidth && el.clientWidth < 560 ? null : el.__qBase;
  const pct = (y) => (base ? y.map((v) => (v == null ? null : v / base)) : null);
  // 一段數字：「單筆 123,456」或帳面損益的「單筆 +12,345（+12.3%）」；v/p = 數字、百分比在 hovertemplate 裡的位置
  const part = (lab, v, p) => `${lab} %{${v}:${fmt}}` + (base ? `（%{${p}:+.1%}）` : "");
  const idx = [], ht = [], cd = [], hi = [];
  P.forEach(({ g, i, j }) => {
    const a = data[i], b = data[j], pa = pct(a.y), pb = pct(b.y);
    const who = `<extra>${g}</extra>`;
    if (shown(a) && shown(b)) {
      // 單筆那條負責整行；customdata[k] = [定期定額值, 單筆％, 定期定額％]
      idx.push(i, j);
      // 定期定額那條：清掉提示文字＋skip，才真的不會再列一行（有 hovertemplate 時 skip 不會生效）
      ht.push(part("單筆", "y", "customdata[1]") + "  ｜  " + part("定期定額", "customdata[0]", "customdata[2]") + who, null);
      cd.push(b.y.map((v, k) => [v, pa ? pa[k] : null, pb ? pb[k] : null]), null);
      hi.push("all", "skip");
    } else {   // 其中一條被隱藏：各自列自己的
      idx.push(i, j);
      ht.push(part("單筆", "y", "customdata[1]") + who, part("定期定額", "y", "customdata[1]") + who);
      cd.push(a.y.map((v, k) => [null, pa ? pa[k] : null]), b.y.map((v, k) => [null, pb ? pb[k] : null]));
      hi.push("all", "all");
    }
  });
  // 和目前一樣就不再 restyle，避免 plotly_restyle → pairHover → restyle 無限迴圈
  const same = idx.every((k, n) => (data[k].hovertemplate ?? null) === ht[n] && (data[k].hoverinfo || "all") === hi[n])
    && el.__qPairY && data.every((t, k) => t.y === el.__qPairY[k]);
  if (same) return;
  el.__qPairY = data.map((t) => t.y);
  window.Plotly.restyle(el, { hovertemplate: ht, customdata: cd, hoverinfo: hi }, idx);
  if (!el.__qPairSync) {   // 點圖例、標的開關隱藏某條線之後，重新決定誰負責列出那一行
    el.__qPairSync = true;
    el.on("plotly_restyle", () => pairHover(el));
  }
}

// ⑤ 帳面損益小圖：資產價值 − 總投入金額（定期定額還沒投入的現金也算在資產裡，所以兩種策略的「總投入」相同）
function pnlChart(el, traces, c) {
  const L = el.layout || {};
  // 用原始 shapes 找「投入本金」虛線：報酬率％模式會先把它改成 y=0（applyMode），直接讀 el.layout 會找不到本金、小圖整個不畫
  const line = ((el.__qOrig && el.__qOrig.shapes) || L.shapes || []).find((s) => s.type === "line" && s.y0 === s.y1 && s.xref === "paper");
  if (!line || !(line.y0 > 0)) return;
  const base = line.y0;
  let wrap = el.parentNode.querySelector(".qplus-pnl-wrap");
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.className = "qplus-pnl-wrap";
    wrap.innerHTML = `<div class="qplus-pnl-h">帳面損益（資產價值 − 總投入金額）</div>
      <div class="qplus-pnl-sub"></div>
      <div class="qplus-pnl"></div>`;
    const anchor = el.nextElementSibling && el.nextElementSibling.classList.contains("qplus-tip") ? el.nextElementSibling : el;
    anchor.parentNode.insertBefore(wrap, anchor.nextSibling);
  }
  // 說明文字依畫出來的策略調整（只畫一種時不提沒畫出來的線）
  const hasLs = traces.some((t) => String(t.name).endsWith(LS)), hasDca = traces.some((t) => String(t.name).endsWith(DCA));
  wrap.querySelector(".qplus-pnl-sub").textContent = "高於 0 = 帳面賺錢、低於 0 = 帳面賠錢。"
    + (hasLs && hasDca ? "定期定額還沒投入的現金也算在資產裡，所以兩種策略的「總投入」一樣，可以直接比。"
      : hasDca ? "定期定額還沒投入的現金也算在資產裡，「總投入」就是你一開始準備的那筆錢。" : "");
  const box = wrap.querySelector(".qplus-pnl");
  const hidden = el.__qHidden || new Set();
  const data = traces.map((t) => ({
    x: t.x, y: t.y.map((v) => (v == null ? null : v - base)),
    customdata: t.y.map((v) => (v == null ? null : v / base - 1)),
    name: t.name, mode: "lines", line: { ...(t.line || {}), width: 1.8 },
    visible: !hidden.has(groupOf(t.name)),
    // 只看單筆／只看定期定額時沒有成對的線，pairHover 不會接手，這個格式就是實際顯示的；這版 Plotly 的 "+,.0f" 會印出未格式化的小數，要用 "+,d"
    hovertemplate: "%{y:+,d}（%{customdata:+.1%}）",
  }));
  const xr = L.xaxis && L.xaxis.range && !L.xaxis.autorange ? L.xaxis.range.slice() : undefined;
  window.Plotly.react(box, data, {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: c.text, family: c.font, size: 12 },
    margin: { l: 60, r: 16, t: 8, b: 30 }, showlegend: false, hovermode: "x unified",
    hoverlabel: { bgcolor: c.panel, bordercolor: c.axis, font: { color: c.text, size: el.clientWidth && el.clientWidth < 560 ? 12 : 13 } },
    xaxis: { gridcolor: c.grid, linecolor: c.axis, tickfont: { color: c.tick }, automargin: true, range: xr, autorange: !xr,
      tickformatstops: TICKFMT, hoverformat: "%Y/%m/%d", spikecolor: c.muted, spikethickness: 1, spikedash: "dot" },
    yaxis: { gridcolor: c.grid, linecolor: c.axis, tickfont: { color: c.tick }, automargin: true, tickformat: ",.0f",
      zeroline: true, zerolinecolor: c.axis, zerolinewidth: 2, title: { text: "帳面損益" } },
  }, { responsive: true, displaylogo: false, displayModeBar: false });
  box.__qFmt = "+,d";   // 註：這版 Plotly 的 "+,.0f" 不會加千分位，"+,d" 才會
   box.__qBase = base;
  pairHover(box);
  el.__qPnl = box;
  if (!el.__qPnlSync) {   // 主圖縮放（拖曳、快速縮放鈕、雙擊還原）→ 小圖跟著
    el.__qPnlSync = true;
    el.on("plotly_relayout", (ev) => {
      const p = el.__qPnl; if (!p || !p.data) return;
      if (ev["xaxis.autorange"]) {
        window.Plotly.relayout(p, { "xaxis.autorange": true });
      } else if (ev["xaxis.range[0]"] !== undefined) {
        window.Plotly.relayout(p, { "xaxis.range": [ev["xaxis.range[0]"], ev["xaxis.range[1]"]] });
      } else if (Array.isArray(ev["xaxis.range"])) {
        window.Plotly.relayout(p, { "xaxis.range": ev["xaxis.range"].slice() });
      }
    });
    el.on("plotly_restyle", () => {   // 點圖例或標的開關隱藏的線，小圖也一起隱藏
      const p = el.__qPnl; if (!p || !p.data) return;
      window.Plotly.restyle(p, { visible: el.data.map((t) => t.visible !== false && t.visible !== "legendonly") });
    });
  }
}

window.__quantChartPlus = {
  // 重畫整張圖之前先記下使用者的選擇（關掉的標的、拉近的時間區間），重畫後用 restore 還原
  //（單筆 vs 定期定額切換「顯示」時會整張重畫；縱軸模式本來就記在 localStorage）
  snapshot(el) {
    if (!el || !el.layout) return null;
    const xa = el.layout.xaxis || {};
    return { hidden: [...(el.__qHidden || [])], range: xa.range && !xa.autorange ? xa.range.slice() : null };
  },
  restore(el, snap) {
    if (!el || !snap || !window.Plotly || !el.data) return;
    const names = new Set(el.data.map((t) => groupOf(t.name)));
    const hidden = new Set(snap.hidden.filter((g) => names.has(g)));
    if (hidden.size) {
      el.__qHidden = hidden;
      const bar = el.parentNode.querySelector(".qplus-tick");
      if (bar) bar.querySelectorAll("button[data-g]").forEach((b) => b.setAttribute("aria-pressed", String(!hidden.has(b.dataset.g))));
      setVisible(el, hidden);
    }
    if (snap.range) {
      window.Plotly.relayout(el, { "xaxis.range": snap.range });
      el.parentNode.querySelectorAll(".qplus-range button").forEach((x) => x.setAttribute("aria-pressed", "false"));
    }
  },
  after(el, traces, c) {
    if (!el || !window.Plotly) return;
    const timeSeries = traces.some((t) => Array.isArray(t.x) && isDate(t.x[0]) && t.x.length > 60);
    const upd = {
      // ① 提示框
      "hoverlabel.bgcolor": c.panel, "hoverlabel.bordercolor": c.axis,
      "hoverlabel.font.color": c.text, "hoverlabel.font.size": el.clientWidth && el.clientWidth < 560 ? 12 : 13,
      "xaxis.spikecolor": c.muted, "xaxis.spikethickness": 1, "xaxis.spikedash": "dot",
    };
    if (timeSeries) {
      // ② 快速縮放鈕改成圖上方的 HTML 膠囊（rangeBar）；圖例移到圖的下方，才不會跟右上角的工具列疊在一起
      upd["xaxis.tickformatstops"] = TICKFMT; upd["xaxis.hoverformat"] = "%Y/%m/%d";
      upd["margin.t"] = 24;
      upd["margin.b"] = 40 + 22 * Math.ceil(traces.length / 4);
      upd["legend.orientation"] = "h"; upd["legend.x"] = 0; upd["legend.y"] = -0.08; upd["legend.yanchor"] = "top";
      upd["legend.font.size"] = 13;
    }
    window.Plotly.relayout(el, upd);
    if (VALUE_CHARTS.has(el.id) && timeSeries) {
      const L = el.layout || {};
      el.__qOrig = {
        y: traces.map((t) => t.y), ht: traces.map((t) => t.hovertemplate || "%{y:,.0f}"),
        shapes: L.shapes || [], tickformat: (L.yaxis && L.yaxis.tickformat) || ",.0f",
        title: (L.yaxis && L.yaxis.title && L.yaxis.title.text) || "",
      };
      el.__qFmt = ",.0f";
      pairHover(el);
      toolbar(el, c);
      tickerBar(el, traces);
    }
    if (timeSeries) { rangeBar(el, traces); tip(el); }
    if (PNL_CHARTS.has(el.id) && timeSeries) pnlChart(el, traces, c);
  },
};
