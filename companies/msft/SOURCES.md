# 微軟 Microsoft（MSFT）資料來源與更新步驟

- 資料檔：`data/msft.json`（schema `v1`）　頁面：`/msft/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`）；每股數字（`eps`、`dps`）為美元。期間沒有股票分割（最近一次是 2003 年），EPS 不用換算。
- CIK：`0000789019`。頻率：每季。財報日約在 1、4、7、10 月最後一週（美股收盤後）。
- 排程：週二至週六 08:30（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md；公布日隔天先做「快報」，再「補完」「核對」）。只補「上次資料之後」的新期間；沒有新財報的月份只檢查事件與公布日；沒有實質變動就不 commit。

## 會計年度與季度標籤

微軟的會計年度在 **6 月 30 日** 結束，**季度標籤用公司自己的會計年度**：

```
FY2027 = 2026/7/1 ─ 2027/6/30
  1Q27 = 2026/7–9      （2026/10 下旬公布）
  2Q27 = 2026/10–12    （2027/1 下旬公布）
  3Q27 = 2027/1–3      （2027/4 下旬公布）
  4Q27 = 2027/4–6      （2027/7 下旬公布，含全年）
```

`annual` 的鍵 `"2026"` 就是 FY2026（2025/7/1–2026/6/30）。

## 期間

1Q09（FY2009 第一季，2008/7–9）–最新一季。FY2008 的 XBRL 有各季營收、毛利、淨利、EPS，但沒有單季營業利益與營業現金流，營業利益率是必要欄位，所以從 FY2009 開始；FY2007 以前沒有 XBRL。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyconcept/CIK0000789019/us-gaap/{概念}.json`（WebFetch 讀得到；容器 curl 會被擋）。讀法：每個 (start, end) 取最近一次申報的值。
2. **微軟投資人網站**：`https://www.microsoft.com/en-us/investor/earnings/fy-{年}-q{季}/press-release-webcast`，同一資料夾還有 `income-statements`、`cash-flows`。10-Q 的 XBRL 進 API 之前，用這裡的數字。
3. SEC 8-K 附件 99.1（財報新聞稿、分部重編）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`。

## 欄位定義（`quarters[]`）

| 欄位 | XBRL 概念與口徑 |
| --- | --- |
| `rev` | FY2016 以前 `SalesRevenueNet`（FY2011 以前 `Revenues`，數字相同）；FY2017 起 `RevenueFromContractWithCustomerExcludingAssessedTax` |
| `gp`、`gm` | `GrossProfit`（微軟稱 Gross margin 金額） |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss` |
| `eps` | `EarningsPerShareDiluted`；第四季見下 |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`，年初累計相減；FY2014–FY2016 這個概念沒有資料，改用 `NetCashProvidedByUsedInOperatingActivitiesContinuingOperations` |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（Additions to property and equipment），年初累計相減 |
| `dps` | `CommonStockDividendsPerShareDeclared`（宣告的每股股利） |

### ASC 606 斷點
微軟 FY2018 採用新收入準則 ASC 606 並**完整追溯重編 FY2016、FY2017**。本頁：

```
FY2009 ─ FY2016   舊準則原始數字（當年 10-K／10-Q 申報）
FY2017 ─ 現在      ASC 606 重編後數字
```
FY2016 的營收舊 85,320、新 91,154（差約 6.8%），比較長期成長時要注意這個斷點。FY2016 全年毛利、營業利益、淨利、EPS 的原始值在 XBRL 只剩重編版，`annual.2016` 這幾欄留空。

### 第四季推算
- 營收、毛利、營業利益、淨利：XBRL 有 4–6 月單季值就用；沒有（營業利益 FY2009–FY2013、全部 FY2021 以後）就用 **全年 − 前三季**，並與新聞稿核對。
- EPS：FY2020 以前取 XBRL 單季值；FY2021 以後取當年第四季財報新聞稿（FY2021 2.17、FY2022 2.23、FY2023 2.69、FY2024 2.95、FY2025 3.65、FY2026 4.81）。

## 核對規則（`python3 tools/validate.py msft`）

1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年（營收、毛利、營業利益、淨利、營業現金流、資本支出）。
3. `waterfall` 小計加總；第一列營收＝最新一季 `rev`。

**任何一項沒過就不發佈**，回到來源修資料，不要放寬核對。

## 更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）

1. 查有沒有新財報：`https://www.microsoft.com/en-us/investor/earnings/fy-{年}-q{季}/press-release-webcast`（下一季）或 SEC 8-K。**沒有新財報 → 跳到第 6 步。**
2. 讀 `income-statements`（營收、營業成本、毛利、研發、行銷、管理、營業利益、其他收益、所得稅、淨利、稀釋 EPS）與 `cash-flows`（Net cash from operations、Additions to property and equipment）。
3. 10-Q 進 XBRL API 後，用 API 核對上一季（以 XBRL 為準），並刪掉 notes 裡對應的「待確認」。第四季：營收等用全年減前三季，EPS 用新聞稿；新增 `annual`。
4. 更新 `waterfall`、`events`（公司公告日期後刪 `est`）。`guidance` 保持空（新聞稿沒有數字財測）。
5. `python3 tools/validate.py msft`；通過才繼續。
6. 查事件：併購、分部調整、股利調整（每年 9 月）、重大合作（優先 8-K 與 news.microsoft.com）。
7. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 已知缺口

- FY2008 以前：見「期間」。
- FY2013 全年毛利：XBRL 全年 57,464 與四季加總 57,600 差 136，全年留空。
- 2Q25 以後每股股利：XBRL API 股利頁讀取被截斷，留空；下次排程可試 10-Q 的 R 頁（FilingSummary.xml）補上。
- 1Q27 營業現金流與資本支出：取自投資人網站，等 10-Q XBRL 核對。
- 分部營收：FY27 起兩大部門（Agents and Infra、Devices and Consumer），之前三大部門；尚未收錄。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `MSFT`（主要掛牌地普通股，幣別 美元） |
| 股價起點 | 2008-07 |
| 股票分割 | 無股票分割（2003 年之後）（Yahoo Close 已依分割調整、不含股利調整，才跟本站已換算成今天股數的 EPS 對得上） |
| EPS 口徑 | 稀釋 EPS；都是公認會計準則數字，不用調整後 EPS |
| 財報公布日 `rd` 來源 | SEC XBRL 的 10-Q／10-K 申報日（rdB:f）；最新一季用新聞稿日（rdB:p） |

**更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）**
1. 新增一季時，同時填該季 `rd`（那一季 EPS 第一次公開的日期）與 `rdB`。讀不到就填 `null`，在 `notes.unavailable` 加「待確認：<季度> 的財報公布日（rd）：原因」，**不可以用「季度結束後幾天」推算**。最新一季的 `rd` 不可為 null。
2. 股價檔 `data/prices/msft.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填、不修改；排程只檢查上個月有沒有進來。
3. 本益比（`tools/pe.py`）與預估本益比不存檔，建置時算出；預估只有每月 1–6 日 Actions 存下的快照，**不回填**。
4. 若這家公司發生股票分割：同一次完成 EPS 重編與股價檔重抓（手動觸發 prices-monthly 並填 `accept=msft`），否則 validate 會因相鄰月份本益比跳動超過 3 倍而失敗。
5. 抽查紀錄（回補時每家人工對第二個獨立來源抽 3 個月：最早一個月、最近一次分割前一個月、最新一個月）：見下表。

| 月份 | Yahoo 收盤價 | 第二來源 | 結果 |
|---|---|---|---|
| 2008-07（2008-07-31） | 25.72 | — | 待確認：2026-11-12 嘗試的免費來源只提供最近約 50 個交易日，讀不到這一天，尚未完成第二來源核對 |
| 2015-06（2015-06-30） | 44.15 | — | 待確認：2026-11-12 嘗試的免費來源只提供最近約 50 個交易日，讀不到這一天，尚未完成第二來源核對 |
| 2026-10（2026-10-30） | 521.91 | stockanalysis.com/stocks/msft/history | 一致（521.91；2026-11-12 讀取，頁面標示已依分割調整） |

