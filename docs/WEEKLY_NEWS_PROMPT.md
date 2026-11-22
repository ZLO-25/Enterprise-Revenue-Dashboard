# 每週大新聞＋token 用量紀錄（排程：每週日 台北 06:00）

> 這份就是排程的指令全文。排程本身只是一句「照 docs/WEEKLY_NEWS_PROMPT.md 做」，所以改這份＝改排程，不用重建排程。
> 2026-11-18 起：**每日檢查不再搜尋大新聞**（省 token），改成每週日把過去一週的新聞一次看完。排程 ID：`trig_01RyLx6r8GG3Zj8MJuboqA8L`。
> 模型：ZL 要求 Sonnet 5.5 medium，但排程工具不能指定單一排程的模型，排程跟著專案預設模型。所以搜尋這一步**一律交給 Sonnet 子代理**（見步驟 3），主流程只做讀寫與回報。

```
 每週日 06:00
   │
   ├─ ① 取得 repo，python3 tools/daily.py brief 只看「③ 新聞範圍」（過去一週或上次新聞日至今）
   ├─ ② Sonnet 子代理：24 家公司各一次標題層級搜尋，只回傳「達標」的候選（附來源、日期）
   ├─ ③ 主流程：公司公告／申報證實 → 已證實；只有媒體 → 待確定；寫進 milestones[]
   ├─ ④ validate → build → commit → push → 更新 Artifact（有寫入才做）
   ├─ ④b 總經一週摘要：python3 tools/daily.py macro（只讀檔，不搜尋、不花子代理）→ 照抄進回報
   └─ ⑤ 記 token：tokens fill → 補上週各排程的實際結算 → tokens auto weekly-news → push，然後回報
```

## 步驟
1. 取得 repo（`add_repo` owner `ZLO-25`、repo `Enterprise-Revenue-Dashboard`、access `push`），clone 一次、`register_repo_root`。先讀 `CLAUDE.md`（資料誠實規則）。
2. `python3 tools/daily.py brief --wait-prep` 不用跑（週日不是檢查日）；若今天是週日且要順便刷新資料，用 `mcp__github__actions_run_trigger` 觸發 `daily-prep.yml` 一次，不必等。接著 `python3 tools/daily.py news-scope`：印出新聞範圍（從上次「每週新聞」日期到今天，最長 14 天；沒有紀錄就是過去 7 天）與 24 家公司代號、名稱、現有 `milestones` 最後一筆日期（避免重複寫），以及核心故事線與類別。
3. **用一個 Sonnet 子代理做搜尋**（Agent，`model: "sonnet"`，同一回合送出所有搜尋，不要一家一個子代理）。給它範圍、公司清單與下面「達標標準」，要求只回傳達標候選：公司、日期、一句話、來源名稱與網址、是公司公告還是媒體。不要叫它判斷投資意義。
4. 達標標準（和舊每日 ④ 相同）：財測或營運變化（預告財報、上下修財測、重大訂單或合約）、資本動作（併購、分割、大額回購、增資、股利變動）、人事（執行長、財務長異動）、監管與法律（出口管制、反壟斷、重大訴訟、調查）、產業事件（主要客戶或對手財報出現與本公司直接相關的訊息）。股價漲跌本身不算。
5. 主流程對每個候選：能開到公司公告或申報文件就標「已證實」（附連結）；只有媒體報導 → 「待確定」，寫媒體名稱，`unc:1`，`note` 以「待確定：」開頭。寫進該公司 `data/<代號>.json` 的 `milestones[]`（格式 `{d, cat, t, src, st:"p", unc?, note?}`，見 docs/DATA_SCHEMA.md 的 milestones[]；`src` 必填）；沒達標的不寫。**類別先對核心故事線**：寫入前看該公司頂層 `story`（`python3 tools/daily.py story` 一次列出全部公司的故事線與類別）。事件是在推進那條線（新世代量產、關鍵客戶或合約、監管核准、主要產能、故事線的挫折）→ `cat` 用 `story.cats` 裡的類別，頁面會自動標「核心」；不是 → 用一般類別。不可為了湊「核心」硬歸類；拿不準就用一般類別，並在回報寫一句。回報裡把歸到核心故事線的事件標「核心」。候選是併購、出售或分拆業務、新增或裁撤部門 → 回報加一行「<公司> 的公司簡介可能需要更新（原因）」，不自己改簡介。
6. 有寫入：`python3 tools/build.py && python3 tools/validate.py`（沒過的公司還原，不發佈）→ commit「每週新聞 <日期>」→ push main → publish `dist/artifacts/all.html` 到 `companies.json` 的 `site.artifact`（先 `action:"read"`）。沒有寫入就跳過這一步。
6b. **每月第一個週日才做：待確認清理**（今天的日期是當月 1～7 日才做；其他週日跳過這一步）。`python3 tools/daily.py pending` 看「近期」清單（reports/pending.md），挑**最多 6 項**，每項用一個 Sonnet 子代理去讀一手來源（申報文件或公司公告，**必須真的讀到那個數字**）。讀到 → 更新 `data/<代號>.json` 並刪掉那一行待確認；讀不到 → 原樣保留，不估計、不內插。做完 `python3 tools/validate.py` 必須通過，沒過就 `git checkout -- data/<代號>.json` 還原那家，不發佈。回報列出每一項的結果與來源連結（解掉的、仍待確認的各幾項）。資料誠實規則一條都不放寬。
6c. **總經一週摘要**（2026-11-22 起，ZL 同意）：`python3 tools/daily.py macro`。它只讀 `data/macro/latest.json` 和 git 歷史裡一週前的那一版，印出：資料新不新與健康狀態、這一週換燈的指標、觀念提醒的新出現／消失／持續、警訊計數、台灣燈號。**不搜尋、不開子代理、不改任何檔案**。規矩：
   - 輸出照抄進回報的「總經」段（可以刪掉「＝持續」的提醒只留條數，其他不改字）。**不加自己的解讀、不寫買賣建議、不判定現在是哪個景氣階段**；愛榭克的觀念只能用頁面上已有的整理，不可寫成他的原話。
   - 輸出寫「拿不到一週前的版本」：多半是淺層 clone，先 `git fetch --depth=600 origin main`（或 `--unshallow`）再跑一次；還是拿不到就照現況回報並寫一句。
   - 輸出寫「待確認：總經資料已 N 天沒更新」：用 `mcp__github__actions_run_trigger` 觸發 `macro-weekly.yml` 一次（inputs `force: true`），不必等，回報照寫待確認。
   - 有「停更？」「抓不到」「連結失效」：原樣列進回報，不自己改 `data/macro/config.json`（檢修表在 docs/MACRO.md，等 ZL 說要修再修）。
7. `python3 tools/daily.py mark news`（記錄本週新聞已跑），和下一步一起 commit。
8. **記 token**（最後一步，不要省）：
   - 先補實際結算：`python3 tools/daily.py tokens fill` 會列出還是「估計」的排程紀錄（最多 7 筆）。對每一筆呼叫 `list_events(session_id=<id>, kinds=["result"], limit=100)`，取**時間最早的那筆** result（排程本身那一回合；之後若有人工對話不要算進去），把各模型 modelUsage 的 inputTokens、cacheReadInputTokens、cacheCreationInputTokens、outputTokens 相加，連同 total_cost_usd、num_turns 寫回：
     `python3 tools/daily.py tokens exact <id> --cost <total_cost_usd> --input N --cache-read N --cache-write N --output N --turns <num_turns>`
     讀不到（has_more 要往前翻才找到就翻一次，仍沒有就跳過）維持估計值，回報寫一行。
   - 再記本次：`python3 tools/daily.py tokens auto weekly-news`（自動讀本工作階段紀錄檔，含子代理，並重寫 reports/token-usage.md；不用 get_session，那個欄位不存在）。
   - commit「token 用量 <日期>」並 push main（和步驟 7 同一個 commit 也可以）。
9. 回報（繁體中文，10～16 行）：

```
【MM/DD 每週新聞】範圍 MM/DD～MM/DD
已證實：公司｜日期｜一句話｜來源
待確定：公司｜日期｜一句話｜媒體
簡介可能需要更新：…（沒有就不寫）
總經（公式判斷，不是買賣建議）：照步驟 6c 的輸出，依序寫 資料與健康｜換燈（轉差在前，★＝核心）｜提醒新出現與消失｜警訊計數｜台灣燈號；沒有變化就寫「本週沒有換燈、提醒沒有變」一行
本週估值訊號：讀 data/daily/_signals.json 最近 7 天的 events（比門檻貴／便宜 15% 以上、回到附近），每則一行；沒有就寫「本週沒有」。提醒，不是買賣建議
上週 token：照 reports/token-usage.md 最近一週那張表的合計與每個排程的平均
本次新聞排程用量：總 xx、約 $xx（不含子代理）
```

## 晚跑或補跑
- 排程當天沒跑成（額度用完等）：每日檢查的 `daily.py brief` 會在「⑩」寫「每週新聞已 N 天沒跑」，超過 9 天就用 `fire_trigger`（`trig_01RyLx6r8GG3Zj8MJuboqA8L`）補觸發一次，並 `python3 tools/daily.py mark newsfire` 避免當天重複。晚跑時範圍自動從上次新聞日起算（最長 14 天）。
- 本週已經有新聞紀錄（`daily.py news-scope` 說今天已跑過）→ 回報「本週已完成」後結束，不重搜。
