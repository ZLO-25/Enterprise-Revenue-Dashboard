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
const VALUE_CHARTS = new Set(["chart-dca-value", "chart-alloc"]);
const MODES = [["value", "金額"], ["pct", "報酬率 %"], ["log", "對數"]];
const KEY = "quant.chart.mode.";
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
  let bar = el.previousElementSibling;
  if (!bar || !bar.classList.contains("qplus-bar")) {
    bar = document.createElement("div");
    bar.className = "qplus-bar";
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
    }
    if (timeSeries) tip(el);
  },
};
