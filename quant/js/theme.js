// 圖表主題色（手寫）：直接讀主站 assets/theme.css 的變數（:root 上），深淺色模式跟著主站走。
// app.js、rates.js 共用；每次畫圖時呼叫（不快取），切換深淺色後下一次畫圖就是對的。
export function themeColors() {
  const cs = getComputedStyle(document.documentElement);
  const v = (n, d = "") => cs.getPropertyValue(n).trim() || d;
  const palette = [1, 2, 3, 4, 5, 6, 7, 8].map((i) => v(`--s${i}`, "#2a78d6"));
  return {
    text: v("--ink", "#121211"), text2: v("--ink-2"), muted: v("--muted"), tick: v("--tick"),
    border: v("--grid"),            // 圖表格線（舊程式碼叫 border）
    grid: v("--grid"), axis: v("--axis"), line: v("--line"),
    panel: v("--surface"), chipBg: v("--chip-bg"), chipInk: v("--chip-ink"),
    accent: v("--accent"), neg: v("--neg"), good: v("--good-text"), bad: v("--bad-text"),
    ls: palette[0], dca: palette[1], palette,
    font: v("--font-ui", "system-ui, sans-serif"),
  };
}

/** 座標軸共同設定：格線 --grid、軸線 --axis、刻度字 --tick */
export function axisBase(c) {
  return { gridcolor: c.grid, linecolor: c.axis, zerolinecolor: c.axis, tickfont: { color: c.tick }, automargin: true };
}
