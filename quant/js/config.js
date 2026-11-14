// 量化回測：資料從哪裡讀（手寫設定檔，tools/quant_sync.py 不會覆蓋）
//
// 目前方案：沿用舊回測站（Lump-Sum-v.s.-DCA）每個平日自動更新的價格資料。
//   兩個網站都在 https://zlo-25.github.io/ 底下，是「同一個網域」，
//   瀏覽器可以直接讀對方的檔案，不需要伺服器、也不用在主 repo 新增排程。
//
//   https://zlo-25.github.io/
//     ├─ Enterprise-Revenue-Dashboard/   ← 主站（這裡）
//     └─ Lump-Sum-v.s.-DCA/
//          ├─ data/manifest.json         ← 標的清單＋更新時間
//          ├─ data/prices/*.json         ← 每檔的還原權息價
//          └─ config/admin-key.json      ← 「管理標的」用的加密 Token
//
// 「⚙️ 管理標的」存檔時改的是舊回測站 repo 的 scripts/tickers.json，
// 它的 GitHub Actions 會抓新資料並部署，這裡重新整理就看得到。
const DCA_SITE = "/Lump-Sum-v.s.-DCA/";
export const DATA_BASE = DCA_SITE + "data/";
export const ADMIN = {
  repo: { owner: "ZLO-25", repo: "Lump-Sum-v.s.-DCA", branch: "main" },
  keyUrl: DCA_SITE + "config/admin-key.json",
  tickersPath: "scripts/tickers.json",
};
