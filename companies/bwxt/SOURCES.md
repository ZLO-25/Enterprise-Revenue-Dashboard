# BWX科技（BWXT） 資料來源與更新步驟

- 資料檔：`data/bwxt.json`（schema `v1`）　頁面：`/bwxt/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**；每股數字（`eps`、`dps`）為美元。
- 頻率：每季。排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md），只補「上次資料之後」的新期間；沒有實質變動就不 commit。
- CIK：`0001486957`。

## 會計年度與期間

會計年度＝曆年（`12-31`）。2015-06-30 分拆火力發電事業（Babcock & Wilcox Enterprises）後改名 BWX Technologies；2015 年前兩季原始季報含火力發電，所以從分拆後第一個完整年度 1Q16 開始。 期間 1Q16–最新一季，共 43 季。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0001486957.json`（新增公司時由 GitHub Actions 的 sec-raw 分支下載，容器讀不到 SEC）。
2. **財報新聞稿（8-K Item 2.02 附件 99.1，精簡版，沒有完整損益表；完整版在 investors.bwxt.com）：3Q26 `https://www.sec.gov/Archives/edgar/data/1486957/000148695726000053/bwxt_93026xerexhibit991.htm`**
3. 投資人關係網站（新聞稿、財報日期、股利宣告）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`、note 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `Revenues`（2017 年以前）→ `RevenueFromContractWithCustomerExcludingAssessedTax` |
| `gp`、`gm` | `gp`＝營收 − `CostOfRevenue`（2023 年起 `CostOfGoodsAndServicesSold`） |
| `opInc`、`om` | `OperatingIncomeLoss`（含合資權益法收益，公司自己的排法） |
| `ni` | `NetIncomeLoss`（歸屬母公司普通股股東） |
| `eps` | `EarningsPerShareDiluted`（10-K 有第四季單季值） |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`（2016 年部分季度只有 `…ContinuingOperations`）（年初累計相減） |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（年初累計相減） |
| `dps` | `CommonStockDividendsPerShareDeclared`（宣告基準）；4Q25 待確認（10-K 全年 0.96 與前三季各 0.25 對不起來） |
| `rd`、`rdB` | 季末後 5–90 天內**第一份**財報 8-K（Item 2.02）的申報日，`rdB:"p"` |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季＝10-K 全年 − 前三季（四季加總＝全年，validate 已核對）。股票分割：期間內沒有。

### 選用區塊
`segments`：無（新聞稿有政府業務／商業業務兩部門營收與營業利益，之後可補）。`guidance.items[]`：全年營收、非 GAAP EPS、自由現金流（Prior Guidance 欄放 guidanceHistory）；公司不給 GAAP 財測。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `bwxt`（GitHub Actions bs-fetch 產生 `data/bs-raw/bwxt.json`，`python3 tools/bs_merge.py bwxt` 與 `--only sbc bwxt` 合併）：`cash`＝`CashAndCashEquivalentsAtCarryingValue`；`debt`＝`LongTermDebtNoncurrent`（或 `LongTermDebt`）＋`LongTermDebtCurrent`／`DebtCurrent`；`buyback`＝`PaymentsForRepurchaseOfCommonStock`；`sbc`＝`ShareBasedCompensation`；`shOut`＝`CommonStockSharesOutstanding`（缺時用封面 `dei:EntityCommonStockSharesOutstanding`）、`dilSh`＝`WeightedAverageNumberOfDilutedSharesOutstanding`（第四季多半沒有單季值）、`equity`＝`StockholdersEquity`、`pretax`、`tax` 同其他美股。沒有值的季度見 notes.unavailable。近似的業主盈餘＝自由現金流 − sbc。

## 電話會議（逐字稿）與非 GAAP
官方網路直播（investors.bwxt.com）；第三方逐字稿尚未選定。公司**有非 GAAP EPS**（排除重組、收購相關費用、退休金調整等），本站一律用 GAAP。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 bwxt 財報 8-K 或 `python3 tools/daily.py inbox bwxt`。沒有新財報 → 只查事件時間軸。
2. 讀新聞稿：兩部門營收與營業利益、GAAP 淨利與 EPS、營業現金流、資本支出、全年展望；完整損益表用 10-Q（XBRL）。
3. 新增一季（`rd`＝新聞稿 8-K 申報日，`rdB:"p"`）；第四季數字＝10-K 全年 − 前三季、EPS 取新聞稿；舊 `guidance` append 進 `guidanceHistory`；更新 `waterfall`、`events`、`summary`（有 segments 的公司同時加 `segments.quarters[]`）。
4. `python3 tools/validate.py bwxt` 通過才繼續。
5. 事件：海軍反應爐與核燃料合約、國家核安全局（NNSA）與能源部合約、在手訂單、新型反應爐（BANR、DRACO）、併購與出售（Kinectrics、PCG、醫療事業）。屬於核心故事線的事件 `cat` 用 `story.cats`（`python3 tools/daily.py story`）。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `BWXT（NYSE，美元）` |
| 股價起點 | 2016-01 |
| 股票分割 | 期間內沒有 |
| EPS 口徑 | GAAP 稀釋 EPS |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/bwxt.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果：待確認：股價回補後抽查最早、中間、最新 3 個月底股價對第二個獨立來源（容器讀不到免費歷史股價網站時維持待確認）。

## 已知缺口
見 `data/bwxt.json` 的 `notes.unavailable`。
