# 伊頓（ETN） 資料來源與更新步驟

- 資料檔：`data/etn.json`（schema `v1`）　頁面：`/etn/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**；每股數字（`eps`、`dps`）為美元。
- 頻率：每季。排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md），只補「上次資料之後」的新期間；沒有實質變動就不 commit。
- CIK：`0001551182`。

## 會計年度與期間

會計年度＝曆年（`12-31`）。2012-11-30 收購 Cooper 後由愛爾蘭註冊的 Eaton Corporation plc（CIK 1551182）承接；2012 年第三季以前取 Eaton Corporation（CIK 0000031277）的申報（sec-raw 分支 `raw/etncorp/`，本機合併後計算）。 期間 1Q09–最新一季，共 71 季。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0001551182.json`（新增公司時由 GitHub Actions 的 sec-raw 分支下載，容器讀不到 SEC）。
2. **財報新聞稿（8-K Item 2.02 附件 99）：3Q26 `https://www.sec.gov/Archives/edgar/data/1551182/000155118226000037/etn09302026exhibit99.htm`。注意 2015-10-19、2017-10-13、2020-01-27 有非財報的 2.02 8-K；1Q22（2022-05-03）抓到的是 8-K 封面，rd 取季末後第一份「發布財報」的 8-K。**
3. 投資人關係網站（新聞稿、財報日期、股利宣告）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`、note 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `SalesRevenueNet`（2018 年以前）→ `RevenueFromContractWithCustomerExcludingAssessedTax`；另有零星 `Revenues`=0 的錯誤標記，不使用 |
| `gp`、`gm` | `gp`＝營收 − `CostOfRevenue`（Cost of products sold） |
| `opInc`、`om` | 損益表不列營業利益：`opInc`＝營收 − `CostOfRevenue` − `SellingGeneralAndAdministrativeExpense` − `ResearchAndDevelopmentExpense`（不含利息與「其他費用淨額」） |
| `ni` | `NetIncomeLoss`（歸屬母公司；伊頓 2012 年用 `NetIncomeLossAvailableToCommonStockholdersBasic`） |
| `eps` | `EarningsPerShareDiluted`（歸屬伊頓普通股股東）；第四季取第四季財報新聞稿（4Q11 起 1.07／0.46／1.00／1.23／1.15／1.12／1.43／1.46／1.09／1.18／1.37／1.80／2.35／2.45／2.91） |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`（年初累計相減） |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（年初累計相減） |
| `dps` | `CommonStockDividendsPerShareDeclared`（宣告基準；2011 年以前 `…CashPaid`） |
| `rd`、`rdB` | 季末後 5–90 天內**第一份**財報 8-K（Item 2.02）的申報日，`rdB:"p"` |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季＝10-K 全年 − 前三季（四季加總＝全年，validate 已核對）。股票分割：2011 年 2 月 1 拆 2：1Q09～3Q10 的 EPS、股利已除以 2（4Q10 EPS 用公司調整後的比較欄 0.82）。

### 選用區塊
`segments`：美洲電氣、全球電氣、航太、車用（4Q21 起；2025 年以前車用＝Vehicle＋eMobility 兩行相加，2026 年公司合併為 Mobility）。`guidance.items[]`：下一季與全年 GAAP EPS、調整後 EPS（非 GAAP）、有機成長率、部門利潤率。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `etn`（GitHub Actions bs-fetch 產生 `data/bs-raw/etn.json`，`python3 tools/bs_merge.py etn` 與 `--only sbc etn` 合併）：`cash`＝`CashAndCashEquivalentsAtCarryingValue`＋`ShortTermInvestments`；`debt`＝`LongTermDebtAndCapitalLeaseObligations`＋`LongTermDebtAndCapitalLeaseObligationsCurrent`＋`ShortTermBorrowings`；`buyback`＝`PaymentsForRepurchaseOfCommonStock`；`sbc`：伊頓只在全年附註揭露，季度讀不到（全部待確認）。bs-fetch 只讀 CIK 1551182，所以 2012 年以前的資產負債表欄位多半沒有值；`shOut`＝`CommonStockSharesOutstanding`（缺時用封面 `dei:EntityCommonStockSharesOutstanding`）、`dilSh`＝`WeightedAverageNumberOfDilutedSharesOutstanding`（第四季多半沒有單季值）、`equity`＝`StockholdersEquity`、`pretax`、`tax` 同其他美股。沒有值的季度見 notes.unavailable。近似的業主盈餘＝自由現金流 − sbc。

## 電話會議（逐字稿）與非 GAAP
官方網路直播（eaton.com 投資人關係）；第三方逐字稿尚未選定。公司**有非 GAAP EPS**（Adjusted EPS，排除無形資產攤提、併購與重組費用），比對預估時 `cons.actualAlt` 要填新聞稿的調整後 EPS。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 etn 財報 8-K 或 `python3 tools/daily.py inbox etn`。沒有新財報 → 只查事件時間軸。
2. 讀新聞稿：損益表（營收、銷貨成本、銷管、研發、利息、其他、稅前、所得稅、淨利、稀釋 EPS）、四個部門營收與利潤、訂單與在手訂單成長、下一季與全年財測（舊的放 guidanceHistory）。
3. 新增一季（`rd`＝新聞稿 8-K 申報日，`rdB:"p"`）；第四季數字＝10-K 全年 − 前三季、EPS 取新聞稿；舊 `guidance` append 進 `guidanceHistory`；更新 `waterfall`、`events`、`summary`（有 segments 的公司同時加 `segments.quarters[]`）。
4. `python3 tools/validate.py etn` 通過才繼續。
5. 事件：資料中心相關收購（Boyd Thermal、Fibrebond、COL Group）、車用業務分拆、訂單與在手訂單成長、股利調升。屬於核心故事線的事件 `cat` 用 `story.cats`（`python3 tools/daily.py story`）。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `ETN（NYSE，美元）` |
| 股價起點 | 2009-01 |
| 股票分割 | 2011 年 2 月 1 拆 2：1Q09～3Q10 的 EPS、股利已除以 2（4Q10 EPS 用公司調整後的比較欄 0.82） |
| EPS 口徑 | GAAP 稀釋 EPS |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/etn.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果：待確認：股價回補後抽查最早、中間、最新 3 個月底股價對第二個獨立來源（容器讀不到免費歷史股價網站時維持待確認）。

## 已知缺口
見 `data/etn.json` 的 `notes.unavailable`。
