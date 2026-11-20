// 「單筆 vs 定期定額」顯示篩選的純函式（手寫；沒有 DOM，方便用 node 測試）
//   模式：both＝兩者、ls＝只看單筆、dca＝只看定期定額
//   只決定「畫哪些線、列哪些列」，不做任何回測計算，數字都來自 engine.js 的結果。

export const VIEW_MODES = ["both", "ls", "dca"];
export const VIEW_LABELS = { both: "兩者", ls: "只看單筆", dca: "只看定期定額" };
export const STRAT_NAME = { ls: "單筆", dca: "定期定額" };

/** 任何輸入都收斂成合法模式（網址、localStorage 可能被改壞）；其他值一律視為 both */
export const normMode = (v) => (v === "ls" || v === "dca" ? v : "both");

/** 寫進網址 hash 參數 v 的值：兩者時省略（回傳空字串） */
export const hashValue = (mode) => (normMode(mode) === "both" ? "" : normMode(mode));

/** 這個模式會出現的策略 */
export const strategiesOf = (mode) => (mode === "ls" ? ["ls"] : mode === "dca" ? ["dca"] : ["ls", "dca"]);

/**
 * 資產價值圖要畫的線。
 *   兩者：每檔 2 條（單筆實線、定期定額虛線）；只有 1 檔時單筆＝ls 色、定期定額＝dca 色；多檔時同一檔同色
 *   單選：每檔 1 條實線；只有 1 檔時用該策略的顏色，多檔各用 palette 不同色
 * 線名固定是「代號 單筆」「代號 定期定額」（chart-plus.js 用名稱分組、配對提示框）
 */
export function valueTraceSpecs(results, mode, { palette, ls, dca }) {
  const m = normMode(mode), out = [];
  results.forEach((r, i) => {
    const pal = palette[i % palette.length], one = results.length === 1;
    if (m !== "dca") out.push({ symbol: r.symbol, strategy: "ls", name: `${r.symbol} ${STRAT_NAME.ls}`, field: "lsValue",
      color: one ? ls : pal, dash: "solid" });
    if (m !== "ls") out.push({ symbol: r.symbol, strategy: "dca", name: `${r.symbol} ${STRAT_NAME.dca}`, field: "dcaValue",
      color: one ? dca : pal, dash: m === "both" ? "dash" : "solid" });
  });
  return out;
}

/** 績效指標表要列的列（依序）：[{symbol, strategy}] */
export function metricRows(results, mode) {
  const s = strategiesOf(normMode(mode));
  return results.flatMap((r) => s.map((st) => ({ symbol: r.symbol, strategy: st })));
}

/** 兩者模式下，期末資產較高的那一列加「較高」標記；單選時沒有比較，不標 */
export function winnerStrategy(r, mode) {
  return normMode(mode) === "both" ? (r.ls.final >= r.dca.final ? "ls" : "dca") : null;
}

/** 逐年報酬表的欄位：哪些策略欄、要不要「差距」欄與「為什麼買完之後…」說明 */
export function annualColumns(mode) {
  const m = normMode(mode);
  return { ls: m !== "dca", dca: m !== "ls", gap: m === "both", why: m === "both" };
}

/** 扣款紀錄與平均成本面板：只看單筆時整個隱藏；星號與單筆價線只在兩者時畫 */
export const showBuysPanel = (mode) => normMode(mode) !== "ls";
export const showLsMarks = (mode) => normMode(mode) === "both";
