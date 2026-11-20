# 雷神技術（RTX） 資料來源與更新步驟

- 資料檔：`data/rtx.json`（schema `v1`）　頁面：`/rtx/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**；每股數字（`eps`、`dps`）為美元。
- 頻率：每季。排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md），只補「上次資料之後」的新期間；沒有實質變動就不 commit。
- CIK：`0000101829`。

## 會計年度與期間

會計年度＝曆年（`12-31`）。SEC 代號 101829 原本是聯合技術（UTC），2020-04-03 與雷神合併並分拆 Otis、Carrier，所以從合併後第一個完整年度 1Q21 開始。 期間 1Q21–最新一季，共 23 季。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0000101829.json`（新增公司時由 GitHub Actions 的 sec-raw 分支下載，容器讀不到 SEC）。
2. **財報新聞稿（8-K Item 2.02 附件 99）：3Q26 `https://www.sec.gov/Archives/edgar/data/101829/000010182926000030/a2026-10x208xkerexhibit99.htm`。注意 2025-02-03 有一份董事長任命的 8-K，不是財報。**
3. 投資人關係網站（新聞稿、財報日期、股利宣告）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`、note 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `Revenues`（2024 年以前）→ `RevenueFromContractWithCustomerExcludingAssessedTax`；同一期間取先有值的概念 |
| `gp`、`gm` | XBRL 沒有單獨的營業成本：`gp`＝營收 −（`CostsAndExpenses` − `ResearchAndDevelopmentExpense` − `SellingGeneralAndAdministrativeExpense`），已逐季對新聞稿 Cost of sales 相符 |
| `opInc`、`om` | `OperatingIncomeLoss`（含其他收入淨額）。4Q23 用 10-K 全年 − 前三季得 1,847，新聞稿寫 1,777（公司事後調整前幾季，未逐季公布） |
| `ni` | `NetIncomeLoss`（歸屬母公司；伊頓 2012 年用 `NetIncomeLossAvailableToCommonStockholdersBasic`） |
| `eps` | `EarningsPerShareDiluted`（歸屬普通股股東）；第四季取第四季財報新聞稿（0.46／0.96／1.05／1.10／1.19） |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`（2021 年只有繼續營業 `…ContinuingOperations`）（年初累計相減） |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（2022 年以前 `PaymentsToAcquireProductiveAssets`）（年初累計相減） |
| `dps` | `CommonStockDividendsPerShareDeclared`（宣告基準：常在第二季宣告兩次，第三季為 0，全年加總正確） |
| `rd`、`rdB` | 季末後 5–90 天內**第一份**財報 8-K（Item 2.02）的申報日，`rdB:"p"` |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季＝10-K 全年 − 前三季（四季加總＝全年，validate 已核對）。股票分割：期間內沒有（2020 年合併換股不是分割）。

### 選用區塊
`segments`：無（新聞稿的部門表把營收與營業利益分段列，另有沖銷與企業項目；之後可補）。`guidance.items[]`：全年調整後營收、調整後 EPS、自由現金流（全部非 GAAP，標明）。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `rtx`（GitHub Actions bs-fetch 產生 `data/bs-raw/rtx.json`，`python3 tools/bs_merge.py rtx` 與 `--only sbc rtx` 合併）：`cash`＝`CashAndCashEquivalentsAtCarryingValue`；`debt`＝`LongTermDebtAndCapitalLeaseObligations`＋`LongTermDebtAndCapitalLeaseObligationsCurrent`＋`ShortTermBorrowings`（含商業本票）；`buyback`＝`PaymentsForRepurchaseOfCommonStock`；`sbc`＝`ShareBasedCompensation`；`shOut`＝`CommonStockSharesOutstanding`（缺時用封面 `dei:EntityCommonStockSharesOutstanding`）、`dilSh`＝`WeightedAverageNumberOfDilutedSharesOutstanding`（第四季多半沒有單季值）、`equity`＝`StockholdersEquity`、`pretax`、`tax` 同其他美股。沒有值的季度見 notes.unavailable。近似的業主盈餘＝自由現金流 − sbc。

## 電話會議（逐字稿）與非 GAAP
官方網路直播（investors.rtx.com）；第三方逐字稿尚未選定。公司**有非 GAAP EPS**（Adjusted EPS，排除收購會計調整、重組與一次性項目），市場預估多半是這個口徑：比對預估時 `cons.actualAlt` 要填新聞稿的調整後 EPS。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 rtx 財報 8-K 或 `python3 tools/daily.py inbox rtx`。沒有新財報 → 只查事件時間軸。
2. 讀新聞稿：損益表（營收、營業成本、研發、銷管、其他收入、營業利益、退休金收益、利息、稅前、所得稅、少數股權、淨利、稀釋 EPS）、在手訂單、全年展望（「up from」的前一版放 guidanceHistory）。
3. 新增一季（`rd`＝新聞稿 8-K 申報日，`rdB:"p"`）；第四季數字＝10-K 全年 − 前三季、EPS 取新聞稿；舊 `guidance` append 進 `guidanceHistory`；更新 `waterfall`、`events`、`summary`（有 segments 的公司同時加 `segments.quarters[]`）。
4. `python3 tools/validate.py rtx` 通過才繼續。
5. 事件：飛彈多年期合約（愛國者、戰斧、AMRAAM、SM 系列）、GTF 引擎檢修進度與費用、部門重組、經營層異動、庫藏股。屬於核心故事線的事件 `cat` 用 `story.cats`（`python3 tools/daily.py story`）。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `RTX（NYSE，美元）` |
| 股價起點 | 2021-01 |
| 股票分割 | 期間內沒有（2020 年合併換股不是分割） |
| EPS 口徑 | GAAP 稀釋 EPS |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/rtx.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果：待確認：股價回補後抽查最早、中間、最新 3 個月底股價對第二個獨立來源（容器讀不到免費歷史股價網站時維持待確認）。

## 已知缺口
見 `data/rtx.json` 的 `notes.unavailable`。
