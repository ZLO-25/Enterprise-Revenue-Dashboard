// 量化回測：資料從哪裡讀（手寫設定檔）
//
// 2026-11-14 起資料搬進主 repo（舊回測 repo 已設為私人並封存，它的網站已下線）：
//
//   Enterprise-Revenue-Dashboard/quant/
//     ├─ tickers.json            ← 要抓哪些標的（「⚙️ 管理標的」就是改這個檔）
//     ├─ scripts/fetch_data.py   ← 用 yfinance 下載還原權息價
//     ├─ data/manifest.json      ← 標的清單＋更新時間     ┐ 由 GitHub Actions
//     ├─ data/prices/*.json      ← 每檔的價格            ┘ quant-prices 每個平日寫入
//     └─ config/admin-key.json   ← 「管理標的」用的加密 Token（第一次設定時產生）
const QUANT = new URL("../", import.meta.url);           // …/quant/
export const DATA_BASE = new URL("data/", QUANT).href;
// 歷次股災回顧：事件清單（手寫設定）與 1990 年那一次用的月平均（總經儀表板的資料檔，只由 GitHub Actions 寫）
export const CRASH_CONFIG = new URL("config/crashes.json", QUANT).href;
export const MACRO_LATEST = new URL("../data/macro/latest.json", QUANT).href;
export const ADMIN = {
  repo: { owner: "ZLO-25", repo: "Enterprise-Revenue-Dashboard", branch: "main" },
  keyUrl: "quant/config/admin-key.json",   // 同時是網址（相對首頁）和 repo 裡的路徑
  tickersPath: "quant/tickers.json",
};
