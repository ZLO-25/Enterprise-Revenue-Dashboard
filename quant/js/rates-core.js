// 升降息週期：純計算（沒有任何網頁相關程式，所以可以用 node 直接測試）。手寫。
//
//   政策利率「有變動」的日子 ──▶ 連續同方向的變動併成一輪 ──▶ 切成四種階段
//
//   利率 ──┐         ┌───────────┐
//          │   ┌─────┘           └────┐
//          └───┘                      └──────
//          ↑首次升   ↑最後一次升  ↑首次降  ↑最後一次降
//          │← 升息期 →│← 高檔停留 →│← 降息期→│← 低檔停留 → 下一輪首次升息
//
// 測試：node --test quant/tests/rates-core.test.mjs

export const PHASE = {
  hike: { label: "升息期" },
  holdHigh: { label: "高檔停留" },
  cut: { label: "降息期" },
  holdLow: { label: "低檔停留" },
};

const DAY = 86400000;
export const dayNum = (iso) => Date.UTC(+iso.slice(0, 4), +iso.slice(5, 7) - 1, +iso.slice(8, 10)) / DAY;
export const daysBetween = (a, b) => dayNum(b) - dayNum(a);

/** points = [[日期, 利率], …]（依日期排序）→ 利率有變動的事件 */
export function policyEvents(points) {
  const out = [];
  let prev = null;
  for (const [d, r] of points) {
    if (r == null || !isFinite(r)) continue;
    if (prev !== null && r !== prev) out.push({ date: d, dir: r > prev ? 1 : -1, from: prev, to: r });
    prev = r;
  }
  return out;
}

/**
 * 切成階段。
 *   endDate  最後一段（進行中）的終點，通常是資料截至日
 *   minDate  只顯示這天以後；跨過這天的階段起點會被裁成 minDate，並用 clippedFrom 記下真正的起點
 *   maxDate  只顯示這天以前（選填）；跨過這天的階段終點會被裁成 maxDate，並用 clippedTo 記下真正的終點
 *            （被裁掉終點的階段不再算「進行中」）
 */
export function buildPhases(points, endDate, minDate = "2000-01-01", maxDate = null) {
  const events = policyEvents(points);
  const runs = [];
  for (const e of events) {
    const last = runs[runs.length - 1];
    if (last && last.dir === e.dir) { last.lastEvt = e; last.n += 1; }
    else runs.push({ dir: e.dir, firstEvt: e, lastEvt: e, n: 1 });
  }
  const phases = [];
  runs.forEach((run, i) => {
    const next = runs[i + 1];
    phases.push({
      type: run.dir > 0 ? "hike" : "cut",
      start: run.firstEvt.date, end: run.lastEvt.date, n: run.n,
      rateFrom: run.firstEvt.from, rateTo: run.lastEvt.to, ongoing: false,
      single: run.n === 1,   // 只調一次：長度 0 天，沒有報酬可算
    });
    phases.push({
      type: run.dir > 0 ? "holdHigh" : "holdLow",
      start: run.lastEvt.date, end: next ? next.firstEvt.date : endDate, n: 0,
      rateFrom: run.lastEvt.to, rateTo: run.lastEvt.to, ongoing: !next, single: false,
    });
  });
  const shown = [];
  for (const p of phases) {
    if (p.end <= minDate && !(p.start === p.end && p.start >= minDate)) continue;
    const q = { ...p };
    if (maxDate && q.start >= maxDate) continue;
    if (q.start < minDate) { q.clippedFrom = q.start; q.start = minDate; }
    if (maxDate && q.end > maxDate) { q.clippedTo = q.end; q.end = maxDate; q.ongoing = false; }
    shown.push(q);
  }
  return shown;
}

/**
 * 把「只存變動日」的階梯線切成 [from, to] 這個視窗：第一點＝視窗起點當天的利率水準（最後一次變動之後），
 * 之後是視窗內的變動日。這樣視窗起點之前就變動過的利率，階梯線一開始就在正確的高度。
 */
export function windowPoints(points, from, to) {
  const out = [];
  let level = null;
  for (const [d, r] of points) {
    if (d <= from) level = r;
    else if (d <= to) out.push([d, r]);
  }
  if (level !== null) out.unshift([from, level]);
  return out;
}

/** 日期排序陣列中，第一個 >= d 的位置（沒有則 length） */
export function lowerBound(dates, d) {
  let lo = 0, hi = dates.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (dates[m] < d) lo = m + 1; else hi = m; }
  return lo;
}

/**
 * 某標的在 [start, end] 的報酬。series = { dates, close }（還原權息價）。
 * 回傳 null＝這段沒有資料。
 *   起點＝start 當天或之後第一個交易日；終點＝end 當天或之前最後一個交易日
 *   partialFrom：標的比 start 晚上市／晚有資料，改從它的第一天算
 */
export function periodReturn(series, start, end) {
  const { dates, close } = series;
  if (!dates || !dates.length) return null;
  const s = lowerBound(dates, start);
  let e = lowerBound(dates, end);
  if (e >= dates.length || dates[e] > end) e -= 1;
  if (s >= dates.length || e < 0 || e <= s) return null;
  const c0 = close[s], c1 = close[e];
  if (!(c0 > 0) || !(c1 > 0)) return null;
  const days = daysBetween(dates[s], dates[e]);
  const cum = c1 / c0 - 1;
  return {
    cum,
    ann: days >= 365 ? Math.pow(1 + cum, 365.25 / days) - 1 : null,   // 不滿 1 年不年化
    days, from: dates[s], to: dates[e],
    partialFrom: s === 0 && daysBetween(start, dates[0]) > 7 ? dates[0] : null,   // 晚了一週以上才算「資料較晚開始」（假日不算）
  };
}

const median = (a) => { const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

/** 每種階段、每個標的：幾段有資料、平均／中位數累積報酬、上漲幾段。單次調整的階段不列入。 */
export function summarize(phases, returnsBySym) {
  const out = {};
  for (const type of Object.keys(PHASE)) {
    out[type] = {};
    for (const sym of Object.keys(returnsBySym)) {
      const vals = [];
      phases.forEach((p, i) => {
        if (p.type !== type || p.single) return;
        const r = returnsBySym[sym][i];
        if (r) vals.push(r.cum);
      });
      out[type][sym] = vals.length
        ? { n: vals.length, mean: vals.reduce((a, b) => a + b, 0) / vals.length, median: median(vals), up: vals.filter((v) => v > 0).length }
        : null;
    }
  }
  return out;
}

/**
 * 事件前後圖：以某一天（每一輪第一次升息／降息日）為 0，前後各 beforeDays／afterDays 天的價格路徑，事件日當天＝100。
 *   事件日價格＝事件日當天或之後第一個交易日的收盤（和 periodReturn 的起點規則一樣）。
 *   x＝距事件日的月數（天數 ÷ 30.4375），y＝收盤 ÷ 事件日收盤 × 100。
 *   標的在事件日之後才開始有資料 → null；資料只涵蓋一部分前後區間 → 有多少畫多少（hasBefore／hasAfter 標示是否完整）。
 */
export function eventPath(series, eventDate, beforeDays = 365, afterDays = 365) {
  const { dates, close } = series;
  if (!dates || !dates.length) return null;
  const i0 = lowerBound(dates, eventDate);
  if (i0 >= dates.length || daysBetween(eventDate, dates[i0]) > 7 || !(close[i0] > 0)) return null;   // 事件日附近沒有交易資料
  const base = close[i0];
  const x = [], y = [];
  for (let i = Math.max(0, lowerBound(dates, shiftDays(eventDate, -beforeDays))); i < dates.length; i += 1) {
    const off = daysBetween(dates[i0], dates[i]);
    if (off > afterDays) break;
    x.push(off / 30.4375); y.push((close[i] / base) * 100);
  }
  return {
    x, y, base0: dates[i0],
    hasBefore: daysBetween(dates[0], dates[i0]) >= beforeDays,
    hasAfter: daysBetween(dates[i0], dates[dates.length - 1]) >= afterDays,
  };
}

/** 事件日前、後各 days 天的報酬（前＝事件日往前 days 天到事件日；後＝事件日到往後 days 天）；資料不夠的那一邊是 null */
export function eventReturns(series, eventDate, days = 182) {
  const { dates } = series;
  if (!dates || !dates.length) return { before: null, after: null };
  const before = daysBetween(dates[0], eventDate) >= days ? periodReturn(series, shiftDays(eventDate, -days), eventDate) : null;
  const after = daysBetween(eventDate, dates[dates.length - 1]) >= days ? periodReturn(series, eventDate, shiftDays(eventDate, days)) : null;
  return { before: before ? before.cum : null, after: after ? after.cum : null };
}

export function shiftDays(iso, n) { return new Date((dayNum(iso) + n) * DAY).toISOString().slice(0, 10); }

/** 每一輪的第一次升息／降息日：升息期、降息期兩種階段的起點（單次調整也算） */
export function firstMoves(phases) {
  return phases.filter((p) => (p.type === "hike" || p.type === "cut") && !p.clippedFrom).map((p) => ({ date: p.start, type: p.type }));
}
