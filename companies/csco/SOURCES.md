# 思科 Cisco Systems（CSCO）資料來源與更新步驟

- 資料檔：`data/csco.json`（schema `v1`）　頁面：`/csco/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`）；`eps`、`dps` 為美元。
- 頻率：每季。財報日約在 2、5、8、11 月中（美股收盤後）。
- 排程：週二至週六（台北）每日檢查（docs/SCHEDULE_PROMPT.md；公布日隔天先做「快報」，再「補完」「核對」）。只補「上次資料之後」的新期間，舊數字不重抓。
- CIK：`0000858877`。

## 會計年度與季度標籤

思科的會計年度是 52／53 週，在 **7 月最後一個星期六**結束；季度標籤用**公司的會計年度**（`company.fiscalYearEnd` 填 `07-25`，讓 `rd` 檢查算得出季末）：

```
FY2027 = 2026/7/26 ─ 2027/7/31（預計）
  1Q27 = 2026/7/26  ─ 2026/10/24  ← 目前最新一季（2026-11-12 公布）
  2Q27 = 2026/10/25 ─ 2027/1/23   ← 預估 2027-02 中公布
  3Q27 ─ 4Q27 ……
```

## 期間

1Q10（2009/7/26–10/24）–最新一季，共 69 季。思科 FY2010 第一季才開始用 XBRL，更早沒有可機器讀取的單季數字。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0000858877.json`（容器 curl 被擋；用 GitHub Actions `sec-raw` 分支的工作流程下載到 `raw/csco/`）。
2. **財報新聞稿（8-K Item 2.02 附件 99.1）**，近年檔名 `exhibit991pressrelease-q{季}f.htm`：
   - 1Q27 `https://www.sec.gov/Archives/edgar/data/858877/000085887726000170/exhibit991pressrelease-q1f.htm`
   - 4Q26 `https://www.sec.gov/Archives/edgar/data/858877/000085887726000106/exhibit991pressrelease-q4f.htm`
   第四季 EPS 與稀釋股數、產品／服務營收、財測、最新一季（10-Q 出來前）都從這裡讀。
3. 投資人關係 `https://investor.cisco.com/`（財報日期、網路直播）。
4. 可信媒體：只用於事件時間軸；公司未證實的一律 `unc:1`，`note` 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `RevenueFromContractWithCustomerExcludingAssessedTax`（FY2018 起，ASC 606）、`Revenues`／`SalesRevenueNet`（以前） |
| `gp`、`gm` | `GrossProfit`；GAAP 毛利含併購無形資產攤銷，低於公司強調的非 GAAP 毛利率 |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss` |
| `eps` | `EarningsPerShareDiluted`（GAAP 稀釋）；第四季見下 |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`（FY14–16 缺時用 `…ContinuingOperations`），年初累計相減 |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`，年初累計相減（正數） |
| `dps` | 每季宣告的每股現金股利（`CommonStockDividendsPerShareDeclared`，缺時用 `…CashPaid`；第四季取三個月值）；2011 年第三季（4Q11）開始配息 |
| `rd`、`rdB` | 季末後 5–90 天內最後一份 8-K Item 2.02 的申報日，`rdB:"p"` |

### 每個會計年度只用一個版本
季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本，全年取原始 10-K，四季加總才會等於全年。

### 第四季推算
**4Q ＝ 10-K 全年 − 前三季**（營收、毛利、營業利益、淨利）；現金流、資本支出、回購＝全年 − 前九月累計。**EPS 不相減**：取第四季財報新聞稿，而且新聞稿的全年 EPS 要和 10-K 一致才用。例外：4Q25 新聞稿全年淨利 104.53 億美元，但 FY2025 10-K 是 101.80 億美元，所以 4Q25 EPS 改用 4Q26 新聞稿比較欄重編後的 0.64 美元（原始 0.71）。

### 選用區塊
- `segments`：產品／服務兩類（新聞稿損益表前兩行），1Q10 起每季都有。產品內的網通、資安、協作、可觀測性四類本站沒有拆。
- `guidance.items[]`：思科每季給下一季營收、GAAP 與非 GAAP EPS、非 GAAP 毛利率，並給全年營收與 EPS。毛利率財測只有非 GAAP，`note` 要寫明。
- `guidanceHistory`：從 2026-08-12（4Q26 新聞稿給的 1Q27 財測）開始累積。

## 核對規則（`python3 tools/validate.py csco`）
1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年（營收、毛利、營業利益、淨利、營業現金流、資本支出）。
3. `segments` 加總 ＝ 營收；`waterfall` 小計自洽。
4. 淨利 ÷ 稀釋股數 ≈ EPS；`rd` 遞增且在季末後 5–120 天。
**任何一項沒過就不發佈**，不放寬核對。

## 資產負債表欄位（shOut、dilSh、cash、debt、buyback、equity、pretax、tax）
- `shOut`：`CommonStockSharesOutstanding`，缺時用 10-Q 封面 `dei:EntityCommonStockSharesOutstanding`。
- `dilSh`：`WeightedAverageNumberOfDilutedSharesOutstanding` 單季值；第四季取新聞稿。
- `cash`：`CashAndCashEquivalentsAtCarryingValue` ＋ 短期投資（`ShortTermInvestments`／`AvailableForSaleSecurities…Current`）。
- `debt`：`LongTermDebtNoncurrent`（或 `LongTermDebt`）＋ `DebtCurrent`／`ShortTermBorrowings`（含商業本票）。
- `buyback`：`PaymentsForRepurchaseOfCommonStock`，年初累計相減。
- `equity`：`StockholdersEquity`；`pretax`：`IncomeLossFromContinuingOperationsBeforeIncomeTaxes…`；`tax`：`IncomeTaxExpenseBenefit`。
- 最新一季在 10-Q 出來前取新聞稿（資產負債表、現金流量表），`shOut` 新聞稿沒有 → `null`。讀不到的見 `notes.unavailable`。

## 電話會議（逐字稿）來源
- 官方：`https://investor.cisco.com/`（網路直播與重播）。第三方逐字稿尚未選定；讀不到寫「待確認：逐字稿尚未取得」。
- **公司有非 GAAP EPS**（新聞稿第一段同時列）。本站 EPS 一律 GAAP 稀釋；和市場預期比較時 `cons.actualAlt` 填非 GAAP EPS、`basis` 寫「調整後」。

## 更新步驟（快報）
1. 查 `data/sec-feed.json` 的 csco 8-K Item 2.02。**沒有新財報 → 跳到第 6 步。**
2. 讀新聞稿：營收（產品、服務）、毛利、營業利益、稅前淨利、所得稅、淨利、GAAP 稀釋 EPS、稀釋股數、營業現金流、資本支出、回購、股利、現金與投資、債務、股東權益、下一季與全年財測、非 GAAP EPS。
3. 新增一季到 `quarters[]`（`rd`＝新聞稿日，`rdB:"p"`）與 `segments.quarters[]`；第四季時新增 `annual`（10-K 出來後）。舊 `guidance` 原封不動 append 進 `guidanceHistory` 再寫新的；換 `waterfall`、`events`、`summary`（舊的精簡後移到 `summaryHistory`）。
4. `python3 tools/validate.py csco` 通過才繼續。
5. 10-Q／10-K 出來後用 XBRL 核對，以申報文件為準並在 notes 記錄。
6. 查事件時間軸：併購、AI 基礎設施訂單、回購授權（優先 8-K 與公司新聞稿）。
7. `asOf` 改成今天，`python3 tools/build.py`，commit、push。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `CSCO`（Nasdaq，美元） |
| 股價起點 | 2009-10（第一季 1Q10 結束的月份） |
| 股票分割 | 2009 年以來沒有股票分割，EPS 不換算 |
| EPS 口徑 | GAAP 稀釋 EPS |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/csco.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。

抽查（2026-11-16 prices-monthly 回補後）：

| 月份 | Yahoo 收盤價（分割調整後） | 第二來源 | 結果 |
|---|---|---|---|
| 2009-10（2009-10-30） | 22.81 | — | 待確認：尚未對第二個獨立來源核對（沒有找到能讀到這一天的免費歷史股價來源） |
| 2020-03（2020-03-31） | 39.31 | — | 待確認：尚未對第二個獨立來源核對（沒有找到能讀到這一天的免費歷史股價來源） |
| 2026-10（2026-10-30） | 104.51 | — | 待確認：尚未對第二個獨立來源核對（沒有找到能讀到這一天的免費歷史股價來源） |

## 已知缺口
- FY2009 以前：沒有 XBRL，未收錄。
- 1Q10–4Q13 稅前淨利、1Q19–2Q19 現金與投資已改從新聞稿補上（稅前 − 所得稅＝淨利每季核對）。
- 1Q27 期末流通股數：要等 10-Q（新聞稿沒有），`null`。

本益比連續性：期間沒有分割；2026-10 本益比 31.3 倍（近五年中位數 19.9 倍）。

第二來源核對（2026-11-17 再試一次）：Stooq 的月線 CSV 擋自動讀取（robots），Macrotrends 只有年資料或擋讀取，ASML 頁也擋。三個抽查月份仍是「待確認」。股價本身照 Yahoo（prices-monthly）保留，不改成 null，因為股價有讀到，只是還沒有第二來源可以比對。
