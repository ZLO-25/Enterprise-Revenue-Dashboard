# 每日排程指令：週二至週六 台北 08:18

> 排程本身只是一句「照 docs/SCHEDULE_PROMPT.md 做」，所以**改這份就等於改排程**（改之前先問 ZL）。這份刻意不寫公司名稱：公司清單從 `companies.json` 讀，各公司怎麼更新寫在 `companies/<代號>/SOURCES.md`，新增公司不用改這份。
> 2026-11-20 起換成「核心＋附件」版（ZL 同意；11/18～11/20 並行測試數字完全相同）：① 一開始只跑 `python3 tools/daily.py brief`（程式在 `tools/daily_brief.py`）拿到全部清單；② 只有今天用得到的步驟才讀 `docs/schedule/` 的附件（flash 快報、complete 補完、analysis 公司分析、verify 核對＋論點卡、profile 公司簡介）。目的是省 token（每多一個步驟，前面的內容就要重讀一次）。資料誠實規則一條都沒有放寬。
> 改規則時：步驟細節改附件，流程與回報格式改這份。舊版全文在 git 歷史（2026-11-20 之前的這個檔）。

```
 git pull → python3 tools/daily.py brief --wait-prep   ← 先叫醒 GitHub 的每日準備；一頁摘要：清單、股價、論點卡燈號、本益比、今天要讀哪些附件
   │
   ├─ 摘要說「安靜日」 → 直接 ⑤ 回報、done（不讀任何附件；大新聞改成每週日 06:00 另一個排程）
   └─ 摘要列出附件     → 只讀列出的那幾份，照做，再 ⑤
```

任務：每天檢查「企業財報追蹤板」所有啟用中的公司，只做今天該做的事。全程繁體中文。這是排程執行，沒有人在旁邊：不確定的數字不填，照資料誠實規則標「待確認」，在回報說明。

## 省 token 的做法（硬規則）
- **互不相干的工具呼叫放在同一回合一起送**（例如多個網頁讀取一次送出；git、腳本串成一行指令）。
- **不要整份讀 `data/<代號>.json`**（每份約 5 萬字）。要哪幾個欄位就用 `python3 -c` 或 `jq` 印那幾個欄位。
- 讀過的檔不重讀；`CLAUDE.md` 已經在系統提示裡就不用再開。
- 沒有到期的公司不讀財報、不開網頁。股價、預估、SEC 申報清單是 GitHub Actions 做的，不要自己重做。

## 測試模式（排程指令裡寫了「測試模式」才適用）
- 照常做完所有步驟，但 **push 到分支 `shadow/<今天日期>`，不 push main、不 publish Artifact、不觸發任何 Actions**。
- 回報第一行寫「【測試模式】」，最後附一行 `git diff --stat main` 的結果。
- 測試模式也**不 fire_trigger**：⑩ 要求加跑或補觸發時，只在回報寫「（測試模式：本來會觸發 …）」。

## 專案
- repo `ZLO-25/Enterprise-Revenue-Dashboard`（main，GitHub Pages）；網站 https://zlo-25.github.io/Enterprise-Revenue-Dashboard/
- `companies.json`（公司清單）、`data/<代號>.json`、`data/calendar.json`（只用 `tools/daily.py` 改）、`data/sec-feed.json`（Actions 寫）、`companies/<代號>/SOURCES.md`、`docs/DATA_SCHEMA.md`
- 無法讀寫 repo（clone 或 push 被拒絕）：不要繞過，回報原因並結束。
- 容器的 `curl` 對 sec.gov 與公司網站多半 403：讀網頁用 WebFetch／WebSearch。WebFetch 單頁約 13 萬字上限：太長的 10-K 改讀 `FilingSummary.xml` → `R#.htm`；**電話會議逐字稿要分段讀**（分兩次問：一次只要「管理層發言與財測」，一次只要「問答段」），兩段都讀到才算補完，讀不到的那段照規則寫待確認。git push 用 `git push -u origin <分支>`，網路錯誤才重試（2s、4s、8s、16s）。

## ⓪ 準備（一回合）
1. clone（沒權限先 `add_repo`：owner `ZLO-25`、repo `Enterprise-Revenue-Dashboard`、access `push`）。
2. `python3 tools/daily.py brief --wait-prep`（**Bash 的 timeout 設 300000**，它最多會等 4 分鐘）。GitHub 排程固定晚 4～6 小時，所以不等排程：這一步會手動觸發 Actions 的 `daily-prep`（SEC 清單、預估快照、股價、期貨、系統健康狀態），等它做完（最多 4 分鐘）再 pull。輸出第一行是結果；「✗」開頭 → 回報 ⑤ 寫一行（資料可能是舊的），其餘照做。若第一行說 gh 不可用且你有 GitHub 工具，用 `mcp__github__actions_run_trigger` 觸發 `daily-prep.yml`（ref main）一次就好，不用等。（測試模式 `--today` 不會觸發也不會等。）**它印的就是今天的工作範圍**，各段意思：
   ① 到期要快報 ② 進行中（補完／核對） ④ 未來 7 天 ⑤ 卡住 ⑥ 日期待辦（照每項的「做法」做） ⑦ 股價 ⑧ 論點卡轉差（體質／估值分兩行；估值紅燈是股價變貴，不置頂） ⑨ 本益比 ⑩ 補跑與優先順序（有缺跑或積壓才出現） ⑪ 要讀哪些附件（含「分析待寫」→ docs/schedule/analysis.md：財報補完後跑公司分析 skill，結論放個股頁標題下方）。
   - 「缺跑」有日期 → 回報寫明補了哪幾天（到期判斷會自動包含）。
   - ⑦ 股價有 ✗ → 手動觸發 prices-monthly 一次（`mcp__github__actions_run_trigger`），回報說明；仍然不可自己填股價。
3. 只讀 ⑪ 列出的附件，照附件做（附件是舊版同一節的原文，拆出來而已）。

## 補跑（額度用完、排程缺跑或中途失敗之後）
摘要 ⑩ 有內容時照它做。設計原則：**狀態存在 repo 裡，不存在 Claude 的記憶裡**，所以任何一次成功的執行都能接著做。
```
 缺跑幾天 ──► ⑩ 列出每個缺跑日（一天一行，沒事寫「無事」）
            ──► 依優先順序：快報 → 補完 → 核對 → 日期待辦 → 公司分析（同類最早到期先做）
            ──► 每類有上限（快報 2、補完 2、核對 3），超過的「留到下一次」
            ──► 每家做完：validate → commit → push → daily.py set（做一家存一家）
            ──► 還有積壓：今天加跑一次（fire_trigger，每天最多一次），其餘明天
```
- **做一家存一家**：每家公司 validate 通過就立刻 commit＋push＋`daily.py set`，不要等全部做完。中途額度用完時，做完的不會遺失，下一次也不會重做。
- **不重複寫**：開始快報前先檢查 `data/<代號>.json` 最後一季是不是已經是目標季度（上一次可能已 push 資料、還沒 set 狀態）。已經有而且 validate 通過 → 只補 `daily.py set`，不重寫。
- **新聞**：每日檢查不搜尋新聞（2026-11-18 起）；每週日 06:00 由另一個排程（docs/WEEKLY_NEWS_PROMPT.md）做。
- **缺跑日的回報**：② 段照抄 ⑩ 的每日一行，不為每一天各寫一份回報。
- **加跑與補觸發**：⑩ 說要 fire_trigger 時才做，做完立刻 `python3 tools/daily.py mark extra`（或 `mark trend`）並 push `data/calendar.json`，避免重複觸發。
- **股價、市場預期快照、SEC 清單、市值、期貨**都是 GitHub Actions 做的，額度用完也照常跑，不需要補；市場預期**不回補**的規則不變。

## ⑥ 日期待辦（摘要 ⑥ 有列出才做）
要等某個日期或外部事件的事（例：Anthropic 上市、12 月初第一次預估本益比快照）都放在 `data/watchlist.json`，不寫死在這份指令。
- 摘要只列出「`from` ≤ 今天、還沒 done」的項目，並附上不開網頁就知道的狀態。照每一項的「做法」（`how`）做；做完 `python3 tools/daily.py watch-done <id> --note "結果"`，和其他變動一起 commit。
- 回報：有變化的寫進「① 今天到了什麼」；還在等的放「⑤ 未完成」一行帶過；超過 `until` 還沒結果的置頂。
- 新的日期待辦直接在 `data/watchlist.json` 加一項（`id`、`from`、`until`、`what`、`how`），不用改這份指令。

## ④ 大新聞（已移到每週日排程）
每日檢查**不再**搜尋大新聞。公司公告若在處理快報、補完、核對時順便看到達標的事件（財測、併購、人事、監管），照舊寫進 `milestones[]`（已證實／待確定規則同 docs/WEEKLY_NEWS_PROMPT.md），其餘等週日。**類別先對核心故事線**：寫入前看該公司頂層 `story`（`python3 tools/daily.py story` 一次列出全部公司的故事線與類別）。事件是在推進那條線（新世代量產、關鍵客戶或合約、監管核准、主要產能、故事線的挫折）→ `cat` 用 `story.cats` 裡的類別，頁面會自動標「核心」；不是 → 用一般類別。不可為了湊「核心」硬歸類；拿不準就用一般類別，並在回報寫一句。

## ⑤ 驗證、發佈、通知
1. 有實質變動（新季度／月份資料、新事件、新的股價月份）：`python3 tools/build.py && python3 tools/validate.py`。只有 `asOf` 變動不算；`asOf` 只在該公司資料真的更新或確認過時才改。
2. push 前看 prices-monthly 是否 `in_progress`（`mcp__github__actions_list`）；是的話等它結束再 push。
3. commit（繁中，例「NVDA 3Q27 快報」）→ push main。
4. Artifact：有變動時 publish `dist/artifacts/all.html` 到 `companies.json` 的 `site.artifact`（先 `action:"read"` 再 publish），`label` 寫這次變動。
5. `python3 tools/daily.py done && python3 tools/daily.py save-lights`，commit＋push `data/calendar.json`、`data/brief-lights.json`（可和上一步同一個 commit）。某家失敗也要 `done`（失敗由 `try` 計數接手）；整個排程沒跑完才不 `done`。
6. **記 token**（最後一步，不要省）：`python3 tools/daily.py tokens auto daily`（自動讀本工作階段紀錄檔，含子代理，並重寫 reports/token-usage.md；不用 get_session，那個欄位不存在），commit＋push `data/token-usage.json`、`reports/token-usage.md`（和第 5 步同一個 commit）。測試模式的排程名寫 `daily-shadow`。指令失敗就在回報寫一行原因，不要手填數字。
7. PushNotification：沒事的日子一行；有快報或紅燈時標題寫公司與重點。

## 每日回報（最後一則訊息；固定五段，沒事的日子只有三四行）
```
【MM/DD 每日更新】
① 今天到了什麼    哪些公司公布財報、月營收、新申報；沒有就寫「無」
② 今天做了什麼    快報／補完／核對／重試第幾次；缺跑補了哪幾天；網站有沒有重新發佈（commit 連結）
③ 大新聞          只有處理財報時順便看到的；平常寫「每週日 06:00 統一整理」
④ 接下來 7 天     照摘要 ④；日期有變動特別標出
⑤ 未完成          stuck（置頂）、摘要 ⑧「論點卡體質」轉差的項目（置頂，只看核心；論點卡段落分體質核心／輔助／估值三組；估值與輔助轉差、紅燈只放附錄，估值訊號不在這裡展開）、待確認項目、重試中（第幾次）。黃燈只是先觀察，不是賣出理由
```
附錄：論點卡估值與輔助（摘要 ⑧ 的「論點卡估值與輔助」「估值與輔助紅燈」兩行照抄；估值訊號不在每日回報展開）、摘要 ⑨ 的本益比／預估本益比照抄、`rd` 缺的（待確認）、用到的來源連結、核對沒過或跳過的公司與原因、Pages／Artifact 是否更新成功。

## 一次性的例外
- stuck 的公司：使用者說「繼續 <代號>」才 `python3 tools/daily.py set <代號> waiting`。
- 手動觸發排程（`fire_trigger`）等於多跑一天，判斷不受影響。

回報最後固定一行：「今天沒有需要動作的事」（預設）；只有結構性變化（`breakWhen` 成立、類型資格掉了）才改寫成建議。分析結論用新 skill 的五選一，預設不動（觀念見 docs/BUFFETT_MUNGER.md）。
