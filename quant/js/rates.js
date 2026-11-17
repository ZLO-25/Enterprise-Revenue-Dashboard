// 🏦 升降息週期分頁（手寫；tools/quant_sync.py 不會覆蓋）
//
//   loader.js 在載入 app.js 之前呼叫 inject()：把分頁按鈕與分頁內容放進 view.html 的容器
//   （app.js 的 showTab／loadHash／標的選擇器本來就是通用的，會自動認得新分頁，所以不用改 app.js）
//
//   quant/data/rates.json（GitHub Actions 每週抓）──┐
//   quant/data/prices/*.json（回測共用的股價檔）─────┴─▶ rates-core.js 切週期、算報酬 ─▶ 圖＋表
//
//   畫面：政策利率階梯線（右軸）疊在各標的累積報酬（左軸，起點 100、對數軸）上，背景色＝四種階段
//   時間區間：直接在圖上拖曳／拉下方滑桿／按快速按鈕；plotly_relayout → updateWindow() 重算表格與報酬起點
import { DATA_BASE } from "./config.js";
import { PHASE, buildPhases, periodReturn, summarize, daysBetween, windowPoints, dayNum, eventPath, eventReturns, firstMoves } from "./rates-core.js";

const QROOT = document.getElementById("quant-dca-view") || document;
const $ = (sel, root = QROOT) => root.querySelector(sel);
const $$ = (sel, root = QROOT) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const MIN_DATE = "2000-01-01";
const PRESETS = [["1 年", 1], ["3 年", 3], ["5 年", 5], ["10 年", 10], ["20 年", 20], ["全部", 0]];
// 日期一律顯示 yyyy/mm（不用英文月份）；不是 ISO 日期的字串原樣放回
const fmtYM = (s) => (typeof s === "string" && /^\d{4}-\d{2}/.test(s) ? `${s.slice(0, 4)}/${s.slice(5, 7)}` : String(s ?? ""));
const TICKFMT = [{ dtickrange: [null, 86400000 * 28], value: "%Y/%m/%d" }, { dtickrange: [86400000 * 28, null], value: "%Y/%m" }];
const isoDate = (v) => typeof v === "string" && /^\d{4}-\d{2}-\d{2}$/.test(v) && !isNaN(dayNum(v));
const addYears = (iso, n) => { const d = new Date(Date.UTC(+iso.slice(0, 4) - n, +iso.slice(5, 7) - 1, +iso.slice(8, 10))); return d.toISOString().slice(0, 10); };
const COUNTRY = { us: "美國", tw: "台灣" };
const PCOLOR = {   // 背景色塊；深淺色模式都用半透明，再加文字標籤（不只靠顏色分辨）
  hike: "rgba(226,83,60,0.20)", holdHigh: "rgba(150,150,150,0.20)",
  cut: "rgba(34,160,110,0.20)", holdLow: "rgba(70,120,230,0.16)",
};
const PBADGE = { hike: "🔺", holdHigh: "⏸", cut: "🔻", holdLow: "⏸" };
const MOVE_COLOR = { hike: "rgba(226,83,60,0.95)", cut: "rgba(34,160,110,0.95)" };
const EVC = ["#2563eb", "#e8590c", "#12805c", "#9c36b5", "#c2255c", "#0891b2", "#a16207", "#5f3dc4"];
const LINE = ["#2563eb", "#e8590c", "#12805c", "#9c36b5", "#c2255c"];

const fmtPct = (x, signed = true) => (x == null || !isFinite(x) ? "—" : `${signed && x > 0 ? "+" : ""}${(x * 100).toFixed(1)}%`);
const cls = (x) => (x > 0 ? "pos" : x < 0 ? "neg" : "");
const fmtLen = (days) => (days < 45 ? `${days} 天` : days < 700 ? `${(days / 30.44).toFixed(0)} 個月` : `${(days / 365.25).toFixed(1)} 年`);

const S = { rates: null, ratesErr: null, manifest: null, cache: new Map(), country: "us", show10y: false, scale: "log", layout: "overlay", evKind: "hike", evSym: null, from: null, to: null, started: false, lastKey: "", obs: null };
let CTX = null;   // 目前畫面用到的資料（圖上拉區間時，重算表格和報酬起點要用）
const curKey = () => `${chipSyms().join()}|${S.country}|${S.show10y}|${S.scale}|${S.layout}|${S.from}|${S.to}`;

// ---------- 把分頁放進畫面（在 app.js 載入前呼叫） ----------
export function inject() {
  if ($("#tab-rates")) return;
  const btn = document.createElement("button");
  btn.setAttribute("role", "tab"); btn.dataset.tab = "rates"; btn.textContent = "🏦 升降息週期";
  const volBtn = $('nav.tabs button[data-tab="vol"]');
  if (volBtn) volBtn.after(btn); else $("nav.tabs").appendChild(btn);
  // 按分頁按鈕時（app.js 的處理會先改網址；這裡等它做完再啟動）
  btn.addEventListener("click", () => setTimeout(() => activate(location.hash), 0));

  const sec = document.createElement("section");
  sec.className = "tab"; sec.id = "tab-rates";
  sec.innerHTML = `
  <div class="layout">
    <form class="panel controls" id="form-rates" autocomplete="off" novalidate>
      <h2>設定</h2>
      <p class="intro">Fed 升息、降息的時候，股票和 ETF 實際上漲了還是跌了？把每一輪利率週期切成四段，看各標的在每一段的報酬。</p>
      <div class="field">
        <span class="label">投資標的 <span class="hint">最多 5 檔，從下拉選單選擇；按 × 移除</span></span>
        <div class="picker" data-picker="rates" data-default="SPY,QQQ,0050.TW" data-max="5"></div>
      </div>
      <div class="field">
        <label for="rates-country">用哪個國家的升降息週期</label>
        <select id="rates-country"><option value="us">美國（聯準會）</option><option value="tw">台灣（中央銀行）</option></select>
        <span class="hint">不同國家週期不同；例如看 0050 時，也可以切到台灣週期比較。</span>
      </div>
      <div class="field">
        <span class="label">時間區間</span>
        <span class="hint">直接在右邊的圖上選：拖曳圖面框選、拉圖下方的滑桿，或按圖上方的「1 年、3 年…」。表格和報酬起點（＝100）會跟著你選的區間更新。</span>
      </div>
      <label class="checkbox"><input type="checkbox" id="rates-10y"> 同時畫 10 年期公債殖利率</label>
      <div class="field" style="margin-top:14px">
        <label for="rates-layout">圖的排列</label>
        <select id="rates-layout"><option value="overlay">利率和報酬疊在同一張圖（像 TradingView）</option><option value="split">上下兩張圖</option></select>
        <span class="hint">疊在一起時：左邊刻度是報酬指數，右邊刻度是利率 %。</span>
      </div>
      <div class="field">
        <label for="rates-scale">報酬指數的刻度</label>
        <select id="rates-scale"><option value="log">對數（建議）</option><option value="linear">線性</option></select>
        <span class="hint">對數＝每格代表「漲幾倍」而不是「漲幾點」，長期走勢才不會被後面的大漲壓扁。下方有白話說明。</span>
      </div>
    </form>
    <div id="out-rates"><div class="panel placeholder"><span class="spinner"></span> 載入利率資料…</div></div>
  </div>`;
  $("main").appendChild(sec);
}

// ---------- 資料 ----------
async function loadRates() {
  if (S.rates || S.ratesErr) return;
  try {
    const r = await fetch(`${DATA_BASE}rates.json?t=${Date.now()}`, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    S.rates = await r.json();
  } catch (e) { S.ratesErr = `利率資料（rates.json）載入失敗（${e.message}）。可能是 GitHub Actions「rates-weekly」還沒執行過。`; }
}
async function loadManifest() {
  if (S.manifest) return;
  const r = await fetch(`${DATA_BASE}manifest.json?t=${Date.now()}`, { cache: "no-store" });
  S.manifest = new Map();
  if (r.ok) for (const g of (await r.json()).groups) for (const t of g.tickers) S.manifest.set(t.symbol, t);
}
function loadSeries(sym) {
  if (!S.cache.has(sym)) {
    const m = S.manifest.get(sym);
    S.cache.set(sym, m && m.file
      ? fetch(`${DATA_BASE}${m.file}`).then((r) => { if (!r.ok) throw new Error(`${sym} 下載失敗 (${r.status})`); return r.json(); }).catch((e) => { S.cache.delete(sym); throw e; })
      : Promise.resolve(null));
  }
  return S.cache.get(sym);
}

// ---------- 讀／寫畫面上的選擇 ----------
const chipSyms = () => $$('.picker[data-picker="rates"] .chip button[data-sym]').map((b) => b.dataset.sym);
function applyHash(hash) {
  const q = (hash || "").replace(/^#/, "").split("?")[1];
  if (!q) return;
  const p = new URLSearchParams(q);
  if (p.get("c") && COUNTRY[p.get("c")]) { S.country = p.get("c"); $("#rates-country").value = S.country; }
  if (p.has("y")) { S.show10y = p.get("y") === "1"; $("#rates-10y").checked = S.show10y; }
  S.from = isoDate(p.get("f")) ? p.get("f") : null;
  S.to = isoDate(p.get("e")) ? p.get("e") : null;
  if (p.get("s") === "lin" || p.get("s") === "log") { S.scale = p.get("s") === "lin" ? "linear" : "log"; $("#rates-scale").value = S.scale; }
  if (p.get("l") === "s" || p.get("l") === "o") { S.layout = p.get("l") === "s" ? "split" : "overlay"; $("#rates-layout").value = S.layout; }
  if (p.get("t")) {
    const want = p.get("t").split(",").filter(Boolean).slice(0, 5);
    if (want.join() !== chipSyms().join()) {
      $$('.picker[data-picker="rates"] .chip button[data-sym]').forEach((b) => b.click());
      const sel = $('.picker[data-picker="rates"] select');
      for (const s of want) { if (sel && [...sel.options].some((o) => o.value === s)) { sel.value = s; sel.dispatchEvent(new Event("change")); } }
    }
  }
}
function writeHash() {
  if (!$("#tab-rates").classList.contains("active")) return;
  history.replaceState(null, "", `#rates?t=${chipSyms().map(encodeURIComponent).join(",")}&c=${S.country}&y=${S.show10y ? 1 : 0}&s=${S.scale === "linear" ? "lin" : "log"}&l=${S.layout === "split" ? "s" : "o"}${S.from ? `&f=${S.from}` : ""}${S.to ? `&e=${S.to}` : ""}`);
}

// ---------- 畫圖 ----------
function colors() {
  const cs = getComputedStyle(QROOT);
  const v = (n) => cs.getPropertyValue(n).trim();
  return { text: v("--text"), muted: v("--muted"), border: v("--border"), panel: v("--panel") };
}

// 各標的的報酬線：x＝全部日期，y＝收盤 ÷ 區間第一天收盤 × 100（區間一變就重算，所以起點永遠是 100）
function lineY(d, from) {
  let i0 = d.dates.findIndex((x) => x >= from);
  if (i0 < 0) return null;
  const base = d.close[i0];
  return { i0, y: d.close.map((v) => (v / base) * 100) };
}
function logTicks(lo, hi) {
  return [10, 20, 30, 50, 70, 100, 150, 200, 300, 500, 700, 1000, 2000, 3000, 5000, 10000].filter((v) => v >= lo * 0.8 && v <= hi * 1.25);
}
const idxAxisKey = () => (S.layout === "overlay" ? "yaxis" : "yaxis2");

// 圖上的文字：階段名稱（圖上緣外）、各標的在這個階段的報酬（階段內上緣，用標的線的顏色）、第一次升／降息的 ▲▼
function phaseLabels(phases, win, c, perSymRet, use, moves) {
  const plotW = Math.max(240, ($("#chart-rates")?.clientWidth || 900) - 80);
  const dpp = daysBetween(win.from, win.to) / plotW;   // 每個像素代表幾天
  const out = [];
  phases.forEach((p, i) => {
    if (!(p.end > win.from && p.start < win.to)) return;
    const x0 = p.start < win.from ? win.from : p.start, x1 = p.end > win.to ? win.to : p.end;
    const w = daysBetween(x0, x1);
    if (w > dpp * 60) out.push({ xref: "x", yref: "paper", x: x0, xanchor: "left", y: 1.0, yanchor: "bottom", showarrow: false, text: PHASE[p.type].label, font: { size: 10, color: c.muted } });
    if (perSymRet && !p.single && w > dpp * (28 + 9 * 7)) {
      const lines = use.map((s, k) => { const r = perSymRet[s]?.[i]; return r ? `<span style="color:${LINE[k % LINE.length]}">${esc(s)} ${fmtPct(r.cum)}</span>` : null; }).filter(Boolean);
      if (lines.length) out.push({ xref: "x", yref: "paper", x: x0, xanchor: "left", y: 0.985, yanchor: "top", showarrow: false, align: "left",
        text: lines.join("<br>"), font: { size: 11, color: c.text }, bgcolor: c.panel, opacity: 0.88, borderpad: 2 });
    }
  });
  for (const m of moves || []) {
    if (m.date < win.from || m.date > win.to) continue;
    out.push({ xref: "x", yref: "paper", x: m.date, xanchor: "center", y: 0, yanchor: "bottom", showarrow: false,
      text: m.type === "hike" ? "▲" : "▼", font: { size: 13, color: MOVE_COLOR[m.type] } });
  }
  return out;
}

function chartFig(phasesAll, policy, tenY, loaded, syms, win, endDate, moves) {
  const c = colors();
  const overlay = S.layout === "overlay";
  const rateAxis = overlay ? "y2" : "y";    // 疊在一起：利率用右邊刻度；上下分開：利率在上圖
  const idxAxis = overlay ? "y" : "y2";
  const traces = [];
  // 先畫報酬（在下層），再畫利率（在上層），疊在一起時利率階梯線才不會被報酬線蓋住
  syms.forEach((sym, i) => {
    const d = loaded[sym], L = lineY(d, win.from);
    traces.push({ x: d.dates, y: L ? L.y : d.close.map(() => null), type: "scatter", mode: "lines", line: { width: 2, color: LINE[i % LINE.length] }, name: sym,
      xaxis: "x", yaxis: idxAxis, hovertemplate: "%{y:.0f}" });
  });
  const pts = policy.points;
  traces.push({
    x: pts.map((p) => p[0]).concat([endDate]), y: pts.map((p) => p[1]).concat([pts[pts.length - 1][1]]),
    type: "scatter", mode: "lines", line: { shape: "hv", width: overlay ? 2 : 2.2, color: c.text }, name: `${COUNTRY[S.country]}政策利率（${overlay ? "右軸 " : ""}%）`,
    xaxis: "x", yaxis: rateAxis, hovertemplate: "%{y:.2f}%",
  });
  if (tenY && tenY.points.length) {
    traces.push({ x: tenY.points.map((p) => p[0]), y: tenY.points.map((p) => p[1]), type: "scatter", mode: "lines",
      line: { width: 1.4, dash: "dot", color: c.muted }, name: `10 年期公債殖利率（月底${overlay ? "，右軸 " : ""}%）`, xaxis: "x", yaxis: rateAxis, hovertemplate: "%{y:.2f}%" });
  }
  const shapes = phasesAll.map((p) => ({ type: "rect", xref: "x", yref: "paper", x0: p.start, x1: p.end, y0: 0, y1: 1,
    fillcolor: PCOLOR[p.type], line: { width: 0 }, layer: "below" }));
  for (const m of moves) shapes.push({ type: "line", xref: "x", yref: "paper", x0: m.date, x1: m.date, y0: 0, y1: 1, line: { color: MOVE_COLOR[m.type], width: 1.3, dash: "dot" }, layer: "below" });
  const isLog = S.scale === "log";
  const idxAxisCfg = {
    title: { text: isLog ? "報酬指數（起點＝100，對數刻度）" : "報酬指數（起點＝100）", standoff: 18 }, type: isLog ? "log" : "linear",
    gridcolor: c.border, zerolinecolor: c.border, automargin: true, fixedrange: true,
  };
  const rateAxisCfg = { title: { text: "利率 %", standoff: 14 }, rangemode: "tozero", automargin: true, ticksuffix: "%", fixedrange: true };
  const xaxis = {
    range: [win.from, win.to], gridcolor: c.border, linecolor: c.border, automargin: true,
    tickformatstops: TICKFMT, hoverformat: "%Y/%m/%d",
    rangeslider: { visible: true, thickness: 0.07, range: [MIN_DATE, endDate], bgcolor: "rgba(128,128,128,0.10)", bordercolor: c.border, borderwidth: 1 },
  };
  const base = {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { color: c.text, size: 12 },
    margin: { l: 56, r: overlay ? 56 : 16, t: 64, b: 30 }, hovermode: "x unified", showlegend: true,
    legend: { orientation: "h", yref: "container", y: 1, yanchor: "top", x: 0 },
    hoverlabel: { bgcolor: c.panel, font: { color: c.text }, bordercolor: c.border },
    dragmode: "zoom", shapes, annotations: [],
  };
  const layout = overlay ? {
    ...base, xaxis,
    yaxis: idxAxisCfg,                                                                   // 左軸：報酬
    yaxis2: { ...rateAxisCfg, overlaying: "y", side: "right", showgrid: false, zeroline: false },   // 右軸：利率（和報酬共用同一張圖）
  } : {
    ...base, xaxis: { ...xaxis, anchor: "y2" },
    yaxis: { ...rateAxisCfg, domain: [0.60, 1], gridcolor: c.border, zerolinecolor: c.border },
    yaxis2: { ...idxAxisCfg, domain: [0, 0.52] },
  };
  return { traces, layout };
}


function tableHtml(phases, syms, perSymRet) {
  const head = `<tr><th>階段</th><th>期間</th><th>長度</th><th>利率</th>${syms.map((s) => `<th>${esc(s)}</th>`).join("")}</tr>`;
  const rows = phases.map((p, i) => {
    const lab = `${PBADGE[p.type]} ${PHASE[p.type].label}${p.ongoing ? "（進行中）" : ""}${p.single ? '<span class="sub">單次調整，無報酬可算</span>' : ""}${p.n > 1 ? `<span class="sub">共 ${p.n} 次調整</span>` : ""}`;
    const clip = (p.clippedFrom ? `實際始於 ${fmtYM(p.clippedFrom)}` : "") + (p.clippedFrom && p.clippedTo ? "、" : "") + (p.clippedTo ? `實際止於 ${fmtYM(p.clippedTo)}` : "");
    const period = `${fmtYM(p.start)}${p.clippedFrom ? "＊" : ""} → ${fmtYM(p.end)}${p.clippedTo ? "＊" : ""}${clip ? `<span class="sub">＊${clip}，只算所選區間內</span>` : ""}`;
    const rate = p.type === "hike" || p.type === "cut" ? `${p.rateFrom.toFixed(2)} → ${p.rateTo.toFixed(2)}%` : `${p.rateTo.toFixed(2)}%`;
    const cells = syms.map((s) => {
      const r = perSymRet[s]?.[i];
      if (p.single || !r) return "<td>—</td>";
      return `<td class="${cls(r.cum)}">${fmtPct(r.cum)}${r.partialFrom ? "＊" : ""}<span class="sub">${r.ann == null ? "不滿 1 年" : `年化 ${fmtPct(r.ann)}`}${r.partialFrom ? `｜自 ${fmtYM(r.partialFrom)} 起` : ""}</span></td>`;
    }).join("");
    return `<tr><td>${lab}</td><td>${period}</td><td>${p.single ? "0 天" : fmtLen(daysBetween(p.start, p.end))}</td><td>${rate}</td>${cells}</tr>`;
  }).reverse().join("");   // 最新在上
  return `<div class="table-wrap"><table class="data"><thead>${head}</thead><tbody>${rows}</tbody></table></div>`;
}

function summaryHtml(phases, syms, perSymRet) {
  const sm = summarize(phases, perSymRet);
  const head = `<tr><th>階段</th>${syms.map((s) => `<th>${esc(s)}</th>`).join("")}</tr>`;
  const rows = Object.keys(PHASE).map((t) => `<tr><td>${PBADGE[t]} ${PHASE[t].label}</td>${syms.map((s) => {
    const x = sm[t][s];
    return x ? `<td class="${cls(x.median)}">中位數 ${fmtPct(x.median)}<span class="sub">平均 ${fmtPct(x.mean)}｜${x.up}/${x.n} 段上漲</span></td>` : "<td>—</td>";
  }).join("")}</tr>`).join("");
  return `<div class="table-wrap"><table class="data"><thead>${head}</thead><tbody>${rows}</tbody></table></div>`;
}

function panelsHtml(phases, use, perSymRet) {
  if (!use.length) return `<div class="panel placeholder">請在左邊選至少一檔標的。</div>`;
  return `<div class="panel"><h2>每一輪週期的報酬</h2>${tableHtml(phases, use, perSymRet)}
      <p class="hint">累積報酬＝階段結束價 ÷ 開始價 − 1（含息還原價）；年化只在階段滿 1 年才顯示。＊＝標的在階段開始後才有資料，從它的第一天算。最新一段在最上面。</p></div>
    <div class="panel"><h2>四種階段的整體表現</h2>${summaryHtml(phases, use, perSymRet)}
      <p class="hint">單次調整（長度 0 天）的階段不列入。樣本只有幾輪，只能看歷史傾向，<b>不能當預測</b>。</p></div>`;
}

// ---------- 區間改變（在圖上拖曳、拉滑桿、按快速按鈕都會走到這裡）：表格、報酬起點、Y 軸範圍一起更新 ----------
function updateWindow(from, to) {
  const X = CTX; if (!X) return;
  const notes = $("#rates-win-notes");
  if (daysBetween(from, to) < 30) { if (notes) notes.innerHTML = `<div class="notice">選到的區間不到 30 天，表格先維持上一次的結果；請再拉寬一點。</div>`; return; }
  S.from = from > MIN_DATE ? from : null; S.to = to < X.endDate ? to : null;
  S.lastKey = curKey();
  const phases = buildPhases(X.policy.points, X.endDate, from, to < X.endDate ? to : null);
  const perSymRet = {}, ys = [], wn = [];
  let lo = Infinity, hi = 0;
  X.use.forEach((s) => {
    const d = X.loaded[s];
    perSymRet[s] = phases.map((p) => (p.single ? null : periodReturn(d, p.start, p.end)));
    const L = lineY(d, from);
    if (!L) { ys.push(d.close.map(() => null)); wn.push(`${esc(s)} 在 ${fmtYM(from)} → ${fmtYM(to)} 這段時間沒有資料。`); return; }
    ys.push(L.y);
    for (let j = L.i0; j < d.dates.length && d.dates[j] <= to; j += 1) { const v = L.y[j]; if (v < lo) lo = v; if (v > hi) hi = v; }
    if (daysBetween(from, d.dates[L.i0]) > 7) wn.push(`${esc(s)} 的資料從 ${fmtYM(d.dates[L.i0])} 才開始，報酬指數從那天起算（起點＝100）。`);
  });
  const t = $("#rates-win-title"); if (t) t.textContent = `　${fmtYM(from)} → ${fmtYM(to)}`;
  if (notes) notes.innerHTML = wn.map((n) => `<div class="notice">${n}</div>`).join("");
  const pn = $("#rates-win-panels"); if (pn) pn.innerHTML = panelsHtml(phases, X.use, perSymRet);
  $$("#rates-range button").forEach((b) => {
    const n = +b.dataset.years, f = n ? addYears(X.endDate, n) : MIN_DATE;
    b.setAttribute("aria-pressed", String(from === (f < MIN_DATE ? MIN_DATE : f) && to === X.endDate));
  });
  const el = $("#chart-rates");
  if (el && el.data) {
    const c = colors(), k = idxAxisKey(), isLog = S.scale === "log";
    const rl = { annotations: phaseLabels(phases, { from, to }, c, perSymRet, X.use, X.moves) };
    if (X.use.length) Plotly.restyle(el, { y: ys }, X.use.map((_, i) => i));
    if (hi > 0 && isFinite(lo)) {
      rl[`${k}.autorange`] = false;
      if (isLog) {
        rl[`${k}.range`] = [Math.log10(lo * 0.96), Math.log10(hi * 1.04)];   // 縱軸貼著所選區間的最低、最高點，起伏才看得清楚（數據不動）
        const tv = logTicks(lo, hi);
        if (tv.length >= 2) { rl[`${k}.tickmode`] = "array"; rl[`${k}.tickvals`] = tv; rl[`${k}.ticktext`] = tv.map(String); } else rl[`${k}.tickmode`] = "auto";
      } else { const pad = (hi - lo) * 0.04 || 1; rl[`${k}.range`] = [lo - pad, hi + pad]; rl[`${k}.tickmode`] = "auto"; }
    }
    Plotly.relayout(el, rl);
  }
  writeHash();
}

// ---------- 事件前後圖：每一輪第一次升息／降息前後 12 個月，股價怎麼走 ----------
function renderEvents() {
  const X = CTX, box = $("#rates-events");
  if (!box) return;
  if (!X || !X.use.length) { box.innerHTML = ""; return; }
  if (!X.use.includes(S.evSym)) S.evSym = X.use[0];
  const kind = S.evKind === "cut" ? "cut" : "hike", kname = kind === "hike" ? "升息" : "降息";
  const d = X.loaded[S.evSym], c = colors();
  const traces = [], rows = [], paths = [];
  X.moves.filter((m) => m.type === kind).forEach((m, i) => {
    const e = eventPath(d, m.date);
    if (!e) { rows.push(`<tr><td>${fmtYM(m.date)}</td><td colspan="2" class="hint">${esc(S.evSym)} 那時還沒有資料</td></tr>`); return; }
    const color = EVC[i % EVC.length];
    traces.push({ x: e.x, y: e.y, type: "scatter", mode: "lines", line: { width: 1.8, color }, name: `${fmtYM(m.date)}${e.hasBefore ? "" : "（前段資料不全）"}`, hovertemplate: "%{y:.0f}" });
    paths.push(e);
    const r = eventReturns(d, m.date, 182);
    const cell = (v, none) => (v == null ? `<td>${none}</td>` : `<td class="${cls(v)}">${fmtPct(v)}</td>`);
    rows.push(`<tr><td><span style="color:${color}">●</span> ${fmtYM(m.date)}</td>${cell(r.before, "資料不足")}${cell(r.after, "還沒滿 6 個月")}</tr>`);
    paths[paths.length - 1].r = r;
  });
  // 平均線：每個月份位置上，有涵蓋到那個位置的各輪取平均
  const grid = [], avg = [];
  for (let m = -12; m <= 12.001; m += 0.25) {
    const vals = [];
    for (const e of paths) {
      if (m < 0 && !e.hasBefore) continue;
      if (m > 0 && !e.hasAfter) continue;
      let k = -1; for (let j = 0; j < e.x.length && e.x[j] <= m; j += 1) k = j;
      if (k >= 0) vals.push(e.y[k]);
    }
    if (vals.length >= 2) { grid.push(m); avg.push(vals.reduce((a, b) => a + b, 0) / vals.length); }
  }
  if (grid.length) traces.push({ x: grid, y: avg, type: "scatter", mode: "lines", line: { width: 3.2, color: c.text, dash: "dash" }, name: "各輪平均（只算資料完整的）", hovertemplate: "%{y:.0f}" });
  const stat = (key) => { const v = paths.map((e) => e.r?.[key]).filter((x) => x != null); return v.length ? { n: v.length, mean: v.reduce((a, b) => a + b, 0) / v.length, up: v.filter((x) => x > 0).length } : null; };
  const sb = stat("before"), sa = stat("after");
  const sumCell = (x) => (x ? `<td class="${cls(x.mean)}">平均 ${fmtPct(x.mean)}<span class="sub">${x.up}/${x.n} 次上漲</span></td>` : "<td>—</td>");
  const symSel = X.use.map((s) => `<option value="${esc(s)}"${s === S.evSym ? " selected" : ""}>${esc(s)}</option>`).join("");
  box.innerHTML = `<div class="panel"><h2>${kname}前後，股價怎麼走？</h2>
    <p class="hint">以每一輪「第一次${kname}」那天為 0、價格＝100，往前、往後各看 12 個月，一條線＝一輪。如果市場是「宣布才反應」，線在 0 之前會是平的；如果在 0 之前就先漲或先跌，代表市場已經提前反映。</p>
    <div class="rates-evctl"><label>事件 <select id="rates-ev-kind"><option value="hike"${kind === "hike" ? " selected" : ""}>第一次升息</option><option value="cut"${kind === "cut" ? " selected" : ""}>第一次降息</option></select></label>
      <label>標的 <select id="rates-ev-sym">${symSel}</select></label></div>
    <div id="chart-rates-ev" class="chart"></div>
    <div class="table-wrap"><table class="data"><thead><tr><th>${COUNTRY[S.country]}第一次${kname}</th><th>${esc(S.evSym)} 前 6 個月</th><th>後 6 個月</th></tr></thead>
      <tbody>${rows.reverse().join("")}<tr><td><b>平均</b></td>${sumCell(sb)}${sumCell(sa)}</tr></tbody></table></div>
    <p class="hint">橫軸＝距離事件日的月數（0＝事件日）。前／後 6 個月＝事件日往前／往後 182 天的報酬（含息還原價）；資料不夠（標的上市太晚、或事件太新）的那一格不算。只有幾次樣本，<b>只能看傾向，不是預測</b>。這張圖只看得到「股價先動了」，看不到當時市場預期的利率（需要利率期貨資料），所以不能證明是哪則消息造成的。</p></div>`;
  const ticks = [-12, -9, -6, -3, 0, 3, 6, 9, 12];
  Plotly.react($("#chart-rates-ev"), traces, {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { color: c.text, size: 12 },
    margin: { l: 52, r: 16, t: 20, b: 44 }, hovermode: "x unified", showlegend: true, legend: { orientation: "h", x: 0, y: -0.2 },
    hoverlabel: { bgcolor: c.panel, font: { color: c.text }, bordercolor: c.border },
    xaxis: { range: [-12, 12], gridcolor: c.border, linecolor: c.border, tickvals: ticks, ticktext: ticks.map((v) => (v === 0 ? "事件日" : v > 0 ? `+${v} 月` : `${v} 月`)), hoverformat: ".1f", fixedrange: true },
    yaxis: { title: { text: `${S.evSym}（事件日＝100）`, standoff: 8 }, gridcolor: c.border, zerolinecolor: c.border, automargin: true, fixedrange: true },
    shapes: [{ type: "line", xref: "x", yref: "paper", x0: 0, x1: 0, y0: 0, y1: 1, line: { color: MOVE_COLOR[kind], width: 1.6, dash: "dot" } }],
  }, { responsive: true, displaylogo: false, displayModeBar: false });
}

let relayoutTimer;
function onRelayout(ev) {
  const X = CTX; if (!X) return;
  let f = ev["xaxis.range[0]"], t = ev["xaxis.range[1]"];
  if (Array.isArray(ev["xaxis.range"])) [f, t] = ev["xaxis.range"];
  if (ev["xaxis.autorange"]) { f = MIN_DATE; t = X.endDate; }
  if (f == null || t == null) return;   // 只改了 Y 軸或標籤：不用處理
  f = String(f).slice(0, 10); t = String(t).slice(0, 10);
  if (!isoDate(f) || !isoDate(t)) return;
  if (f < MIN_DATE) f = MIN_DATE;
  if (t > X.endDate) t = X.endDate;
  if (f >= t) return;
  clearTimeout(relayoutTimer);
  relayoutTimer = setTimeout(() => updateWindow(f, t), 120);   // 拖曳過程會連續觸發，等停下來再算
}

// ---------- 主流程 ----------
export async function render() {
  const out = $("#out-rates");
  await loadRates();
  if (S.ratesErr) { out.innerHTML = `<div class="notice error">❌ ${esc(S.ratesErr)}</div>`; return; }
  try { await loadManifest(); } catch { /* 沒有 manifest 就沒有標的可選 */ }
  const R = S.rates, c = S.country;
  const policy = R.series[`${c}_policy`], tenY = S.show10y ? R.series[`${c}_10y`] : null;
  const notes = [];
  if (!policy || !policy.points.length) {
    const why = (R.unavailable || []).filter((u) => u.includes(c === "us" ? "美國" : "台灣"));
    out.innerHTML = `<div class="notice">⚠️ ${COUNTRY[c]}的政策利率資料目前是<b>待確認</b>（沒有可驗證的官方來源，所以不顯示，也不估計）。</div>${why.length ? `<ul class="hint">${why.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>` : ""}<p class="hint">可以先把上方「用哪個國家的升降息週期」切回美國。</p>`;
    CTX = null;
    return;
  }
  if (S.show10y && !(tenY && tenY.points.length)) notes.push(`${COUNTRY[c]} 10 年期公債殖利率目前是待確認，所以沒有畫。`);
  const syms = chipSyms();
  const endDate = policy.through || R.updated.slice(0, 10);
  // 起迄日（來自網址或上一次在圖上選的區間；預設＝2000 年起到資料截至日）：不合理就退回預設
  let from = isoDate(S.from) ? S.from : MIN_DATE, to = isoDate(S.to) ? S.to : endDate;
  if (from < MIN_DATE) from = MIN_DATE;
  if (to > endDate) to = endDate;
  if (daysBetween(from, to) < 30) { notes.push("網址裡的時間區間不合理（至少要 30 天），已改回預設（2000 年起到最新）。"); from = MIN_DATE; to = endDate; S.from = S.to = null; }
  const win = { from, to };
  const phasesAll = buildPhases(policy.points, endDate);
  const moves = firstMoves(buildPhases(policy.points, endDate, "1900-01-01"));   // 每一輪第一次升息／降息（含 2000 年以前，事件前後圖要用）

  const loaded = {}, missing = [];
  await Promise.all(syms.map(async (s) => {
    try { const d = await loadSeries(s); if (d && d.dates?.length) loaded[s] = d; else missing.push(s); } catch { missing.push(s); }
  }));
  const use = syms.filter((s) => loaded[s]);
  if (missing.length) notes.push(`查無資料、已跳過：<b>${missing.map(esc).join("、")}</b>（可到「⚙️ 管理標的」新增）。`);
  for (const s of use) { const cur = S.manifest.get(s)?.note; if (cur) notes.push(`${esc(s)}：${esc(cur)}`); }

  const srcs = [policy, tenY].filter(Boolean).map((x) => `<li>${esc(x.name)}：${esc(x.source)}，資料截至 ${esc(fmtYM(x.through || x.asOf))}（<a href="${esc(x.url)}" target="_blank" rel="noopener">來源</a>）</li>`).join("");
  const unav = (R.unavailable || []).map((u) => `<li>${esc(u)}</li>`).join("");
  out.innerHTML = `
    ${notes.map((n) => `<div class="notice">${n}</div>`).join("")}
    <div class="panel"><h2>${COUNTRY[c]}升降息週期 vs 報酬<span class="sub" id="rates-win-title" style="font-weight:400"></span></h2>
      <div class="rates-range" id="rates-range" role="group" aria-label="快速選時間區間">${PRESETS.map(([t, n]) => `<button type="button" class="secondary small" data-years="${n}">${t}</button>`).join("")}</div>
      <div id="chart-rates" class="chart tall"></div>
      <p class="hint">背景色＝階段：🔺升息期　⏸高檔停留　🔻降息期　⏸低檔停留。▲▼ 虛線＝每一輪第一次升息／降息。階段內的數字＝各標的在該階段的報酬；縱軸會貼著所選區間的最高、最低點，所以區間越短，起伏看起來越大（數字不變）。<b>選時間區間</b>：在圖上按住左右拖曳框選、拉圖下方的滑桿（拖兩端調整範圍、拖中間平移），或按上面的「1 年、3 年…」；雙擊圖面回到上一個範圍。滑鼠移到圖上看數字（日期顯示 年/月/日）。</p></div>
    <div id="rates-win-notes"></div>
    <div id="rates-win-panels"></div>
    <div id="rates-events"></div>
    <div class="panel"><h2>「對數刻度」是什麼意思？</h2>
      <p class="hint">一般（線性）刻度：每一格代表<b>漲幾點</b>。對數刻度：每一格代表<b>漲幾倍</b>。</p>
<pre class="hint" style="white-space:pre;overflow-x:auto;margin:6px 0">
線性：  0    500   1000  1500  2000      ← 每格 +500
        │─────│─────│─────│─────│
對數：  100   200   400   800   1600     ← 每格 ×2
        │─────│─────│─────│─────│
</pre>
      <p class="hint">例子：SPY 從 100 漲到 200（漲 1 倍），和從 800 漲到 1600（也漲 1 倍），在對數圖上<b>爬升的高度一樣</b>；線性圖上後者看起來大很多，前面 20 年的起伏就被壓成一條平線。看 20 年以上的長期走勢、或同時比較漲幅差很多的標的，建議用對數；只看短期、想比較實際點數時用線性。你可以在左邊「報酬指數的刻度」隨時切換比較。</p></div>
    <div class="panel"><h2>怎麼切、資料哪來</h2>
      <ul class="hint">
        <li>只看政策利率「有變動」的日子；連續同方向的調整併成一輪，方向一反轉就開始新的一輪。</li>
        <li>升息期＝首次升息到最後一次升息；高檔停留＝最後一次升息到下一次降息；降息期、低檔停留同理。</li>
        <li>只調一次的輪，長度 0 天，列出但不算報酬。最後一段標「進行中」，到資料截至日為止。</li>
        <li>資料從 2000 年起；你在圖上選的時間區間之外的部分不算，階段跨過區間邊界時會被截斷（表上有＊）。</li>
        <li>報酬用各標的自己的幣別，不換匯。^GSPC、^TWII 是價格指數，不含股息。</li>
        ${srcs}${unav}
      </ul>
      <p class="hint">利率資料更新：${esc(fmtYM(R.updated))}（GitHub Actions 每週自動抓取）。</p></div>`;
  CTX = { policy, endDate, use, loaded, phasesAll, moves };
  const fig = chartFig(phasesAll, policy, tenY, loaded, use, win, endDate, moves);
  const el = $("#chart-rates");
  await Plotly.react(el, fig.traces, fig.layout, { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] });
  el.on("plotly_relayout", onRelayout);
  updateWindow(from, to);
  renderEvents();
  setTimeout(() => window.dispatchEvent(new Event("resize")), 30);
}

// ---------- 啟動／切到這個分頁時 ----------
let timer;
const schedule = () => { clearTimeout(timer); timer = setTimeout(render, 120); };
export function activate(hash) {
  if (!S.started) {
    S.started = true;
    $("#rates-country").addEventListener("change", (e) => { S.country = e.target.value; render(); });
    $("#rates-10y").addEventListener("change", (e) => { S.show10y = e.target.checked; render(); });
    $("#out-rates").addEventListener("click", (e) => {
      const b = e.target.closest("#rates-range button[data-years]"); if (!b || !CTX) return;
      const n = +b.dataset.years, f = n ? addYears(CTX.endDate, n) : MIN_DATE;
      Plotly.relayout($("#chart-rates"), { "xaxis.range": [f < MIN_DATE ? MIN_DATE : f, CTX.endDate] });   // 會觸發 plotly_relayout → updateWindow
    });
    $("#out-rates").addEventListener("change", (e) => {
      if (e.target.id === "rates-ev-kind") { S.evKind = e.target.value; renderEvents(); }
      if (e.target.id === "rates-ev-sym") { S.evSym = e.target.value; renderEvents(); }
    });
    $("#rates-scale").addEventListener("change", (e) => { S.scale = e.target.value; render(); });
    $("#rates-layout").addEventListener("change", (e) => { S.layout = e.target.value; render(); });
    const chips = $('.picker[data-picker="rates"] .chips');
    if (chips) new MutationObserver(schedule).observe(chips, { childList: true });
    matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => { if ($("#tab-rates").classList.contains("active")) render(); });
  }
  applyHash(hash);
  const key = curKey();
  if (key !== S.lastKey || !$("#chart-rates")) { S.lastKey = key; render(); }
  else setTimeout(() => window.dispatchEvent(new Event("resize")), 30);
}
window.__quantRates = { activate, render };
