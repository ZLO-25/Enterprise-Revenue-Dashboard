# L3哈里斯（LHX） 資料來源與更新步驟

- 資料檔：`data/lhx.json`（schema `v1`）　頁面：`/lhx/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**；每股數字（`eps`、`dps`）為美元。
- 頻率：每季。排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md），只補「上次資料之後」的新期間；沒有實質變動就不 commit。
- CIK：`0000202058`。

## 會計年度與期間

會計年度約為曆年（52／53 週，在最接近 12 月 31 日的週五結帳，例：FY2025 結束於 2026-01-02），季度也在最接近季末的週五結帳，季度標籤用最接近的日曆季。2019 年以前 Harris 的會計年度在 6 月底結束，2019 下半年是過渡期（10-KT），所以從 1Q20 開始。 期間 1Q20–最新一季，共 27 季。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0000202058.json`（新增公司時由 GitHub Actions 的 sec-raw 分支下載，容器讀不到 SEC）。
2. **財報新聞稿（8-K Item 2.02 附件 99.1）：3Q26 `https://www.sec.gov/Archives/edgar/data/202058/000020205826000084/exhibit991q3cy26earnings.htm`。注意：1Q22～3Q23 的 8-K 只附一頁公告（數字放在公司網站的投資人信），2022-01-14 有一份部門重編的 2.02 8-K（不是財報），rd 取季末後第一份「發布財報」的 8-K。**
3. 投資人關係網站（新聞稿、財報日期、股利宣告）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`、note 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `RevenueFromContractWithCustomerExcludingAssessedTax`。FY2025 的 10-K 把全年值標成錯的期間，改用 10-K 全年值 21,865（與 4Q25 新聞稿一致） |
| `gp`、`gm` | `gp`＝營收 − `CostOfGoodsAndServicesSold`（損益表的 Cost of revenue／Cost of product sales and services） |
| `opInc`、`om` | `OperatingIncomeLoss`（2023 年起）。1Q20～3Q22 損益表沒有營業利益這一行：2020–2021 用新聞稿的 稅前淨利 − 業外收益 − 利息；1Q22～3Q22 用 10-Q XBRL 的同一算法；4Q22 取 4Q23 新聞稿去年同期欄 495 |
| `ni` | `NetIncomeLoss`（歸屬母公司；伊頓 2012 年用 `NetIncomeLossAvailableToCommonStockholdersBasic`） |
| `eps` | `EarningsPerShareDiluted`；第四季取第四季財報新聞稿（0.91／2.46／2.17／0.83／2.37／1.59；4Q22 的 2.17 取 4Q23 新聞稿去年同期欄，因為 4Q22 的 8-K 只有一頁公告） |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`（年初累計相減） |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（年初累計相減） |
| `dps` | `CommonStockDividendsPerShareCashPaid`（實際發放）；2020–2021 年 XBRL 只有全年值，季度待確認 |
| `rd`、`rdB` | 季末後 5–90 天內**第一份**財報 8-K（Item 2.02）的申報日，`rdB:"p"` |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季＝10-K 全年 − 前三季（四季加總＝全年，validate 已核對）。股票分割：期間內沒有。

### 選用區塊
`segments`：無（2022、2023、2026 年三度改部門架構，且有部門間沖銷與「其他」列）。`guidance.items[]`：全年營收、GAAP EPS、營業現金流、資本支出、自由現金流（非 GAAP）；不給單季財測。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `lhx`（GitHub Actions bs-fetch 產生 `data/bs-raw/lhx.json`，`python3 tools/bs_merge.py lhx` 與 `--only sbc lhx` 合併）：`cash`＝`CashAndCashEquivalentsAtCarryingValue`＋`ShortTermInvestments`（有才加）；`debt`＝`LongTermDebtAndCapitalLeaseObligations`（或 `LongTermDebtNoncurrent`）＋`LongTermDebtAndCapitalLeaseObligationsCurrent`＋`ShortTermBorrowings`；`buyback`＝`PaymentsForRepurchaseOfCommonStock`；`sbc`＝`ShareBasedCompensation`；`shOut`＝`CommonStockSharesOutstanding`（缺時用封面 `dei:EntityCommonStockSharesOutstanding`）、`dilSh`＝`WeightedAverageNumberOfDilutedSharesOutstanding`（第四季多半沒有單季值）、`equity`＝`StockholdersEquity`、`pretax`、`tax` 同其他美股。沒有值的季度見 notes.unavailable。近似的業主盈餘＝自由現金流 − sbc。

## 電話會議（逐字稿）與非 GAAP
官方網路直播（investors.l3harris.com）；第三方逐字稿尚未選定。公司**有非 GAAP EPS**（排除收購無形資產攤提、LHX NeXt 等），本站一律用 GAAP。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 lhx 財報 8-K 或 `python3 tools/daily.py inbox lhx`。沒有新財報 → 只查事件時間軸。
2. 讀新聞稿：營收、營業成本、營業利益、淨利、稀釋 EPS、營業現金流、資本支出、訂單與在手訂單、全年財測（Prior 欄放 guidanceHistory）。
3. 新增一季（`rd`＝新聞稿 8-K 申報日，`rdB:"p"`）；第四季數字＝10-K 全年 − 前三季、EPS 取新聞稿；舊 `guidance` append 進 `guidanceHistory`；更新 `waterfall`、`events`、`summary`（有 segments 的公司同時加 `segments.quarters[]`）。
4. `python3 tools/validate.py lhx` 通過才繼續。
5. 事件：飛彈推進大單（THAAD、PAC-3、GMLRS）、戰爭部對飛彈子公司的投資、太空與飛彈預警衛星、部門重組、出售非核心業務。屬於核心故事線的事件 `cat` 用 `story.cats`（`python3 tools/daily.py story`）。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `LHX（NYSE，美元）` |
| 股價起點 | 2020-01 |
| 股票分割 | 期間內沒有 |
| EPS 口徑 | GAAP 稀釋 EPS |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/lhx.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果：待確認：股價回補後抽查最早、中間、最新 3 個月底股價對第二個獨立來源（容器讀不到免費歷史股價網站時維持待確認）。

## 已知缺口
見 `data/lhx.json` 的 `notes.unavailable`。
