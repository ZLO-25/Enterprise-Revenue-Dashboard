# 新增一家公司的標準流程

使用者說「加入 XXX」時，照這份文件做（或直接用 [`docs/NEW_COMPANY_PROMPT.md`](NEW_COMPANY_PROMPT.md) 的模板）。目標：**只新增設定與資料，不改共用程式**（`assets/`、`tools/build.py`、首頁、通用模板與排程指令都不用動）。

## 1. 先重述需求（給使用者看）

用自己的話說明：要追蹤哪家公司、哪個交易所、幣別、公布頻率（月／季）、有沒有公司專屬指標。有影響做法的疑問一次問清楚，其餘用預設並在最後說明選了什麼。

## 2. 整體流程

```
說「加入 XXX」
      │
      ▼
 ① python3 tools/new_company.py <代號> --name … --ticker … --exchange … --currency …
      │   自動建立：data/<代號>.json（空殼）、companies/<代號>/SOURCES.md（範本）、companies.json 一筆（enabled:false）
      ▼
 ② 補完 SOURCES.md（來源、欄位、核對規則、更新步驟）
      │
      ▼
 ③ 蒐集資料 ──► ④ 填 data/<代號>.json（schema v1，見 docs/DATA_SCHEMA.md）
      │
      ▼
 ⑤ python3 tools/validate.py <代號>   ◄── 沒過就修資料，直到通過
      │
      ▼
 ⑥ companies.json：enabled 改 true、補 primarySource ──► python3 tools/validate.py && python3 tools/build.py
      │
      ▼
 ⑦ 無頭瀏覽器檢查 ──► ⑧ commit / push（Pages 自動部署）──► ⑨ 發佈合併版 Artifact
```

和舊流程的差別：**不用再寫頁面模板、不用再寫核對函式**。資料符合 v1，通用模板 `templates/generic.frag.html` 與通用核對 `v1_generic` 就直接生效；只有公司真的有特殊口徑（例：PLTR 的非 GAAP 對照全年公布值）才需要在 `tools/validate.py` 的 `CHECKS` 多加一個函式。

## 3. 各步驟細節

### ① 腳手架
```
python3 tools/new_company.py nvda --name 輝達 --name-en NVIDIA --ticker NVDA --exchange "Nasdaq NVDA" --currency USD
```
- `code`：小寫英數字，同時是資料檔名、資料夾名與網址路徑（`nvda` → `/nvda/`）。
- 台股：`--currency TWD --exchange "TWSE 2454"`；有月營收的公司加 `--frequency monthly+quarterly`（月營收欄位目前只有台積電舊格式支援，新公司先以季報為主，月營收可放 `extra`）。
- 會計年度不是曆年（例：NVDA 的 FY 到 1 月底）：季度標籤仍用公司自己的會計季度（`4Q26` = FY2026 Q4），並在 SOURCES.md 寫清楚對應的月份。

### ② `companies/<代號>/SOURCES.md`
腳手架已產生範本，照 `companies/pltr/SOURCES.md` 的深度補完：來源（依可信度排序）、欄位定義與單位、第四季推算、核對規則、每週更新步驟、已知缺口。**排程每次都照這份做，所以要寫到沒看過這個專案的人也能執行。**

### ③ 蒐集資料
- 美股優先用 SEC EDGAR XBRL（`https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/<概念>.json`，WebFetch 讀得到）與 8-K 財報新聞稿；台股用公開資訊觀測站與公司 IR。
- 從公司最早能取得的一季開始；取不到的欄位填 `null` 並寫進 `notes.unavailable`。
- 第四季通常要用「全年減前三季累計」推算（EPS 除外），並與公司公布的全年數字核對。

### ④ `data/<代號>.json`
格式見 [`docs/DATA_SCHEMA.md`](DATA_SCHEMA.md)。重點：
- 共用欄位 `quarters[]` 每季都要有 `rev`、`gm`、`om`、`eps`（不能 null）。
- 公司專屬指標放 `extra`（表格＋選擇要畫圖的欄位）、營收拆分放 `segments`，**不要塞進共用欄位**，首頁與比較圖才不會壞。
- `guidance.items[]`、`events[]`（含 `est:1`）、`waterfall`、`milestones[]`、`sources[]` 都要填。

### ⑤ 核對
`python3 tools/validate.py <代號>` 做三層檢查：設定完整 → 共通格式 → v1 通用（自洽、四季＝全年、分部加總、損益拆解加總、財測區間）。**沒過就修資料，不要放寬核對。**

### ⑥ `companies.json`
腳手架已加好一筆；把 `enabled` 改成 `true`，確認 `primarySource: {n, url}`（首頁「資料新鮮度與來源」會顯示）。`enabled:false` 的公司不會建置、也不會被排程更新。然後：
```
python3 tools/validate.py       # 連 companies.json 一起檢查
python3 tools/build.py          # 產生 <path>/index.html、首頁、dist/artifacts/*.html
```

### ⑦ 檢查頁面
用無頭瀏覽器（Playwright）開首頁與新頁面：桌機 1280 寬、手機 390 寬、深色模式；確認沒有 JavaScript 錯誤、沒有水平捲動、沒有 `undefined`／`NaN`。容器對 jsDelivr 多半被擋，Pages 頁面已改用 `assets/vendor/chart.umd.js` 本地副本，本機 `file://` 開啟即可看到圖。

### ⑧ 發佈
commit 並 push 到 `main`，GitHub Pages 會自動重新部署（根目錄、main 分支）。

### ⑨ Artifact
Artifact 是**單一合併版**：`python3 tools/build.py` 會把新公司自動加成 `dist/artifacts/all.html` 的新分頁。用 Artifact 工具先 `read` `companies.json` 的 `site.artifact`，再 publish `dist/artifacts/all.html` 到同一個 `url`。不必為新公司另開 Artifact。

## 4. 想客製頁面時
通用模板不夠用（例：台積電的製程結構、建廠甘特圖）才複製 `templates/generic.frag.html` 為 `templates/<代號>.frag.html` 改寫，並把 `companies.json` 的 `template` 改成該名稱。模板必須保留占位符：`{{THEME}}`、`{{COMMON_JS}}`、`{{LONGTERM_JS}}`、`{{DATA}}`、`{{CHARTJS}}`、`{{HOME}}`。

## 5. 完成後要告訴使用者
網站網址、資料涵蓋期間、**取不到的欄位**、選了哪些預設、下一次排程什麼時候會更新這家公司。
