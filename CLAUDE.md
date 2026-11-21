# 企業財報追蹤板：給 Claude 的專案規則

全程用繁體中文。說明要讓使用者能拿去教別人：先用自己的話重述目標，多用 ASCII 圖。

## 觸發句
使用者說「加入新公司：XXX」「新增公司 XXX」「add new company: XXX」（可一次多家）時：
照 [`docs/NEW_COMPANY_PROMPT.md`](docs/NEW_COMPANY_PROMPT.md) 的「完整模板」執行，等同使用者貼了整份模板並填了公司名稱。

## 資料誠實規則（所有工作都適用，包含每日排程）
- 每個數字都要能追到來源（主管機關申報文件或公司公告），而且真的讀到那個數字。
- 讀不到、算不出來、來源對不起來的數字：填 `null`，在 `notes.unavailable`（台積電、PLTR 舊格式則寫進回報）加一行，以「待確認：」開頭說明哪一季、哪個欄位、為什麼。
- 不估計、不內插、不從記憶補數字。
- 內容分四種來源，頁面每一句都要標：書面（申報文件、新聞稿）、口頭（電話會議；2026-11 起允許收錄，必附逐字稿連結與發言人，只摘要，不寫進書面財測欄位、不參與核對）、分析師預估（只能用事前快照，不回補）、觀點（Claude 的判斷）。讀不到逐字稿寫「待確認：逐字稿尚未取得」，不用新聞報導代替。
- 只有媒體報導、公司未證實的事件：`unc:1`，`note` 以「待確定：」開頭。
- `python3 tools/validate.py` 沒過就不發佈；不可以為了通過核對去改數字或放寬核對。

## 本益比與股價（新增）
- 股價檔 `data/prices/<代號>.json` **只由 GitHub Actions（prices-monthly）寫入**，Claude 不手填、不修改。本益比與預估本益比**不存檔、不手填**，由 `tools/pe.py` 在建置時算出。
- 每個季度都要有 `rd`（那一季 EPS 第一次公開的日期）與 `rdB`；讀不到填 `null` 並在 `notes.unavailable` 寫「待確認：<季度> 的財報公布日（rd）：原因」，不可用季度結束後幾天推算。
- 每日收盤價 `data/daily/<代號>.json` **只由 GitHub Actions（prices-daily）寫入**（每天多班、含重試；財報季度更新 push 後會自動重算）。裡面的每日本益比、市值、P/S、EV/Sales、距估值門檻都是 `tools/daily_calc.py` 的公式算的，Claude 不手填、不重算、不需要觸發。
- 個股 K 棒 `data/kbar/` **只由 GitHub Actions（prices-daily，`tools/kbar_update.py`）寫入**，AES 加密（密碼與期貨共用 `FUTURES_PASSWORD`），Claude 不手改、不手填、不在本機產生。
- ETF（`etf/` 頁，[`docs/ETF.md`](docs/ETF.md)）：清單 `data/etf/config.json` 由 Claude 維護；`data/etf/latest.json`、`data/etf/daily/` **只由 GitHub Actions（prices-daily 的 `tools/etf_update.py`）寫入**。
- 預估本益比（分析師預估）只有每月快照，**不回填**；它是網站上唯一不是財報／公司公告的數字，一律標「分析師預估」。

## 常用指令
```
python3 tools/validate.py       # 核對設定與所有啟用中的公司
python3 tools/build.py          # 產生網站與合併版 Artifact（dist/artifacts/all.html）
python3 tools/new_company.py …  # 新增公司腳手架（本益比需要 --yahoo/--price-from 或 --no-price）
python3 tools/pe.py             # 本益比計算的固定測試案例
python3 tools/daily_calc.py     # 每日估值公式的固定測試案例
python3 tools/prices_update.py --check  # 股價是否已到最新（只有 GitHub Actions 會真的抓）
python3 tools/daily.py          # 每日排程今天的工作清單與狀態（set／try／done 改 data/calendar.json）
python3 tools/daily.py story    # 各公司核心故事線與類別（寫 milestones 前先對；屬於故事線的事件 cat 用 story.cats）
python3 tools/daily.py brief    # 每日排程的一頁摘要（清單＋股價＋論點卡轉差＋本益比＋今天要讀哪些附件）
python3 tools/daily.py inbox [代號]      # SEC 收件匣：Actions（daily-prep）預抓的財報新聞稿 data/inbox/<代號>/pr-*.txt＋XBRL 核對表（快報、核對先看，tools/sec_inbox.py）
python3 tools/daily.py trend-facts    # 世界趨勢月報的事實表（網站財報數字一頁，tools/trend_facts.py）
python3 tools/company_brief.py <代號>  # 分析用的公司一頁摘要（不要整份讀 data/<代號>.json；含巴菲特＋蒙格檢查表摘要）
python3 tools/buffett.py <代號>        # 檢查表指標（盈餘殖利率對公債、十年成績單、回購、保留盈餘、股票酬勞與扣酬勞後現金流…）原始輸出
python3 tools/bs_merge.py --only sbc <代號>…   # 把 data/bs-raw/ 的股票酬勞（sbc）單獨合併（SEC 抓取要用 GitHub Actions 的 bs-fetch，field 填 sbc；非 SEC 公司加 --no-source）
python3 tools/capex_chain.py    # AI 資本支出鏈：四家雲端大廠資本支出合計（日曆季）與賣方營收年增率，印最近 8 季
python3 tools/tw_sbc.py <tw-raw 分支的 raw/<股票代號>/fs> <代號>   # 台股股票酬勞：讀現金流量表「股份基礎給付酬勞成本」產生 data/bs-raw/ 提案，再跑上一行合併（報表沒列這一行不當成 0）
```

## 合併 PR 的規則
- **合併前必須看到 CI（`.github/workflows/ci.yml`）是綠燈**：資料核對、建置、單元測試、JavaScript 語法、瀏覽器冒煙測試。CI 紅燈就先修，不可略過。
- 合併後刪除該 PR 的分支（PR 頁面可 Restore branch）。保留清單：`sec-raw`、`tw-raw`（Actions 的原始資料）、`rollback/*`、`shadow/*`、`pr-shots-*`。注意：這個雲端環境的 proxy 不允許刪分支，要請 ZL 在 GitHub 刪，或把 repo 設定「合併後自動刪除 head 分支」打開。
- 單元測試放在 `tools/tests/`（`python3 -m unittest discover -s tools/tests`）；新增邏輯要附測試。

## 每日準備與系統健康
- GitHub 排程固定晚 4～6 小時、每個工作一天只跑 1～3 次（實測 2026-11），加備援班沒用。每日檢查用 `python3 tools/daily.py brief --wait-prep` 手動觸發 Actions 的 `daily-prep`（SEC 清單、預估快照、叫醒股價與期貨、算健康狀態）並等它做完。
- SEC 收件匣：`tools/sec_inbox.py`（只由 Actions 的 daily-prep 跑）寫 `data/inbox/`（新聞稿文字＋XBRL 核對表）並重算 `data/bs-raw/`；只是「準備」與「核對」，不自動改 `data/<代號>.json`。
- 系統健康：`python3 tools/status.py` → `data/status/latest.json`（只由 Actions 寫，網站「系統健康」頁讀它）；紅燈才開 issue。估值門檻被穿越的訊號：`tools/signals.py` → `data/daily/_signals.json`（只由 Actions 寫）。

## 總經儀表板（macro/）
- 說明在 [`docs/MACRO.md`](docs/MACRO.md)。指標清單、四階段對照表、外部連結在 `data/macro/config.json`（Claude 維護）；`data/macro/latest.json` **只由 GitHub Actions（macro-weekly，`tools/macro_fetch.py`）寫入**，Claude 不手填、不修改。
- 愛榭克（Izaax）的判讀來自書摘、他本人的公開文章、分享會聽眾筆記與讀書筆記（他部落格要登入的文章沒有讀、不引用）：頁面標「整理，不是原話」，不可用引號假裝引述、不可補來源裡沒有的門檻。每一則「他怎麼想」（`concepts`）都要指到 `about.sources` 的出處；本站自己的說明標「教學」。這一頁不判定現在是哪個景氣階段。
- 觀念提醒（`reminders`）成立與否、警訊計數、基期、停更與連結失效，全部只在 `tools/macro_fetch.py` 算（Actions 跑），頁面只畫。方向燈門檻在 `config.json` 的 `light`。長期運作的檢修表在 `docs/MACRO.md`。
- 「AI 資本支出鏈」由 `tools/capex_chain.py` 在建置時用各公司財報加總，不存檔；缺一家就留空標待確認。

## 文件
- `docs/ADDING_A_COMPANY.md` 新增公司流程
- `docs/DATA_SCHEMA.md` 資料格式 v1
- `docs/SCHEDULE_PROMPT.md` 每日排程指令（公司無關，新增公司不用改）。排程本身只是一句「照這份做」，所以改這份就等於改排程，改之前先問使用者
- `docs/schedule/` 每日排程的附件（flash 快報／complete 補完／analysis 公司分析／verify 核對＋論點卡／profile 公司簡介）：SCHEDULE_PROMPT.md 是核心，摘要 ⑪ 列出才讀；步驟細節改附件（2026-11-20 起）
- `docs/WEEKLY_NEWS_PROMPT.md` 每週日 06:00 的大新聞＋token 用量排程（每日檢查不再搜尋新聞）；token 用量紀錄在 `data/token-usage.json`，週報表在 `reports/token-usage.md`（只用 `python3 tools/daily.py tokens ...` 改）
- `docs/TREND_PROMPT.md` 世界科技趨勢月報排程指令（每月 2 日；輸出 reports/trend/）
- `companies/<代號>/SOURCES.md` 各公司來源與更新步驟

## 巴菲特＋蒙格（觀念與指標）
- 觀念清單、四關、三個賣出理由、指標對應都在 [`docs/BUFFETT_MUNGER.md`](docs/BUFFETT_MUNGER.md)，頁面文字與 prompt 以它為準。
- **不可捏造巴菲特或蒙格的原話**：一律意譯，標「意譯，不是原話」與「觀點」；不用引號假裝引述，不寫年份、信件出處、數字典故。只能用清單裡的觀念。
- 檢查表指標只有 `tools/buffett.py` 一個計算處（建置時算，前端只畫）；算不出來寫原因。能力圈與「反過來想」只有提問，不做表單。
- 論點卡：`role`（core／aux）、`warnWhen`／`breakWhen` 兩層、type 含 option；compounder 要通過十年紀錄資格。分析結論五選一，預設不動。

## 公司分析 skill
使用者說「分析 X」「X 財報快評」「趨勢分析」時，用 `.claude/skills/long-term-company-analysis/`。作者觀點檔放在專案資料夾，不進 repo（repo 公開、內容含付費文章轉述）。
