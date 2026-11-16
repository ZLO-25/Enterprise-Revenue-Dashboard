// 執行：node --test quant/tests/rates-core.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { policyEvents, buildPhases, periodReturn, summarize, lowerBound } from "../js/rates-core.js";

// 人造利率：2 次升、停、1 次降、停、2 次降、再 1 次升（進行中）
const pts = [
  ["1999-01-01", 4.0], ["1999-06-30", 4.25], ["1999-08-24", 4.5], ["2000-02-02", 4.75],
  ["2001-01-03", 4.5], ["2001-02-01", 4.5], ["2001-03-20", 4.0],
  ["2002-01-01", 4.0], ["2002-06-01", 4.25],
];
test("policyEvents：只留有變動的日子", () => {
  const ev = policyEvents(pts);
  assert.deepEqual(ev.map((e) => [e.date, e.dir]), [["1999-06-30", 1], ["1999-08-24", 1], ["2000-02-02", 1], ["2001-01-03", -1], ["2001-03-20", -1], ["2002-06-01", 1]]);
});
test("buildPhases：升→高檔→降→低檔→升（進行中），從 2000-01-01 起裁切", () => {
  const ph = buildPhases(pts, "2002-12-31", "2000-01-01");
  assert.deepEqual(ph.map((p) => p.type), ["hike", "holdHigh", "cut", "holdLow", "hike", "holdHigh"]);
  assert.equal(ph[0].clippedFrom, "1999-06-30");
  assert.equal(ph[0].start, "2000-01-01");
  assert.equal(ph[0].end, "2000-02-02");
  assert.equal(ph[1].end, "2001-01-03");              // 高檔停留到第一次降息為止
  assert.equal(ph[2].n, 2);                           // 連續兩次降息併成一輪
  assert.equal(ph[3].end, "2002-06-01");
  assert.equal(ph[4].single, true);                   // 只升一次
  assert.equal(ph[5].ongoing, true);
  assert.equal(ph[5].end, "2002-12-31");
});
test("整段發生在 minDate 之前的階段不顯示", () => {
  const ph = buildPhases(pts, "2002-12-31", "2000-01-01");
  assert.ok(ph.every((p) => p.end > "2000-01-01"));
});
test("periodReturn：起點取之後第一個交易日、終點取之前最後一個交易日、不滿一年不年化", () => {
  const s = { dates: ["2020-01-02", "2020-01-03", "2020-06-30", "2020-07-01"], close: [100, 110, 120, 130] };
  const r = periodReturn(s, "2020-01-01", "2020-06-30");
  assert.equal(r.from, "2020-01-02"); assert.equal(r.to, "2020-06-30");
  assert.ok(Math.abs(r.cum - 0.2) < 1e-12);
  assert.equal(r.ann, null);
  assert.equal(r.partialFrom, null);
});
test("periodReturn：滿一年才年化；標的較晚有資料就標 partialFrom；沒資料回 null", () => {
  const d = [], c = [];
  for (let y = 2010; y <= 2012; y++) { d.push(`${y}-01-04`); c.push(100 * Math.pow(1.1, y - 2010)); }
  const s = { dates: d, close: c };
  const r = periodReturn(s, "2009-01-01", "2012-12-31");
  assert.equal(r.partialFrom, "2010-01-04");
  assert.ok(Math.abs(r.ann - 0.1) < 0.002);
  assert.equal(periodReturn(s, "2013-01-01", "2014-01-01"), null);
  assert.equal(periodReturn(s, "2000-01-01", "2001-01-01"), null);
});
test("summarize：單次調整的階段不列入", () => {
  const ph = buildPhases(pts, "2002-12-31", "2000-01-01");
  const fake = ph.map((p) => ({ cum: 0.1 }));
  const sm = summarize(ph, { X: fake });
  assert.equal(sm.hike.X.n, 1);   // 只有第一段升息期（第二輪升息是單次）
  assert.equal(sm.cut.X.up, 1);
});
test("lowerBound", () => { assert.equal(lowerBound(["a", "c", "e"], "b"), 1); assert.equal(lowerBound(["a"], "z"), 1); });
