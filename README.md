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
companies.json ─────┐   公司清單：代號、名稱、交易所、幣別、頻率、路徑、Artifact 網址、是否啟用
data/<代號>.json ───┼─► tools/build.py ─► <路徑>/index.html（單檔自足，可直接開啟）
templates/*.frag.html┤                  ├► index.html（首頁）
assets/theme.css ───┤                   └► dist/artifacts/*.html（給 Claude Artifact，不進 git）
assets/common.js ───┘
tools/validate.py ── 發佈前核對（分項加總＝總數、四季＝全年…）
companies/<代號>/SOURCES.md ── 來源、欄位定義、核對規則、更新步驟（排程照這份做）
docs/ADDING_A_COMPANY.md ── 新增公司的標準流程
docs/SCHEDULE_PROMPT.md ── 排程任務的完整指令
```

## 常用指令

```
python3 tools/validate.py     # 核對所有啟用中的公司
python3 tools/build.py        # 產生所有頁面
```

## 更新方式

Claude 排程每週一早上 8:00（台北時間）依各公司的 `SOURCES.md` 更新資料；核對沒過的公司不發佈，只有實質變動才 commit、push 與更新 Artifact。

## 新增公司

見 [`docs/ADDING_A_COMPANY.md`](docs/ADDING_A_COMPANY.md)：新增 `companies.json` 一筆設定、`data/<代號>.json`、`companies/<代號>/SOURCES.md` 與頁面模板，共用程式不用改。

## 資料來源與聲明

資料來自各公司的投資人關係網站、SEC EDGAR（10-Q、10-K、8-K）與公開資訊；只有媒體報導、公司未證實的消息標為「待確定」。調整後（non-GAAP）數字是公司自訂指標。

**本專案為公開資料整理，不構成投資建議。**
