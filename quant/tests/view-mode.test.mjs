import test from "node:test";
import assert from "node:assert/strict";
import { normMode, hashValue, strategiesOf, valueTraceSpecs, metricRows, winnerStrategy, annualColumns, showBuysPanel, showLsMarks } from "../js/view-mode.js";

const R = (symbol, lsF, dcaF) => ({ symbol, ls: { final: lsF }, dca: { final: dcaF } });
const results = [R("SPY", 120, 110), R("QQQ", 100, 130)];
const colors = { palette: ["p1", "p2", "p3"], ls: "LS", dca: "DCA" };

test("normMode / hashValue：非法值當成 both，兩者時網址省略", () => {
  assert.equal(normMode("ls"), "ls"); assert.equal(normMode("dca"), "dca");
  for (const bad of [undefined, null, "", "both", "x", 1]) assert.equal(normMode(bad), "both");
  assert.equal(hashValue("both"), ""); assert.equal(hashValue("ls"), "ls"); assert.equal(hashValue("dca"), "dca"); assert.equal(hashValue("zzz"), "");
});

test("strategiesOf", () => {
  assert.deepEqual(strategiesOf("both"), ["ls", "dca"]);
  assert.deepEqual(strategiesOf("ls"), ["ls"]);
  assert.deepEqual(strategiesOf("dca"), ["dca"]);
});

test("valueTraceSpecs：兩者＝每檔 2 條、定期定額虛線、同檔同色", () => {
  const t = valueTraceSpecs(results, "both", colors);
  assert.deepEqual(t.map((x) => x.name), ["SPY 單筆", "SPY 定期定額", "QQQ 單筆", "QQQ 定期定額"]);
  assert.deepEqual(t.map((x) => x.dash), ["solid", "dash", "solid", "dash"]);
  assert.deepEqual(t.map((x) => x.color), ["p1", "p1", "p2", "p2"]);
});

test("valueTraceSpecs：單選＝只有所選策略、全實線、多檔各用 palette 不同色", () => {
  const ls = valueTraceSpecs(results, "ls", colors);
  assert.deepEqual(ls.map((x) => x.name), ["SPY 單筆", "QQQ 單筆"]);
  assert.ok(ls.every((x) => x.dash === "solid" && x.field === "lsValue"));
  assert.deepEqual(ls.map((x) => x.color), ["p1", "p2"]);
  const dca = valueTraceSpecs(results, "dca", colors);
  assert.deepEqual(dca.map((x) => x.name), ["SPY 定期定額", "QQQ 定期定額"]);
  assert.ok(dca.every((x) => x.dash === "solid" && x.field === "dcaValue"));
});

test("valueTraceSpecs：只有 1 檔時用策略色", () => {
  const one = [R("SPY", 1, 2)];
  assert.deepEqual(valueTraceSpecs(one, "both", colors).map((x) => x.color), ["LS", "DCA"]);
  assert.deepEqual(valueTraceSpecs(one, "ls", colors).map((x) => x.color), ["LS"]);
  assert.deepEqual(valueTraceSpecs(one, "dca", colors).map((x) => x.color), ["DCA"]);
});

test("metricRows：單選只列所選策略", () => {
  assert.equal(metricRows(results, "both").length, 4);
  assert.deepEqual(metricRows(results, "ls"), [{ symbol: "SPY", strategy: "ls" }, { symbol: "QQQ", strategy: "ls" }]);
  assert.deepEqual(metricRows(results, "dca").map((x) => x.strategy), ["dca", "dca"]);
});

test("winnerStrategy：只有兩者模式才標較高", () => {
  assert.equal(winnerStrategy(results[0], "both"), "ls");
  assert.equal(winnerStrategy(results[1], "both"), "dca");
  assert.equal(winnerStrategy(results[0], "ls"), null);
  assert.equal(winnerStrategy(results[0], "dca"), null);
});

test("annualColumns：單選沒有差距欄與說明", () => {
  assert.deepEqual(annualColumns("both"), { ls: true, dca: true, gap: true, why: true });
  assert.deepEqual(annualColumns("ls"), { ls: true, dca: false, gap: false, why: false });
  assert.deepEqual(annualColumns("dca"), { ls: false, dca: true, gap: false, why: false });
});

test("扣款面板：只看單筆隱藏；單筆星號只在兩者畫", () => {
  assert.equal(showBuysPanel("both"), true); assert.equal(showBuysPanel("dca"), true); assert.equal(showBuysPanel("ls"), false);
  assert.equal(showLsMarks("both"), true); assert.equal(showLsMarks("dca"), false);
});
