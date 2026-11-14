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

## 資料（2026-11-14 起搬進主 repo）
舊回測 repo 已設為私人並封存、網站下線，所以價格資料改由主 repo 自己產生：
```
quant/tickers.json ──▶ .github/workflows/quant-prices.yml（每個平日台北 06:30、改 tickers.json 時、手動）
                         單元測試 → quant/scripts/fetch_data.py（yfinance）→ 只 git add quant/data
                                   ↓
                       quant/data/manifest.json、quant/data/prices/*.json ──▶ 網頁讀取
```
「⚙️ 管理標的」改的是本 repo 的 `quant/tickers.json`；加密 Token 存在 `quant/config/admin-key.json`
（第一次在網站上設定時產生；Token 需要本 repo 的 Contents: Read and write）。

## 回測站程式有更新時（舊 repo 已封存，通常不會再用到）
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
