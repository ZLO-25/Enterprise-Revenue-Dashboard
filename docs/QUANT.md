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
  js/theme.js      手寫：圖表主題色（讀主站 assets/theme.css 的變數）
  js/view-mode.js  手寫：「兩者／只看單筆／只看定期定額」的純函式（測試：quant/tests/view-mode.test.mjs）
  view.html  quant.css  js/app.js  js/admin.js  js/engine.js  vendor/
                   ↑ 原本由 tools/quant_sync.py 從 Lump-Sum-v.s.-DCA 產生；
                     2026-11-20 起改為手寫維護（舊回測 repo 已封存），直接改這些檔。
                     tools/quant_sync.py 沒加 --force 會直接報錯，避免蓋掉手改
```

## 網址
`#dca` `#rolling` `#alloc` `#vol` `#learn`（別名 `#winrate` `#edu`；`#wall` 看盤牆已移除，舊連結導到 `#dca`）→ 量化視圖；
`#dca?t=SPY,QQQ&a=…` 這類分享參數照舊還原。其他 hash（`#companies` 等錨點）或沒有 hash → 原主站。

## 資料（2026-11-14 起搬進主 repo）
舊回測 repo 已設為私人並封存、網站下線，所以價格資料改由主 repo 自己產生：
```
quant/tickers.json ──▶ .github/workflows/quant-prices.yml（每個平日台北 06:30、改 tickers.json 時、手動）
                         單元測試 → quant/scripts/fetch_data.py（yfinance）→ 只 git add quant/data
                                   ↓
                       quant/data/manifest.json、quant/data/prices/*.json ──▶ 網頁讀取
```
「管理標的」改的是本 repo 的 `quant/tickers.json`；加密 Token 存在 `quant/config/admin-key.json`
（第一次在網站上設定時產生；Token 需要本 repo 的 Contents: Read and write）。

**網站沒更新？** GitHub Pages 偶爾會漏掉某次推送（2026-11-14 合併 #3 後就發生過：
Actions 裡沒有出現新的「pages build and deployment」）。檢查方式與補救：
```
線上 quant/data/manifest.json 是 404 或舊日期？
  └─▶ Actions 看最新一筆 pages build 的 commit 是不是 main 最新那筆
        └─ 不是 ─▶ 對 main 隨便推一個小 commit（或合併一個小 PR），Pages 就會重新部署
```

## 升降息週期分頁（#rates，2026-11-16 起）
回測的第 7 個分頁：Fed／台灣央行升降息的每一輪週期，各標的（股票、ETF）的報酬。
```
.github/workflows/rates-weekly.yml（每週，不經過 Claude；改 fetch_rates.py 時也會跑）
   quant/scripts/fetch_rates.py
      美國：FRED DFEDTAR＋DFEDTARU（政策利率，只存「有變動」的日子）、DGS10（10 年期，月底值）
      台灣：中央銀行開放資料 EG28D01.csv（重貼現率，每次調整的日期與利率）
            櫃買中心 BDdys100.YYYYMMDD-C.xls（10 年期指標公債平均殖利率，每月最後一個營業日；已抓過的月份沿用）
          └─▶ quant/data/rates.json（只有 Actions 寫，Claude 不手填；某序列抓不到 → 沿用舊的並寫進 unavailable）
quant/loader.js ── site.rates 開著時：載入 rates.css、在 app.js 之前呼叫 js/rates.js 的 inject()（放分頁按鈕與內容）
quant/js/rates-core.js  週期切分＋報酬計算（純函式）   測試：node --test quant/tests/rates-core.test.mjs
quant/js/rates.js       畫面（Plotly：上圖利率階梯＋背景階段色，下圖累積報酬，共用時間軸）＋表格
```
- 2026-11-20 起 view.html / js/app.js / quant.css 都是手寫維護，可以直接改；這個分頁的分頁按鈕與內容仍由 rates.js 的 inject() 放進去。
- 總開關：`companies.json` 的 `site.rates`。false（或沒有這個欄位）→ 側邊欄沒有這一項、不載入 rates.js／rates.css／rates.json。
- 週期規則：連續同方向的調整併成一輪；升息期＝首次到最後一次升息，高檔停留＝最後一次升息到下一次降息，降息期、低檔停留同理；
  只調一次的輪長度 0 天（列出、不算報酬）；最後一段標「進行中」；只顯示 2000 年起（跨過的階段起點截在 2000-01-01）。
- 報酬：還原權息價，起點＝階段起日當天或之後第一個交易日，終點＝階段迄日當天或之前最後一個交易日；滿 1 年才顯示年化。
- 網址：`#rates?t=SPY,QQQ&c=us&y=0&s=log&l=o`（t 標的、c us／tw、y 是否畫 10 年期殖利率、s log／lin 報酬刻度、l o／s 疊在同一張圖／上下兩張、f／e 時間區間起迄日）。
- 時間區間（直接在圖上選，側邊欄沒有這個欄位）：圖上方快速按鈕（1／3／5／10／20 年、全部）、在圖面按住拖曳框選、拉圖下方的縮放滑桿（雙擊還原）。每次區間改變（plotly_relayout，停 120ms 後）rates.js 的 updateWindow() 重算：表格與整體表現（至少 30 天）、報酬指數（區間第一天＝100，用 Plotly.restyle 改 y）、Y 軸範圍與對數刻度、階段標籤；階段超出區間的部分被截斷（表上用＊標示）。純函式在 rates-core.js 的 buildPhases（minDate／maxDate）。
- 主圖輔助（2026-11-17）：第一次升息／降息畫 ▲▼ 虛線；每個階段內用各標的線的顏色直接寫出該階段報酬（階段太窄就不寫）；縱軸貼著所選區間最高最低點（只改刻度範圍，數據不動）。
- 事件前後圖（分頁下方）：每一輪「第一次升息／降息」為 0、價格＝100，前後各 12 個月（rates-core.js 的 eventPath／eventReturns／firstMoves）；表列出前、後 6 個月（182 天）報酬與平均。標的上市太晚或事件太新的那一邊不算。只看得到股價先動，無法證明是哪則消息造成（沒有利率預期資料，例如 Fed 利率期貨）。
- 日期顯示：全站（升降息分頁與單筆 vs 定期定額等圖）軸刻度一律 yyyy/mm（拉近到一個月內才顯示日），提示框 yyyy/mm/dd，不出現英文月份（chart-plus.js 的 tickformatstops／hoverformat）。
- 圖的預設：利率（右軸 %）和各標的報酬指數（左軸，對數）疊在同一張圖，背景色是階段；可切換成上下兩張、或線性刻度。
- 台灣 10 年期公債殖利率（2026-11-17 起）：櫃買中心「債券等殖成交系統指標利率行情表」每日 .xls（`https://www.tpex.org.tw/storage/bond_zone/tradeinfo/govbond/YYYY/YYYYMM/BDdys100.YYYYMMDD-C.xls`），取 10 年期那一列的平均殖利率。網站上最早只有約 2005 年底起的檔，更早的月份標「待確認」、不估計。找不到檔時櫃買中心回 HTTP 200 的 HTML 404 頁，程式看檔頭判斷。
- 在分支上測試：推到分支會觸發 rates-weekly（paths 含 fetch_rates.py），資料會提交回同一個分支；手動執行可勾「probe」只試探來源。

## 回測站程式有更新時
舊 repo 已封存，不會再有更新；`tools/quant_sync.py` 已加防呆，沒有 `--force` 只印說明並 exit 1。
它的輸出會蓋掉 2026-11-20 之後所有手寫改動（主站風格、顯示篩選、看盤牆移除），除非要還原到舊版，否則不要跑。

## CSS 隔離
quant.css 每條規則都加上 `#quant-dca-view` 前綴；主站同名的元素樣式（p、h1~h3、section、table、th、td）與 class（.controls .card .chip）在容器內覆蓋。
2026-11-20 起不再追求「和原回測站一模一樣」，而是和主站一模一樣（見下面「2026-11-20」）。

## Rollback
1. 立即：`companies.json` 的 `site.sidebar` 改成 `false` → `python3 tools/build.py` → push。
2. 完整：分支 `rollback/pre-quant` = 整合前的 main（32dee65）。

## 2026-11-18 調整（歷史紀錄；其中「載入後補丁」已在 2026-11-20 搬回原始檔，見下一節）
- 看盤牆移除：`assets/sidebar.js` 拿掉側邊欄項目；`quant/loader.js` 載入後用 CSS 隱藏 `view.html` 裡的看盤牆分頁按鈕與內容（`view.html`、`js/app.js` 是產生檔，不改），`#wall` 導到 `#dca`。`QuantDCA.hide()` 仍在，離開量化視圖時照常呼叫。
- 升降息週期（`quant/js/rates.js`）：分頁頂端加一段觀點備註：利率像地心引力，但不預測利率、不用它猜時機。
- 單筆 vs 定期定額（`quant/loader.js` 載入後注入）：加一句機會成本備註（觀點，意譯）。

## 2026-11-20：樣式對齊主站＋單筆／定期定額顯示篩選
純樣式與顯示，**計算邏輯與數字不變**（同一組參數改前改後的績效指標、卡片、各分頁表格文字完全相同）。
```
主站 assets/theme.css（:root 變數，深淺色自動切換）
   --page --surface --ink --ink-2 --muted --line --grid --axis --tick --accent --chip-bg/ink --s1…--s8 --font-ui --font-data
        │                                   │
        ▼ CSS 別名（quant.css 第 1 節）       ▼ 執行時 getComputedStyle（quant/js/theme.js）
   --panel→--surface  --ls→--s1  --dca→--s2     圖表：palette＝--s1…--s8、格線 --grid、軸線 --axis、刻度字 --tick、字體 --font-ui
```
- 頁首：eyebrow「量化回測與配置」＋ h1（目前分頁名稱）＋ lede 一句話（寫在分頁按鈕的 `data-title`／`data-lede`，切分頁時 app.js 的 showTab 換掉）＋ meta-row（資料更新時間、上傳 CSV、管理標的）。
  分頁列是主站 `.secnav` 膠囊。版面寬度 1180px，與主站 `.wrap` 對齊。
- 控制項：主要按鈕＝chip 配色（--chip-bg／--chip-ink），次要按鈕＝細邊框；圖表工具列（縱軸、標的、區間）與「顯示」都用主站 `.seg`。
  圖上的區間快速鈕改成 HTML 按鈕（chart-plus.js 的 rangeBar），不再用 Plotly 內建 rangeselector。
- 沒有 emoji（側邊欄圖示除外）；表格裡的獲勝標記改成「期末較高」小標籤（CSS）。
- 看盤牆整段刪除（view.html 的分頁與 section、app.js 的 Wall、quant.css 的 wall 樣式、loader.js 的隱藏補丁）。
  `#wall` 別名仍導到 `#dca`；`app.deactivate()` 留成空函式（loader／側邊欄離開量化視圖時會呼叫）。機會成本備註直接寫在 view.html。
- 顯示篩選（只在「單筆 vs 定期定額」）：結果區最上方「顯示：兩者｜只看單筆｜只看定期定額」。
```
state.lastDca（上次回測結果）──切換──▶ renderDca(mode)   不重新回測，只重畫
   mode＝both：現況       mode＝ls：只畫單筆線、卡片、指標列、逐年欄；隱藏「扣款紀錄與平均成本」
                           mode＝dca：只畫定期定額；扣款圖不畫單筆星號與單筆價線；結論改成該策略自己的摘要（不出現誰贏）
```
  網址參數 `v=ls|dca`（兩者時省略；網址沒有 v 就是兩者），localStorage `quant.dca.view` 記預設（沒有網址參數時使用）。
  「依模式挑哪些線、列、欄」都在 `quant/js/view-mode.js`（純函式），測試 `node --test quant/tests/view-mode.test.mjs`（CI 有跑）。
