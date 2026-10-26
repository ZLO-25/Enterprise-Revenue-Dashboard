# 排程任務完整指令（每月 12 日 07:48 台北時間）

> 這份文件就是排程任務的指令全文（排程每次都是新的工作階段，不記得之前的對話）。改排程行為時先改這份，再用 `update_trigger` 把內容同步到排程（排程 prompt ＝ 本檔扣掉這段標題與引言）。
>
> **這份指令刻意不寫任何公司名稱**：公司清單每次從 `companies.json` 讀，各公司怎麼更新寫在 `companies/<代號>/SOURCES.md`。新增公司只要照 `docs/NEW_COMPANY_PROMPT.md` 做完（`enabled:true` ＋ 寫好 SOURCES.md），下次排程就會自動納入，**不需要改排程**。
>
> 為什麼是每月 12 日：台灣上市公司月營收在每月 10 日前公布，12 日留兩天緩衝；美股公司季報約在季末後 3–8 週公布，10-Q 也在 40 天內申報，每月跑一次最多晚約一個月就會補上。

任務：每月更新「企業財報追蹤板」所有啟用中的公司，**只補上次資料之後的新資料**，直接 push 到 GitHub，並同步合併版 Claude Artifact。全程用繁體中文回報。這是排程執行，沒有人在旁邊回答問題：不確定的數字不要填，照下面的「資料誠實規則」標成待確認，在最後的回報裡說明。

## 專案
- GitHub repo：`ZLO-25/Enterprise-Revenue-Dashboard`（main 分支，GitHub Pages 從根目錄發佈）　網站：https://zlo-25.github.io/Enterprise-Revenue-Dashboard/
- 結構：`companies.json`（公司清單，**唯一的公司來源**）、`data/<代號>.json`（資料）、`companies/<代號>/SOURCES.md`（來源、欄位、核對規則、更新步驟）、`templates/`、`assets/`、`tools/build.py`、`tools/validate.py`、`docs/DATA_SCHEMA.md`
- 先讀 repo 根目錄的 `CLAUDE.md`（專案規則，包含資料誠實規則）。
- 如果無法讀寫這個 repo（clone 或 push 被拒絕）：**不要嘗試其他方式繞過**，在回報寫明原因並結束。

## 執行環境提醒
- 容器的 `curl` 對 sec.gov、公司網站多半被擋（403）；**讀網頁請用 WebFetch／WebSearch**。SEC 的 XBRL（`data.sec.gov/api/xbrl/companyconcept/...`）與 `efts.sec.gov` 全文搜尋用 WebFetch 讀得到。WebFetch 單頁約 13 萬字上限，太長的 10-K 改讀 `FilingSummary.xml` → `R#.htm`。
- git 只用 clone／commit／push；push 用 `git push -u origin main`，網路錯誤才重試（2s、4s、8s、16s）。

## 公司清單：每次動態讀取，不要寫死
- 公司清單 ＝ `companies.json` 裡 `enabled:true` 的每一家，**這次讀到幾家就做幾家**（包含上次排程之後才新增的公司）。不要依照記憶、舊回報或這份指令假設有哪些公司。
- 每家公司的更新方法只看它自己的 `companies/<代號>/SOURCES.md`（來源、單位、會計年度、第四季推算、核對規則、更新步驟）。不同公司寫法不同（月營收、季報、會計年度不同），**照各自的 SOURCES.md 做，不要拿別家的做法套用**。
- 某家公司缺 `companies/<代號>/SOURCES.md` 或 `data/<代號>.json`：這家跳過、不改檔案，在回報列出原因，其他公司照常做。

## 步驟
1. 把 repo clone 下來（`git clone https://github.com/ZLO-25/Enterprise-Revenue-Dashboard`），讀 `CLAUDE.md`、`companies.json`。若沒有這個 repo 的存取權，先用 `add_repo` 工具（owner `ZLO-25`，repo `Enterprise-Revenue-Dashboard`，access `push`）附加；仍失敗就回報後結束。
2. **記下每家公司的「上次資料位置」**（動手改之前先記）：從 `data/<代號>.json` 讀出
   - 最新一季（`quarters[]` 最後一筆的季度標籤）
   - 最新一個月（有 `monthly` 的公司：最後一個有數字的月份）
   - `asOf`（上次更新日；事件時間軸只查這天之後的消息）
3. **只抓上次資料位置之後的新資料**：照該公司 SOURCES.md 的「更新步驟」，查有沒有比上次資料位置更新的月份或季度；中間如果漏了不只一期（例如上次排程失敗），**依序全部補齊**。
   - **舊數字不重抓、不重新核對、不修改**。唯一例外是 SOURCES.md 明寫的「暫定值換正式值」類項目（例如 `provisional` 月份換成官網精確值、預估公布日 `est` 換成公司公告日、董事會核准後把 `dps` 從 `null` 改成金額、待確定事件被公司證實或否認），以及它寫的「同步更新最新一季相關欄位」（例如 `guidance`、`waterfall`、`annual`）。
   - 沒有新月份也沒有新季度 → 這家只檢查事件時間軸與下一個公布日。
   - 只改 `data/<代號>.json`；模板、`assets/`、`tools/`、其他公司的檔案一律不動。`asOf` 設成台北時間今天（只有 `asOf` 變動不算實質變動）。
4. **新增的每一個數字都要確認正確**：
   - 一定要真的從主管機關申報文件或公司公告（SOURCES.md 列的一手來源）讀到那個數字，記下來源網址。
   - SOURCES.md 有交叉核對規則的（例如新聞稿對 XBRL、季營收對三個月月營收加總、第四季＝全年減前三季）都要做；兩個來源對不起來就以 SOURCES.md 指定的為準，並在回報寫出差多少。
   - **資料誠實規則**：讀不到、算不出來、來源對不起來的數字填 `null`，在 `notes.unavailable`（沒有這個欄位的舊格式公司就寫進回報）加一行「待確認：<哪一季／月>、<哪個欄位>、<原因>」。只有媒體報導、公司未證實的事件 `unc:1`，`note` 以「待確定：」開頭。**不估計、不內插、不從記憶補數字。**
5. 核對：`python3 tools/validate.py <代號>`。**沒過的公司不發佈**：用 `git checkout -- data/<代號>.json` 還原、保留原值，回報說明哪一項、差多少。不可以為了通過核對去改數字或放寬核對。
6. 判斷實質變動：所有公司都沒有實質變動 → 不 commit、不發佈、不通知，**安靜結束**。
7. 有實質變動：`python3 tools/build.py`（會重產各公司頁面、首頁、`dist/artifacts/`），再 `python3 tools/validate.py` 一次。commit 訊息用繁體中文簡述這次新增的期間（例：「<公司> 加入 <季度> 季報」「<公司> 更新 <月份> 營收」），`git push -u origin main`；GitHub Pages 會自動重新部署。
8. Artifact：只有**一個合併版 Artifact**（總覽＋各公司分頁），網址在 `companies.json` 的 `site.artifact`。任何公司有變動時，用 Artifact 工具 publish：`file_path` 用 `dist/artifacts/all.html`，`url` 用 `site.artifact`。發佈前先用 `action:"read"` 讀該 Artifact（工具要求先讀才能更新）。`label` 寫這次變動。不要建立新的 Artifact；各公司自己的 `artifact` 欄位不用更新。
9. 有變動時用 PushNotification 通知使用者（內容即下面回報的精簡版）。沒有變動就不通知。

## 回報（最後一則訊息，繁體中文，簡短好懂）
- 這次處理了哪些公司（從 `companies.json` 讀到的清單），各自的「上次資料位置 → 這次更新到哪」，例如：
  ```
  公司     上次資料      這次更新到    新增
  ─────   ──────────   ──────────   ─────────────
  XXX     3Q26          4Q26          1 季
  YYY     2026-09 月    2026-10 月    1 個月
  ZZZ     2Q27          2Q27          無新財報
  ```
- 每家公司新增了哪些數字（營收、年增率、利潤率等重點），以及每個新數字的來源
- 事件時間軸的新增或變動，分「已證實」和「待確定」兩組，各附來源
- 所有「待確認」「待確定」項目（哪家、哪一期、哪個欄位、原因）
- 核對沒過、被跳過或沒能更新的公司與原因
- GitHub Pages（push 是否成功）與合併版 Artifact 是否更新成功
- 各公司下一個公布日
- 使用的來源連結
