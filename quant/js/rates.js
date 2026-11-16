// 🏦 升降息週期分頁（手寫；tools/quant_sync.py 不會覆蓋）
//
//   loader.js 在載入 app.js 之前呼叫 inject()：把分頁按鈕與分頁內容放進 view.html 的容器
//   （app.js 的 showTab／loadHash／標的選擇器本來就是通用的，會自動認得新分頁，所以不用改 app.js）
//
//   quant/data/rates.json（GitHub Actions 每週抓）──┐
//   quant/data/prices/*.json（回測共用的股價檔）─────┴─▶ rates-core.js 切週期、算報酬 ─▶ 圖＋表
//
//   畫面：上圖＝政策利率階梯線（背景色＝四種階段），下圖＝各標的累積報酬（起點 100、對數軸），兩圖共用時間軸
import { DATA_BASE } from "./config.js";
import { PHASE, buildPhases, periodReturn, summarize, daysBetween } from "./rates-core.js";

const QROOT = document.getElementById("quant-dca-view") || document;
const $ = (sel, root = QROOT) => root.querySelector(sel);
const $$ = (sel, root = QROOT) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const MIN_DATE = "2000-01-01";
const COUNTRY = { us: "美國", tw: "台灣" };
const PCOLOR = {   // 背景色塊；深淺色模式都用半透明，再加文字標籤（不只靠顏色分辨）
  hike: "rgba(226,83,60,0.20)", holdHigh: "rgba(150,150,150,0.20)",
  cut: "rgba(34,160,110,0.20)", holdLow: "rgba(70,120,230,0.16)",
};
const PBADGE = { hike: "🔺", holdHigh: "⏸", cut: "🔻", holdLow: "⏸" };
const LINE = ["#2563eb", "#e8590c", "#12805c", "#9c36b5", "#c2255c"];

const fmtPct = (x, signed = true) => (x == null || !isFinite(x) ? "—" : `${signed && x > 0 ? "+" : ""}${(x * 100).toFixed(1)}%`);
const cls = (x) => (x > 0 ? "pos" : x < 0 ? "neg" : "");
const fmtLen = (days) => (days < 45 ? `${days} 天` : days < 700 ? `${(days / 30.44).toFixed(0)} 個月` : `${(days / 365.25).toFixed(1)} 年`);

const S = { rates: null, ratesErr: null, manifest: null, cache: new Map(), country: "us", show10y: false, started: false, lastKey: "", obs: null };

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
      <label class="checkbox"><input type="checkbox" id="rates-10y"> 同時畫 10 年期公債殖利率</label>
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
  history.replaceState(null, "", `#rates?t=${chipSyms().map(encodeURIComponent).join(",")}&c=${S.country}&y=${S.show10y ? 1 : 0}`);
}

// ---------- 畫圖 ----------
function colors() {
  const cs = getComputedStyle(QROOT);
  const v = (n) => cs.getPropertyValue(n).trim();
  return { text: v("--text"), muted: v("--muted"), border: v("--border"), panel: v("--panel") };
}

function chartFig(phases, policy, tenY, perSym, syms, endDate) {
  const c = colors();
  const traces = [{
    x: policy.points.map((p) => p[0]).concat([endDate]), y: policy.points.map((p) => p[1]).concat([policy.points[policy.points.length - 1][1]]),
    type: "scatter", mode: "lines", line: { shape: "hv", width: 2.2, color: c.text }, name: `${COUNTRY[S.country]}政策利率`,
    xaxis: "x", yaxis: "y", hovertemplate: "%{y:.2f}%",
  }];
  if (tenY && tenY.points.length) {
    traces.push({ x: tenY.points.map((p) => p[0]), y: tenY.points.map((p) => p[1]), type: "scatter", mode: "lines",
      line: { width: 1.4, dash: "dot", color: c.muted }, name: "10 年期公債殖利率（月底）", xaxis: "x", yaxis: "y", hovertemplate: "%{y:.2f}%" });
  }
  syms.forEach((sym, i) => {
    const s = perSym[sym];
    if (!s) return;
    traces.push({ x: s.x, y: s.y, type: "scatter", mode: "lines", line: { width: 1.6, color: LINE[i % LINE.length] }, name: sym,
      xaxis: "x", yaxis: "y2", hovertemplate: "%{y:.0f}" });
  });
  const shapes = phases.map((p) => ({ type: "rect", xref: "x", yref: "paper", x0: p.start, x1: p.end, y0: 0, y1: 1,
    fillcolor: PCOLOR[p.type], line: { width: 0 }, layer: "below" }));
  const annotations = phases.filter((p) => daysBetween(p.start, p.end) > 330).map((p) => ({
    xref: "x", yref: "paper", x: p.start, xanchor: "left", y: 1.0, yanchor: "bottom", showarrow: false,
    text: PHASE[p.type].label, font: { size: 10, color: c.muted },
  }));
  let lo = Infinity, hi = 0;
  for (const sym of syms) { const s = perSym[sym]; if (s) for (const v of s.y) { if (v < lo) lo = v; if (v > hi) hi = v; } }
  const tv = [10, 20, 30, 50, 70, 100, 150, 200, 300, 500, 700, 1000, 2000, 3000, 5000, 10000].filter((v) => v >= lo * 0.8 && v <= hi * 1.25);
  const layout = {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", font: { color: c.text, size: 12 },
    margin: { l: 56, r: 16, t: 34, b: 40 }, hovermode: "x unified", showlegend: true, legend: { orientation: "h", y: -0.12, x: 0 },
    hoverlabel: { bgcolor: c.panel, font: { color: c.text }, bordercolor: c.border },
    xaxis: { anchor: "y2", range: [MIN_DATE, endDate], gridcolor: c.border, linecolor: c.border, automargin: true },
    yaxis: { domain: [0.60, 1], title: { text: "利率 %" }, gridcolor: c.border, zerolinecolor: c.border, rangemode: "tozero", automargin: true },
    yaxis2: { domain: [0, 0.52], title: { text: "累積報酬指數（起點＝100，對數軸）" }, type: "log", gridcolor: c.border, automargin: true,
      ...(tv.length >= 2 ? { tickmode: "array", tickvals: tv, ticktext: tv.map(String) } : {}) },
    shapes, annotations,
  };
  return { traces, layout };
}

function tableHtml(phases, syms, perSymRet) {
  const head = `<tr><th>階段</th><th>期間</th><th>長度</th><th>利率</th>${syms.map((s) => `<th>${esc(s)}</th>`).join("")}</tr>`;
  const rows = phases.map((p, i) => {
    const lab = `${PBADGE[p.type]} ${PHASE[p.type].label}${p.ongoing ? "（進行中）" : ""}${p.single ? '<span class="sub">單次調整，無報酬可算</span>' : ""}${p.n > 1 ? `<span class="sub">共 ${p.n} 次調整</span>` : ""}`;
    const period = `${p.start}${p.clippedFrom ? "＊" : ""} → ${p.end}${p.clippedFrom ? `<span class="sub">＊實際始於 ${p.clippedFrom}，只算 2000 年起</span>` : ""}`;
    const rate = p.type === "hike" || p.type === "cut" ? `${p.rateFrom.toFixed(2)} → ${p.rateTo.toFixed(2)}%` : `${p.rateTo.toFixed(2)}%`;
    const cells = syms.map((s) => {
      const r = perSymRet[s]?.[i];
      if (p.single || !r) return "<td>—</td>";
      return `<td class="${cls(r.cum)}">${fmtPct(r.cum)}${r.partialFrom ? "＊" : ""}<span class="sub">${r.ann == null ? "不滿 1 年" : `年化 ${fmtPct(r.ann)}`}${r.partialFrom ? `｜自 ${r.partialFrom} 起` : ""}</span></td>`;
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
    return;
  }
  if (S.show10y && !(tenY && tenY.points.length)) notes.push(`${COUNTRY[c]} 10 年期公債殖利率目前是待確認，所以沒有畫。`);
  const syms = chipSyms();
  const endDate = policy.through || R.updated.slice(0, 10);
  const phases = buildPhases(policy.points, endDate, MIN_DATE);

  const loaded = {}, missing = [];
  await Promise.all(syms.map(async (s) => {
    try { const d = await loadSeries(s); if (d && d.dates?.length) loaded[s] = d; else missing.push(s); } catch { missing.push(s); }
  }));
  const use = syms.filter((s) => loaded[s]);
  if (missing.length) notes.push(`查無資料、已跳過：<b>${missing.map(esc).join("、")}</b>（可到「⚙️ 管理標的」新增）。`);

  const perSymRet = {}, perSymLine = {};
  for (const s of use) {
    const d = loaded[s];
    perSymRet[s] = phases.map((p) => (p.single ? null : periodReturn(d, p.start, p.end)));
    const i0 = d.dates.findIndex((x) => x >= MIN_DATE);
    if (i0 >= 0) {
      const base = d.close[i0];
      perSymLine[s] = { x: d.dates.slice(i0), y: d.close.slice(i0).map((v) => (v / base) * 100) };
      if (d.dates[i0] > "2000-01-08") notes.push(`${esc(s)} 的資料從 ${d.dates[i0]} 才開始，圖上從那天起算（起點＝100）。`);
    }
    const cur = S.manifest.get(s)?.note;
    if (cur) notes.push(`${esc(s)}：${esc(cur)}`);
  }

  const srcs = [policy, tenY].filter(Boolean).map((x) => `<li>${esc(x.name)}：${esc(x.source)}，資料截至 ${esc(x.through || x.asOf)}（<a href="${esc(x.url)}" target="_blank" rel="noopener">來源</a>）</li>`).join("");
  const unav = (R.unavailable || []).map((u) => `<li>${esc(u)}</li>`).join("");
  out.innerHTML = `
    ${notes.map((n) => `<div class="notice">${n}</div>`).join("")}
    <div class="panel"><h2>${COUNTRY[c]}升降息週期 vs 報酬</h2>
      <div id="chart-rates" class="chart tall"></div>
      <p class="hint">背景色＝階段：🔺升息期　⏸高檔停留　🔻降息期　⏸低檔停留。滑鼠移到圖上看數字；拖曳可放大，雙擊還原。</p></div>
    ${use.length ? `<div class="panel"><h2>每一輪週期的報酬</h2>${tableHtml(phases, use, perSymRet)}
      <p class="hint">累積報酬＝階段結束價 ÷ 開始價 − 1（含息還原價）；年化只在階段滿 1 年才顯示。＊＝標的在階段開始後才有資料，從它的第一天算。最新一段在最上面。</p></div>
    <div class="panel"><h2>四種階段的整體表現</h2>${summaryHtml(phases, use, perSymRet)}
      <p class="hint">單次調整（長度 0 天）的階段不列入。樣本只有幾輪，只能看歷史傾向，<b>不能當預測</b>。</p></div>` : `<div class="panel placeholder">請在左邊選至少一檔標的。</div>`}
    <div class="panel"><h2>怎麼切、資料哪來</h2>
      <ul class="hint">
        <li>只看政策利率「有變動」的日子；連續同方向的調整併成一輪，方向一反轉就開始新的一輪。</li>
        <li>升息期＝首次升息到最後一次升息；高檔停留＝最後一次升息到下一次降息；降息期、低檔停留同理。</li>
        <li>只調一次的輪，長度 0 天，列出但不算報酬。最後一段標「進行中」，到資料截至日為止。</li>
        <li>只顯示 2000 年以後；跨過 2000-01-01 的階段起點會被截在那天（表上有＊）。</li>
        <li>報酬用各標的自己的幣別，不換匯。^GSPC、^TWII 是價格指數，不含股息。</li>
        ${srcs}${unav}
      </ul>
      <p class="hint">利率資料更新：${esc(R.updated)}（GitHub Actions 每週自動抓取）。</p></div>`;
  if (use.length) {
    const fig = chartFig(phases, policy, tenY, perSymLine, use, endDate);
    Plotly.react($("#chart-rates"), fig.traces, fig.layout, { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] });
  } else {
    const fig = chartFig(phases, policy, tenY, {}, [], endDate);
    Plotly.react($("#chart-rates"), fig.traces, fig.layout, { responsive: true, displaylogo: false });
  }
  writeHash();
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
    const chips = $('.picker[data-picker="rates"] .chips');
    if (chips) new MutationObserver(schedule).observe(chips, { childList: true });
    matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => { if ($("#tab-rates").classList.contains("active")) render(); });
  }
  applyHash(hash);
  const key = `${chipSyms().join()}|${S.country}|${S.show10y}`;
  if (key !== S.lastKey || !$("#chart-rates")) { S.lastKey = key; render(); }
  else setTimeout(() => window.dispatchEvent(new Event("resize")), 30);
}
window.__quantRates = { activate, render };
