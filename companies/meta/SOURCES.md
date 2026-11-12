# Meta Platforms（META）資料來源與更新步驟

- 資料檔：`data/meta.json`（schema `v1`）　頁面：`/meta/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`）；`eps`、`dps` 為美元。Meta 從上市到現在沒有股票分割（2027 年 1 月的 C 股配股見文末）。
- CIK：`0001326801`（原 Facebook, Inc.，2021-10 改名 Meta Platforms）。頻率：每季。會計年度＝日曆年。財報日約在 1 月底／2 月初、4 月底、7 月底、10 月底（美股收盤後）。
- 排程：週二至週六 08:18（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md；公布日隔天先做「快報」，再「補完」「核對」）。

## 期間

1Q12（2012/1–3）–最新一季。Facebook 2012 年 5 月在 Nasdaq 上市，XBRL 從 2012 年季報開始。1Q12 是上市前的季度（數字取自後來季報的比較欄），所以這一季沒有財報公布日與稀釋股數。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyconcept/CIK0001326801/us-gaap/{概念}.json`。容器與使用者電腦的 curl 會被 SEC 擋（403），**只有 web-fetch 代理讀得到**。讀法：每個 (start, end) 只看 10-K／10-Q。不要用 GitHub Actions 代抓 SEC 資料（曾被權限檢查擋下）。
2. **財報新聞稿 PDF**：`https://s21.q4cdn.com/399680738/files/doc_news/Meta-Reports-{First|Second|Third|Fourth}-Quarter-{年}-Results-{公布年}.pdf`（第四季為 `…-Fourth-Quarter-and-Full-Year-{年}-Results-{公布年}.pdf`；2020 年以前名稱是 Facebook-Reports-…）。部分年度只有 investor.atmeta.com 的 press-release-details 頁面（見 `sources`）。投資人關係網站的列表頁要 JavaScript，WebFetch 讀不到，請用 WebSearch 找精確網址。
3. 8-K PDF（特別股、公司債等）：`https://d18rn0p25nwr6d.cloudfront.net/CIK-0001326801/<uuid>.pdf`（從 investor.atmeta.com 的 sec-filings-details 頁找）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`。

## 欄位定義（`quarters[]`）

| 欄位 | XBRL 概念與口徑 |
| --- | --- |
| `rev` | 3Q18 以前 `Revenues`；之後 `RevenueFromContractWithCustomerExcludingAssessedTax`（重疊年度數字相同） |
| `gp`、`gm` | **營收 − `CostOfRevenue`**。Meta 損益表沒有「毛利」這一行 |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss` |
| `eps` | `EarningsPerShareDiluted`；第四季見下 |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`，年初累計相減 |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（Purchases of property and equipment），年初累計相減。**不含融資租賃本金**，所以本頁 `fcf` 比 Meta 自己公布的 Free cash flow 高（3Q26：本頁 −1,156，公司 −2,120） |
| `dps` | `CommonStockDividendsPerShareDeclared`；2024 年第一季開始配息，之前留空（不是缺資料） |

### 第四季推算
- 營收、營業成本、營業利益、淨利、稅前、所得稅：**全年 − 前三季**。已用 4Q13（2,585；推算 2,586，差 1 為四捨五入）、4Q15（5,841）、4Q17（12,972）新聞稿抽查營收。
- EPS：XBRL 沒有第四季單季值，**一律取第四季新聞稿**：4Q12 0.03、4Q13 0.20、4Q14 0.25、4Q15 0.54、4Q16 1.21、4Q17 1.44、4Q18 2.38、4Q19 2.56、4Q20 3.88、4Q21 3.67、4Q22 1.76、4Q23 5.33、4Q24 8.02、4Q25 8.88。不可用全年減前三季。
- 現金流、買回：年初累計（Q1、上半年、前九月、全年）相減。

### 版本選擇
- 同一期間有多個申報版本時（後來的 10-K 有時會重分類舊數字），逐年選一個「四季加總＝全年」一致的版本，不在同一年混用；現金流與資本支出以最早申報的版本為主。
- 3Q26 營業現金流用新聞稿單季 32,786（累計相減得 32,785，差 1）。

### 一次性項目（看趨勢時要排除）
- 3Q25：所得稅 18,954（稅前 21,663），EPS 只有 1.05。
- 3Q26：與 52 州檢察長和解，認列 98.9 億美元費用（列在管理費用）。公司表示扣除後營業利益 228.8 億、EPS 7.40。

## 核對規則（`python3 tools/validate.py meta`）
1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年。
3. `waterfall` 小計加總；第一列營收＝最新一季 `rev`。
4. 淨利 ÷ 稀釋股數 ≈ EPS。
**任何一項沒過就不發佈**，回到來源修資料，不要放寬核對。

## 更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）
1. 查新財報：WebSearch「Meta Reports {季別} Quarter {年} Results」，或照上面 PDF 網址規則。**沒有新財報 → 跳到第 6 步。**
2. 讀新聞稿：損益表（Revenue、Cost of revenue、Income from operations、Interest and other income、Provision for income taxes、Net income、Diluted EPS、Diluted shares）、現金流量表（OCF、Purchases of property and equipment、Repurchases、Dividends）、資產負債表（現金、有價證券、長期負債、股東權益）、分部（Family of Apps、Reality Labs）、CFO Outlook。
3. 新增一季；第四季用全年減前三季、EPS 用新聞稿，並新增 `annual`。
4. 更新 `guidance`（先把舊的整份 append 進 `guidanceHistory`）、`waterfall`、`events`。Meta 的 CFO Outlook 只給「下一季營收」區間，加上全年總費用、全年資本支出（含融資租賃本金）、稅率。
5. `python3 tools/validate.py meta`；通過才繼續。
6. 查事件：大型資本支出、融資（公司債、特別股）、訴訟和解、股利調整、C 股進度（優先 8-K）。
7. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 電話會議逐字稿（口頭內容）
- 官方：investor.atmeta.com 每季的 earnings call transcript（PDF）。第三方逐字稿可用，但必附網址與發言人；讀不到寫「待確認：逐字稿尚未取得」，不用新聞報導代替。

## 非 GAAP 說明
- Meta 主要報表是 GAAP；新聞稿只對一次性項目（如 3Q26 和解費用）另給「扣除後」數字。本站 EPS 一律 GAAP 稀釋。分析師預估若是調整後口徑，`summary.scorecard[].cons.actualAlt` 填新聞稿的扣除後 EPS。

## 資產負債表欄位（shOut、dilSh、cash、debt、buyback、equity、pretax、tax）
- 本次由 XBRL 直接讀取（不是 bs-fetch）：dilSh＝`WeightedAverageNumberOfDilutedSharesOutstanding`（第四季沒有單季值→null）；cash＝`CashAndCashEquivalentsAtCarryingValue` + `MarketableSecuritiesCurrent`（任一項缺就整格 null）；debt＝`LongTermDebtNoncurrent`（2022 年 8 月首次發債；新聞稿沒有短期負債列）；buyback＝`PaymentsForRepurchaseOfCommonStock`（2016 年起，2016 年為 0）；equity＝`StockholdersEquity`；pretax、tax 見上。
- shOut：`dei:CommonStockSharesOutstanding` 讀取失敗（A、B 股分列），全部 null。
- 讀不到的季度原因彙整在 `notes.unavailable`。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `META`（美元） |
| 股價起點 | 2012-05（上市月） |
| 股票分割 | 無。**2027-01-19 起預計每 1 股 A／B 股配 1 股 C 股**，公司預期 A 股股價呈現類似 1 拆 2 的效果：發放後要同一次把 EPS 依新股數重編，並手動觸發 prices-monthly（`accept=meta`），否則本益比會斷崖 |
| EPS 口徑 | GAAP 稀釋 EPS |
| 財報公布日 `rd` 來源 | 10-Q／10-K 申報日（rdB:f）；最新一季用新聞稿日（rdB:p） |

股價檔 `data/prices/meta.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。本益比與預估本益比建置時算出，預估不回填。

2026-11-12 已手動觸發 prices-monthly 回補。抽查紀錄（最早 2012-05；沒有股票分割，改抽中間的 2020-03；最新 2026-10）：

| 月份 | Yahoo 收盤價 | 第二來源 | 結果 |
|---|---|---|---|
| 2012-05（2012-05-31） | 29.6 | — | 待確認：尚未對第二個獨立來源核對（這次沒有找到能讀到這一天的免費歷史股價來源，沒有逐一嘗試） |
| 2020-03（2020-03-31） | 166.8 | — | 待確認：尚未對第二個獨立來源核對（這次沒有找到能讀到這一天的免費歷史股價來源，沒有逐一嘗試） |
| 2026-10（2026-10-30） | 614.99 | — | 待確認：尚未對第二個獨立來源核對（這次沒有找到能讀到這一天的免費歷史股價來源，沒有逐一嘗試） |

## 已知缺口
- 分部（應用程式家族／Reality Labs）歷史各季：尚未收錄，只讀過 3Q25、3Q26。
- 其餘見 `notes.unavailable`。
