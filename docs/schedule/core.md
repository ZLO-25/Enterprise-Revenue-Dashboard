# 每日排程（核心版）：週二至週六 台北 08:18

> 這是每日排程的指令。和舊版 docs/SCHEDULE_PROMPT.md 的規則**完全相同**，只差在：
> ① 一開始只跑一個指令 `python3 tools/daily.py brief`（程式在 `tools/daily_brief.py`） 拿到全部清單；② 只有今天用得到的步驟才去讀 `docs/schedule/` 的附件。
> 目的：省 token（每多一個步驟，前面的內容就要重讀一次）。資料誠實規則一條都沒有放寬。

```
 git pull → python3 tools/daily.py brief   ← 一頁摘要：清單、股價、論點卡燈號、本益比、今天要讀哪些附件
   │
   ├─ 摘要說「安靜日」 → 只做 ④ 大新聞 → ⑤ 回報、done（不讀任何附件）
   └─ 摘要列出附件     → 只讀列出的那幾份，照做，再 ④ ⑤
```

任務：每天檢查「企業財報追蹤板」所有啟用中的公司，只做今天該做的事。全程繁體中文。這是排程執行，沒有人在旁邊：不確定的數字不填，照資料誠實規則標「待確認」，在回報說明。

## 省 token 的做法（硬規則）
- **互不相干的工具呼叫放在同一回合一起送**（例如所有新聞搜尋一次送出；git、腳本串成一行指令）。
- **不要整份讀 `data/<代號>.json`**（每份約 5 萬字）。要哪幾個欄位就用 `python3 -c` 或 `jq` 印那幾個欄位。
- 讀過的檔不重讀；`CLAUDE.md` 已經在系統提示裡就不用再開。
- 沒有到期的公司不讀財報、不開網頁。股價、預估、SEC 申報清單是 GitHub Actions 做的，不要自己重做。

## 測試模式（排程指令裡寫了「測試模式」才適用）
- 照常做完所有步驟，但 **push 到分支 `shadow/<今天日期>`，不 push main、不 publish Artifact、不觸發任何 Actions**。
- 回報第一行寫「【測試模式】」，最後附一行 `git diff --stat main` 的結果。

## 專案
- repo `ZLO-25/Enterprise-Revenue-Dashboard`（main，GitHub Pages）；網站 https://zlo-25.github.io/Enterprise-Revenue-Dashboard/
- `companies.json`（公司清單）、`data/<代號>.json`、`data/calendar.json`（只用 `tools/daily.py` 改）、`data/sec-feed.json`（Actions 寫）、`companies/<代號>/SOURCES.md`、`docs/DATA_SCHEMA.md`
- 無法讀寫 repo（clone 或 push 被拒絕）：不要繞過，回報原因並結束。
- 容器的 `curl` 對 sec.gov 與公司網站多半 403：讀網頁用 WebFetch／WebSearch。git push 用 `git push -u origin <分支>`，網路錯誤才重試（2s、4s、8s、16s）。

## ⓪ 準備（一回合）
1. clone（沒權限先 `add_repo`：owner `ZLO-25`、repo `Enterprise-Revenue-Dashboard`、access `push`）。
2. `python3 tools/daily.py brief`。**它印的就是今天的工作範圍**，各段意思：
   ① 到期要快報 ② 進行中（補完／核對） ④ 未來 7 天 ⑤ 卡住 ⑥ 日期待辦（照每項的「做法」做） ⑦ 股價 ⑧ 論點卡轉差 ⑨ 本益比 ⑩ 要讀哪些附件（含「分析待寫」→ docs/schedule/analysis.md：財報補完後跑公司分析 skill，結論放個股頁標題下方）。
   - 「缺跑」有日期 → 回報寫明補了哪幾天（到期判斷會自動包含）。
   - ⑦ 股價有 ✗ → 手動觸發 prices-monthly 一次（`mcp__github__actions_run_trigger`），回報說明；仍然不可自己填股價。
3. 只讀 ⑩ 列出的附件，照附件做。附件就是舊版指令的原文，一字不改（analysis.md 是 2026-11-17 新增，舊版同一節為「②b 公司分析」）。

## ④ 大新聞檢查（每天，每家公司一次標題層級搜尋）
- 範圍：摘要第一段的「新聞檢查範圍」。**所有公司的搜尋在同一回合一起送出**。
- 只有達標才深入讀：財測或營運變化（預告財報、上下修財測、重大訂單）、資本動作（併購、分割、大額回購、增資、股利變動）、人事（執行長、財務長異動）、監管與法律（出口管制、反壟斷、重大訴訟、調查）、產業事件（主要客戶或對手的財報出現與本公司直接相關的訊息）。
- 公司公告或申報文件證實 →「已證實」；只有媒體報導 →「待確定」並寫媒體名稱（`unc:1`，`note` 以「待確定：」開頭）。股價漲跌本身不算新聞。
- 達標的新聞寫進該公司 `milestones[]`；沒達標的不寫、不列。
- 達標的是併購、出售或分拆業務、新增或裁撤部門 → 回報 ⑤ 加一行「<公司> 的公司簡介可能需要更新（原因）」，不自己改簡介。

## ⑤ 驗證、發佈、通知
1. 有實質變動（新季度／月份資料、新事件、新的股價月份）：`python3 tools/build.py && python3 tools/validate.py`。只有 `asOf` 變動不算；`asOf` 只在該公司資料真的更新或確認過時才改。
2. push 前看 prices-monthly 是否 `in_progress`（`mcp__github__actions_list`）；是的話等它結束再 push。
3. commit（繁中，例「NVDA 3Q27 快報」）→ push main。
4. Artifact：有變動時 publish `dist/artifacts/all.html` 到 `companies.json` 的 `site.artifact`（先 `action:"read"` 再 publish），`label` 寫這次變動。
5. `python3 tools/daily.py done && python3 tools/daily.py save-lights`，commit＋push `data/calendar.json`、`data/brief-lights.json`（可和上一步同一個 commit）。某家失敗也要 `done`（失敗由 `try` 計數接手）；整個排程沒跑完才不 `done`。
6. PushNotification：沒事的日子一行；有快報或紅燈時標題寫公司與重點。

## 每日回報（最後一則訊息；固定五段，沒事的日子只有三四行）
```
【MM/DD 每日更新】
① 今天到了什麼    哪些公司公布財報、月營收、新申報；沒有就寫「無」
② 今天做了什麼    快報／補完／核對／重試第幾次；缺跑補了哪幾天；網站有沒有重新發佈（commit 連結）
③ 大新聞          分「已證實」「待確定」，各附來源
④ 接下來 7 天     照摘要 ④；日期有變動特別標出
⑤ 未完成          stuck（置頂）、摘要 ⑧ 轉差的論點卡（置頂）、待確認項目、重試中（第幾次）
```
附錄：摘要 ⑨ 的本益比／預估本益比照抄、`rd` 缺的（待確認）、用到的來源連結、核對沒過或跳過的公司與原因、Pages／Artifact 是否更新成功。

## 一次性的例外
- stuck 的公司：使用者說「繼續 <代號>」才 `python3 tools/daily.py set <代號> waiting`。
- 手動觸發排程（`fire_trigger`）等於多跑一天，判斷不受影響。
