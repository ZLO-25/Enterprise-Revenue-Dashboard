# 新增一家公司的標準流程

使用者說「加入 XXX」時，照這份文件做。目標：**只新增設定與資料，不改共用程式**（`assets/`、`tools/build.py`、首頁與排程指令都不用動）。

## 1. 先重述需求（給使用者看）

用自己的話說明：要追蹤哪家公司、哪個交易所、幣別、公布頻率（月／季）、有沒有公司專屬指標。有影響做法的疑問一次問清楚，其餘用預設並在最後說明選了什麼。

## 2. 整體流程

```
說「加入 XXX」
      │
      ▼
 ① 定代號與資料頻率 ──► ② 寫 companies/<代號>/SOURCES.md（來源、欄位、核對規則）
      │                                  │
      ▼                                  ▼
 ③ 蒐集資料 ──► ④ 寫 data/<代號>.json ──► ⑤ 在 tools/validate.py 加核對函式
                                         │
      ┌──────────────────────────────────┘
      ▼
 ⑥ 做頁面模板 templates/<代號>.frag.html（複製 pltr 當起點）
      │
      ▼
 ⑦ companies.json 加一筆 ──► ⑧ python3 tools/validate.py && python3 tools/build.py
      │
      ▼
 ⑨ 無頭瀏覽器檢查 ──► ⑩ commit / push（Pages 自動部署）──► ⑪ 發佈 Artifact、把網址寫回 companies.json
```

## 3. 各步驟細節

### ① 代號與頻率
- `code`：小寫英文代號，同時是資料檔名、資料夾名與網址路徑（例：`nvda` → `/nvda/`）。
- 頻率：`quarterly`（只有季報）或 `monthly+quarterly`（有月營收，如台積電）。

### ② `companies/<代號>/SOURCES.md`
照 `companies/pltr/SOURCES.md` 的章節寫：來源（依可信度排序）、欄位定義與單位、核對規則、更新步驟、已知缺口。**排程每次都照這份做，所以要寫到沒看過這個專案的人也能執行。**

### ③ 蒐集資料
- 優先用 SEC EDGAR（美股）或公司投資人關係網站、公開資訊觀測站（台股）。
- 季度從公司最早能取得的一季開始；取不到的欄位填 `null`，並寫進 SOURCES.md 的「已知缺口」。
- 第四季通常要用「全年減前三季累計」推算，並與公司公布的全年數字核對。

### ④ `data/<代號>.json` 結構（schema `v1`）

共用欄位（每家公司都要有）：

| 欄位 | 內容 |
| --- | --- |
| `asOf` | 資料截至日 `YYYY-MM-DD` |
| `company` | 代號、名稱、交易所、幣別、單位說明 |
| `quarters[]` | 每季：`q`（如 `2Q26`）、`rev`、`gp`、`gm`、`opInc`、`om`、`ni`、`eps`、`ocf`、`capex`、`fcf`、`dps`；金額單位寫在 `company.unit`（建議百萬元） |
| `annual{}` | 公司公布的全年數字（鍵為年份） |
| `guidance` | 公司給的下一季或全年財測 |
| `events[]` | 之後的公布日 `{date, t}`；預估日期加 `est:1` 並在 `t` 註明 |
| `waterfall` | 最新一季從營收到淨利的拆解 `{q, rows:[{n, v, t?}], note}` |
| `milestones[]` | 重要事件 `{d, cat, t, src, st:"p"/"f", unc?:1, note?}`；日期只能是 `YYYY-MM-DD`、`YYYY-MM`、`YYYY-Qn`、`YYYY-Hn`、`YYYY`；`unc:1` 的 `note` 要以「待確定：」開頭 |

選用區塊（有才放）：`monthly`（月營收）、`fabs`（建廠時程）。**公司專屬指標放在以代號命名的獨立區塊**，例如 PLTR 的 `pltr.quarters[]`（政府／商業拆分、TCV、RDV…），不要塞進共用欄位。

首頁用 `companies.json` 的 `schema` 欄位選「摘要轉接器」（`templates/home.frag.html` 的 `ADAPTERS`）：
- 資料符合 `v1`（`quarters[]` 有 `rev`、`gm`、`om`、`eps`）→ 直接可用，不必改任何程式。
- 資料格式不同 → 在 `ADAPTERS` 加一個以 schema 名稱為鍵的函式（約 8 行），回傳最新營收、年增率、毛利率、營益率、EPS、下一個公布日。（台積電是舊格式 `tsmc-legacy`，因此有專屬轉接器。）

### ⑤ 核對函式
在 `tools/validate.py` 的 `CHECKS` 加 `"<代號>": 函式`。至少包含：分項加總＝總數、四季加總＝全年、比率與金額自洽。

### ⑥ 頁面模板
複製 `templates/pltr.frag.html` 為 `templates/<代號>.frag.html`，改欄位與文字。模板必須保留三個占位符：`{{THEME}}`（共用樣式）、`{{COMMON_JS}}`（共用函式）、`{{DATA}}`（資料 JSON，放在 `<script type="application/json" id="company-data">`）；導覽列第一個連結保留 `{{HOME}}`。只有公司有的區塊（月營收、建廠…）依資料是否存在才顯示。

### ⑦ `companies.json`
```json
{
  "code": "nvda", "name": "輝達", "nameEn": "NVIDIA", "ticker": "NVDA",
  "exchange": "Nasdaq NVDA", "currency": "USD", "frequency": "quarterly",
  "path": "nvda/", "schema": "v1", "template": "nvda",
  "title": "輝達財報追蹤板", "description": "一句話說明（給搜尋引擎與分享預覽）",
  "artifact": null, "enabled": true
}
```
`enabled:false` 的公司不會建置、也不會被排程更新。

### ⑧ 建置與核對
```
python3 tools/validate.py       # 所有啟用公司的核對
python3 tools/build.py          # 產生 <path>/index.html、首頁、dist/artifacts/*.html
```

### ⑨ 檢查頁面
用無頭瀏覽器（Playwright）開首頁與新頁面：桌機 1280 寬、手機 390 寬、深色模式；確認沒有 JavaScript 錯誤、沒有水平捲動、沒有 `undefined`／`NaN`。

### ⑩ 發佈
commit 並 push 到 `main`，GitHub Pages 會自動重新部署（根目錄、main 分支）。

### ⑪ Artifact
Artifact 是**單一合併版**：`python3 tools/build.py` 會把新公司自動加成 `dist/artifacts/all.html` 的新分頁。用 Artifact 工具發佈 `dist/artifacts/all.html` 到 `companies.json` 的 `site.artifact`（帶同一個 `url`），不必為新公司另開 Artifact。個別的 `dist/artifacts/<代號>.html` 僅供需要單獨分享時使用。

## 4. 完成後要告訴使用者
網站網址、資料涵蓋期間、**取不到的欄位**、選了哪些預設、下一次排程什麼時候會更新這家公司。
