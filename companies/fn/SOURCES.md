# Fabrinet（FN） 資料來源與更新步驟

- 資料檔：`data/fn.json`（schema `v1`）　頁面：`/fn/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**；每股數字（`eps`）為美元。不配發現金股利，`dps` 全部留空。
- 頻率：每季。排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md），只補「上次資料之後」的新期間；沒有實質變動就不 commit。
- CIK：`0001408710`。

## 會計年度與期間

會計年度在 6 月最後一個週五結束（例如 FY2026 結束於 2026-06-26）。季度標籤用公司的會計季度：`1Q27`＝2026 年 7～9 月。2010 年 6 月上市，SEC XBRL 從 FY2012 才有完整季度資料，所以期間從 1Q12（2011 年 7～9 月）開始。FY2012、FY2013 的 10-Q 申報期間日期有重複或缺漏（2011 年泰國水災），季末日改用 XBRL 三個月期間的結束日。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0001408710.json`（新增公司時由 GitHub Actions 的 sec-raw 分支下載，容器讀不到 SEC；原始檔在 sec-raw 分支 `raw/fn/`）。
2. **財報新聞稿（8-K Item 2.02 附件 99.1，有完整損益表）**：最新一季 `https://www.sec.gov/Archives/edgar/data/1408710/000140871026000034/fn-20261102xex991q127.htm`
3. 投資人關係網站 investor.fabrinet.com（新聞稿、簡報、電話會議）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`、note 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `SalesRevenueNet`（2014 年以前）→ `Revenues`（同一期間取最新申報） |
| `gp`、`gm` | `GrossProfit` |
| `opInc`、`om` | `OperatingIncomeLoss`（3Q14 含淹水保險理賠） |
| `ni` | `NetIncomeLoss` |
| `eps` | `EarningsPerShareDiluted` |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`（部分年度只有 `…ContinuingOperations`；年初累計相減） |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（年初累計相減，正數） |
| `dps` | 不配息，留空 |
| `rd`、`rdB` | 季末後 5–120 天內、晚於上一季的**第一份**財報 8-K（Item 2.02）申報日，`rdB:"p"`；例外：4Q14 的新聞稿延到 2014-10-16 才發布（收入認列調整），1Q19 沒有財報 8-K，用 10-Q 申報日 2018-11-06（`rdB:"f"`） |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季＝10-K 全年 − 前三季（四季加總＝全年，validate 已核對）；第四季 EPS 取第四季財報新聞稿（XBRL 沒有第四季單季 EPS）。股票分割：期間內沒有。

### 選用區塊
`segments`：無（10-K 有依產品別：光通訊、非光通訊，之後可補）。`guidance.items[]`：下一季營收、GAAP 與非 GAAP EPS（Fabrinet 會給 GAAP EPS 財測）。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `fn`（GitHub Actions bs-fetch 產生 `data/bs-raw/fn.json`，`python3 tools/bs_merge.py fn` 與 `--only sbc fn` 合併）：`cash`＝`CashAndCashEquivalentsAtCarryingValue`＋`ShortTermInvestments`／`MarketableSecuritiesCurrent`；`debt`＝`LongTermDebtNoncurrent`（或 `LongTermDebt`）＋`LongTermDebtCurrent`；`buyback`＝`PaymentsForRepurchaseOfCommonStock`；`sbc`＝`ShareBasedCompensation`；`shOut`＝`CommonStockSharesOutstanding`（缺時用封面 `dei:EntityCommonStockSharesOutstanding`）、`dilSh`＝`WeightedAverageNumberOfDilutedSharesOutstanding`（第四季多半沒有單季值）、`equity`＝`StockholdersEquity`、`pretax`、`tax` 同其他美股。沒有值的季度見 notes.unavailable。近似的業主盈餘＝自由現金流 − sbc。

## 電話會議（逐字稿）與非 GAAP
官方網路直播（investor.fabrinet.com）；第三方逐字稿尚未選定，讀不到時寫「待確認：逐字稿尚未取得」。公司**有非 GAAP EPS**（排除股票酬勞與部分一次性項目），財測也只給非 GAAP EPS；本站 `eps` 一律用 GAAP 稀釋 EPS，市場預期比較時 `cons.actualAlt` 填新聞稿的非 GAAP EPS。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 fn 財報 8-K 或 `python3 tools/daily.py inbox fn`。沒有新財報 → 只查事件時間軸。
2. 讀新聞稿：營收、毛利、營業利益、GAAP 淨利與稀釋 EPS、營業現金流、資本支出、下一季財測。
3. 新增一季（`rd`＝新聞稿 8-K 申報日，`rdB:"p"`）；第四季數字＝10-K 全年 − 前三季、EPS 取新聞稿；舊 `guidance` append 進 `guidanceHistory`；更新 `waterfall`、`events`、`summary`。
4. `python3 tools/validate.py fn` 通過才繼續。
5. 事件：大客戶專案（資料中心光模組、資料中心互連、高效能運算）、新廠房與產能、客戶集中度變化、水災等營運事件。屬於核心故事線的事件 `cat` 用 `story.cats`（`python3 tools/daily.py story`）。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `FN（NYSE，美元）` |
| 股價起點 | 2011-09（本頁資料起點；2010 年 6 月上市） |
| 股票分割 | 期間內沒有。 |
| EPS 口徑 | GAAP 稀釋 EPS |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`）；例外：4Q14 的新聞稿延到 2014-10-16 才發布（收入認列調整），1Q19 沒有財報 8-K，用 10-Q 申報日 2018-11-06（`rdB:"f"`） |

股價檔 `data/prices/fn.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果：待確認：股價回補後抽查最早、中間、最新 3 個月底股價對第二個獨立來源（容器讀不到免費歷史股價網站時維持待確認）。

## 已知缺口
見 `data/fn.json` 的 `notes.unavailable`。
