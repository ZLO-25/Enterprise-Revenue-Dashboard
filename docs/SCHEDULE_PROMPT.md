# 排程任務完整指令（每日檢查：週二至週六 台北 08:30）

> 這份文件就是排程任務的指令全文（排程每次都是新的工作階段，不記得之前的對話）。改排程行為時先改這份，再**新建**一個排程（現有排程不能改內容，只能啟用／停用）；排程 prompt ＝ 本檔扣掉這段標題與引言。
>
> **這份指令刻意不寫任何公司名稱**：公司清單每次從 `companies.json` 讀，各公司怎麼更新寫在 `companies/<代號>/SOURCES.md`。新增公司照 `docs/NEW_COMPANY_PROMPT.md` 做完（`enabled:true` ＋ SOURCES.md），公布日寫進該公司 `events[]`，隔天起每日排程自動納入，**不需要改排程**。
>
> 為什麼改成每日：原本每月 12 日一次，財報公布後平均要等 15 天（台積電最久 29 天）才更新。現在公布日隔天先放「快報」，之後「補完」「核對」，失敗隔天自動重試。

```
 每天（週二至週六）台北 08:30
   │
   ▼
 ⓪ git pull；python3 tools/daily.py   ← 便宜：只讀檔，列出今天誰到期、誰進行中、缺跑幾天
   │
   ├─ ① 快報   公布日已過的公司：數字＋書面財測先上線（狀態 flash）
   ├─ ② 補完   電話會議重點、一頁總結定稿（狀態 completed）
   ├─ ③ 核對   10-Q／XBRL 對上，解除待確認（verified → 回到 waiting）
   ├─ ④ 大新聞檢查（每家一次標題層級搜尋）
   └─ ⑤ 驗證、發佈、通知、每日回報（固定五段）
 失敗：python3 tools/daily.py try <代號> --note 原因 → 明天自動重試，連 5 次失敗轉 stuck（停止重試、等使用者）
```

任務：每天檢查「企業財報追蹤板」所有啟用中的公司，只做今天該做的事，直接 push 到 GitHub，並同步合併版 Claude Artifact。全程繁體中文。這是排程執行，沒有人在旁邊回答問題：不確定的數字不要填，照「資料誠實規則」標成待確認，在回報說明。**省額度是硬需求**：沒有到期的公司不讀財報、不開網頁；機械性工作（股價、預估、SEC 申報清單）是 GitHub Actions 做的，不要自己重做。

## 專案
- GitHub repo：`ZLO-25/Enterprise-Revenue-Dashboard`（main 分支，GitHub Pages 從根目錄發佈）　網站：https://zlo-25.github.io/Enterprise-Revenue-Dashboard/
- 結構：`companies.json`（公司清單，唯一來源）、`data/<代號>.json`（資料）、`data/calendar.json`（排程狀態檔，只用 `tools/daily.py` 改）、`data/sec-feed.json`（SEC 新申報清單，Actions 寫入）、`companies/<代號>/SOURCES.md`、`templates/`、`assets/`、`tools/`、`docs/DATA_SCHEMA.md`
- 先讀 repo 根目錄 `CLAUDE.md`。無法讀寫 repo（clone 或 push 被拒絕）：**不要繞過**，回報原因並結束。

## 執行環境提醒
- 容器的 `curl` 對 sec.gov、公司網站多半被擋（403）；**讀網頁請用 WebFetch／WebSearch**。SEC 的 XBRL（`data.sec.gov/api/xbrl/companyconcept/...`）與 `efts.sec.gov` 全文搜尋用 WebFetch 讀得到。WebFetch 單頁約 13 萬字上限，太長的 10-K 改讀 `FilingSummary.xml` → `R#.htm`。
- git 只用 clone／commit／push；push 用 `git push -u origin main`，網路錯誤才重試（2s、4s、8s、16s）。

## 步驟

### ⓪ 準備（約 1 分鐘）
1. clone repo（沒有權限先 `add_repo`：owner `ZLO-25`，repo `Enterprise-Revenue-Dashboard`，access `push`），讀 `CLAUDE.md`、`companies.json`。
2. `python3 tools/daily.py`：印出今天的清單。**這份清單就是今天的工作範圍**。
   - 「缺跑」有日期 → 上次成功到今天之間缺了排程（失敗或超出額度）。因為到期判斷是「公布日早於今天」，缺跑的事會自動出現在清單；新聞檢查範圍也已自動加長。回報要寫明補了哪幾天。
   - `data/sec-feed.json` 是 Actions 每天寫的 SEC 申報清單（8-K Item 2.02＝財報新聞稿、10-Q／10-K）。美股公司的 `events` 還是預估日（`est`）時，看這份就知道公司有沒有公布，**不必搜尋網頁**。
3. 如果 GitHub Actions 的 prices-monthly 正在跑（用 `mcp__github__actions_list` 看 `prices-monthly.yml` 最近一次 `status` 是不是 `in_progress`），**這次不要 push**，先做完檔案修改，等它結束再 push。

### ① 快報（到期的公司）
清單 ① 列出的公司才做。照該公司 `SOURCES.md` 的「更新步驟」，**只抓最新一期**：
- 公布日（`events` 裡早於今天的項目）已過 → 讀財報新聞稿（8-K 附件 99.1／公司公告），寫入新的一季（或月營收），填 `rd`／`rdB`、更新 `guidance`（**財測保留歷史**，見 DATA_SCHEMA）、`waterfall`、`annual`、`events`（處理完的公布日從 `events` 移除，加入下一個公布日）。
- 預估日（`est`）已過但公司還沒公告：**不算失敗**。美股看 `sec-feed.json`；其他公司搜尋一次是否已公告新日期，更新 `events`；仍沒有就下一天再查。
- 快報只收書面來源（新聞稿、申報文件）。電話會議留給「補完」。
- 做完：`python3 tools/validate.py <代號>` → 過了才算成功：`python3 tools/daily.py set <代號> flash --target <季度>`。沒過／來源讀不到：`git checkout -- data/<代號>.json`，`python3 tools/daily.py try <代號> --note "原因"`。
- 公司頁的季度總結（階段 2 完成後）標「初版」；快報先寫「成績單」「展望變化」兩格，其餘寫「待補完」。

### ② 補完（狀態 flash 的公司，快報的隔天起）
- 讀電話會議逐字稿（公司官方優先，其次第三方並註明網站），寫「管理層說法」「問答重點」，把一頁總結定稿；內容規則見 DATA_SCHEMA「summary」：每句標來源類別（書面／口頭／分析師預估／觀點），口頭內容附逐字稿連結與發言人，只摘要不整段照抄。
- 讀不到逐字稿：該格寫「待確認：逐字稿尚未取得」，`try` 一次，明天再試；**不要用新聞報導代替**。
- 成功：`python3 tools/daily.py set <代號> completed`。

### ③ 核對（狀態 completed 的公司）
- 等 10-Q／年報出來（看 `sec-feed.json` 的 periodic，或該公司 SOURCES.md 的核對來源），把快報數字對 XBRL／正式申報，解除 `notes.unavailable` 裡的「待確認：XBRL 核對」類項目；不一致就以 SOURCES.md 指定的來源為準並在回報寫出差多少。
- 完成：`python3 tools/daily.py set <代號> verified`（回到 waiting）。10-Q 還沒出來就維持 completed，**不算失敗、不加 try**，但超過 45 天仍沒有，回報提醒。

### ④ 大新聞檢查（每天，每家公司一次標題層級搜尋）
範圍：`daily.py` 印的「新聞檢查範圍」（平常過去 1 天；週二班加過去一週回顧；缺跑時自動加長）。**只有達標才深入讀**：
財測或營運變化（預告財報、上下修財測、重大訂單或合約）、資本動作（併購、分割、大額回購、增資、股利變動）、人事（執行長、財務長異動）、監管與法律（出口管制、反壟斷、重大訴訟、調查）、產業事件（主要客戶或對手財報出現與本公司直接相關的訊息）。
- 公司公告或申報文件證實 → 「已證實」；只有媒體報導 → 「待確定」並寫媒體名稱（`unc:1`，`note` 以「待確定：」開頭）。
- 股價大漲大跌本身不算新聞，除非找得到上面五類原因。
- 達標的新聞同時寫進該公司 `milestones[]`；沒達標的不寫、不列在回報。

### 本益比、股價與財報公布日（每次寫入新一季時都要做）
- **新增每一季時同時填 `rd` 與 `rdB`**（那一季 EPS 第一次公開的日期）：美股優先用 8-K Item 2.02 新聞稿日（`rdB:"p"`），讀不到才用該季 10-Q／10-K 申報日（`rdB:"f"`）；台積電用財報新聞稿（Earnings Release）開頭的日期（`rdB:"p"`）；台達電用公司公告或法說會日（`rdB:"c"`），讀不到時手動觸發 `rd-twse` 工作流程（證交所 BWIBBU 財報換季日，`rdB:"t"`，偏保守）再用 `python3 tools/rd_import.py <代號>` 匯入；三星用正式財報法說會日（`rdB:"c"`）。讀不到填 `null`，並在 `notes.unavailable` 加「待確認：<季度> 的財報公布日（rd）：原因」，**不可以用季度結束後幾天推算**；最新一季的 `rd` 不可為 null。預估公布日（`est`）換成公司公告日時，確認 `rd` 一致。
- **股價不是你寫的**：`data/prices/<代號>.json` 由 GitHub Actions（prices-monthly，每月 1～6 日）寫入。先 `git pull` 取得最新；檢查每家公司的股價檔最後一個月是不是上個月。沒進來 → 用 GitHub 工具手動觸發 prices-monthly 一次（`mcp__github__actions_run_trigger`），並在回報說明；仍然不可以自己填股價、不可以估計。
- **股票分割**：EPS 重編（SOURCES.md 步驟）與股價檔重抓必須在同一次完成：重編 EPS 後觸發 prices-monthly 並在 `accept` 填該公司代號；否則 validate 會因本益比相鄰月份跳動超過 3 倍而失敗。
- **預估本益比**：由 Actions 每月存當月快照，**不補、不回填、不用今天的預估填過去的月份**；回報列各公司最新預估本益比，缺的列待確認。
- 本益比與預估本益比都不存檔、不手填（`tools/pe.py` 建置時算出）。

### ⑤ 驗證、發佈、通知
1. 有實質變動（新季度／月份資料、新事件、新的股價月份）：`python3 tools/build.py`，再 `python3 tools/validate.py` 全部一次。只有 `asOf` 變動不算實質變動；**`asOf` 只在該公司資料真的更新或確認過時才改**（不是每次執行都改）。
2. commit（繁體中文簡述，例：「NVDA 3Q27 快報」「NVDA 3Q27 補完：電話會議重點」）→ `git push -u origin main`（先確認第 ⓪.3）。
3. Artifact：只有一個合併版 Artifact，網址在 `companies.json` 的 `site.artifact`。有變動時 publish `dist/artifacts/all.html`（先 `action:"read"` 再 publish），`label` 寫這次變動。
4. `python3 tools/daily.py done`（記 lastSuccess ＝ 今天）後 commit＋push `data/calendar.json`（和上一步同一個 commit 即可）。**如果某家失敗了，也要 `done`**——失敗的公司由 `try` 的計數接手，明天重試；沒跑完整個排程才不 `done`。
5. 每次都用 PushNotification 通知（沒事的日子一行，有快報或紅燈時標題直接寫公司與重點）。

## 每日回報（最後一則訊息；固定五段，沒事的日子只有三四行）
```
【MM/DD 每日更新】
① 今天到了什麼    哪些公司公布財報、月營收、新申報；沒有就寫「無」
② 今天做了什麼    快報／補完／核對／重試第幾次；缺跑補了哪幾天；網站有沒有重新發佈（commit 連結）
③ 大新聞          過去一天（週二加過去一週回顧），分「已證實」「待確定」，各附來源
④ 接下來 7 天     即將公布的公司與日期；日期有變動特別標出
⑤ 未完成          待確認項目、重試中（第幾次）、stuck 的公司（置頂）、論點轉紅燈的項目
```
另外附：各公司最新本益比與預估本益比、`rd` 缺的（待確認）、使用的來源連結、核對沒過或被跳過的公司與原因、Pages／Artifact 是否更新成功。

## 一次性的例外
- 公司停止重試（stuck）後，使用者說「繼續 <代號>」才 `python3 tools/daily.py set <代號> waiting` 重新開始。
- 手動觸發同一個排程（`fire_trigger`）等於多跑一天，`daily.py` 的判斷不受影響。
