# 企業財報追蹤板（Enterprise Revenue Dashboard）

多家公司的公開財務資料整理，同一套版型、各公司一頁，GitHub Pages 發佈。

**網站：** https://zlo-25.github.io/Enterprise-Revenue-Dashboard/

| 路徑 | 內容 |
| --- | --- |
| `/` | 首頁總覽：各公司最新營收與年增率、獲利率、EPS、資料截至日、下一個公布日 |
| `/tsmc/` | 台積電（2330 / TSM）：2015 年以來月營收、季報、製程結構、技術里程碑、建廠時程 |
| `/pltr/` | Palantir（PLTR）：3Q19 起每季營收、政府與商業拆分、GAAP 與調整後獲利、現金流、合約與客戶指標、財測、重要事件 |

## 架構

```
companies.json ─────┐   公司清單：代號、名稱、交易所、幣別、頻率、路徑、主要來源、是否啟用
data/<代號>.json ───┼─► tools/build.py ─► <路徑>/index.html（單檔自足，Chart.js 用 assets/vendor/ 本地副本）
templates/           │                  ├► index.html（首頁：卡片、長期體質記分板、跨公司比較、資料新鮮度）
  generic.frag.html ─┤                  └► dist/artifacts/all.html（合併版 Claude Artifact，不進 git）
  home.frag.html     │
  tsmc/pltr.frag.html│
assets/theme.css ───┤
assets/common.js ───┤   共用前端函式
assets/adapters.js ─┤   轉接層：各種資料格式 → 標準季度序列（首頁與長期指標只認這一種）
assets/longterm.js ─┘   長期指標：近四季（TTM）、年化成長（CAGR）、利潤率變化、自由現金流率、連續年增、資料新鮮度
tools/validate.py ── 三層核對：companies.json 設定 → 共通格式 → v1 通用（自洽、四季＝全年、分部加總、損益拆解）＋公司專屬
tools/new_company.py ── 新增公司腳手架（一行指令產生資料空殼、SOURCES.md、companies.json 設定）
companies/<代號>/SOURCES.md ── 來源、欄位定義、核對規則、更新步驟（排程照這份做）
docs/DATA_SCHEMA.md ── 資料格式 v1 說明
docs/ADDING_A_COMPANY.md ── 新增公司的標準流程
docs/NEW_COMPANY_PROMPT.md ── 新增公司的 prompt 模板（只填公司名稱就能交給 Claude）
docs/SCHEDULE_PROMPT.md ── 排程任務的完整指令
```

## 長期投資人視角

每一頁都有「長期觀察」：把一年當成一個整體看，不被單季起伏牽著走。

```
單季數字 ──加總 4 季──► TTM（近四季） ──對 3／5 年前的 TTM──► CAGR（年化成長）
     │                      │
     │                      ├─► 近四季加權毛利率、營業利益率、淨利率 ──► 跟 3 年前比（變化幾個百分點）
     │                      └─► 近四季自由現金流 ÷ 營收 ──► 獲利有沒有變成現金
     └─► 每季年增率 ──► 連續幾季為正、近 20 季有幾成為正 ──► 成長穩不穩
```

首頁的「長期體質記分板」與「跨公司比較」只比比率與指數化走勢，不比金額（幣別不同）。

## 常用指令

```
python3 tools/validate.py     # 核對 companies.json 與所有啟用中的公司（任何一項沒過就以非 0 結束）
python3 tools/build.py        # 產生所有頁面與合併版 Artifact
python3 tools/new_company.py nvda --name 輝達 --name-en NVIDIA --ticker NVDA --exchange "Nasdaq NVDA" --currency USD   # 新增公司腳手架
```

## 更新方式

Claude 排程每月 12 日早上 07:48（台北時間）依各公司的 `SOURCES.md` 更新資料；核對沒過的公司不發佈，只有實質變動才 commit、push 與更新 Artifact。

## 新增公司

見 [`docs/ADDING_A_COMPANY.md`](docs/ADDING_A_COMPANY.md)，或把 [`docs/NEW_COMPANY_PROMPT.md`](docs/NEW_COMPANY_PROMPT.md) 填上公司名稱交給 Claude。資料符合 v1 格式（[`docs/DATA_SCHEMA.md`](docs/DATA_SCHEMA.md)）就直接用通用頁面模板，首頁、比較圖、長期指標、排程都會自動納入，共用程式不用改。

## 發佈設定

GitHub Pages：Settings → Pages → Deploy from a branch → `main` / `/ (root)`。頁面是 `tools/build.py` 預先產生並 commit 的，GitHub 只需原樣發佈（根目錄有 `.nojekyll`）。

## 資料來源與聲明

資料來自各公司的投資人關係網站、SEC EDGAR（10-Q、10-K、8-K）與公開資訊；只有媒體報導、公司未證實的消息標為「待確定」。調整後（non-GAAP）數字是公司自訂指標。

**本專案為公開資料的整理與計算，不構成任何投資建議；整理過程可能有誤或延遲，使用前請自行核對；過去的財務表現不代表未來結果。**
