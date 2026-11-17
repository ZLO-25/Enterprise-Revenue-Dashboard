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

**網站沒更新？** GitHub Pages 偶爾會漏掉某次推送（2026-11-14 合併 #3 後就發生過：
Actions 裡沒有出現新的「pages build and deployment」）。檢查方式與補救：
```
線上 quant/data/manifest.json 是 404 或舊日期？
  └─▶ Actions 看最新一筆 pages build 的 commit 是不是 main 最新那筆
        └─ 不是 ─▶ 對 main 隨便推一個小 commit（或合併一個小 PR），Pages 就會重新部署
```

## 🏦 升降息週期分頁（#rates，2026-11-16 起）
回測的第 7 個分頁：Fed／台灣央行升降息的每一輪週期，各標的（股票、ETF）的報酬。
```
.github/workflows/rates-weekly.yml（每週，不經過 Claude；改 fetch_rates.py 時也會跑）
   quant/scripts/fetch_rates.py
      美國：FRED DFEDTAR＋DFEDTARU（政策利率，只存「有變動」的日子）、DGS10（10 年期，月底值）
      台灣：中央銀行開放資料 EG28D01.csv（重貼現率，每次調整的日期與利率）
          └─▶ quant/data/rates.json（只有 Actions 寫，Claude 不手填；某序列抓不到 → 沿用舊的並寫進 unavailable）
quant/loader.js ── site.rates 開著時：載入 rates.css、在 app.js 之前呼叫 js/rates.js 的 inject()（放分頁按鈕與內容）
quant/js/rates-core.js  週期切分＋報酬計算（純函式）   測試：node --test quant/tests/rates-core.test.mjs
quant/js/rates.js       畫面（Plotly：上圖利率階梯＋背景階段色，下圖累積報酬，共用時間軸）＋表格
```
- 不要手改 view.html / js/app.js / quant.css（它們是 quant_sync.py 產生的）；這個分頁完全靠手寫檔外掛。
- 總開關：`companies.json` 的 `site.rates`。false（或沒有這個欄位）→ 側邊欄沒有這一項、不載入 rates.js／rates.css／rates.json。
- 週期規則：連續同方向的調整併成一輪；升息期＝首次到最後一次升息，高檔停留＝最後一次升息到下一次降息，降息期、低檔停留同理；
  只調一次的輪長度 0 天（列出、不算報酬）；最後一段標「進行中」；只顯示 2000 年起（跨過的階段起點截在 2000-01-01）。
- 報酬：還原權息價，起點＝階段起日當天或之後第一個交易日，終點＝階段迄日當天或之前最後一個交易日；滿 1 年才顯示年化。
- 網址：`#rates?t=SPY,QQQ&c=us&y=0&s=log&l=o`（t 標的、c us／tw、y 是否畫 10 年期殖利率、s log／lin 報酬刻度、l o／s 疊在同一張圖／上下兩張）。
- 圖的預設：利率（右軸 %）和各標的報酬指數（左軸，對數）疊在同一張圖，背景色是階段；可切換成上下兩張、或線性刻度。
- 待確認：台灣 10 年期公債殖利率還沒有可自動下載的官方來源，頁面顯示「待確認」，不用任何未驗證的數字。
- 在分支上測試：推到分支會觸發 rates-weekly（paths 含 fetch_rates.py），資料會提交回同一個分支；手動執行可勾「probe」只試探來源。

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
