# 奇異航太（GE） 資料來源與更新步驟

- 資料檔：`data/ge.json`（schema `v1`）　頁面：`/ge/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**；每股數字（`eps`、`dps`）為美元。
- 頻率：每季。排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md），只補「上次資料之後」的新期間；沒有實質變動就不 commit。
- CIK：`0000040545`。

## 會計年度與期間

會計年度＝曆年（`12-31`）。和舊奇異是同一法人：2023-01 分拆 GE HealthCare、2024-04-02 分拆 GE Vernova。從 1Q24 開始，2024 年四季用 2025 年申報／新聞稿裡重編、只含航太的比較數字（原始 1Q24 季報含 GE Vernova）。 期間 1Q24–最新一季，共 11 季。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0000040545.json`（新增公司時由 GitHub Actions 的 sec-raw 分支下載，容器讀不到 SEC）。
2. **財報新聞稿（8-K Item 2.02 附件 99）：3Q26 `https://www.sec.gov/Archives/edgar/data/40545/000004054526000063/ge3q2026earningsrelease.htm`。第二季與第四季的新聞稿附完整損益表，其他季只有非 GAAP 對照表（含成本費用合計、利息、非營業退休金、分拆費用）。**
3. 投資人關係網站（新聞稿、財報日期、股利宣告）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`、note 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | 各季財報新聞稿的 Total revenue (GAAP)（2024 年取 2025 年新聞稿的上年同期欄）；與 XBRL `Revenues` 差 1 以內 |
| `gp`、`gm` | 2025 年起 XBRL 沒有單獨標銷售成本：`gp`＝營收 −（成本費用合計 − `SellingGeneralAndAdministrativeExpense` − `ResearchAndDevelopmentExpense` − 分拆費用 − 利息與其他財務費用 − 非營業退休金 − 商譽減損），即減掉設備成本、服務成本與保險損失；合計、利息、非營業退休金、分拆費用取新聞稿。已對新聞稿完整損益表的 2Q24、4Q24、2Q25、4Q25 核對，差 1 以內 |
| `opInc`、`om` | 損益表不列營業利益：`opInc`＝營收 −（成本費用合計 − 利息與其他財務費用 − 非營業退休金）。公司的「Operating profit」是非 GAAP，口徑不同 |
| `ni` | `NetIncomeLoss`（歸屬母公司普通股股東） |
| `eps` | `EarningsPerShareDiluted`（含停業部門的淨 EPS）；4Q25 取 4Q25 新聞稿 2.40。新聞稿標題用的是持續營業 EPS（Continuing EPS），口徑不同 |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`（年初累計相減；2024 年取重編版本） |
| `capex` | `PaymentsToAcquireProductiveAssets`（年初累計相減） |
| `dps` | `CommonStockDividendsPerShareDeclared`（宣告基準：2024 年第一季 0、第二季 0.56） |
| `rd`、`rdB` | 季末後 5–90 天內**第一份**財報 8-K（Item 2.02）的申報日，`rdB:"p"` |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季＝10-K 全年 − 前三季（四季加總＝全年，validate 已核對）。股票分割：期間內沒有。

### 選用區塊
`segments`：無（CES、DPT 兩部門公布的是調整後營收，加總不等於 GAAP 營收，之後可補）。`guidance.items[]`：全年營業利益、調整後 EPS、自由現金流（全部非 GAAP）。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `ge`（GitHub Actions bs-fetch 產生 `data/bs-raw/ge.json`，`python3 tools/bs_merge.py ge` 與 `--only sbc ge` 合併）：`cash`＝`CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`；`debt`＝`LongTermDebtAndCapitalLeaseObligations`＋`DebtCurrent`；`buyback`＝`PaymentsForRepurchaseOfCommonStock`；`sbc`＝`ShareBasedCompensation`；`shOut`＝`CommonStockSharesOutstanding`（缺時用封面 `dei:EntityCommonStockSharesOutstanding`）、`dilSh`＝`WeightedAverageNumberOfDilutedSharesOutstanding`（第四季多半沒有單季值）、`equity`＝`StockholdersEquity`、`pretax`、`tax` 同其他美股。沒有值的季度見 notes.unavailable。近似的業主盈餘＝自由現金流 − sbc。

## 電話會議（逐字稿）與非 GAAP
官方網路直播（geaerospace.com/investor-relations）；第三方逐字稿尚未選定。公司**有非 GAAP EPS**（Adjusted EPS，排除保險業務、分拆、重組、持股評價等），市場預估多半是這個口徑：比對預估時 `cons.actualAlt` 要填新聞稿的調整後 EPS。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 ge 財報 8-K 或 `python3 tools/daily.py inbox ge`。沒有新財報 → 只查事件時間軸。
2. 讀新聞稿：Total revenue、Total costs and expenses、利息、非營業退休金、分拆費用、訂單、部門營收與營業利益、全年展望（Prior 欄放 guidanceHistory）；淨利、EPS、現金流、銷管、研發用 10-Q XBRL。
3. 新增一季（`rd`＝新聞稿 8-K 申報日，`rdB:"p"`）；第四季數字＝10-K 全年 − 前三季、EPS 取新聞稿；舊 `guidance` append 進 `guidanceHistory`；更新 `waterfall`、`events`、`summary`（有 segments 的公司同時加 `segments.quarters[]`）。
4. `python3 tools/validate.py ge` 通過才繼續。
5. 事件：大型引擎訂單（LEAP、GEnx、GE9X）、耐用度改善包認證、供應鏈與交付、國防引擎合約、併購（CPP）、舊保險業務。屬於核心故事線的事件 `cat` 用 `story.cats`（`python3 tools/daily.py story`）。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `GE（NYSE，美元）` |
| 股價起點 | 2024-01 |
| 股票分割 | 期間內沒有 |
| EPS 口徑 | GAAP 稀釋 EPS |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/ge.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果：待確認：股價回補後抽查最早、中間、最新 3 個月底股價對第二個獨立來源（容器讀不到免費歷史股價網站時維持待確認）。

## 已知缺口
見 `data/ge.json` 的 `notes.unavailable`。
