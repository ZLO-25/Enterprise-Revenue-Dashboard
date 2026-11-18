# 每日排程附件：快報（到期的公司）

> 每日排程的附件（由 docs/schedule/core.md 指示才讀）。內容與舊版 docs/SCHEDULE_PROMPT.md 同一節一字不改，只是拆出來，安靜日不用讀。

### ① 快報（到期的公司）
清單 ① 列出的公司才做。照該公司 `SOURCES.md` 的「更新步驟」，**只抓最新一期**：
- 公布日（`events` 裡早於今天的項目）已過 → 讀財報新聞稿（8-K 附件 99.1／公司公告），寫入新的一季（或月營收），填 `rd`／`rdB`、更新 `guidance`（**財測保留歷史**，見 DATA_SCHEMA）、`waterfall`、`annual`、`events`（處理完的公布日從 `events` 移除，加入下一個公布日）。
- 預估日（`est`）已過但公司還沒公告：**不算失敗**。美股看 `sec-feed.json`；其他公司搜尋一次是否已公告新日期，更新 `events`；仍沒有就下一天再查。
- 快報只收書面來源（新聞稿、申報文件）。電話會議留給「補完」。
- **資產負債表 8 欄位**（shOut、dilSh、cash、debt、buyback、equity、pretax、tax）：新的一季每個 key 都要有（validate 會擋缺 key）。美股：手動觸發 GitHub Actions 的 `bs-fetch`（mode `build`，等它跑完會 commit `data/bs-raw/`），再 `python3 tools/bs_merge.py <代號>`（只在該季的值讀得到時才會有值）；新一季若 SEC 資料還沒進來，值為 null，merge 會自動寫「待確認」，10-Q 出來後在「③ 核對」重跑。非美股（台積電、台達電、三星）：從財報 PDF／簡報手動讀，口徑照該公司 SOURCES.md「資產負債表欄位」一節；讀不到填 null 並寫待確認，不估計。
- **股票酬勞 `sbc`（第 9 欄位）**：新的一季要補。來源是 10-Q／10-K 現金流量表的 `ShareBasedCompensation`（年初累計，相減成單季；第四季＝全年 − 前九個月）。美股：`bs-fetch`（mode `build`、field `sbc`，只重抓這一欄，其他欄位的提案不動）跑完後 `python3 tools/bs_merge.py --only sbc <代號>`（只寫 sbc，不會動其他 8 欄位）。10-Q 還沒申報時值為 null，merge 自動寫「待確認」，10-Q 出來後重跑。非 SEC 公司（台積電、三星、台達電、ASML、萬潤）維持 null，來源是年報、尚未讀取，不估計。
- 財測有新的：先把舊的整份 `guidance` append 進 `guidanceHistory`，再寫新的（DATA_SCHEMA「guidanceHistory」）。
- 寫 `summary`（`status:"flash"`、`flashDate` ＝ 今天）：`headline`、`scorecard`（市場預期從 `data/consensus/<代號>.json` 最後一張 ≤ 公布日的快照抄；沒有快照就不放 `cons`，不要補）、`outlook`（只寫書面財測的變化）；`mgmt`、`qa` 先空著，`pending` 寫「電話會議重點待補完」。上一季的 `summary` 先精簡進 `summaryHistory`。
- 做完：`python3 tools/validate.py <代號>` → 過了才算成功：`python3 tools/daily.py set <代號> flash --target <季度>`。沒過／來源讀不到：`git checkout -- data/<代號>.json`，`python3 tools/daily.py try <代號> --note "原因"`。
- 公司頁的季度總結（階段 2 完成後）標「初版」；快報先寫「成績單」「展望變化」兩格，其餘寫「待補完」。

### 本益比、股價與財報公布日（每次寫入新一季時都要做）
- **新增每一季時同時填 `rd` 與 `rdB`**（那一季 EPS 第一次公開的日期）：美股優先用 8-K Item 2.02 新聞稿日（`rdB:"p"`），讀不到才用該季 10-Q／10-K 申報日（`rdB:"f"`）；台積電用財報新聞稿（Earnings Release）開頭的日期（`rdB:"p"`）；台達電用公司公告或法說會日（`rdB:"c"`），讀不到時手動觸發 `rd-twse` 工作流程（證交所 BWIBBU 財報換季日，`rdB:"t"`，偏保守）再用 `python3 tools/rd_import.py <代號>` 匯入；三星用正式財報法說會日（`rdB:"c"`）。讀不到填 `null`，並在 `notes.unavailable` 加「待確認：<季度> 的財報公布日（rd）：原因」，**不可以用季度結束後幾天推算**；最新一季的 `rd` 不可為 null。預估公布日（`est`）換成公司公告日時，確認 `rd` 一致。
- **股價不是你寫的**：`data/prices/<代號>.json` 由 GitHub Actions（prices-monthly，每月 1～6 日）寫入。先 `git pull` 取得最新；檢查每家公司的股價檔最後一個月是不是上個月。沒進來 → 用 GitHub 工具手動觸發 prices-monthly 一次（`mcp__github__actions_run_trigger`），並在回報說明；仍然不可以自己填股價、不可以估計。
- **股票分割**：EPS 重編（SOURCES.md 步驟）與股價檔重抓必須在同一次完成：重編 EPS 後觸發 prices-monthly 並在 `accept` 填該公司代號；否則 validate 會因本益比相鄰月份跳動超過 3 倍而失敗。
- **預估本益比**：由 Actions 每月存當月快照，**不補、不回填、不用今天的預估填過去的月份**；回報列各公司最新預估本益比，缺的列待確認。
- 本益比與預估本益比都不存檔、不手填（`tools/pe.py` 建置時算出）。
