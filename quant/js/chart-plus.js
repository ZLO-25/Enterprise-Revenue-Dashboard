// 量化回測圖表的「好用度」加強（手寫；tools/quant_sync.py 不會覆蓋）
//
//   app.js 的 plot() 畫完圖後會呼叫 window.__quantChartPlus.after(el, traces, colors)：
//
//   ① 提示框看得清楚：背景用卡片色、字用正文色（原本深色模式是白底淺字，幾乎看不到）
//   ② 時間軸圖表加「1年／3年／5年／10年／全部」快速縮放鈕
//   ③ 資產類圖表加「金額／報酬率％／對數」切換：
//        金額     原始數字
//        報酬率％  每條線 ÷ 自己的起點 − 1 → 不同幣別、不同金額也能放在一起比
//        對數     縱軸改對數刻度 → 漲很多的那條不會把其他線壓成一條平線
//      選擇記在瀏覽器（localStorage），下次打開沿用
//   ④ 圖表下方一行小提示：點圖例隱藏、雙擊只看那一條、拖曳框選放大、雙擊圖面還原
//   ⑤ 「單筆 vs 定期定額」主圖下方加一張「帳面損益」小圖：每條線 − 總投入金額
//        > 0 帳面賺、< 0 帳面賠；主圖縮放時小圖跟著縮放
//   ⑥ 比較 2 檔以上時，圖上方一排「標的開關」：按一下把那一檔的所有線（單筆＋定期定額）一起收起來
//   （手機版圖表加高寫在 quant.css，由 tools/quant_sync.py 產生）
const VALUE_CHARTS = new Set(["chart-dca-value", "chart-alloc"]);
const MODES = [["value", "金額"], ["pct", "報酬率 %"], ["log", "對數"]];
const KEY = "quant.chart.mode.";
const PNL_CHARTS = new Set(["chart-dca-value"]);   // 有「總投入金額」那條水平線的圖
const isDate = (v) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}/.test(v);

function loadMode(id) { try { return localStorage.getItem(KEY + id) || "value"; } catch { return "value"; } }
function saveMode(id, m) { try { localStorage.setItem(KEY + id, m); } catch { /* 無痕模式 */ } }

function rangeButtons(c) {
  return {
    buttons: [
      { count: 1, label: "1年", step: "year", stepmode: "backward" },
      { count: 3, label: "3年", step: "year", stepmode: "backward" },
      { count: 5, label: "5年", step: "year", stepmode: "backward" },
      { count: 10, label: "10年", step: "year", stepmode: "backward" },
      { step: "all", label: "全部" },
    ],
    x: 0, xanchor: "left", y: 1.0, yanchor: "bottom", pad: { b: 4 },
    bgcolor: c.panel, activecolor: c.accent, bordercolor: c.border, borderwidth: 1,
    font: { color: c.text, size: 13 },
  };
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
    bar.innerHTML = `<span class="qplus-lab">縱軸</span>` + MODES.map(([m, t]) =>
      `<button type="button" data-m="${m}">${t}</button>`).join("");
    el.parentNode.insertBefore(bar, el);
    bar.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-m]"); if (!b) return;
      saveMode(id, b.dataset.m); mark(bar, b.dataset.m); applyMode(el, b.dataset.m, c);
    });
  }
  const m = loadMode(id); mark(bar, m);
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
  bar.innerHTML = `<span class="qplus-lab">標的</span>` + groups.map(({ g, color }) =>
    `<button type="button" class="qplus-t" data-g="${esc(g)}" aria-pressed="true"><i class="qplus-sw" style="background:${esc(color)}"></i>${esc(g)}</button>`).join("");
}

// ⑤ 帳面損益小圖：資產價值 − 總投入金額（定期定額還沒投入的現金也算在資產裡，所以兩種策略的「總投入」相同）
function pnlChart(el, traces, c) {
  const L = el.layout || {};
  const line = (L.shapes || []).find((s) => s.type === "line" && s.y0 === s.y1 && s.xref === "paper");
  if (!line || !(line.y0 > 0)) return;
  const base = line.y0;
  let wrap = el.parentNode.querySelector(".qplus-pnl-wrap");
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.className = "qplus-pnl-wrap";
    wrap.innerHTML = `<div class="qplus-pnl-h">帳面損益（資產價值 − 總投入金額）</div>
      <div class="qplus-pnl-sub">高於 0 = 帳面賺錢、低於 0 = 帳面賠錢。定期定額還沒投入的現金也算在資產裡，所以兩種策略的「總投入」一樣，可以直接比。</div>
      <div class="qplus-pnl"></div>`;
    const anchor = el.nextElementSibling && el.nextElementSibling.classList.contains("qplus-tip") ? el.nextElementSibling : el;
    anchor.parentNode.insertBefore(wrap, anchor.nextSibling);
  }
  const box = wrap.querySelector(".qplus-pnl");
  const hidden = el.__qHidden || new Set();
  const data = traces.map((t) => ({
    x: t.x, y: t.y.map((v) => (v == null ? null : v - base)),
    customdata: t.y.map((v) => (v == null ? null : v / base - 1)),
    name: t.name, mode: "lines", line: { ...(t.line || {}), width: 1.8 },
    visible: !hidden.has(groupOf(t.name)),
    hovertemplate: "%{y:+,.0f}（%{customdata:+.1%}）",
  }));
  const xr = L.xaxis && L.xaxis.range && !L.xaxis.autorange ? L.xaxis.range.slice() : undefined;
  window.Plotly.react(box, data, {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: c.text, family: getComputedStyle(el).fontFamily, size: 12 },
    margin: { l: 60, r: 16, t: 8, b: 30 }, showlegend: false, hovermode: "x unified",
    hoverlabel: { bgcolor: c.panel, bordercolor: c.border, font: { color: c.text, size: 13 } },
    xaxis: { gridcolor: c.border, linecolor: c.border, automargin: true, range: xr, autorange: !xr,
      spikecolor: c.muted, spikethickness: 1, spikedash: "dot" },
    yaxis: { gridcolor: c.border, linecolor: c.border, automargin: true, tickformat: ",.0f",
      zeroline: true, zerolinecolor: c.muted, zerolinewidth: 2, title: { text: "帳面損益" } },
  }, { responsive: true, displaylogo: false, displayModeBar: false });
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
  after(el, traces, c) {
    if (!el || !window.Plotly) return;
    const timeSeries = traces.some((t) => Array.isArray(t.x) && isDate(t.x[0]) && t.x.length > 60);
    const upd = {
      // ① 提示框
      "hoverlabel.bgcolor": c.panel, "hoverlabel.bordercolor": c.border,
      "hoverlabel.font.color": c.text, "hoverlabel.font.size": 13,
      "xaxis.spikecolor": c.muted, "xaxis.spikethickness": 1, "xaxis.spikedash": "dot",
    };
    if (timeSeries) {
      // ② 快速縮放按鈕放在圖的左上方；圖例移到圖的下方，才不會跟右上角的工具列疊在一起
      upd["xaxis.rangeselector"] = rangeButtons(c);
      upd["margin.t"] = 44;
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
      toolbar(el, c);
      tickerBar(el, traces);
    }
    if (timeSeries) tip(el);
    if (PNL_CHARTS.has(el.id) && timeSeries) pnlChart(el, traces, c);
  },
};
