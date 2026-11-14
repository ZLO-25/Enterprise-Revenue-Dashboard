# 左側導覽欄＋量化回測（單筆 vs 定期定額）

## 架構
```
companies.json  site.sidebar = true / false   ← 總開關（false = 網站回到加入側邊欄以前，一個 byte 都不差）
        │
tools/build.py  page() 注入 assets/sidebar.css、assets/sidebar.js（Artifact 版不注入）
        │
        ├─ 首頁 index.html
        │    #main-dashboard-view  原本的財報追蹤板（display:contents，內容不動）
        │    #quant-dca-view       空的；第一次點量化功能才載入 quant/loader.js
        │
        └─ 個股頁、期貨 K 棒頁：只有側邊欄，量化連結帶到首頁 #dca 等

quant/
  loader.js        手寫：載入 quant.css、view.html、Plotly、js/app.js、js/admin.js
  js/config.js     手寫：價格資料與「管理標的」的位置
  view.html  quant.css  js/app.js  js/admin.js  js/engine.js  vendor/
                   ↑ 由 tools/quant_sync.py 從 Lump-Sum-v.s.-DCA 產生，不要手改
```

## 網址
`#dca` `#rolling` `#alloc` `#vol` `#wall` `#learn`（別名 `#winrate` `#edu`）→ 量化視圖；
`#dca?t=SPY,QQQ&a=…` 這類分享參數照舊還原。其他 hash（`#companies` 等錨點）或沒有 hash → 原主站。

## 資料
價格資料仍由舊回測站（Lump-Sum-v.s.-DCA）的 GitHub Actions 每個平日更新；兩站同在
`https://zlo-25.github.io/` 網域，瀏覽器直接讀 `/Lump-Sum-v.s.-DCA/data/`。主 repo 沒有新增排程。
「⚙️ 管理標的」改的也是舊 repo 的 `scripts/tickers.json`，沿用原本的加密 Token。

## 回測站有更新時
```
python3 tools/quant_sync.py <Lump-Sum-v.s.-DCA 的本機路徑>   # 對不上會直接報錯
python3 tools/build.py
```

## CSS 隔離
quant.css 每條規則都加上 `#quant-dca-view` 前綴；`:root` 變數改掛在容器上；
主站同名的元素樣式（p、h1~h3、section、table、th、td）與 class（.controls .card .chip）在容器內先還原。
驗證方式：同一份資料下，原回測站與整合後的 666 個元素逐一比對 computed style，桌機淺色、手機深色都 0 差異。

## Rollback
1. 立即：`companies.json` 的 `site.sidebar` 改成 `false` → `python3 tools/build.py` → push。
2. 完整：分支 `rollback/pre-quant` = 整合前的 main（32dee65）。
