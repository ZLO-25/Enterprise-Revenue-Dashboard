# 排程任務完整指令（每週一 08:00 台北時間）

> 這份文件就是排程任務的指令全文（排程每次都是新的工作階段，不記得之前的對話）。改排程行為時先改這份，再用 `update_trigger` 把內容同步到排程。

任務：每週更新「企業財報追蹤板」所有啟用中的公司，直接 push 到 GitHub，並同步各公司的 Claude Artifact。全程用繁體中文回報。這是排程執行，沒有人在旁邊回答問題：遇到不確定的數字就保留原值，在最後的回報裡說明。

## 專案
- GitHub repo：`ZLO-25/Enterprise-Revenue-Dashboard`（main 分支，GitHub Pages 從根目錄發佈）　網站：https://zlo-25.github.io/Enterprise-Revenue-Dashboard/
- 結構：`companies.json`（公司清單）、`data/<代號>.json`（資料）、`companies/<代號>/SOURCES.md`（來源、欄位、核對規則、更新步驟）、`templates/`、`assets/`、`tools/build.py`、`tools/validate.py`、`docs/ADDING_A_COMPANY.md`
- 如果無法讀寫這個 repo（clone 或 push 被拒絕）：**不要嘗試其他方式繞過**，在回報寫明原因並結束。

## 執行環境提醒
- 容器的 `curl` 對 sec.gov、公司網站多半被擋（403）；**讀網頁請用 WebFetch／WebSearch**。SEC 的 XBRL（`data.sec.gov/api/xbrl/companyconcept/...`）與 `efts.sec.gov` 全文搜尋用 WebFetch 讀得到。
- git 只用 clone／commit／push；push 用 `git push -u origin main`，網路錯誤才重試（2s、4s、8s、16s）。

## 步驟
1. 先把 repo clone 下來（`git clone https://github.com/ZLO-25/Enterprise-Revenue-Dashboard`），讀 `companies.json`。若沒有這個 repo 的存取權，先用 `add_repo` 工具（owner `ZLO-25`，repo `Enterprise-Revenue-Dashboard`，access `push`）附加；仍失敗就回報後結束。
2. 對每個 `enabled:true` 的公司，**照 `companies/<代號>/SOURCES.md` 的「更新步驟」逐項做**，只改 `data/<代號>.json`；模板、`assets/`、`tools/` 一律不動。`asOf` 設成台北時間今天（只有 `asOf` 變動不算實質變動）。
3. 核對：`python3 tools/validate.py <代號>`。**沒過的公司不發佈**：用 `git checkout -- data/<代號>.json` 還原、保留原值，回報說明哪一項、差多少。
4. 判斷實質變動：所有公司都沒有實質變動 → 不 commit、不發佈、不通知，**安靜結束**。
5. 有實質變動：`python3 tools/build.py`（會重產各公司頁面、首頁、`dist/artifacts/`），再 `python3 tools/validate.py` 一次。commit 訊息用繁體中文簡述（例：「PLTR 加入 3Q26 季報」「台積電更新 10 月營收」），`git push -u origin main`；GitHub Pages 會自動重新部署。
6. Artifact：對有變動的公司，用 Artifact 工具 publish：`file_path` 用 `dist/artifacts/<代號>.html`，`url` 用 `companies.json` 該公司的 `artifact`（台積電 https://claude.ai/artifact/CY6SJ1sY6vZa2nrhpQg7Gn）。若該公司 `artifact` 為 `null`：第一次發佈不帶 `url`（帶 `icon`，例如 chart），把回傳網址寫進 `companies.json` 的 `artifact` 欄位並再 commit／push 一次。`label` 寫這次變動（例：「加入 3Q26 季報」）。發佈前先用 `action:"read"` 讀該 Artifact（工具要求先讀才能更新）。不要建立重複的新 Artifact。
7. 有變動時用 PushNotification 通知使用者（內容即下面回報的精簡版）。沒有變動就不通知。

## 回報（最後一則訊息，繁體中文，簡短好懂）
- 每家公司這次新增或修正了哪些數字（例：台積電 10 月營收 X 億、年增 Y%；PLTR 3Q26 營收 X、調整後營益率 Y%）
- 用小 ASCII 表格列出各公司最新數字
- 事件時間軸的新增或變動，分「已證實」和「待確定」兩組，各附來源
- GitHub Pages（push 是否成功）與各 Artifact 是否更新成功
- 核對沒過、沒能更新或不確定的項目與原因
- 各公司下一個公布日
- 使用的來源連結
