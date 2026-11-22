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
`#dca` `#monthly` `#rolling` `#alloc` `#vol` `#learn`（別名 `#winrate` `#edu`；`#wall` 看盤牆已移除，舊連結導到 `#dca`）→ 量化視圖；
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
- 深淺色切換（系統設定或主站 `data-theme`）：目前分頁馬上重畫；其他畫過圖的分頁記在 `state.staleTabs`，切回去時才重畫（app.js 的 showTab）。
  升降息週期由 rates.js 自己監聽重畫（它的表單沒有 submit 處理，不能對它 requestSubmit，否則瀏覽器會整頁重新載入）。
- 冒煙測試 `tools/smoke_test.py` 的 `quant()`：開 `/#dca`、用預設參數跑一次回測、切三種顯示篩選，檢查資產價值圖的線、按鈕 aria-pressed、扣款面板有無。

## 2026-11-20 第二階段：每月定期投入、大跌與回本、個股頁「回測這檔」
所有數字只由 `quant/data/prices` 的還原權息價算出；算不出來就寫原因，不估計。純函式在 `quant/js/engine.js`，測試 `node --test quant/tests/engine-phase2.test.mjs`（CI 有跑）。

**A. 每月定期投入（`#monthly`，側邊欄與分頁列在「單筆 vs 定期定額」後面）**
回答「每個月從薪水固定投 X 元，從某年到現在累積多少、中間最慘虧多少」（「單筆 vs 定期定額」是手上已有一整筆錢，兩者不同，觀念教室第 6 節與這個分頁互相連結）。
```
monthlyContribution(series, {monthly, initial, start, end})
  每月第一個交易日買進（開始日當月：開始日當天或之後第一個交易日；月初休市順延）
  initial＝開始當天一次買進；可買零股；不計手續費、稅、匯率；資料起點晚於開始日 → 從資料第一天算（頁面提醒）
  輸出：累積投入、期末資產、帳面損益、XIRR（不滿 365 天不給）、
        最難熬的時候（帳面損益率＝資產÷累積投入−1 的最低點）、帳面低於本金的最長連續天數、逐年表
        資產從高點回落最多的一次（valueDrawdown＝assetDrawdown(dates, value)：資產價值從先前最高點到之後最低點，取跌幅 % 最大的一次；
          高點／低點日與金額、回落金額與 %、回到高點那天；持續投入的新錢也算在資產裡，所以實際市場跌幅更大，頁面有註明）
xirr(flows)  二分法解 Σ金額/(1+r)^(天數/365)=0；用 Python 獨立重算 SPY/QQQ/0050.TW 的現金流，小數點後 12 位以上一致
```
網址：`#monthly?t=SPY,QQQ&a=10000&i=0&s=2010-01-01&e=…`（t 標的、a 每月金額、i 起始資金、s／e 起迄日）。圖表沿用 chart-plus（區間鈕、標的開關、縱軸「金額／對數」；沒有「報酬率 %」，因為資產線一直有新錢進來）。

**B. 波動與風險：大跌與回本**
`drawdownEpisodes(dates, values, threshold)`：從前高算起，最大跌幅達門檻（預設 20%，可選 10／20／30／50%；剛好等於也算）的每一段；回到（>=）前高時結束，之後再跌是新的一段；還沒回本 → `recoveryDate: null`，記從高點到資料最後一天的天數。
畫面：統計結果之前的「大跌與回本」面板（摘要、每檔一張表，預設最深 10 次、可展開全部、水下曲線緊接在表下面；手機寬度 ≤640px 表格改直排卡片 table.ddt）；單日漲跌頻率、連漲連跌等照舊在後面。網址 `#vol?t=…&s=&e=&g=3,5,10,15&d=20`（g 單日門檻、d 大跌門檻）。

**C. 個股頁「回測這檔」**
個股頁標題區底下兩個文字連結：`每月定期投入` → `../#monthly?t=<代號>`、`單筆 vs 定期定額` → `../#dca?t=<代號>`。`tools/build.py` 在輸出個股頁時注入（三種模板共用一處；`site.sidebar` 為 false 或 Artifact／合併版不放）；代號取 `companies.json` 的 `price.yahoo`，且必須在 `quant/tickers.json` 裡。
`quant/tickers.json` 新增群組「財報追蹤公司」，放啟用中、有 `price.yahoo`、原本不在清單裡的公司（代號全來自 companies.json）。價格由 GitHub Actions 的 quant-prices（tickers.json 改動時自動跑）抓；合併前本機沒有這些代號的資料，頁面照既有機制顯示「查無資料」。`fetch_data.py` 的 `currency_of` 補上 `.TWO`（TWD）、`.KS`（KRW）、`.AS`（EUR）。
只帶 `t=` 的連結：其餘欄位一律用頁面預設值（`loadHash` 對缺的參數退回預設，不沿用上次手動改過的值；#dca／#monthly／#rolling／#vol 都一樣，下拉選單退回 HTML 標 selected 的那一項；結束日期只有 #dca、#monthly 預設今天，#vol 預設空白＝到資料最後一天），並自動跑一次。

**D. 其他**
- `rates.js` 的 `loadSeries`：manifest 讀不到時不再把 null 永久快取（下次執行會重試）。
- 「單筆 vs 定期定額」切換顯示篩選時保留使用者關掉的標的與拉近的區間（`chart-plus.js` 的 `snapshot`／`restore`）；重新回測則回到預設。
- 冒煙測試 `tools/smoke_test.py` 另外開 `#monthly?t=SPY,QQQ`、`#vol?t=SPY,QQQ`（換門檻）各跑一次，並檢查個股頁有 `.bt-link`。

## 2026-11-20 事故：快取裡的舊檔混上新檔，「量化回測工具載入失敗」
**現象**：量化回測改版上線後，剛看過網站的人看到「量化回測工具載入失敗，請重新整理頁面。」
**原因**：GitHub Pages 的檔案是 `Cache-Control: max-age=600`（10 分鐘內瀏覽器不問伺服器）。快取是「每個網址」各管各的：
```
新 app.js?v=<新>  ──import "./engine.js"（沒有版本號）──▶  瀏覽器快取裡的舊 engine.js   → 缺 export drawdownEpisodes
舊 index.html（快取）→ view.html?v=<舊>（伺服器對任何 ?v= 都回最新檔，或快取的舊檔）  → 新 app.js 找不到新元素 → null.addEventListener
```
**兩層防護**
1. 根治：模組之間的 import 一律帶版本號。`tools/build.py` 的 `stamp_quant_imports()` 把 `quant/js/*.js` 的 `from "./x.js"` 改寫成 `from "./x.js?v=<qv>"`（`qv` 就是 `quant_ver()`，與 loader 動態 import 的版本同一個），所以新版 app.js 一定拿到新版 engine.js。
   - `quant_ver()` 算雜湊前會把 `?v=…` 正規化掉，否則版本號寫進檔案又影響版本號、每次 build 都變；build 連跑兩次結果相同。
   - 同一模組只能有一種網址形式，否則會變成兩份實例（`window.__quantApp`、`__quantRates`、theme 訂閱等狀態會分裂）。loader 的動態 import 與靜態 import 的網址完全相同（`.../js/engine.js?v=<qv>`）；實測七個分頁全載入後，每個模組只被請求一種網址。
   - node 測試（`quant/tests/*.mjs`）直接 import `../js/engine.js`（不帶版本）仍可執行，`node --check` 不受影響。
2. 保險：`quant/loader.js` 的 mount 失敗時，若這個分頁（sessionStorage，鍵含版本）還沒試過，就用 `fetch(url, {cache: "reload"})` 重抓目前頁面 HTML 與 `FILES` 清單內所有量化檔案（有版本與無版本網址都抓），然後 `location.reload()` 一次；已試過仍失敗才顯示錯誤，訊息帶「請按 Ctrl+F5」與原始錯誤，不會無限重載（sessionStorage 讀不到時視為已試過）。成功載入會清掉旗標。旗標寫不進去（舊版 Safari 無痕可讀不可寫）時也不重載，直接顯示說明。
   `FILES` 寫死在 loader.js（不另抓 json，因為那份也可能是舊的）；`quant/tests/test_cache_heal.py` 檢查 `quant/js/*.js` 都在清單內。

**限制**：使用者瀏覽器快取的是「修正前的舊 loader.js」（沒有復原邏輯）時，這一次轉換救不了，等 10 分鐘快取過期或 Ctrl+F5 就會好；新版上線後的每次改版則由兩層防護處理。

**改 `quant/` 之後一定要跑 `python3 tools/build.py`**（會重算 `qv`、改寫 import 的版本、更新各頁的 sidebar 設定），並把 `quant/js` 與網頁一起 commit。沒跑的話本機的 `test_cache_heal.py` 會失敗（import 版本與現算的 `quant_ver()` 不一致）；CI 會先跑 build.py 再測試，所以另有一步「量化回測版本號已建置」比對 repo 裡的 `quant/js` 與 `index.html` 的 `qv`，不一致就擋。
`prices-monthly` 會重跑 build.py，提交時連 `quant/js` 一起加（不然網頁的 `qv` 與 import 內的版本號會分家，import 指向舊版本號的網址，正好是這次事故的樣子，而且自動復原只重抓目前版本的網址，救不回來）。
**測試**：`tools/smoke_test.py` 的 `stale_cache()` 用 route 模擬快取：(a) 無版本的舊 engine.js（不需重新整理）、(b) 舊 engine.js 卡在同一網址、(c) 舊 view.html（b、c 要自動復原且只重新整理一次）、(d) 救不回來時只重新整理一次並顯示 Ctrl+F5 說明、(e) sessionStorage 寫不進去時不重新整理。
另用真的 HTTP 快取（模仿 GitHub Pages `max-age=600`＋ETag 的伺服器、Playwright persistent context）重演過：改版前 → 改版後（無修正）在 F5、頁面 HTML 過期而其他檔案還新鮮、只從個股頁點進來時都重現事故；改版後 → 修正版、修正版 → 模擬的下一版，在各種「哪些檔案過期」的單一與兩兩組合下都正常（最多自動重新整理一次）。唯一仍會失敗的是「快取裡是改版前的舊 loader（沒有復原功能）＋舊 index.html＋舊 view.html，但 app.js 已過期」這種罕見組合，等 10 分鐘或 Ctrl+F5。

## 2026-11-22：歷次股災回顧（波動與風險分頁最上面）

ZL 想要一張「以前跌多深、跌多久、多久回來」的表，在市場恐慌時對照（起因是一則社群貼文；貼文的數字沒有寫指數與起訖日，**不引用，一律重算**）。

```
quant/config/crashes.json   事件名稱＋到哪一段時間去找（Claude 維護；不放任何跌幅數字，測試會擋）
        │
        ▼
engine.js crashInWindow()   視窗內「先高後低、跌最深」的一段＝高點與低點；回本＝低點後第一次收盤回到那個高點
        │                   （和 drawdownEpisodes 不同：那個從歷史新高算起，前一次沒回本時下一次事件會被併在一起）
        ▼
app.js renderCrash()        預設「三個一起比較」（engine.js crashCompare() 算誰跌最深、中位數），也可切到單一指數看明細；最後一列「這一次」＝最近 365 天裡跌最深的一段
```

- 指數：`^TWII`（1997-07 起）、`^GSPC`（1927 起）、`^IXIC`；都在 `quant/tickers.json`，由 quant-prices 每個平日更新，所以「這一次」會跟著動。全部是價格指數（不含股息），表下的教學有說明。
- 1990 年台股泡沫：日線沒有涵蓋，改用總經儀表板資料檔（`data/macro/latest.json` 的 `tw.series.twstock`，國發會景氣指標檔的每月平均，1990-01 起）另外算一列，標「月平均，日線會更深」。這個檔讀不到時那一列顯示待確認。
- 某個指數沒有那段時間的資料：明細表不列那個事件，表下說明有幾個沒列。
- 「看這一段走勢」：把下面的表單換成那個指數、那段時間（到回本日）並送出，網址變成 `#vol?t=^GSPC&s=…&e=…&d=10`。
- 入口：首頁「市場情緒」那一行、總經儀表板「教學」區，都連到 `#vol`。
- 加事件：在 `crashes.json` 的 `events` 照時間順序加一筆（`id`、`name`、`from`、`to`、`what`）；視窗抓寬一點沒關係，但不要把兩次不同的大跌包在同一個視窗裡。
- 三個一起比較（2026-11-22 ZL 追加，預設檢視）：每個事件一列、三個指數並排，每格是跌幅、同一把尺的橫條（整條＝跌 100%）、高低點月份、跌多久、多久回本。「跌最深」的標記、上方「跌最深的次數」與最後一列中位數都由 `crashCompare()` 算：次數與中位數只用三個指數都有日線的事件（三邊才是同一批）；有月平均的格子而它不是最深的那個，就不標誰最深（月平均會把跌幅算淺，比不出來）。手機上一個事件一張卡、三個指數直排。
- 測試：`quant/tests/engine-phase2.test.mjs`（crashInWindow 六個手算例子、crashCompare 三個例子＋設定檔檢查）。
