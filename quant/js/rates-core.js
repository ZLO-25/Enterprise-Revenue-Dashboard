// 升降息週期：純計算（沒有任何網頁相關程式，所以可以用 node 直接測試）。手寫；tools/quant_sync.py 不會覆蓋。
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
 */
export function buildPhases(points, endDate, minDate = "2000-01-01") {
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
    if (q.start < minDate) { q.clippedFrom = q.start; q.start = minDate; }
    shown.push(q);
  }
  return shown;
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
