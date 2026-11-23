// 原本由 tools/quant_sync.py 從 Lump-Sum-v.s.-DCA 產生（標 [主站] 的是當時的改動處）；2026-11-20 起改為手寫維護（直接改這支檔）
// ============================================================
// app.js — 畫面與互動（計算邏輯都在 engine.js）
// ============================================================
import {
  lumpSumVsDca, rollingComparison, assetAllocation, volatilityStats,
  yearlyTimingTest, toDay, fromDay, monthlyContribution, drawdownEpisodes, crashInWindow, crashCompare,
} from "./engine.js?v=dc4a96da";
import { DATA_BASE, CRASH_CONFIG, MACRO_LATEST } from "./config.js?v=dc4a96da";
import { themeColors, axisBase } from "./theme.js?v=dc4a96da";
import {
  normMode, hashValue, VIEW_LABELS, valueTraceSpecs, metricRows, winnerStrategy,
  annualColumns, showBuysPanel, showLsMarks,
} from "./view-mode.js?v=dc4a96da";
// [主站] 所有選取都限定在量化容器內，不會選到主站的元素
const QROOT = document.getElementById("quant-dca-view") || document;

const $ = (sel, root = QROOT) => root.querySelector(sel);
const $$ = (sel, root = QROOT) => [...root.querySelectorAll(sel)];
const today = new Date().toISOString().slice(0, 10);

// 歷史重大事件（高點 = 崩盤前、低點 = 谷底）
const EVENTS = [
  ["", "— 自訂開始日期 —"],
  ["2022-01-03", "2022 升息前高點 (2022-01-03)"],
  ["2022-10-12", "2022 熊市低點 (2022-10-12)"],
  ["2020-02-19", "2020 新冠疫情高點 (2020-02-19)"],
  ["2020-03-23", "2020 新冠疫情低點 (2020-03-23)"],
  ["2007-10-09", "2007 金融海嘯高點 (2007-10-09)"],
  ["2009-03-09", "2009 金融海嘯低點 (2009-03-09)"],
  ["2000-03-24", "2000 網路泡沫高點 (2000-03-24)"],
  ["2002-10-09", "2002 網路泡沫低點 (2002-10-09)"],
  ["1929-09-03", "1929 大蕭條高點 (1929-09-03，僅 ^GSPC 有資料)"],
  ["1932-06-01", "1932 大蕭條低點 (1932-06-01，僅 ^GSPC 有資料)"],
];

// ---------- 狀態 ----------
const state = {
  manifest: null,
  meta: new Map(),      // symbol -> { symbol, name, file, currency, start, end, note }
  cache: new Map(),     // symbol -> Promise<series>
  pickers: {},          // pickerName -> [symbols]
};

// ---------- 格式化 ----------
const curPrefix = (cur) => ({ TWD: "NT$", USD: "$", HKD: "HK$", KRW: "₩", EUR: "€" }[cur] || "");
const fmtMoney = (v, cur) => `${curPrefix(cur)}${Math.round(v).toLocaleString("en-US")}`;
const fmtPct = (x, signed = true) =>
  x == null || !isFinite(x) ? "—" : `${signed && x > 0 ? "+" : ""}${(x * 100).toFixed(2)}%`;
const fmtNum = (x, d = 2) => (x == null || !isFinite(x) ? "—" : x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
const cls = (x) => (x > 0 ? "pos" : x < 0 ? "neg" : "");
const ymd = (d) => (d ? String(d).replace(/-/g, "/") : "—");   // yyyy/mm/dd
/** 天數 → 「約 N 年 M 個月」（不到 45 天就只寫天數） */
function spanTxt(days) {
  if (days == null || !isFinite(days)) return "—";
  if (days < 45) return `${days} 天`;
  const tm = Math.round(days / 30.4375), y = Math.floor(tm / 12), m = tm % 12;
  return `約 ${y ? `${y} 年` : ""}${y && m ? " " : ""}${m ? `${m} 個月` : ""}`;
}
/** 表格用：「1,234 天」下面一行小字「約 3 年 5 個月」 */
const spanCell = (days) => (days == null ? "—" : `${days.toLocaleString("en-US")} 天${days < 45 ? "" : `<span class="sub">${spanTxt(days)}</span>`}`);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const label = (sym) => {
  const m = state.meta.get(sym);
  return m && m.name ? `${sym}（${m.name}）` : sym;
};
const currencyOf = (sym) => state.meta.get(sym)?.currency || "";

// ---------- 資料載入 ----------
async function loadManifest() {
  const status = $("#data-status");
  try {
    // 加上時間戳記，避免 GitHub Pages 的 CDN 快取（約 10 分鐘）讓「管理標的」改完後還看到舊清單
    const res = await fetch(`${DATA_BASE}manifest.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    state.manifest = await res.json();
    for (const g of state.manifest.groups) for (const t of g.tickers) state.meta.set(t.symbol, { ...t, group: g.name });
    window.__tickerMeta = state.meta; // 給管理編輯器顯示「是否已有資料」
    status.textContent = `資料更新：${state.manifest.updated}（${state.meta.size} 檔）`;
    status.title = state.manifest.source;
  } catch {
    status.innerHTML = "找不到價格資料，請確認 GitHub Actions 已執行，或先上傳 CSV";
  }
  refreshTickerSelects();
}

/** 網站沒有這個代號的資料（尚未收錄，或 Yahoo 抓不到） */
class NoDataError extends Error {
  constructor(sym) {
    super(`查無資料：「${sym}」尚未收錄。可到右上角「管理標的」新增（約 2 分鐘後可用），或用「上傳 CSV」。`);
    this.symbol = sym;
  }
}

function loadSeries(sym) {
  if (!state.cache.has(sym)) {
    const m = state.meta.get(sym);
    if (!m || !m.file) return Promise.reject(new NoDataError(sym));
    const v = encodeURIComponent(state.manifest?.updated || "");
    state.cache.set(sym, fetch(`${DATA_BASE}${m.file}?v=${v}`).then((r) => {
      if (!r.ok) throw new Error(`${sym} 資料下載失敗 (${r.status})`);
      return r.json();
    }).catch((e) => { state.cache.delete(sym); throw e; }));
  }
  return state.cache.get(sym);
}

/** 依群組產生 <option>，所有「選標的」的下拉選單共用 */
function tickerOptions(selected) {
  const groups = new Map();
  for (const m of state.meta.values()) {
    if (!groups.has(m.group)) groups.set(m.group, []);
    groups.get(m.group).push(m);
  }
  return [...groups].map(([g, list]) => `<optgroup label="${esc(g)}">${list.map((m) =>
    `<option value="${esc(m.symbol)}"${m.symbol === selected ? " selected" : ""}>${esc(m.symbol)}　${esc(m.name || "")}${m.start ? `（${m.start.slice(0, 4)} 起）` : ""}</option>`).join("")}</optgroup>`).join("");
}

/** 資料清單載入或上傳 CSV 後，重建所有下拉選單 */
function refreshTickerSelects() {
  $$(".picker select").forEach((sel) => { sel.innerHTML = `<option value="">＋ 從清單選擇標的加入…</option>${tickerOptions()}`; });
  // 資產配置的輸入框用 datalist 提供建議，也可以自己打任何代號
  let dl = $("#ticker-list");
  if (!dl) { dl = document.createElement("datalist"); dl.id = "ticker-list"; document.body.appendChild(dl); }
  dl.innerHTML = [...state.meta.values()].map((m) => `<option value="${esc(m.symbol)}">${esc(m.name || "")}</option>`).join("");
  const t = $("#timing-sym");
  if (t) t.innerHTML = tickerOptions(t.value || "^GSPC");
  Object.keys(state.pickers).forEach(renderChips);
}

/** 使用者輸入 → 代號（可輸入代號或名稱） */
function resolveSymbol(text) {
  const q = text.trim();
  if (!q) return null;
  const up = q.toUpperCase();
  for (const sym of state.meta.keys()) if (sym.toUpperCase() === up) return sym;
  // 只輸入數字代號也可以：0050 → 0050.TW、0005 → 0005.HK
  for (const sym of state.meta.keys()) if (sym.toUpperCase().split(".")[0] === up) return sym;
  for (const m of state.meta.values()) if ((m.name || "").toLowerCase().includes(q.toLowerCase())) return m.symbol;
  return state.meta.size ? null : up; // 清單還沒載入時先接受
}

// ---------- 自訂 CSV ----------
function parseCsv(text, fileName) {
  const lines = text.replace(/^﻿/, "").split(/\r?\n/).filter((l) => l.trim());
  const head = lines[0].split(",").map((h) => h.trim().replace(/^"|"$/g, "").toLowerCase());
  const hasHeader = head.some((h) => /[a-z一-鿿]/.test(h) && !/^\d/.test(h));
  let di = 0, pi = 1;
  if (hasHeader) {
    di = Math.max(0, head.findIndex((h) => h === "date" || h.includes("日期")));
    const prefer = ["adj close", "adj_close", "adjclose", "close", "收盤價", "price", "價格"];
    const found = prefer.map((p) => head.indexOf(p)).find((i) => i >= 0);
    pi = found ?? (di === 0 ? 1 : 0);
  }
  const rows = [];
  for (const line of lines.slice(hasHeader ? 1 : 0)) {
    const c = line.split(",").map((x) => x.trim().replace(/^"|"$/g, ""));
    const d = normDate(c[di]);
    const p = parseFloat((c[pi] || "").replace(/[^0-9.\-]/g, ""));
    if (d && p > 0) rows.push([d, p]);
  }
  rows.sort((a, b) => (a[0] < b[0] ? -1 : 1));
  const dedup = rows.filter((r, i) => i === rows.length - 1 || rows[i + 1][0] !== r[0]);
  if (dedup.length < 10) throw new Error("CSV 內有效資料少於 10 筆。需要「日期」和「收盤價」兩個欄位。");
  const symbol = "CSV:" + fileName.replace(/\.[^.]+$/, "");
  return { symbol, dates: dedup.map((r) => r[0]), close: dedup.map((r) => r[1]) };
}

function normDate(s) {
  if (!s) return null;
  let m = s.match(/^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})/);
  if (m) return `${m[1]}-${m[2].padStart(2, "0")}-${m[3].padStart(2, "0")}`;
  m = s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})/); // 美式 M/D/YYYY
  if (m) return `${m[3]}-${m[1].padStart(2, "0")}-${m[2].padStart(2, "0")}`;
  return null;
}

$("#csv-upload").addEventListener("change", async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  try {
    const s = parseCsv(await f.text(), f.name);
    state.meta.set(s.symbol, { symbol: s.symbol, name: "自己上傳的資料", currency: "", start: s.dates[0], end: s.dates.at(-1), group: "我上傳的資料" });
    state.cache.set(s.symbol, Promise.resolve(s));
    refreshTickerSelects();
    alert(`已載入 ${s.symbol}：${s.dates[0]} ~ ${s.dates.at(-1)}，共 ${s.dates.length} 筆。\n在任何「投資標的」下拉選單的「我上傳的資料」群組裡就能選到「${s.symbol}」（重新整理頁面後會消失）。`);
  } catch (err) {
    alert(err.message);
  }
  e.target.value = "";
});

// ---------- 標的選擇器 ----------
function initPickers() {
  $$(".picker").forEach((el) => {
    const name = el.dataset.picker;
    state.pickers[name] = el.dataset.default.split(",").filter(Boolean);
    el.innerHTML = `
      <select aria-label="從清單選擇投資標的"></select>
      <div class="picker-row" style="margin-top:6px">
        <input type="text" placeholder="或手動輸入代號，例如 00631L、AAPL" aria-label="手動輸入代號" autocapitalize="characters" autocomplete="off" spellcheck="false">
        <button type="button" class="secondary small">加入</button>
      </div>
      <div class="chips"></div>
      <div class="picker-msg" role="status"></div>`;
    const sel = $("select", el), input = $("input", el), btn = $("button", el);
    const add = (sym) => {
      const max = +el.dataset.max;
      const list = state.pickers[name];
      pickerMsg(name, "");
      if (list.includes(sym)) { pickerMsg(name, `${esc(sym)} 已經在清單裡了`); return false; }
      if (max === 1) list.splice(0, list.length, sym);
      else if (list.length >= max) { pickerMsg(name, `最多 ${max} 檔，請先按 × 移除一檔`); return false; }
      else list.push(sym);
      renderChips(name);
      return true;
    };
    // 下拉選單：選了就加入
    sel.addEventListener("change", () => { const v = sel.value; sel.value = ""; if (v) add(v); });
    // 手動輸入：清單裡有就用清單的代號（0050 → 0050.TW）；沒有也照樣加入，執行時再標示「查無資料」
    const addTyped = () => {
      const raw = input.value.trim();
      if (!raw) return;
      const sym = resolveSymbol(raw) || raw.toUpperCase();
      if (add(sym)) {
        input.value = "";
        if (!state.meta.has(sym)) pickerMsg(name, `「${esc(sym)}」目前不在資料清單中，執行時會跳過。可到「管理標的」新增。`, "bad");
      }
    };
    btn.addEventListener("click", addTyped);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addTyped(); } });
  });
}

/** 在標的輸入框下方顯示訊息 */
function pickerMsg(name, html, kind = "") {
  const m = $(`.picker[data-picker="${name}"] .picker-msg`);
  if (m) { m.innerHTML = html; m.className = `picker-msg ${kind}`; }
}

function renderChips(name) {
  const el = $(`.picker[data-picker="${name}"] .chips`);
  if (!el) return;
  el.innerHTML = state.pickers[name].map((s) => {
    const m = state.meta.get(s);
    const title = m ? `${m.name || ""}${m.start ? `｜資料 ${m.start} 起` : ""}${m.note ? `｜${m.note}` : ""}` : "";
    const missing = state.meta.size && !(m && m.file) ? " missing" : "";
    return `<span class="chip${missing}" title="${esc(title || "查無資料")}">${esc(s)}<button type="button" aria-label="移除 ${esc(s)}" data-sym="${esc(s)}">×</button></span>`;
  }).join("");
  $$("button", el).forEach((b) => b.addEventListener("click", () => {
    state.pickers[name] = state.pickers[name].filter((x) => x !== b.dataset.sym);
    renderChips(name);
  }));
}

/** 執行後：把查無資料的代號標在輸入框下方，其餘照常計算 */
function showMissing(name, missing) {
  pickerMsg(name, missing.length
    ? `查無資料：<b>${missing.map(esc).join("、")}</b>${name === "rolling" ? "" : "（已跳過，其他標的照常計算）"}。網站只收錄「管理標的」清單裡的代號，新增後約 2 分鐘可用；也可以用「上傳 CSV」。`
    : "", "bad");
}

// ---------- 圖表 ----------
function plot(el, traces, layout = {}) {
  if (!window.Plotly) { el.innerHTML = `<div class="notice error">圖表元件載入失敗（可能是網路阻擋 CDN），請重新整理。</div>`; return; }
  const c = themeColors();
  Plotly.react(el, traces, {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: { color: c.text, family: c.font, size: 12 },
    margin: { l: 60, r: 16, t: 30, b: 40 },
    legend: { orientation: "h", y: 1.1, x: 0 },
    hovermode: "x unified",
    ...layout,
    // 座標軸設定合併（而不是整個覆蓋），automargin 避免刻度數字被切掉
    xaxis: { ...axisBase(c), ...layout.xaxis },
    yaxis: { ...axisBase(c), ...layout.yaxis },
  }, { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] });
  window.__quantChartPlus?.after(el, traces, c);   // [主站]
}

function busy(out, msg = "計算中…") {
  out.innerHTML = `<div class="panel placeholder"><span class="spinner"></span> ${msg}</div>`;
}
function errorBox(out, msg) {
  out.innerHTML = `<div class="notice error">${esc(msg)}</div>`;
}
const notices = (list) => list.map((n) => `<div class="notice">${n}</div>`).join("");

function readNum(id, { min = -Infinity, max = Infinity, name } = {}) {
  const v = parseFloat($(id).value);
  if (!isFinite(v) || v < min || v > max) throw new Error(`「${name}」需介於 ${min} ~ ${max}`);
  return v;
}

// ---------- 分頁 ----------
function showTab(name) {
  $$("nav.tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === name));
  $$("section.tab").forEach((s) => s.classList.toggle("active", s.id === `tab-${name}`));
  // 頁首：標題與一句話說明跟著分頁換（文字寫在分頁按鈕的 data-title／data-lede）
  const tabBtn = $(`nav.tabs button[data-tab="${name}"]`);
  if (tabBtn) {
    if (tabBtn.dataset.title) $("#q-title").textContent = tabBtn.dataset.title;
    $("#q-lede").textContent = tabBtn.dataset.lede || "";
    // 手機上分頁列會橫向捲動：把選中的分頁捲到看得見的位置（只動分頁列自己，不捲整頁）
    const sc = tabBtn.parentElement;
    if (sc && sc.scrollWidth > sc.clientWidth) {
      const r = tabBtn.getBoundingClientRect(), s = sc.getBoundingClientRect();
      sc.scrollLeft += r.left - s.left - (s.width - r.width) / 2;
    }
  }
  if (name === "vol" && state.manifest) loadCrash();   // 歷次股災回顧：第一次打開才讀三個指數
  // 隱藏時畫的圖寬度會錯，切回來時重算
  setTimeout(() => $$(`#tab-${name} .js-plotly-plot`).forEach((p) => window.Plotly && Plotly.Plots.resize(p)), 30);
  // 這個分頁隱藏期間切換過深淺色：圖的顏色是畫圖當下讀的，切回來時重畫一次
  //（延後一拍：loadHash 接著自己會送出表單時，會先把標記清掉，避免同一組參數跑兩次）
  setTimeout(() => { if (state.staleTabs.delete(name)) $(`#tab-${name} form`)?.requestSubmit(); }, 0);
}
$$("nav.tabs button").forEach((b) => b.addEventListener("click", () => {
  showTab(b.dataset.tab);
  history.replaceState(null, "", `#${b.dataset.tab}`);
  window.dispatchEvent(new CustomEvent("quant:tab", { detail: b.dataset.tab }));
}));

// ============================================================
// 1. 單筆 vs 定期定額
// ============================================================
function updatePlanHint() {
  const m = +$("#dca-months").value, n = +$("#dca-count").value, a = +$("#dca-amount").value;
  if (!(m > 0 && n > 0 && a > 0)) return;
  const gap = m / n;
  const gapTxt = gap >= 1 ? `約每 ${fmtNum(gap, gap % 1 ? 1 : 0)} 個月` : `約每 ${Math.round(gap * 30.4)} 天`;
  $("#dca-plan-hint").textContent = `→ ${gapTxt}扣款一次，每次投入 ${Math.round(a / n).toLocaleString("en-US")}，共 ${n} 次。`;
}
["#dca-months", "#dca-count", "#dca-amount"].forEach((id) => $(id).addEventListener("input", updatePlanHint));

$("#form-dca").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = $("#out-dca");
  try {
    const tickers = state.pickers.dca;
    if (!tickers.length) throw new Error("請至少選一個投資標的");
    const opts = {
      amount: readNum("#dca-amount", { min: 1, name: "總投資金額" }),
      start: $("#dca-start").value,
      end: $("#dca-end").value || today,
      dcaMonths: Math.round(readNum("#dca-months", { min: 1, max: 240, name: "分幾個月買完" })),
      dcaCount: Math.round(readNum("#dca-count", { min: 1, max: 520, name: "分幾次扣款" })),
      cashYield: readNum("#dca-yield", { min: 0, max: 20, name: "現金年利率" }) / 100,
    };
    if (!opts.start) throw new Error("請選擇開始日期");
    if (opts.start >= opts.end) throw new Error("開始日期必須早於結束日期");
    busy(out, "下載資料並計算中…");
    saveHash("dca", { t: tickers.join(","), a: opts.amount, s: opts.start, e: $("#dca-end").value, m: opts.dcaMonths, n: opts.dcaCount, y: $("#dca-yield").value , v: hashValue(state.dcaView) });

    const results = [], warns = [];
    const missing = [];
    for (const sym of tickers) {
      try {
        const series = await loadSeries(sym);
        const r = lumpSumVsDca(series, opts);
        if (r.error) { warns.push(`${esc(sym)}：${esc(r.error)}`); continue; }
        results.push(r);
      } catch (err) { missing.push(sym); }
    }
    showMissing("dca", missing);
    if (!results.length) { errorBox(out, missing.length ? "所有標的都查無資料，請看輸入框下方的說明。" : warns.join("；")); return; }
    renderDca(out, results, opts, warns);
  } catch (err) { errorBox(out, err.message); }
});

// 顯示篩選（兩者／只看單筆／只看定期定額）：只決定畫什麼，不重新回測；上一次的結果留在 state.lastDca
const STRAT_LONG = { ls: "單筆投入", dca: "定期定額" };   // 卡片、摘要用的全名（圖上的線名用 STRAT_NAME 的短名）
const VIEW_KEY = "quant.dca.view";
function loadViewPref() { try { return normMode(localStorage.getItem(VIEW_KEY)); } catch { return "both"; } }
function saveViewPref(m) { try { localStorage.setItem(VIEW_KEY, m); } catch { /* 無痕模式 */ } }
state.dcaView = loadViewPref();
state.lastDca = null;
state.staleTabs = new Set();   // 隱藏期間切換過深淺色、切回來要重畫的分頁（見 showTab、init 的 redraw）

/** 把 v 參數寫進目前網址（兩者時移除），其他參數不動 */
function syncViewToHash() {
  const [tab, q] = location.hash.slice(1).split("?");
  if (tab !== "dca" || !q) return;
  const p = new URLSearchParams(q), v = hashValue(state.dcaView);
  v ? p.set("v", v) : p.delete("v");
  history.replaceState(null, "", `#dca?${p.toString()}`);
}
function setDcaView(mode) {
  state.dcaView = normMode(mode);
  saveViewPref(state.dcaView);
  syncViewToHash();
  const last = state.lastDca;
  if (!last) return;
  // 切換顯示會整張重畫：保留使用者關掉的標的與拉近的區間（重新回測、改設定則照舊回到預設）
  const snap = window.__quantChartPlus?.snapshot($("#chart-dca-value"));
  renderDca($("#out-dca"), last.results, last.opts, last.warns);
  window.__quantChartPlus?.restore($("#chart-dca-value"), snap);
}

function renderDca(out, results, opts, warns0) {
  const c = themeColors();
  const mode = normMode(state.dcaView);
  state.lastDca = { results, opts, warns: warns0 };
  const warns = [...warns0];   // 切換顯示會重畫，提醒事項不能越加越多
  // 提醒事項
  for (const r of results) {
    const gap = toDay(r.actualStart) - toDay(opts.start);
    if (gap > 7) warns.push(`<b>${esc(r.symbol)}</b> 的資料從 ${state.meta.get(r.symbol)?.start || r.actualStart} 開始，實際回測起點為 <b>${r.actualStart}</b>（不是你選的 ${opts.start}）。不同起點的標的不能直接比較。`);
    if (r.skipped) warns.push(`<b>${esc(r.symbol)}</b>：結束日期太早，${opts.dcaCount} 次扣款中有 <b>${r.skipped} 次還沒執行</b>，那部分以現金計算。`);
    if (r.years < 1) warns.push(`<b>${esc(r.symbol)}</b>：回測期間不到 1 年，年化報酬率會被放大，請以總報酬率為主。`);
  }
  const curs = new Set(results.map((r) => currencyOf(r.symbol)).filter(Boolean));
  if (curs.size > 1) warns.push(`同時包含不同幣別的標的（${[...curs].join("、")}），金額沒有換匯，請比較「報酬率」而不是金額。`);
  const notesUniq = [...new Set(results.map((r) => state.meta.get(r.symbol)?.note).filter((n) => n && n.includes("不含股息")))];
  if (notesUniq.length) warns.push("指數（^GSPC、^TWII）是價格指數，<b>不含股息</b>，長期報酬會被低估。");

  // 結論：兩者＝比較句；單選＝該策略自己的摘要（不出現「誰贏」）
  const verdicts = results.map((r) => {
    if (mode !== "both") {
      const x = r[mode];
      return `<p><b>${esc(label(r.symbol))}</b>：${STRAT_LONG[mode]}的期末資產 <b>${fmtMoney(x.final, currencyOf(r.symbol))}</b>，總報酬 <b class="${cls(x.totalReturn)}">${fmtPct(x.totalReturn)}</b>，年化 <b class="${cls(x.cagr)}">${fmtPct(x.cagr)}</b>，最大回撤 <b class="neg">${fmtPct(x.mdd)}</b>。</p>`;
    }
    const lsWin = r.ls.final >= r.dca.final;
    const diff = lsWin ? r.ls.final / r.dca.final - 1 : r.dca.final / r.ls.final - 1;
    const lastBuy = r.buys.at(-1);
    const buyMove = lastBuy ? lastBuy.price / r.price[0] - 1 : 0;
    const why = !lastBuy ? "" : buyMove >= 0
      ? `買進期間（${r.actualStart} ~ ${lastBuy.date}）價格<b class="pos">上漲 ${fmtPct(buyMove, false)}</b>，DCA 後面幾筆越買越貴，所以單筆投入佔優勢。`
      : `買進期間（${r.actualStart} ~ ${lastBuy.date}）價格<b class="neg">下跌 ${fmtPct(-buyMove, false)}</b>，DCA 後面幾筆買在比較低的價格，所以定期定額佔優勢。`;
    return `<p><b>${esc(label(r.symbol))}</b>：<b style="color:${lsWin ? c.ls : c.dca}">${lsWin ? "單筆投入" : "定期定額"}</b> 的期末資產多了 <b>${fmtPct(diff, false)}</b>。${why}</p>`;
  }).join("");

  const cards = results.map((r) => {
    const cur = currencyOf(r.symbol);
    const card = (st) => `<div class="card ${st}"><div class="k">${esc(r.symbol)}・${STRAT_LONG[st]}</div><div class="v">${fmtMoney(r[st].final, cur)}</div><div class="s"><span class="${cls(r[st].totalReturn)}">${fmtPct(r[st].totalReturn)}</span>｜年化 ${fmtPct(r[st].cagr)}</div></div>`;
    return (mode !== "dca" ? card("ls") : "") + (mode !== "ls" ? card("dca") : "");
  }).join("");

  const sel = results.length > 1
    ? `<select id="dca-detail-sel" style="width:auto">${results.map((r, i) => `<option value="${i}">${esc(label(r.symbol))}</option>`).join("")}</select>` : "";

  const viewBar = `<div class="q-viewbar"><span class="qplus-lab">顯示</span><div class="seg" role="group" aria-label="顯示哪一種策略" id="dca-view-seg">${
    Object.keys(VIEW_LABELS).map((m) => `<button type="button" data-v="${m}" aria-pressed="${m === mode}">${VIEW_LABELS[m]}</button>`).join("")}</div></div>`;

  const readValue = mode === "both"
    ? "實線是單筆投入、虛線是定期定額，灰色虛線是投入本金。DCA 在買進期間只有部分資金在市場內，所以起伏比較小；買完之後兩條線會「平行」移動，差距就固定在買進期間造成的那一段。"
    : mode === "ls"
      ? `${results.length > 1 ? "每種顏色是一檔標的，" : ""}線是單筆投入（第一天全部買進、之後抱著不動）的資產價值，灰色虛線是投入本金。線在虛線之上＝帳面賺錢，之下＝帳面賠錢。`
      : `${results.length > 1 ? "每種顏色是一檔標的，" : ""}線是定期定額的資產價值（含還沒投入的現金），灰色虛線是投入本金。買進期間只有部分資金在市場內，所以起伏比較小；買完之後就是 100% 持有，漲跌和標的本身一致。`;

  const buysPanel = showBuysPanel(mode) ? `
    <div class="panel">
      <h3>扣款紀錄與平均成本 ${sel}</h3>
      <div class="chart short" id="chart-dca-buys"></div>
      <p class="how-to-read" id="dca-buys-text"></p>
      <details class="explain"><summary>查看每一筆扣款明細</summary><div class="table-wrap" id="dca-buys-table"></div></details>
    </div>` : "";

  const cols = annualColumns(mode);
  const whyBox = cols.why ? `
      <details class="explain" open><summary>為什麼買完之後，兩邊每年的報酬率都一樣？</summary>
        <p>因為 DCA 買完之後，手上也是 <b>100% 持有同一檔標的</b>，和單筆投入一模一樣，所以每年漲跌的百分比自然相同。兩者的差別只發生在<b>買進期間</b>：</p>
<pre class="ascii">
買進期間（例：第 1 年）              買完之後（第 2 年起）
  單筆：100% 在市場                    單筆：100% 在市場 ┐ 持股比例相同
  定投：一部分在市場 + 一部分現金       定投：100% 在市場 ┘ → 每年報酬率相同
  → 報酬率不同，差距在這裡產生          → 差距「按比例」跟著放大或縮小
</pre>
        <p>所以要看「差距」欄的<b>金額</b>：買完之後，差距的百分比固定不變，但金額會隨市場一起變大或變小。這也說明了單筆 vs 定投真正的勝負，在買進期間就已經決定了。</p>
      </details>` : "";

  out.innerHTML = `
    ${viewBar}
    ${notices(warns)}
    <div class="verdict"><h3>${mode === "both" ? "結論" : `摘要：${STRAT_LONG[mode]}`}</h3>${verdicts}
      <p class="hint">記得：這只是「一個起點」的結果。${mode === "both" ? "想知道一般情況下誰比較常贏，請看「勝率分析」。" : "想看另一種策略，可以切換上方的「顯示」。"}</p></div>
    <div class="cards">${cards}</div>

    <div class="panel">
      <h3>資產價值變化</h3>
      <div class="chart" id="chart-dca-value"></div>
      <p class="how-to-read"><b>這張圖怎麼看：</b>${readValue}</p>
    </div>
${buysPanel}
    <div class="panel">
      <h3>績效指標</h3>
      <div class="table-wrap">${metricsTable(results, mode)}</div>
      <details class="explain"><summary>這些指標是什麼意思？</summary>
        <ul>
          <li><b>總報酬率</b> = 期末資產 ÷ 總投資金額 − 1。兩種策略用同一個分母，才能公平比較。</li>
          <li><b>年化報酬率 (CAGR)</b> = (期末 ÷ 期初)^(1/年數) − 1，把總報酬換算成「平均每年」。</li>
          <li><b>最大回撤</b>：資產從最高點跌到最低點的最大幅度。DCA 在買進期間資金沒有全部進場，回撤通常比較小，這就是它「心理上比較舒服」的原因。</li>
          <li><b>平均持股比例</b>：整段期間平均有多少比例的錢在市場內。單筆是 100%。</li>
          <li><b>平均成本 vs 平均價格</b>：見「觀念教室 → 平均成本迷思」。</li>
        </ul>
      </details>
    </div>

    <div class="panel">
      <h3>逐年報酬率與年底資產</h3>
      <p class="hint" style="margin-top:0">每格上方是當年報酬率，下方是年底總資產${mode === "ls" ? "" : "（含未投入現金）"}。第一年從開始日起算，最後一年到結束日為止（可能不滿一年）。</p>
      ${annualTable(results, mode)}${whyBox}
    </div>`;

  $("#dca-view-seg", out).addEventListener("click", (e) => {
    const b = e.target.closest("button[data-v]");
    if (b && b.dataset.v !== state.dcaView) setDcaView(b.dataset.v);
  });

  // 圖 1：資產價值（只畫所選策略的線）
  const bySym = new Map(results.map((r) => [r.symbol, r]));
  const traces = valueTraceSpecs(results, mode, c).map((sp) => ({
    x: bySym.get(sp.symbol).dates, y: bySym.get(sp.symbol)[sp.field], name: sp.name, mode: "lines",
    line: { color: sp.color, width: 2, dash: sp.dash }, hovertemplate: "%{y:,.0f}",
  }));
  plot($("#chart-dca-value"), traces, {
    yaxis: { tickformat: ",.0f", title: { text: "資產價值" } },
    shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: opts.amount, y1: opts.amount, line: { color: c.muted, dash: "dot", width: 1 } }],
  });

  if (!showBuysPanel(mode)) return;
  const drawBuys = (r) => {
    const end = r.buys.length ? r.buys.at(-1).date : r.dates.at(-1);
    const iEnd = Math.min(r.dates.length - 1, r.dates.indexOf(end) + 40);
    const xs = r.dates.slice(0, iEnd + 1), ys = r.price.slice(0, iEnd + 1);
    const marks = showLsMarks(mode);
    const tr = [
      { x: xs, y: ys, name: "價格（還原權息）", mode: "lines", line: { color: c.muted, width: 1.5 }, hovertemplate: "%{y:,.2f}" },
      { x: r.buys.map((b) => b.date), y: r.buys.map((b) => b.price), name: "DCA 扣款", mode: "markers", marker: { color: c.dca, size: 9, symbol: "triangle-up" }, hovertemplate: "扣款 %{y:,.2f}" },
    ];
    if (marks) tr.push({ x: [r.dates[0]], y: [r.price[0]], name: "單筆買進", mode: "markers", marker: { color: c.ls, size: 13, symbol: "star" }, hovertemplate: "單筆 %{y:,.2f}" });
    const shapes = [];
    if (r.dca.avgCost) shapes.push({ type: "line", x0: xs[0], x1: xs.at(-1), y0: r.dca.avgCost, y1: r.dca.avgCost, line: { color: c.dca, dash: "dash", width: 1.5 } });
    if (marks) shapes.push({ type: "line", x0: xs[0], x1: xs.at(-1), y0: r.price[0], y1: r.price[0], line: { color: c.ls, dash: "dot", width: 1.5 } });
    plot($("#chart-dca-buys"), tr, { shapes, yaxis: { title: { text: "價格" } } });
    const lower = r.dca.avgCost < r.price[0];
    $("#dca-buys-text").innerHTML = !r.dca.avgCost ? ""
      : marks
        ? `<b>這張圖怎麼看：</b>藍色星星是單筆買進價 <b>${fmtNum(r.price[0])}</b>（藍色點線），橘色三角形是每次扣款，橘色虛線是 DCA 的平均成本 <b>${fmtNum(r.dca.avgCost)}</b>。`
          + `平均成本${lower ? "<b class='pos'>低於</b>" : "<b class='neg'>高於</b>"}單筆買進價，所以${lower ? "定期定額" : "單筆投入"}買到比較多股數。`
          + `（扣款日平均價格是 ${fmtNum(r.dca.avgPrice)}，平均成本一定 ≤ 它，但這不代表會贏過單筆。）`
        : `<b>這張圖怎麼看：</b>灰線是標的價格，橘色三角形是每次扣款，橘色虛線是 DCA 的平均成本 <b>${fmtNum(r.dca.avgCost)}</b>。`
          + `（扣款日平均價格是 ${fmtNum(r.dca.avgPrice)}，平均成本一定 ≤ 它：價格貴時自動少買、便宜時多買。）`;
    $("#dca-buys-table").innerHTML = `<table class="data"><thead><tr><th>扣款日</th><th>價格</th><th>投入金額</th><th>買到股數</th></tr></thead><tbody>${
      r.buys.map((b) => `<tr><td>${b.date}${b.times > 1 ? `（${b.times} 筆合併）` : ""}</td><td>${fmtNum(b.price)}</td><td>${Math.round(b.amount).toLocaleString("en-US")}</td><td>${fmtNum(b.shares, 4)}</td></tr>`).join("")
    }</tbody></table>`;
  };
  drawBuys(results[0]);
  $("#dca-detail-sel")?.addEventListener("change", (e) => drawBuys(results[+e.target.value]));
}

function metricsTable(results, mode) {
  const bySym = new Map(results.map((r) => [r.symbol, r]));
  const rows = metricRows(results, mode).map(({ symbol, strategy }) => {
    const r = bySym.get(symbol), cur = currencyOf(symbol), x = r[strategy];
    const win = winnerStrategy(r, mode) === strategy;
    const tail = strategy === "ls"
      ? `<td>100%</td><td>${fmtNum(r.price[0])}</td><td>—</td>`
      : `<td>${fmtPct(x.avgExposure, false)}</td><td>${fmtNum(x.avgCost)}</td><td>${fmtNum(x.avgPrice)}</td>`;
    return `<tr class="${win ? "win" : ""}"><td>${esc(symbol)} ${strategy === "ls" ? "單筆投入" : "定期定額"}</td><td>${fmtMoney(x.final, cur)}</td><td class="${cls(x.totalReturn)}">${fmtPct(x.totalReturn)}</td><td class="${cls(x.cagr)}">${fmtPct(x.cagr)}</td><td class="neg" title="${x.mddPeak} → ${x.mddTrough}">${fmtPct(x.mdd)}</td>${tail}</tr>`;
  }).join("");
  return `<table class="data"><thead><tr><th>策略</th><th>期末資產</th><th>總報酬率</th><th>年化報酬率</th><th>最大回撤</th><th>平均持股比例</th><th>平均成本</th><th>扣款日平均價格</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function annualTable(results, mode) {
  // 每檔一張表，只有 4 欄，手機也放得下；每格同時顯示「報酬率」與「年底資產」；單選時只留該策略欄
  const cols = annualColumns(mode);
  return results.map((r) => {
    const cur = currencyOf(r.symbol);
    const rows = r.annual.map((a) => {
      const gap = a.dcaEnd - a.lsEnd;
      const buying = a.dcaInvestedPct < 0.9999 && cols.dca;
      return `<tr>
        <td>${a.year}${buying ? `<div class="sub">買進中・已投入 ${Math.round(a.dcaInvestedPct * 100)}%</div>` : ""}</td>
        ${cols.ls ? `<td><span class="${cls(a.ls)}">${fmtPct(a.ls)}</span><div class="sub">${fmtMoney(a.lsEnd, cur)}</div></td>` : ""}
        ${cols.dca ? `<td><span class="${cls(a.dca)}">${fmtPct(a.dca)}</span><div class="sub">${fmtMoney(a.dcaEnd, cur)}</div></td>` : ""}
        ${cols.gap ? `<td class="${cls(gap)}">${gap >= 0 ? "+" : "−"}${fmtMoney(Math.abs(gap), cur)}<div class="sub">${fmtPct(a.dcaEnd / a.lsEnd - 1)}</div></td>` : ""}
      </tr>`;
    }).join("");
    return `<h4 class="q-h4">${esc(label(r.symbol))}</h4>
      <div class="table-wrap"><table class="data annual${cols.gap ? "" : " one"}"><thead><tr><th>年度</th>${cols.ls ? "<th>單筆</th>" : ""}${cols.dca ? "<th>定期定額</th>" : ""}${cols.gap ? `<th>差距<br><span class="sub">定投 − 單筆</span></th>` : ""}</tr></thead><tbody>${rows}</tbody></table></div>`;
  }).join("");
}

// ============================================================
// 1b. 每月定期投入（薪水定投）
// ============================================================
$("#form-monthly").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = $("#out-monthly");
  try {
    const tickers = state.pickers.monthly;
    if (!tickers.length) throw new Error("請至少選一個投資標的");
    const opts = {
      monthly: readNum("#monthly-amount", { min: 1, name: "每月投入金額" }),
      initial: readNum("#monthly-init", { min: 0, name: "一開始已有的資金" }),
      start: $("#monthly-start").value,
      end: $("#monthly-end").value || today,
    };
    if (!opts.start) throw new Error("請選擇開始日期");
    if (opts.start >= opts.end) throw new Error("開始日期必須早於結束日期");
    busy(out, "下載資料並計算中…");
    saveHash("monthly", { t: tickers.join(","), a: opts.monthly, i: opts.initial || "", s: opts.start, e: $("#monthly-end").value });

    const results = [], warns = [], missing = [];
    for (const sym of tickers) {
      try {
        const series = await loadSeries(sym);
        const r = monthlyContribution(series, opts);
        if (r.error) { warns.push(`${esc(sym)}：${esc(r.error)}`); continue; }
        results.push(r);
      } catch (err) { missing.push(sym); }
    }
    showMissing("monthly", missing);
    if (!results.length) { errorBox(out, missing.length ? "所有標的都查無資料，請看輸入框下方的說明。" : warns.join("；")); return; }
    renderMonthly(out, results, opts, warns);
  } catch (err) { errorBox(out, err.message); }
});

function renderMonthly(out, results, opts, warns0) {
  const c = themeColors();
  const warns = [...warns0];
  for (const r of results) {
    const gap = toDay(r.actualStart) - toDay(opts.start);
    if (gap > 7) warns.push(`<b>${esc(r.symbol)}</b> 的資料從 ${ymd(state.meta.get(r.symbol)?.start || r.actualStart)} 開始，實際投入起點為 <b>${ymd(r.actualStart)}</b>（不是你選的 ${ymd(opts.start)}）。不同起點的標的不能直接比較。`);
    if (r.xirr == null && r.years < 1) warns.push(`<b>${esc(r.symbol)}</b>：回測期間不到 1 年，不顯示年化報酬率（會被放大），請看帳面損益。`);
    else if (r.xirr == null) warns.push(`<b>${esc(r.symbol)}</b>：年化報酬率（XIRR）算不出來（現金流找不到合理的解），請看帳面損益。`);
  }
  const curs = new Set(results.map((r) => currencyOf(r.symbol)).filter(Boolean));
  if (curs.size > 1) warns.push(`同時包含不同幣別的標的（${[...curs].join("、")}），金額沒有換匯，請比較「報酬率」而不是金額。`);
  if (results.some((r) => (state.meta.get(r.symbol)?.note || "").includes("不含股息"))) warns.push("指數（^GSPC、^TWII）是價格指數，<b>不含股息</b>，長期報酬會被低估。");

  const sign = (x) => (x > 0 ? "+" : x < 0 ? "−" : "");
  const money = (x, cur) => `${sign(x)}${fmtMoney(Math.abs(x), cur)}`;
  const verdicts = results.map((r) => {
    const cur = currencyOf(r.symbol);
    const bad = r.underwater
      ? `最難熬的時候是 <b>${ymd(r.worst.date)}</b>，帳面虧 <b class="neg">${fmtPct(r.worst.rate)}</b>。`
      : "期間內帳面沒有低於本金。";
    const vd = r.valueDrawdown;
    const fall = vd ? `資產從高點最多一次回落 <b class="neg">${fmtPct(Math.abs(vd.pct), false)}</b>（${ymd(vd.peakDate)} → ${ymd(vd.troughDate)}）。` : "";
    return `<p><b>${esc(label(r.symbol))}</b>：${r.count} 次投入共 <b>${fmtMoney(r.totalInvested, cur)}</b>，期末資產 <b>${fmtMoney(r.final, cur)}</b>，帳面損益 <b class="${cls(r.pnl)}">${money(r.pnl, cur)}（${fmtPct(r.pnlRate)}）</b>。${bad}${fall}</p>`;
  }).join("");

  const cards = results.map((r) => {
    const cur = currencyOf(r.symbol);
    return `<div class="q-tgroup"><h4 class="q-h4">${esc(label(r.symbol))}<span class="sub">${ymd(r.actualStart)} ~ ${ymd(r.actualEnd)}</span></h4><div class="cards">
      <div class="card"><div class="k">累積投入</div><div class="v">${fmtMoney(r.totalInvested, cur)}</div><div class="s">${r.count} 次投入</div></div>
      <div class="card"><div class="k">期末資產</div><div class="v">${fmtMoney(r.final, cur)}</div><div class="s">${ymd(r.actualEnd)} 收盤價（還原權息）</div></div>
      <div class="card"><div class="k">帳面損益</div><div class="v ${cls(r.pnl)}">${money(r.pnl, cur)}</div><div class="s"><span class="${cls(r.pnlRate)}">${fmtPct(r.pnlRate)}</span>｜期末資產 ÷ 累積投入 − 1</div></div>
      <div class="card"><div class="k">年化報酬率（資金加權）</div><div class="v ${cls(r.xirr)}">${r.xirr == null ? "—" : fmtPct(r.xirr)}</div><div class="s">${r.xirr == null ? (r.years < 1 ? "期間不到 1 年不顯示" : "算不出來") : "XIRR，見下方說明"}</div></div>
    </div></div>`;
  }).join("");

  // 最難熬的時候：每檔一張卡片（兩個指標並列＋低於本金最長期間）；卡片自動換行，手機上直排，不用左右滑
  const none = (r) => !r.underwater;
  const kv = (rows) => `<dl class="q-kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>`;
  const worstTable = `<div class="q-worst-grid">${results.map((r) => {
    const cur = currencyOf(r.symbol), vd = r.valueDrawdown, uw = r.underwater;
    const a = none(r) ? `<p class="q-kv-none">期間內帳面沒有低於本金。</p>` : kv([
      ["日期", ymd(r.worst.date)],
      ["當時累積投入", fmtMoney(r.worst.invested, cur)],
      ["當時資產", fmtMoney(r.worst.value, cur)],
      ["帳面虧損", `<span class="neg">${fmtPct(r.worst.rate)}</span>`],
    ]);
    const b = !vd ? `<p class="q-kv-none">期間內資產沒有從高點回落過。</p>` : kv([
      ["高點", `${ymd(vd.peakDate)}<span class="sub">${fmtMoney(vd.peakValue, cur)}</span>`],
      ["之後最低點", `${ymd(vd.troughDate)}<span class="sub">${fmtMoney(vd.troughValue, cur)}</span>`],
      ["回落", `<span class="neg">${money(vd.amount, cur)}</span><span class="sub neg">${fmtPct(vd.pct)}</span>`],
      ["回到高點那天", vd.recoveryDate ? ymd(vd.recoveryDate) : `<span class="neg">還沒回到</span><span class="sub">到 ${ymd(r.actualEnd)}</span>`],
    ]);
    const c2 = none(r) ? `<p class="q-kv-none">—</p>` : kv([
      ["天數", spanCell(uw.days)],
      ["期間", `${ymd(uw.from)} ~ ${ymd(uw.to)}`],
      ["結果", uw.recovered ? `${ymd(uw.recoveryDate)} 回到本金以上` : "到資料最後一天仍低於本金"],
    ]);
    return `<div class="q-worst"><h4 class="q-h4">${esc(label(r.symbol))}</h4>
      <div class="q-wk">帳面虧最多的那天<span class="sub">資產 ÷ 累積投入 − 1 最低</span></div>${a}
      <div class="q-wk">資產從高點回落最多的一次<span class="sub">資產價值從先前最高點跌到之後最低點</span></div>${b}
      <div class="q-wk">帳面低於本金的最長連續期間</div>${c2}</div>`;
  }).join("")}</div>`;

  const annual = results.map((r) => {
    const cur = currencyOf(r.symbol), lastY = r.annual.at(-1).year;
    const rows = r.annual.map((a) => `<tr><td>${a.year}${a.year === lastY && a.endDate && a.endDate.slice(5) < "12-25" ? `<span class="sub">到 ${a.endDate.slice(5).replace("-", "/")}</span>` : ""}</td>
      <td>${fmtMoney(a.contributed, cur)}</td><td>${fmtMoney(a.endInvested, cur)}</td><td>${fmtMoney(a.endValue, cur)}</td>
      <td><span class="${cls(a.pnlRate)}">${fmtPct(a.pnlRate)}</span></td></tr>`).join("");
    return `<h4 class="q-h4">${esc(label(r.symbol))}</h4><div class="table-wrap"><table class="data annual"><thead><tr><th>年度</th><th>當年投入</th><th>年底累積投入</th><th>年底資產</th><th>帳面損益</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }).join("");

  out.innerHTML = `
    ${notices(warns)}
    <div class="verdict"><h3>摘要</h3>${verdicts}
      <p class="hint">計算規則：每月第一個交易日買進（開始日當月從開始日當天或之後第一個交易日）、還原權息價、可買零股；不計手續費、稅與匯率。這只是「一個起點」的歷史結果，不是預測。</p></div>
    ${cards}

    <div class="panel">
      <h3>資產價值 vs 累積投入本金</h3>
      <div class="chart" id="chart-monthly-value"></div>
      <p class="how-to-read"><b>這張圖怎麼看：</b>彩色線是你手上的資產價值，灰色階梯線是你累積投入的本金（每個月多一階）。彩色線在灰線上方＝帳面賺錢、下方＝帳面賠錢，兩條線之間的距離就是帳面損益。時間拉長以後，彩色線通常會越離越遠，因為早期投入的錢已經滾了很久。縱軸可以切成「對數」，看長期走勢比較清楚。</p>
      <div class="qplus-pnl-wrap" id="monthly-pnl-wrap">
        <div class="qplus-pnl-h">帳面損益率（資產價值 ÷ 累積投入 − 1）</div>
        <div class="qplus-pnl-sub">0% 以上＝帳面賺、以下＝帳面賠；圓點是各檔「最難熬的那天」。</div>
        <div class="chart short" id="chart-monthly-pnl"></div>
      </div>
    </div>

    <div class="panel">
      <h3>最難熬的時候</h3>
      ${worstTable}
      <p class="how-to-read"><b>怎麼看：</b>每個月都投入的人，帳面最慘的時候不一定是股價最低的那天，而是「資產 ÷ 累積投入」最低的那天（早期投的錢多半已經賺很多，晚期才投的錢還沒時間緩衝），所以常常落在剛開始投的前幾個月。「資產從高點回落最多的一次」看的是另一件事：手上的資產從之前的最高點，最多一次縮水了多少錢、幾 %（以跌幅 % 最大的那一次為準）。<b>期間內每個月持續投入的錢也算在資產裡</b>，新錢會把資產往上墊，所以同一段時間實際的市場跌幅比這個數字更大；「回到高點那天」也可能是新錢墊回來的，不代表股價已經回升。「最長連續期間」是帳面一直低於累積投入本金的最長一段，也就是最久看不到賺錢的日子。</p>
    </div>

    <div class="panel">
      <h3>逐年</h3>
      <p class="hint" style="margin-top:0">每年投入多少、年底累積投入、年底資產與帳面損益。第一年從開始日起算，最後一年到結束日為止（可能不滿一年）。</p>
      ${annual}
    </div>

    <details class="explain panel"><summary>年化報酬率（資金加權，XIRR）是什麼意思？</summary>
      <p>每個月投入的錢，在市場裡待的時間不一樣：十年前投的那筆待了十年，上個月投的才待一個月。所以不能把「總報酬 ÷ 總投入」直接除以年數。XIRR 把每一筆錢投入的日期都算進去，找出一個「平均每年報酬率」：假如每一筆投入都以這個年利率成長，到期末剛好變成現在的期末資產。</p>
<pre class="ascii">
投入（負）  -1萬   -1萬   -1萬   ……   -1萬        期末資產（正）
日期        1/2    2/1    3/1    ……   今天         + 現在的資產
            └──────┴──────┴──────┴──────┴──→ 找一個年利率 r，讓全部折現後剛好 = 0
</pre>
      <p>它和「總報酬率」回答不同的問題：總報酬率看的是「整體賺了幾成」，XIRR 看的是「平均每年約賺幾成」。期間不到 1 年時年化會被放大，所以不顯示。</p>
    </details>
    <details class="explain panel"><summary>這個回測的限制</summary>
      <ul>
        <li>每月第一個交易日買進，沒有算手續費、稅（美股股息有預扣稅，還原權息價假設股息全額再投入，會稍微高估）與匯率。</li>
        <li>可買零股；實際下單有最小單位時，會有一點誤差。</li>
        <li>指數（^GSPC、^TWII）不含股息，長期報酬會被低估。</li>
        <li>只是「一個起點」的結果：換一個開始日期，最難熬的時候和結果都會不同。</li>
        <li>過去績效不代表未來。</li>
      </ul>
    </details>`;

  // 圖 1：資產價值 vs 累積投入本金（本金用階梯灰線；每檔的本金一樣時只畫一條）
  const traces = [];
  results.forEach((r, i) => traces.push({ x: r.dates, y: r.value, name: `${r.symbol} 資產價值`, mode: "lines",
    line: { color: c.palette[i % c.palette.length], width: 2 }, hovertemplate: "%{y:,.0f}" }));
  const seen = new Set();
  results.forEach((r) => {
    const key = `${r.actualStart}|${r.count}|${r.totalInvested}`;
    const same = results.every((x) => `${x.actualStart}|${x.count}|${x.totalInvested}` === key);
    if (same && seen.has(key)) return;
    seen.add(key);
    traces.push({ x: r.dates, y: r.invested, name: same && results.length > 1 ? "累積投入本金" : `${r.symbol} 投入本金`, mode: "lines",
      line: { color: c.muted, width: 1.6, shape: "hv" }, hovertemplate: "%{y:,.0f}" });
  });
  plot($("#chart-monthly-value"), traces, { yaxis: { tickformat: ",.0f", title: { text: "金額" } } });

  // 圖 2：帳面損益率
  const pt = results.map((r, i) => ({ x: r.dates, y: r.rate.map((v) => v * 100), name: r.symbol, mode: "lines",
    line: { color: c.palette[i % c.palette.length], width: 1.6 }, hovertemplate: "%{y:+.1f}%" }));
  results.forEach((r, i) => { if (r.underwater) pt.push({ x: [r.worst.date], y: [r.worst.rate * 100], mode: "markers", showlegend: false, hoverinfo: "skip",
    marker: { color: c.palette[i % c.palette.length], size: 9, line: { color: c.panel, width: 1.5 } } }); });
  plot($("#chart-monthly-pnl"), pt, { yaxis: { ticksuffix: "%", zeroline: true, zerolinecolor: c.axis, zerolinewidth: 2, title: { text: "帳面損益率" } } });
}

// ============================================================
// 2. 勝率分析（滾動起點）
// ============================================================
$("#form-rolling").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = $("#out-rolling");
  try {
    const sym = state.pickers.rolling[0];
    if (!sym) throw new Error("請選擇一個投資標的");
    const opts = {
      amount: 1,
      from: $("#roll-from").value || null,
      horizonMonths: +$("#roll-horizon").value,
      dcaMonths: Math.round(readNum("#roll-months", { min: 1, max: 120, name: "分幾個月買完" })),
      dcaCount: Math.round(readNum("#roll-count", { min: 1, max: 520, name: "分幾次扣款" })),
      cashYield: readNum("#roll-yield", { min: 0, max: 20, name: "現金年利率" }) / 100,
    };
    if (opts.dcaMonths > opts.horizonMonths) throw new Error("「分幾個月買完」不能超過「每次持有幾年」");
    busy(out, "逐月計算中…");
    saveHash("rolling", { t: sym, f: opts.from || "", h: opts.horizonMonths, m: opts.dcaMonths, n: opts.dcaCount, y: $("#roll-yield").value });
    let series;
    try { series = await loadSeries(sym); } catch (err) { showMissing("rolling", [sym]); throw new Error("此標的查無資料，請看輸入框下方的說明。"); }
    showMissing("rolling", []);
    // 讓「計算中」先畫出來
    await new Promise((r) => setTimeout(r, 10));
    const res = rollingComparison(series, opts);
    if (res.error) throw new Error(res.error);
    renderRolling(out, sym, res, opts);
  } catch (err) { errorBox(out, err.message); }
});

function renderRolling(out, sym, res, opts) {
  const c = themeColors();
  const hY = opts.horizonMonths / 12;
  const win = res.lsWinRate;
  const first = res.rows[0].start, last = res.rows.at(-1).start;
  const note = state.meta.get(sym)?.note;
  out.innerHTML = `
    ${note ? notices([`${esc(sym)}：${esc(note)}`]) : ""}
    <div class="verdict">
      <h3>結論</h3>
      <p>從 <b>${first.slice(0, 7)}</b> 到 <b>${last.slice(0, 7)}</b>，共 <b>${res.count}</b> 個月份起點。每次拿到錢後持有 <b>${hY} 年</b>，
      單筆投入有 <b style="color:${c.ls}">${fmtPct(win, false)}</b> 的機率贏過「${opts.dcaMonths} 個月分 ${opts.dcaCount} 次」的定期定額。</p>
      <p>典型情況（中位數）下，單筆投入的期末資產比 DCA ${res.medianDiff >= 0 ? "多" : "少"} <b>${fmtPct(Math.abs(res.medianDiff), false)}</b>。
      最好的情況單筆多 ${fmtPct(res.best.diff, false)}（${res.best.start.slice(0, 7)} 起），最差的情況單筆少 ${fmtPct(-res.worst.diff, false)}（${res.worst.start.slice(0, 7)} 起）。</p>
      <p class="hint">換句話說：大約每 10 次有 ${Math.round(win * 10)} 次單筆比較好；但輸的時候（通常是崩盤前夕）可能輸很多。這就是「期望報酬」與「後悔風險」的取捨。</p>
    </div>
    <div class="cards">
      <div class="card ls"><div class="k">單筆投入勝率</div><div class="v">${fmtPct(win, false)}</div><div class="s">${res.count} 個起點</div></div>
      <div class="card dca"><div class="k">定期定額勝率</div><div class="v">${fmtPct(1 - win, false)}</div><div class="s">多半發生在崩盤前</div></div>
      <div class="card"><div class="k">單筆領先幅度（中位數）</div><div class="v ${cls(res.medianDiff)}">${fmtPct(res.medianDiff)}</div><div class="s">10%~90% 區間：${fmtPct(res.p10Diff)} ~ ${fmtPct(res.p90Diff)}</div></div>
    </div>
    <div class="panel">
      <h3>每個起點的勝負</h3>
      <div class="chart" id="chart-roll-time"></div>
      <p class="how-to-read"><b>這張圖怎麼看：</b>橫軸是「拿到錢的月份」，縱軸是持有 ${hY} 年後單筆比 DCA 多賺（正）或少賺（負）的百分比。
      <span style="color:${c.ls}">■ 藍色</span> = 單筆贏，<span style="color:${c.dca}">■ 橘色</span> = 定期定額贏。橘色常集中在 1929、2000、2007 這類大崩盤前夕。</p>
    </div>
    <div class="panel">
      <h3>勝負幅度分布</h3>
      <div class="chart short" id="chart-roll-hist"></div>
      <p class="how-to-read"><b>這張圖怎麼看：</b>把所有起點的結果做成直方圖。越多柱子落在 0 的右邊，代表單筆越常贏；柱子離 0 越遠，代表贏或輸得越多。</p>
    </div>
    <details class="explain panel"><summary>計算方式與注意事項</summary>
      <ul>
        <li>每個月的第一個交易日當作一個起點，兩種策略都從同一筆錢開始，比較 ${hY} 年後（最接近的交易日）的期末資產。</li>
        <li>勝負幅度 = 單筆期末資產 ÷ DCA 期末資產 − 1。</li>
        <li>相鄰起點的持有期間大量重疊，所以樣本<b>並非互相獨立</b>，勝率是「歷史描述」，不是精確的機率。</li>
        <li>DCA 還沒投入的現金以 ${fmtPct(opts.cashYield, false)} 年利率計息；調高利率會讓 DCA 勝率上升，可以自己試試。</li>
      </ul>
    </details>`;

  plot($("#chart-roll-time"), [{
    type: "bar", x: res.rows.map((r) => r.start), y: res.rows.map((r) => r.diff * 100),
    marker: { color: res.rows.map((r) => (r.diff >= 0 ? c.ls : c.dca)) },
    hovertemplate: "%{x|%Y-%m} 起：單筆 %{y:+.1f}%<extra></extra>", name: "單筆 − DCA",
  }], { bargap: 0, showlegend: false, yaxis: { ticksuffix: "%", title: { text: "單筆比 DCA 多賺" } }, hovermode: "closest" });

  // 直方圖（手動分箱，plotly-basic 沒有 histogram）
  const vals = res.rows.map((r) => r.diff * 100);
  const lo = Math.floor(Math.min(...vals)), hi = Math.ceil(Math.max(...vals));
  const width = Math.max(0.5, (hi - lo) / 40);
  const bins = new Map();
  for (const v of vals) {
    const b = lo + Math.floor((v - lo) / width) * width;
    bins.set(b, (bins.get(b) || 0) + 1);
  }
  const xs = [...bins.keys()].sort((a, b) => a - b);
  plot($("#chart-roll-hist"), [{
    type: "bar", x: xs.map((x) => x + width / 2), y: xs.map((x) => bins.get(x)), width: width * 0.95,
    marker: { color: xs.map((x) => (x + width / 2 >= 0 ? c.ls : c.dca)) },
    hovertemplate: "%{x:.1f}%：%{y} 次<extra></extra>",
  }], { showlegend: false, xaxis: { ticksuffix: "%", title: { text: "單筆比 DCA 多賺" } }, yaxis: { title: { text: "次數" } }, hovermode: "closest" });
}

// ============================================================
// 3. 資產配置
// ============================================================
function addAllocRow(sym = "", w = "") {
  const row = document.createElement("div");
  row.className = "alloc-row";
  row.innerHTML = `<input type="text" class="alloc-sym" list="ticker-list" value="${esc(sym)}" placeholder="代號，例如 0050" aria-label="標的代號" autocapitalize="characters" autocomplete="off" spellcheck="false">
    <input type="number" class="alloc-w" value="${w}" min="0" max="100" step="5" aria-label="比例 %" placeholder="%">
    <button type="button" aria-label="移除">✕</button>
    <div class="picker-msg bad alloc-msg"></div>`;
  $("button", row).addEventListener("click", () => { row.remove(); updateAllocSum(); });
  $(".alloc-w", row).addEventListener("input", updateAllocSum);
  $(".alloc-sym", row).addEventListener("input", () => { $(".alloc-msg", row).textContent = ""; });
  $("#alloc-rows").appendChild(row);
  updateAllocSum();
}
function readAllocRows() {
  return $$("#alloc-rows .alloc-row").map((r) => {
    return { raw: $(".alloc-sym", r).value.trim(), w: parseFloat($(".alloc-w", r).value) || 0, el: r };
  }).filter((x) => x.raw || x.w);
}
function updateAllocSum() {
  const sum = readAllocRows().reduce((a, r) => a + r.w, 0);
  const el = $("#alloc-sum");
  const ok = Math.abs(sum - 100) < 0.01;
  el.textContent = `合計 ${fmtNum(sum, sum % 1 ? 1 : 0)}%${ok ? " ✓" : "（需等於 100%）"}`;
  el.className = `alloc-sum ${ok ? "ok" : "bad"}`;
}
$("#alloc-add").addEventListener("click", () => addAllocRow());
$("#alloc-wd").addEventListener("change", (e) => { $("#alloc-wd-box").hidden = !e.target.checked; });

$("#form-alloc").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = $("#out-alloc");
  try {
    const rows = readAllocRows();
    if (!rows.length) throw new Error("請至少新增一個標的");
    rows.forEach((r) => { $(".alloc-msg", r.el).textContent = ""; });
    const syms = rows.map((r) => resolveSymbol(r.raw) || r.raw.toUpperCase());
    // 查無資料的列：在該列下方標示。資產配置需要每一檔都有資料，比例才算得對，所以這裡不會略過
    const bad = rows.filter((r, i) => !state.meta.get(syms[i])?.file);
    bad.forEach((r) => { $(".alloc-msg", r.el).textContent = `查無資料：「${r.raw}」尚未收錄，可到「管理標的」新增。`; });
    if (bad.length) throw new Error("有標的查無資料（見左側輸入框下方）。資產配置的比例需要每一檔都有資料，請移除或替換後再試。");
    if (new Set(syms).size !== syms.length) throw new Error("有重複的標的，請合併比例");
    const sum = rows.reduce((a, r) => a + r.w, 0);
    if (Math.abs(sum - 100) > 0.01) throw new Error(`目前比例合計 ${sum}%，需剛好 100%`);
    const opts = {
      capital: readNum("#alloc-capital", { min: 1, name: "期初資金" }),
      start: $("#alloc-start").value,
      end: $("#alloc-end").value || today,
      weights: rows.map((r) => r.w / 100),
      rebalance: $("#alloc-rebal").value,
      withdraw: {
        enabled: $("#alloc-wd").checked,
        amount: readNum("#alloc-wd-amt", { min: 0, name: "每次提領" }),
        freq: $("#alloc-wd-freq").value,
        inflation: readNum("#alloc-wd-inf", { min: 0, max: 15, name: "提領調高" }) / 100,
      },
    };
    if (!opts.start || opts.start >= opts.end) throw new Error("請確認開始與結束日期");
    busy(out);
    const series = await Promise.all(syms.map(loadSeries));
    const res = assetAllocation(series, opts);
    if (res.error) throw new Error(res.error);
    renderAlloc(out, syms, res, opts);
  } catch (err) { errorBox(out, err.message); }
});

function renderAlloc(out, syms, res, opts) {
  const c = themeColors();
  const warns = [];
  if (toDay(res.actualStart) - toDay(opts.start) > 7) {
    const late = syms.map((s) => [s, state.meta.get(s)?.start]).filter(([, d]) => d && d > opts.start).map(([s, d]) => `${s}（${d} 起）`);
    warns.push(`實際回測起點為 <b>${res.actualStart}</b>，因為 ${late.join("、") || "部分標的"} 在那之前沒有資料。`);
  }
  const curs = new Set(syms.map(currencyOf).filter(Boolean));
  const cur = curs.size === 1 ? [...curs][0] : "";
  if (curs.size > 1) warns.push(`同時混合不同幣別的標的（${[...curs].join("、")}），但<b>沒有做匯率換算</b>，結果會失真。建議同一幣別的標的放在一起回測。`);
  const wdRate = opts.withdraw.enabled ? (opts.withdraw.amount * (opts.withdraw.freq === "month" ? 12 : 1)) / opts.capital : 0;

  out.innerHTML = `
    ${notices(warns)}
    ${res.bankrupt ? `<div class="notice error"><b>資金在 ${res.bankruptDate} 耗盡。</b>在這個起點與提領速度下，投資組合撐了 ${fmtNum((toDay(res.bankruptDate) - toDay(res.actualStart)) / 365.25, 1)} 年。試試降低提領金額或提高債券比例。</div>` : ""}
    <div class="cards">
      <div class="card"><div class="k">期初資金</div><div class="v">${fmtMoney(opts.capital, cur)}</div><div class="s">${res.actualStart} 起</div></div>
      <div class="card"><div class="k">期末餘額</div><div class="v">${res.bankrupt ? "歸零" : fmtMoney(res.final, cur)}</div><div class="s">${res.actualEnd}</div></div>
      <div class="card"><div class="k">累計提領</div><div class="v">${fmtMoney(res.totalWithdrawn, cur)}</div><div class="s">${opts.withdraw.enabled ? `初始提領率 ${fmtPct(wdRate, false)}／年` : "未啟用提領"}</div></div>
      <div class="card"><div class="k">投資組合年化報酬（TWR）</div><div class="v ${cls(res.twrCagr)}">${fmtPct(res.twrCagr)}</div><div class="s">已排除提領影響</div></div>
      <div class="card"><div class="k">最大回撤</div><div class="v neg">${fmtPct(res.mdd)}</div><div class="s">${res.mddPeak} → ${res.mddTrough}</div></div>
    </div>
    <div class="panel">
      <h3>資產餘額變化</h3>
      <div class="chart" id="chart-alloc"></div>
      <p class="how-to-read"><b>這張圖怎麼看：</b>藍線是帳戶餘額（已扣除提領）。有提領時，餘額低於本金不代表投資虧損，要看上方的 TWR 年化報酬才知道投資組合本身的表現。</p>
    </div>
    <div class="panel">
      <h3>年度壓力測試表</h3>
      <div class="table-wrap">${allocTable(syms, res, cur)}</div>
      <details class="explain"><summary>表格說明與計算順序</summary>
        <ul>
          <li><b>標的報酬</b>：上一年最後一個交易日收盤 → 今年最後一個交易日收盤（第一年從開始日起算）。</li>
          <li><b>組合報酬</b>：時間加權報酬，不受提領影響。</li>
          <li>每個交易日的處理順序：① 用收盤價計算市值 → ② 若進入新的再平衡週期，依目標比例重新分配 → ③ 若進入新的提領週期，等比例賣出提領金額；不夠提領時視為破產。</li>
          <li>提領金額每年調高 ${fmtPct(opts.withdraw.inflation, false)}（以日曆年計算）。</li>
          <li>未計入交易成本、稅與匯率。</li>
        </ul>
      </details>
    </div>`;

  const shapes = [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: opts.capital, y1: opts.capital, line: { color: c.muted, dash: "dot", width: 1 } }];
  if (res.bankrupt) shapes.push({ type: "line", yref: "paper", y0: 0, y1: 1, x0: res.bankruptDate, x1: res.bankruptDate, line: { color: c.bad, dash: "dash", width: 2 } });
  plot($("#chart-alloc"), [{ x: res.dates, y: res.values, name: "帳戶餘額", mode: "lines", line: { color: c.ls, width: 2 }, hovertemplate: "%{y:,.0f}" }],
    { shapes, showlegend: false, yaxis: { tickformat: ",.0f" } });
}

function allocTable(syms, res, cur) {
  const head = syms.map((s) => `<th>${esc(s)} 報酬</th><th>${esc(s)} 年底金額</th>`).join("");
  const body = res.annual.map((r) => `<tr><td>${r.year}</td>${r.assets.map((a) => `<td class="${cls(a.ret)}">${fmtPct(a.ret)}</td><td>${fmtMoney(a.value, cur)}</td>`).join("")}
    <td class="${cls(r.portfolioRet)}">${fmtPct(r.portfolioRet)}</td><td>${fmtMoney(r.withdrawn, cur)}</td><td><b>${fmtMoney(r.endValue, cur)}</b></td></tr>`).join("");
  return `<table class="data"><thead><tr><th>年度</th>${head}<th>組合報酬</th><th>當年提領</th><th>年底餘額</th></tr></thead><tbody>${body}</tbody></table>`;
}

// ============================================================
// 4. 波動與風險
// ============================================================
$("#form-vol").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = $("#out-vol");
  try {
    const syms = state.pickers.vol;
    if (!syms.length) throw new Error("請至少選一個投資標的");
    const ths = [...new Set($$(".vol-t").map((i) => parseFloat(i.value)).filter((x) => x > 0))].sort((a, b) => a - b);
    if (!ths.length) throw new Error("請設定至少一個門檻");
    busy(out);
    const res = [], warns = [];
    const missing = [];
    for (const s of syms) {
      try {
        const r = volatilityStats(await loadSeries(s), ths, $("#vol-start").value || null, $("#vol-end").value || null);
        if (r.error) warns.push(esc(r.error)); else res.push(r);
      } catch (err) { missing.push(s); }
    }
    showMissing("vol", missing);
    if (!res.length) throw new Error(missing.length ? "所有標的都查無資料，請看輸入框下方的說明。" : warns.join("；") || "沒有可分析的資料");
    saveHash("vol", { t: syms.join(","), s: $("#vol-start").value, e: $("#vol-end").value, g: ths.join(","), d: Math.round(state.ddThr * 100) });
    renderVol(out, res, ths, warns);
  } catch (err) { errorBox(out, err.message); }
});

// 「大跌與回本」的門檻（跌幾 % 才算一次大跌）：10／20／30／50，只決定表與圖怎麼畫，不重新下載；寫進網址參數 d
const DD_CHOICES = [10, 20, 30, 50];
state.ddThr = 0.2;
state.lastVol = null;
const normDd = (v) => (DD_CHOICES.includes(Math.round(+v)) ? Math.round(+v) / 100 : 0.2);
function syncHashParam(tab, k, v) {
  const [t, q] = location.hash.slice(1).split("?");
  if (t !== tab || !q) return;
  const p = new URLSearchParams(q);
  v === "" || v == null ? p.delete(k) : p.set(k, v);
  history.replaceState(null, "", `#${tab}?${p.toString()}`);
}

function renderVol(out, res, ths, warns) {
  const c = themeColors();
  state.lastVol = { res, ths, warns };
  const starts = new Set(res.map((r) => r.start));
  if (starts.size > 1) warns.push("各標的資料起點不同（見表格「統計期間」），次數會受資料長度影響；比較時建議看「每年平均次數」或設定相同的開始日期。");
  const td = (v) => `<td>${v}</td>`;
  const rows = [
    ["統計期間", (r) => `${r.start}<br>~ ${r.end}`],
    ["交易日數", (r) => r.days.toLocaleString("en-US")],
    ...ths.flatMap((t, k) => [
      [`單日漲 ≥ ${t}%（次）`, (r) => `<span class="pos">${r.counts[k].up}</span> <span class="hint" style="display:inline">（${fmtNum(r.counts[k].up / (r.days / r.perYear), 1)}／年）</span>`],
      [`單日跌 ≥ ${t}%（次）`, (r) => `<span class="neg">${r.counts[k].down}</span> <span class="hint" style="display:inline">（${fmtNum(r.counts[k].down / (r.days / r.perYear), 1)}／年）</span>`],
    ]),
    ["最長連漲", (r) => `${r.maxUp.days} 天 <span class="pos">${fmtPct(r.maxUp.ret)}</span><br><span class="hint" style="display:inline">${r.maxUp.from || ""} ~ ${r.maxUp.to || ""}</span>`],
    ["最長連跌", (r) => `${r.maxDown.days} 天 <span class="neg">${fmtPct(r.maxDown.ret)}</span><br><span class="hint" style="display:inline">${r.maxDown.from || ""} ~ ${r.maxDown.to || ""}</span>`],
    ["最大回撤", (r) => `<span class="neg">${fmtPct(r.mdd)}</span><br><span class="hint" style="display:inline">${r.mddPeak} → ${r.mddTrough}</span>`],
    ["年化報酬率 (CAGR)", (r) => `<span class="${cls(r.cagr)}">${fmtPct(r.cagr)}</span>`],
    ["年化波動率", (r) => fmtPct(r.annVol, false)],
    ["索提諾比率", (r) => fmtNum(r.sortino)],
  ];
  out.innerHTML = `
    ${notices(warns)}
    <div class="panel" id="vol-dd-panel">
      <h3>大跌與回本</h3>
      <p class="hint" style="margin-top:0">長期持有最真實的體驗：從前一個高點算起跌了多深、跌了多久、多久才回到原來的高點。一段大跌在價格回到前高時結束。</p>
      <div class="q-viewbar"><span class="qplus-lab">大跌門檻（從前高算起）</span><span class="seg" id="vol-dd-seg" role="group" aria-label="大跌門檻">${DD_CHOICES.map((p) => `<button type="button" data-d="${p}" aria-pressed="${p === Math.round(state.ddThr * 100)}">跌 ${p}% 以上</button>`).join("")}</span></div>
      <div id="vol-dd-body"></div>
      <h4 class="q-h4">水下曲線（距離歷史高點的跌幅）</h4>
      <div class="chart" id="chart-vol-dd"></div>
      <p class="how-to-read"><b>這張圖怎麼看：</b>0% 代表創新高；越往下代表離高點越遠。曲線「泡在水下」越久，代表需要越久才能回本；上面表格裡的每一段大跌，就是這張圖裡跌破虛線（目前選的門檻）的那些「水坑」。</p>
    </div>
    <div class="panel">
      <h3>統計結果</h3>
      <div class="table-wrap"><table class="data"><thead><tr><th>指標</th>${res.map((r) => `<th>${esc(r.symbol)}</th>`).join("")}</tr></thead>
      <tbody>${rows.map(([k, f]) => `<tr><td>${k}</td>${res.map((r) => td(f(r))).join("")}</tr>`).join("")}</tbody></table></div>
      <details class="explain"><summary>這些指標怎麼看？</summary>
        <ul>
          <li><b>單日漲跌次數</b>：次數越多代表股性越活潑（或越暴躁）。括號內是「平均每年幾次」，資料長度不同時用它比較才公平。</li>
          <li><b>最長連漲／連跌</b>：連續收紅（或收黑）的最多天數與累積漲跌幅；平盤日會中斷連續。</li>
          <li><b>最大回撤</b>：從歷史高點跌到低點的最大幅度，代表「抱股最痛的程度」。</li>
          <li><b>年化波動率</b>：每日報酬標準差 × √(每年交易日數)。本工具依資料自動判斷每年交易日數（股票約 252、加密貨幣約 365）。</li>
          <li><b>索提諾比率</b>：平均日報酬 ÷ 下檔標準差 × √(每年交易日數)，下檔標準差只計算負報酬（無風險利率 = 0）。越高代表承受同樣下跌風險，換到越多報酬。</li>
        </ul>
      </details>
    </div>
    <div class="panel"><h3>大漲大跌頻率（每年平均次數）</h3><div class="chart short" id="chart-vol-bar"></div>
      <p class="how-to-read"><b>這張圖怎麼看：</b>向上的柱子是大漲次數、向下的是大跌次數，換算成「平均每年」以便比較不同長度的資料。</p></div>`;

  $("#vol-dd-seg", out).addEventListener("click", (e) => {
    const b = e.target.closest("button[data-d]");
    if (!b) return;
    state.ddThr = normDd(b.dataset.d);
    $$("#vol-dd-seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    syncHashParam("vol", "d", Math.round(state.ddThr * 100));
    drawDd();
  });
  $("#vol-dd-body", out).addEventListener("click", (e) => {   // 「顯示全部 N 次」
    const b = e.target.closest("button[data-more]");
    if (!b) return;
    const open = b.getAttribute("aria-expanded") !== "true";
    b.setAttribute("aria-expanded", String(open));
    b.textContent = open ? "只顯示最深的 10 次" : `顯示全部 ${b.dataset.more} 次`;
    b.closest(".q-ddblock").querySelectorAll("tr.more").forEach((tr) => { tr.hidden = !open; });
  });
  drawDd();

  const bars = [];
  res.forEach((r, i) => {
    const yrs = r.days / r.perYear;
    bars.push({ type: "bar", name: r.symbol, x: ths.map((t) => `≥ ${t}%`), y: r.counts.map((x) => x.up / yrs), marker: { color: c.palette[i % c.palette.length] }, legendgroup: r.symbol, offsetgroup: r.symbol, hovertemplate: `${r.symbol} 漲 %{x}：%{y:.1f} 次／年<extra></extra>` });
    bars.push({ type: "bar", name: r.symbol, x: ths.map((t) => `≥ ${t}%`), y: r.counts.map((x) => -x.down / yrs), marker: { color: c.palette[i % c.palette.length], opacity: 0.55 }, legendgroup: r.symbol, offsetgroup: r.symbol, showlegend: false, hovertemplate: `${r.symbol} 跌 %{x}：%{customdata:.1f} 次／年<extra></extra>`, customdata: r.counts.map((x) => x.down / yrs) });
  });
  plot($("#chart-vol-bar"), bars, { barmode: "group", hovermode: "closest", yaxis: { title: { text: "次數／年（正 = 大漲，負 = 大跌）" } } });

}

/** 「大跌與回本」：摘要＋每檔一張表＋水下曲線（換門檻時只重畫這一塊） */
function drawDd() {
  if (!state.lastVol) return;
  const { res } = state.lastVol, c = themeColors(), thr = state.ddThr, pct = Math.round(thr * 100);
  const body = $("#vol-dd-body");
  if (!body) return;
  const eps = res.map((r) => ({ r, list: drawdownEpisodes(r.dates, r.px, thr).sort((a, b) => a.depth - b.depth || (a.peakDate < b.peakDate ? -1 : 1)) }));

  const summary = eps.map(({ r, list }) => {
    if (!list.length) return `<p><b>${esc(label(r.symbol))}</b>：${ymd(r.start)} ~ ${ymd(r.end)} 沒有跌 ${pct}% 以上的大跌（最大回撤 <b class="neg">${fmtPct(r.mdd)}</b>）。</p>`;
    const rec = list.filter((e) => e.recovered), open = list.find((e) => !e.recovered);
    const longest = rec.length ? rec.reduce((a, e) => (e.daysTotal > a.daysTotal ? e : a)) : null;
    const tail = [
      longest ? `已回本的最久 <b>${spanTxt(longest.daysTotal)}</b>才回本（${ymd(longest.peakDate)} 高點 → ${ymd(longest.recoveryDate)}）` : "",
      open ? `最近一段<b class="neg">尚未回本</b>（從 ${ymd(open.peakDate)} 的高點算起已 ${spanTxt(open.daysSincePeak)}）` : "",
    ].filter(Boolean).join("；");
    return `<p><b>${esc(label(r.symbol))}</b>：跌 ${pct}% 以上共 <b>${list.length}</b> 次，最深 <b class="neg">${fmtPct(list[0].depth)}</b>，${tail}。</p>`;
  }).join("");

  const blocks = eps.map(({ r, list }) => {
    if (!list.length) return "";
    // data-k：手機上表格改成直排卡片（quant.css 的 table.ddt），每格前面用它當小標題
    const rows = list.map((e, i) => `<tr${i >= 10 ? ' class="more" hidden' : ""}>
      <td data-k="高點日">${ymd(e.peakDate)}</td><td data-k="低點日">${ymd(e.troughDate)}</td><td data-k="最大跌幅" class="neg">${fmtPct(e.depth)}</td><td data-k="高點→低點">${spanCell(e.daysToTrough)}</td>
      ${e.recovered
        ? `<td data-k="回到高點日">${ymd(e.recoveryDate)}</td><td data-k="低點→回本">${spanCell(e.daysToRecover)}</td><td data-k="高點→回本">${spanCell(e.daysTotal)}</td>`
        : `<td colspan="3" class="wide" data-k="回到高點日" style="text-align:left"><span class="neg">尚未回本</span><span class="sub">至資料最後一天（${ymd(e.lastDate)}）已 ${e.daysSincePeak.toLocaleString("en-US")} 天${e.daysSincePeak < 45 ? "" : `（${spanTxt(e.daysSincePeak)}）`}</span></td>`}</tr>`).join("");
    return `<div class="q-ddblock"><h4 class="q-h4">${esc(label(r.symbol))}<span class="sub">跌 ${pct}% 以上共 ${list.length} 次，依跌幅由深到淺</span></h4>
      <div class="table-wrap"><table class="data ddt"><thead><tr><th>高點日</th><th>低點日</th><th>最大跌幅</th><th>高點→低點</th><th>回到高點日</th><th>低點→回本</th><th>高點→回本</th></tr></thead><tbody>${rows}</tbody></table></div>
      ${list.length > 10 ? `<button type="button" class="q-textbtn" data-more="${list.length}" aria-expanded="false">顯示全部 ${list.length} 次</button>` : ""}</div>`;
  }).join("");

  body.innerHTML = `<div class="verdict"><h3>摘要</h3>${summary}</div>${blocks}
    <details class="explain"><summary>這張表怎麼看？</summary><ul>
      <li><b>一段大跌</b>：從一個高點開始，價格一直低於那個高點，直到價格回到（或超過）那個高點才算結束；只列最大跌幅達到門檻的。</li>
      <li><b>高點→低點</b>：從高點日跌到最低點花了多久；<b>低點→回本</b>：從最低點漲回原高點花了多久；<b>高點→回本</b>：兩段加起來，也就是「帳面一直低於高點」的總時間。</li>
      <li>用的是還原權息價，股息再投入已算進去；指數（^GSPC、^TWII）不含股息，回本會比實際慢。</li>
      <li>天數是日曆天；「約幾年幾個月」只是方便閱讀。過去的大跌與回本時間不代表未來。</li></ul></details>`;

  plot($("#chart-vol-dd"), res.map((r, i) => ({
    x: r.drawdown.dates, y: r.drawdown.values.map((v) => v * 100), name: r.symbol, mode: "lines",
    line: { color: c.palette[i % c.palette.length], width: 1.2 }, fill: res.length === 1 ? "tozeroy" : "none", hovertemplate: "%{y:.1f}%",
  })), { yaxis: { ticksuffix: "%" }, shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: -pct, y1: -pct, line: { color: c.muted, dash: "dot", width: 1 } }] });
}

// ============================================================
// 觀念教室：每年買在最高點 vs 最低點
// ============================================================
$("#form-timing").addEventListener("submit", async (e) => {
  e.preventDefault();
  const out = $("#out-timing");
  try {
    const sym = $("#timing-sym").value;
    const fromYear = Math.round(readNum("#timing-from", { min: 1900, max: 2100, name: "從哪一年" }));
    const toYear = Math.round(readNum("#timing-to", { min: fromYear, max: 2100, name: "到哪一年" }));
    const amount = readNum("#timing-amt", { min: 1, name: "每年投入" });
    out.innerHTML = `<span class="spinner"></span> 計算中…`;
    const r = yearlyTimingTest(await loadSeries(sym), { amount, fromYear, toYear });
    if (r.error) throw new Error(r.error);
    const cur = currencyOf(sym);
    const gap = r.best / r.worst - 1;
    out.innerHTML = `
      <div class="cards">
        <div class="card"><div class="k">總投入（${r.fromYear}～${r.toYear}，${r.years} 年）</div><div class="v">${fmtMoney(r.invested, cur)}</div><div class="s">價值計算到 ${r.endDate}</div></div>
        <div class="card dca"><div class="k">每年都買在最高點</div><div class="v">${fmtMoney(r.worst, cur)}</div><div class="s">${fmtPct(r.worst / r.invested - 1)}</div></div>
        <div class="card ls"><div class="k">每年都買在最低點</div><div class="v">${fmtMoney(r.best, cur)}</div><div class="s">${fmtPct(r.best / r.invested - 1)}</div></div>
        <div class="card"><div class="k">每年第一天就買</div><div class="v">${fmtMoney(r.first, cur)}</div><div class="s">${fmtPct(r.first / r.invested - 1)}</div></div>
      </div>
      <p>神準擇時和最倒楣擇時只差 <b>${fmtPct(gap, false)}</b>；但最倒楣的人，資產仍是投入本金的 <b>${fmtNum(r.worst / r.invested, 1)} 倍</b>。${r.worst > r.invested ? "重點是「有沒有一直投入」，而不是「買在哪一天」。" : "這段期間市場整體下跌，任何擇時都難以避免虧損，這也是要搭配股債配置的原因。"}</p>
      <details class="explain"><summary>查看每年的最高點與最低點</summary><div class="table-wrap"><table class="data"><thead><tr><th>年度</th><th>最高點（日期）</th><th>最低點（日期）</th><th>年初</th></tr></thead><tbody>${
        r.rows.map((x) => `<tr><td>${x.year}</td><td>${fmtNum(x.high.price)}（${x.high.date.slice(5)}）</td><td>${fmtNum(x.low.price)}（${x.low.date.slice(5)}）</td><td>${fmtNum(x.first.price)}</td></tr>`).join("")
      }</tbody></table></div></details>`;
  } catch (err) { out.innerHTML = `<div class="notice error">${esc(err.message)}</div>`; }
});

// ============================================================
// 歷次股災回顧（波動與風險分頁最上面；第一次打開這個分頁才讀資料）
//   事件名稱與視窗：quant/config/crashes.json（手寫設定，不含任何跌幅數字）
//   每個數字：engine.js 的 crashInWindow() 用指數日線算；1990 年台股用國發會的月平均補，並標明
// ============================================================
const crash = { loading: null, cfg: null, table: null, monthly: {}, idx: -1 };   // idx：-1＝三個指數一起比較（預設），0 以上＝看單一指數的明細
const median = (a) => { const b = [...a].sort((x, y) => x - y), n = b.length; return n ? (n % 2 ? b[(n - 1) / 2] : (b[n / 2 - 1] + b[n / 2]) / 2) : null; };

/** 每個指數 × 每個事件算一次；回傳 { rows: [{ev, cells:[{state, r, start}]}], current: [...] } */
function crashTable(cfg, series) {
  const cell = (s, from, to) => {
    if (!s || !s.dates.length) return { state: "nodata", start: null };
    if (to != null && s.dates[0] > to) return { state: "nodata", start: s.dates[0] };
    const r = crashInWindow(s.dates, s.close, from, to);
    return r ? { state: "ok", r } : { state: "flat" };
  };
  const rows = cfg.events.map((ev) => ({ ev, cells: series.map((s) => cell(s, ev.from, ev.to)) }));
  const current = series.map((s) => (s && s.dates.length ? cell(s, fromDay(toDay(s.dates[s.dates.length - 1]) - cfg.current.days), null) : { state: "nodata", start: null }));
  return { rows, current };
}

function loadCrash() {
  if (!crash.loading) crash.loading = (async () => {
    const res = await fetch(`${CRASH_CONFIG}?v=${encodeURIComponent(state.manifest?.updated || "")}`);
    if (!res.ok) throw new Error(`事件清單讀不到（${res.status}）`);
    crash.cfg = await res.json();
    const series = await Promise.all(crash.cfg.indices.map((ix) => loadSeries(ix.sym).catch(() => null)));
    crash.series = series;
    crash.table = crashTable(crash.cfg, series);
    renderCrash();
    // 月平均補充（例如 1990 年台股）：另外讀總經儀表板的資料檔，讀不到就維持「沒有資料」
    if (crash.cfg.events.some((e) => e.monthly)) fetch(MACRO_LATEST, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).then((doc) => {
      if (!doc) return;
      for (const [k, m] of Object.entries(crash.cfg.monthly || {})) {
        const pts = m.path.split(".").reduce((o, key) => (o == null ? o : o[key]), doc);
        if (Array.isArray(pts) && pts.length > 12) crash.monthly[k] = { dates: pts.map((p) => p[0]), close: pts.map((p) => p[1]) };
      }
      renderCrash();
    }).catch(() => {});
  })().catch((e) => { crash.loading = null; $("#crash-body").innerHTML = `<div class="notice error">${esc(e.message)}</div>`; });
  return crash.loading;
}

function renderCrash() {
  const body = $("#crash-body"), { cfg, table } = crash;
  if (!body || !cfg || !table) return;
  const k = crash.idx, all = k < 0, ix = all ? null : cfg.indices[k];
  const month = (d) => ymd(d).slice(0, 7);
  // 日線沒有涵蓋、但設定檔有月平均可以補的格子（1990 年台股）：補上並標明；月平均還沒讀到＝pending
  const fill = (ev, c, i) => {
    const m = ev.monthly && cfg.monthly && cfg.monthly[ev.monthly];
    if (c.state !== "nodata" || !m || cfg.indices[i].sym !== "^TWII") return c;
    const ms = crash.monthly[ev.monthly], r = ms ? crashInWindow(ms.dates, ms.close, ev.from, ev.to) : null;
    return r ? { state: "ok", r, monthly: true, m } : { ...c, m, pending: true };
  };
  const seg = `<div class="q-viewbar" style="margin-bottom:8px"><span class="qplus-lab">怎麼看</span><span class="seg" id="crash-seg" role="group" aria-label="怎麼看">` +
    `<button type="button" data-i="-1" aria-pressed="${all}">三個一起比較</button>` +
    cfg.indices.map((x, i) => `<button type="button" data-i="${i}" aria-pressed="${i === k}">${esc(x.name)}</button>`).join("") +
    `</span><span class="hint" style="display:inline">${esc(all ? "都是價格指數，不含股息；回本時間從高點起算" : ix.note || "")}</span></div>`;
  const teach = `<details class="explain"><summary>這張表怎麼算、怎麼讀？（教學）</summary><ul>
      <li><b>怎麼算</b>：每個事件給一段時間（例如金融海嘯是 2007 年 6 月到 2009 年底），在那段時間裡找「先高後低、跌最深」的一段當作高點與低點；回本是低點之後第一次收盤回到那個高點。每個數字都附日期，可以自己對。</li>
      <li><b>指數不含股息</b>：這三個都是價格指數，沒有把股息算進去。實際持有（股息再投入）會比表上更早回本。</li>
      <li><b>「多久回本」說的是最倒楣的人</b>：也就是剛好在最高那一天一次買滿、之後完全沒有再投入的人。下跌期間持續投入的人，成本會被拉低，回本會快很多；可以到「每月定期投入」分頁用同一段時間試算。</li>
      <li><b>事件的名稱與時間範圍是本站訂的</b>（寫在設定檔），同一個事件在不同指數的高點、低點日期不一樣是正常的。</li>
      <li><b>三個一起比較怎麼讀</b>：橫條的長度就是跌幅，三欄用同一把尺（整條＝跌 100%），所以可以直接比長短。「跌最深」只在比得出來的時候標；有一格是月平均（會把跌幅算淺）而它又不是最深的那個，就不標。</li>
      <li><b>它不能告訴你這次會跌到哪裡</b>：樣本只有十次上下，每次原因都不同。它的用途是在恐慌時提醒自己：以前也跌過、也回來過，以及回來可能要等多久。</li>
      <li>資料來源：${esc(state.manifest?.source || "Yahoo Finance 日線")}；1990 年台股那一列用國發會景氣指標檔的每月平均。社群上流傳的股災數字常常沒寫是哪個指數、哪一天到哪一天，這裡不引用，一律重算。</li></ul></details>`;

  // ---------- 三個指數一起比較（預設）：每個事件一列，三個指數並排，橫條用同一把尺 ----------
  if (all) {
    const evRows = table.rows.map(({ ev, cells }) => ({ name: ev.name, what: ev.what, cells: cells.map((c, i) => fill(ev, c, i)) }));
    const curRow = { name: cfg.current.name, what: cfg.current.what, cells: table.current };
    const cmp = crashCompare(evRows.map((x) => x.cells)), curDeep = crashCompare([curRow.cells]).deepest[0];
    const names = cfg.indices.map((x) => x.name);
    const cellHtml = (c, i, deep) => {
      const dk = `data-k="${esc(names[i])}"`;
      if (c.state !== "ok") return `<td ${dk} class="wide"><div class="crash-c"><span class="sub">${c.state === "flat" ? "這段時間沒有下跌" : c.pending ? "待確認：日線沒有涵蓋這一段，月平均資料讀取中或讀不到" : c.start ? `沒有資料（日線從 ${month(c.start)} 開始）` : "沒有資料（尚未收錄）"}</span></div></td>`;
      const r = c.r;
      return `<td ${dk} class="wide"><div class="crash-c"><span class="neg crash-d">${fmtPct(r.depth)}</span>${deep ? '<span class="crash-tag deep">跌最深</span>' : ""}${c.monthly ? '<span class="crash-tag">月平均，日線會更深</span>' : ""}${r.partial && !c.monthly ? '<span class="crash-tag">資料較晚開始</span>' : ""}
        <span class="crash-bar" aria-hidden="true"><i style="width:${Math.min(100, Math.max(0, -r.depth * 100)).toFixed(1)}%"></i></span>
        <span class="sub">${month(r.peakDate)} → ${month(r.troughDate)}，下跌 ${spanTxt(r.daysToTrough)}</span>
        <span class="sub">${r.recovered ? `回本 ${spanTxt(r.daysTotal)}` : `尚未回本，離高點 ${fmtPct(r.fromPeakNow)}`}</span></div></td>`;
    };
    const rowHtml = (x, deep, klass = "") => `<tr${klass ? ` class="${klass}"` : ""}><td data-k="事件" class="wide"><b>${esc(x.name)}</b><span class="sub">${esc(x.what || "")}</span></td>${x.cells.map((c, i) => cellHtml(c, i, deep === i)).join("")}</tr>`;
    const medRow = cmp.common
      ? `<tr class="crash-med"><td data-k="事件" class="wide"><b>中位數</b><span class="sub">只算三個指數都有日線的 ${cmp.common} 次事件，三邊才是同一批</span></td>${names.map((nm, i) => `<td data-k="${esc(nm)}" class="wide"><div class="crash-c"><span class="neg crash-d">${fmtPct(cmp.medDepth[i])}</span>
          <span class="crash-bar" aria-hidden="true"><i style="width:${Math.min(100, Math.max(0, -cmp.medDepth[i] * 100)).toFixed(1)}%"></i></span>
          <span class="sub">${cmp.medRecover[i].n ? `回本 ${spanTxt(Math.round(cmp.medRecover[i].days))}${cmp.medRecover[i].n < cmp.common ? `（已回本的 ${cmp.medRecover[i].n} 次）` : ""}` : "都還沒回本"}</span></div></td>`).join("")}</tr>`
      : "";
    const list = (f) => names.map((nm, i) => `${esc(nm)} ${f(i)}`).join("、");
    const curOk = curRow.cells.some((c) => c.state === "ok");
    const summary = (cmp.common
      ? `<p>三個指數都有日線可算的 <b>${cmp.common}</b> 次事件裡，跌最深的次數：${list((i) => `<b>${cmp.wins[i]}</b> 次`)}。跌幅中位數：${list((i) => `<b class="neg">${fmtPct(cmp.medDepth[i])}</b>`)}。</p>`
      : `<p>目前沒有三個指數都算得出來的事件（可能有指數還沒收錄資料）。</p>`) +
      (curOk ? `<p>這一次（最近一年裡跌最深的一段）：${names.map((nm, i) => { const c = curRow.cells[i]; return `${esc(nm)} ${c.state === "ok" ? `<b class="neg">${fmtPct(c.r.depth)}</b>${c.r.recovered ? "（已回本）" : ""}` : c.state === "flat" ? "沒有下跌" : "沒有資料"}`; }).join("、")}。</p>` : "");
    body.innerHTML = `${seg}
      <div class="verdict">${summary}</div>
      <div class="table-wrap"><table class="data ddt crash-cmp"><thead><tr><th>事件</th>${names.map((nm) => `<th>${esc(nm)}</th>`).join("")}</tr></thead>
        <tbody>${evRows.map((x, i) => rowHtml(x, cmp.deepest[i])).join("")}${rowHtml(curRow, curDeep, "crash-now")}${medRow}</tbody></table></div>
      <p class="hint" style="margin:6px 0 0">每一格：跌幅、高點月份 → 低點月份、跌了多久、從高點算起多久回本。要看確切日期或那一段的走勢，切到單一指數。</p>
      ${teach}`;
    return;
  }

  // ---------- 單一指數的明細 ----------
  const sym = ix.sym;
  const none = (c, colspan) => `<td colspan="${colspan}" class="wide" data-k="這個指數" style="text-align:left"><span class="sub" style="display:inline">${c.state === "flat" ? "這段時間沒有下跌" : c.start ? `沒有資料（日線從 ${ymd(c.start)} 開始）` : "沒有資料（尚未收錄）"}</span></td>`;
  // 一列：事件｜高點→低點｜跌多久｜跌幅｜多久回本｜看走勢
  const detail = (name, what, c, from, to, extra = "") => {
    const first = `<td data-k="事件" class="wide"><b>${esc(name)}</b><span class="sub">${esc(what || "")}</span>${extra}</td>`;
    if (c.state !== "ok") return `<tr>${first}${none(c, 5)}</tr>`;
    const r = c.r, mon = c.monthly;
    const fd = mon ? month : ymd, span = (d) => (mon ? spanTxt(d) : spanCell(d));
    const rec = r.recovered
      ? `${span(r.daysTotal)}<span class="sub">${fd(r.recoveryDate)} 回到高點（低點起算 ${spanTxt(r.daysToRecover)}）</span>`
      : `<span class="neg">尚未回本</span><span class="sub">至 ${fd(r.lastDate)} 已 ${spanTxt(r.daysSincePeak)}，離高點 ${fmtPct(r.fromPeakNow)}</span>`;
    const go = mon ? "" : `<button type="button" class="q-textbtn" data-crash-go="${esc(from)}|${esc(r.recoveryDate || to || "")}">看這一段走勢</button>`;
    return `<tr>${first}
      <td data-k="高點 → 低點">${fd(r.peakDate)}<span class="sub">→ ${fd(r.troughDate)}</span></td>
      <td data-k="下跌多久">${span(r.daysToTrough)}</td>
      <td data-k="跌幅" class="neg">${fmtPct(r.depth)}${mon ? '<span class="sub">月平均，日線會更深</span>' : ""}${r.partial && !mon ? '<span class="sub">資料較晚開始，高點可能更早</span>' : ""}</td>
      <td data-k="多久回本（高點起算）">${rec}</td>
      <td data-k="" class="wide" style="text-align:left">${go}</td></tr>`;
  };
  let skipped = 0;
  const rowsHtml = table.rows.map(({ ev, cells }) => {
    const c = fill(ev, cells[k], k);
    if (c.state === "nodata" && !c.pending) { skipped++; return ""; }   // 這個指數沒有那段時間的資料：不佔版面，表格下面說一聲
    const extra = c.monthly ? `<span class="sub">※ ${esc(c.m.name)}：${esc(c.m.note)}</span>` : c.pending ? `<span class="sub">待確認：日線沒有涵蓋這一段，月平均資料讀取中或讀不到。</span>` : "";
    return detail(ev.name, ev.what, c, ev.from, ev.to, extra);
  }).join("");
  const cur = table.current[k];
  const curHtml = detail(cfg.current.name, cfg.current.what, cur, cur.state === "ok" ? fromDay(toDay(cur.r.lastDate) - cfg.current.days) : "", "");

  // 摘要：已回本的事件，高點到回本要多久（只算日線算得出來的）
  const done = table.rows.map((x) => x.cells[k]).filter((c) => c.state === "ok");
  const recd = done.filter((c) => c.r.recovered);
  const worst = done.length ? done.reduce((a, c) => (c.r.depth < a.r.depth ? c : a)) : null;
  const longest = recd.length ? recd.reduce((a, c) => (c.r.daysTotal > a.r.daysTotal ? c : a)) : null;
  const summary = done.length
    ? `<p><b>${esc(ix.name)}</b>：表上有日線可算的 ${done.length} 次事件，跌幅的中位數 <b class="neg">${fmtPct(median(done.map((c) => c.r.depth)))}</b>，最深 <b class="neg">${fmtPct(worst.r.depth)}</b>。` +
      (recd.length ? `已回本的 ${recd.length} 次裡，從高點到回本的中位數是 <b>${spanTxt(Math.round(median(recd.map((c) => c.r.daysTotal))))}</b>，最久 <b>${spanTxt(longest.r.daysTotal)}</b>。` : "") +
      (cur.state === "ok" ? `<br>這一次：從 ${ymd(cur.r.peakDate)} 的高點算起最深 <b class="neg">${fmtPct(cur.r.depth)}</b>，${cur.r.recovered ? `已在 ${ymd(cur.r.recoveryDate)} 回到高點` : `至 ${ymd(cur.r.lastDate)} 離高點 <b class="neg">${fmtPct(cur.r.fromPeakNow)}</b>`}。` : "") + "</p>"
    : `<p><b>${esc(ix.name)}</b>：${cur.state === "nodata" && !crash.series[k] ? "這個指數還沒有收錄資料（新增後約一個工作天內會有）。" : "表上的事件都沒有資料。"}</p>`;

  body.innerHTML = `${seg}
    <div class="verdict">${summary}</div>
    <div class="table-wrap"><table class="data ddt crash-t"><thead><tr><th>事件</th><th>高點 → 低點</th><th>下跌多久</th><th>跌幅</th><th>多久回本（高點起算）</th><th></th></tr></thead><tbody>${rowsHtml}${curHtml}</tbody></table></div>
    ${skipped ? `<p class="hint" style="margin:6px 0 0">另有 ${skipped} 個事件，${esc(ix.name)}沒有那段時間的資料，所以沒有列出；可以切到其他指數，或切到「三個一起比較」。</p>` : ""}
    ${teach}`;
}

$("#crash-body").addEventListener("click", (e) => {
  const seg = e.target.closest("#crash-seg button");
  if (seg) { crash.idx = +seg.dataset.i; renderCrash(); return; }
  const go = e.target.closest("[data-crash-go]");
  if (go) {
    const [s, en] = go.dataset.crashGo.split("|"), sym = crash.cfg.indices[crash.idx].sym;
    const q = new URLSearchParams({ t: sym, s, d: "10" }); if (en) q.set("e", en);
    history.replaceState(null, "", `#vol?${q}`);
    loadHash();
    $("#out-vol").scrollIntoView({ behavior: "smooth", block: "start" });
  }
});

// ============================================================
// 網址參數（方便把設定好的回測分享給別人）
// ============================================================
function saveHash(tab, params) {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v != null)).toString();
  history.replaceState(null, "", `#${tab}?${q}`);
}
function loadHash() {
  const [tab, q] = location.hash.slice(1).split("?");
  if (!tab || !$(`#tab-${tab}`)) return;
  showTab(tab);
  if (!q) return;
  const p = new URLSearchParams(q);
  // 網址有的參數用網址的；沒有的退回頁面預設值（所以只帶 t 的連結，其餘欄位一律是預設，不會沿用上次手動改過的值）
  // 結束日期的預設：dca／monthly 是「今天」（init 填的）；波動與風險的結束日預設空白（＝到資料最後一天），不能填成今天
  const TODAY_END = new Set(["#dca-end", "#monthly-end"]);
  // 下拉選單沒有 defaultValue：預設是 HTML 裡標 selected 的那一項
  const defOf = (el, id) => (el.tagName === "SELECT" ? ([...el.options].find((o) => o.defaultSelected) || el.options[0] || {}).value || ""
    : el.defaultValue || (TODAY_END.has(id) ? today : ""));
  const set = (id, k) => { const el = $(id); el.value = p.has(k) ? p.get(k) : defOf(el, id); };
  const pick = (name, def, max = 5) => {
    const list = (p.get("t") || "").split(",").map((x) => x.trim()).filter(Boolean).slice(0, max);
    state.pickers[name] = list.length ? list : def.split(",");
    renderChips(name);
  };
  if (tab === "dca") {
    pick("dca", $('.picker[data-picker="dca"]').dataset.default);
    state.dcaView = normMode(p.get("v"));   // 網址沒有 v ＝ 兩者（分享連結要一致）
    state.staleTabs.delete("dca");          // 下面就會重新送出，不用再因為主題重畫一次
    set("#dca-amount", "a"); set("#dca-start", "s"); set("#dca-end", "e"); set("#dca-months", "m"); set("#dca-count", "n"); set("#dca-yield", "y");
    updatePlanHint();
    $("#form-dca").requestSubmit();
  } else if (tab === "monthly") {
    pick("monthly", $('.picker[data-picker="monthly"]').dataset.default);
    state.staleTabs.delete("monthly");
    set("#monthly-amount", "a"); set("#monthly-init", "i"); set("#monthly-start", "s"); set("#monthly-end", "e");
    $("#form-monthly").requestSubmit();
  } else if (tab === "vol") {
    pick("vol", $('.picker[data-picker="vol"]').dataset.default);
    state.staleTabs.delete("vol");
    state.ddThr = normDd(p.get("d"));
    set("#vol-start", "s"); set("#vol-end", "e");
    if (p.get("g")) {
      const g = p.get("g").split(",");
      $$(".vol-t").forEach((el, i) => { el.value = g[i] != null && +g[i] > 0 ? g[i] : el.defaultValue; });
    } else $$(".vol-t").forEach((el) => { el.value = el.defaultValue; });
    $("#form-vol").requestSubmit();
  } else if (tab === "rolling") {
    pick("rolling", $('.picker[data-picker="rolling"]').dataset.default, 1);
    state.staleTabs.delete("rolling");
    set("#roll-from", "f"); set("#roll-horizon", "h"); set("#roll-months", "m"); set("#roll-count", "n"); set("#roll-yield", "y");
    $("#form-rolling").requestSubmit();
  }
}

// ============================================================
// 初始化
// ============================================================
function initEvents() {
  $$("select[data-event-for]").forEach((sel) => {
    sel.innerHTML = EVENTS.map(([d, t]) => `<option value="${d}">${t}</option>`).join("");
    const startInput = $(`#${sel.dataset.eventFor}-start`);
    sel.addEventListener("change", () => { if (sel.value) startInput.value = sel.value; });
    startInput.addEventListener("input", () => { sel.value = ""; });
  });
}

/** 表格比畫面寬時，顯示「可左右滑動」提示（手機上特別需要） */
function markScrollable() {
  $$(".table-wrap").forEach((w) => w.classList.toggle("scrollable", w.scrollWidth > w.clientWidth + 2));
}
let scrollTimer;
new MutationObserver(() => { clearTimeout(scrollTimer); scrollTimer = setTimeout(markScrollable, 100); })
  .observe($("main"), { childList: true, subtree: true });
window.addEventListener("resize", () => { clearTimeout(scrollTimer); scrollTimer = setTimeout(markScrollable, 100); });

async function init() {
  $$('input[type="date"][id$="-end"]').forEach((i) => { i.max = today; });
  $("#dca-end").value = today;
  $("#monthly-end").value = today;
  $("#alloc-end").value = today;
  initEvents();
  initPickers();
  addAllocRow("SPY", 60);
  addAllocRow("BND", 40);
  updatePlanHint();
  await loadManifest();
  loadHash();
  if ($("#tab-vol").classList.contains("active")) loadCrash();   // 直接開在波動與風險分頁：清單讀完後補讀歷次股災回顧
  // 切換深淺色（系統設定，或主站的 data-theme）時重畫圖表：顏色是畫圖當下讀主站變數，所以重畫就對了
  //   目前分頁：馬上重新送出表單；其他畫過圖的分頁：記下來，切回去時再重畫（showTab）
  //   升降息週期（#form-rates）沒有 submit 處理，對它 requestSubmit 會變成瀏覽器原生送出、整頁重新載入；它由 rates.js 自己重畫
  const redraw = () => {
    $$("section.tab:not(.active)").forEach((s) => { if (s.id !== "tab-rates" && $(".js-plotly-plot", s)) state.staleTabs.add(s.id.slice(4)); });
    $$("section.tab.active form").forEach((f) => { if (f.id !== "form-rates" && $(".js-plotly-plot", f.parentElement)) f.requestSubmit(); });
  };
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", redraw);
  new MutationObserver(redraw).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
}
// [主站] loader.js 用：等初始化完成、依網址切分頁、離開時呼叫 deactivate
const ready = init();
// 離開量化視圖時 loader／側邊欄會呼叫 deactivate()；看盤牆移除後沒有東西要停，留著空函式讓呼叫端不會壞
window.__quantApp = { ready, loadHash, showTab, deactivate: () => {} };

