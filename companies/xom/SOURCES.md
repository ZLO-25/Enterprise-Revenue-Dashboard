# 埃克森美孚（XOM） 資料來源與更新步驟

- 資料檔：`data/xom.json`（schema `v1`）　頁面：`/xom/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**；每股數字（`eps`、`dps`）為美元。
- 頻率：每季。排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md），只補「上次資料之後」的新期間；沒有實質變動就不 commit。
- CIK：`0002115436（2026-07-01 起；之前 0000034088）`。

## 會計年度與期間

會計年度＝曆年（`12-31`）。2026-07-01 遷冊德州的控股公司重組後，申報人改為 ExxonMobil Holdings Corporation（CIK 2115436）；1Q26 以前取 Exxon Mobil Corporation（CIK 34088）的申報（sec-raw 分支 `raw/xom/`＋`raw/xomh/`，本機合併後計算；`companies.json` 的 `cikPrev` 讓 bs-fetch 一起抓舊代號）。從 1Q18 開始。 期間 1Q18–最新一季，共 35 季。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0002115436.json`（2Q26 起）與 `https://data.sec.gov/api/xbrl/companyfacts/CIK0000034088.json`（1Q26 以前）（新增公司時由 GitHub Actions 的 sec-raw 分支下載，容器讀不到 SEC）。
2. **財報新聞稿（8-K Item 2.02 附件 99.1）：3Q26 `https://www.sec.gov/Archives/edgar/data/2115436/000211543626000018/livef8k3q26991.htm`。新聞稿沒有完整損益表（只有各部門獲利、產量、現金流），損益細項用 10-Q XBRL。**
3. 投資人關係網站（新聞稿、財報日期、股利宣告）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`、note 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | 損益表的「營收與其他收入合計」＝`CostsAndExpenses`＋稅前淨利（`IncomeLossFromContinuingOperationsBeforeIncomeTaxes…`）。XBRL 的 `Revenues` 前後口徑不一（2018～2019 部分季度只標銷售收入，之後重編成合計），所以不直接用 |
| `gp`、`gm` | 石油公司不列毛利：`gp`＝營收 −（`CostsAndExpenses` − 銷管 − `DepreciationDepletionAndAmortization` − `ExplorationExpense` − `InterestExpense` − `TaxesOther`），即減掉原油與產品採購、生產與製造費用（含少量非服務退休金費用） |
| `opInc`、`om` | 損益表不列營業利益：`opInc`＝營收 −（`CostsAndExpenses` − `InterestExpense`）＝稅前淨利＋利息 |
| `ni` | `NetIncomeLoss`（歸屬母公司普通股股東） |
| `eps` | `EarningsPerShareDiluted`；第四季取第四季財報新聞稿（1.41／1.33／−4.70／2.08／3.09／1.91／1.72／1.53） |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`（年初累計相減） |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（Additions to property, plant and equipment）（年初累計相減） |
| `dps` | `CommonStockDividendsPerShareCashPaid`（實際發放） |
| `rd`、`rdB` | 季末後 5–90 天內**第一份**財報 8-K（Item 2.02）的申報日，`rdB:"p"` |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季＝10-K 全年 − 前三季（四季加總＝全年，validate 已核對）。股票分割：期間內沒有。

### 選用區塊
`segments`：無（四個部門只公布獲利，不公布營收）。`guidance`：公司不給營收、EPS 財測，只放回購計畫。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `xom`（GitHub Actions bs-fetch 產生 `data/bs-raw/xom.json`，`python3 tools/bs_merge.py xom` 與 `--only sbc xom` 合併）：`cash`＝`CashAndCashEquivalentsAtCarryingValue`；`debt`＝`LongTermDebtAndCapitalLeaseObligations`＋`DebtCurrent`；`buyback`＝`PaymentsForRepurchaseOfCommonStock`；`sbc`＝`ShareBasedCompensation`（XBRL 有才填）；`shOut`＝`CommonStockSharesOutstanding`（缺時用封面 `dei:EntityCommonStockSharesOutstanding`）、`dilSh`＝`WeightedAverageNumberOfDilutedSharesOutstanding`（第四季多半沒有單季值）、`equity`＝`StockholdersEquity`、`pretax`、`tax` 同其他美股。沒有值的季度見 notes.unavailable。近似的業主盈餘＝自由現金流 − sbc。

## 電話會議（逐字稿）與非 GAAP
官方網路直播（investor.exxonmobil.com）；第三方逐字稿尚未選定。公司**有非 GAAP 盈餘**（Earnings excluding identified items，另有排除「估計時間差」的版本），本站一律用 GAAP。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 xom 財報 8-K 或 `python3 tools/daily.py inbox xom`。沒有新財報 → 只查事件時間軸。
2. 讀新聞稿：GAAP 盈餘與 EPS、各部門獲利、產量、營業現金流、自由現金流、股東回饋；損益細項（成本費用合計、稅前、利息、銷管、折舊、探勘、其他稅捐）用 10-Q XBRL。
3. 新增一季（`rd`＝新聞稿 8-K 申報日，`rdB:"p"`）；第四季數字＝10-K 全年 − 前三季、EPS 取新聞稿；舊 `guidance` append 進 `guidanceHistory`；更新 `waterfall`、`events`、`summary`（有 segments 的公司同時加 `segments.quarters[]`）。
4. `python3 tools/validate.py xom` 通過才繼續。
5. 事件：蓋亞那與二疊紀產量、LNG 投產、併購（先鋒、Denbury）、結構性降本、回購計畫、中東等外部事件、大額減損。屬於核心故事線的事件 `cat` 用 `story.cats`（`python3 tools/daily.py story`）。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `XOM（NYSE，美元）` |
| 股價起點 | 2018-01 |
| 股票分割 | 期間內沒有 |
| EPS 口徑 | GAAP 稀釋 EPS |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/xom.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果：待確認：股價回補後抽查最早、中間、最新 3 個月底股價對第二個獨立來源（容器讀不到免費歷史股價網站時維持待確認）。

## 已知缺口
見 `data/xom.json` 的 `notes.unavailable`。
