# 高意（COHR） 資料來源與更新步驟

- 資料檔：`data/cohr.json`（schema `v1`）　頁面：`/cohr/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**；每股數字（`eps`）為美元。不配發現金股利，`dps` 全部留空。
- 頻率：每季。排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md），只補「上次資料之後」的新期間；沒有實質變動就不 commit。
- CIK：`0000820318`。

## 會計年度與期間

會計年度 6 月 30 日結束。季度標籤用公司的會計季度：`1Q27`＝2026 年 7～9 月。前身 II-VI：2019-09 併入 Finisar、2022 年併入 Coherent Inc. 後改名 Coherent Corp.（2022-09-08）。FY2014 以前的損益表沒有「營業利益」小計，所以期間從 1Q15（2014 年 7～9 月）開始。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0000820318.json`（新增公司時由 GitHub Actions 的 sec-raw 分支下載，容器讀不到 SEC；原始檔在 sec-raw 分支 `raw/cohr/`）。
2. **財報新聞稿（8-K Item 2.02 附件 99.1，有完整損益表）**：最新一季 `https://www.sec.gov/Archives/edgar/data/820318/000119312526447200/d176836dex991.htm`
3. 投資人關係網站 investors.coherent.com（新聞稿、簡報、電話會議）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`、note 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `Revenues` → `RevenueFromContractWithCustomerExcludingAssessedTax`（同一期間取最新申報） |
| `gp`、`gm` | 營收 − `CostOfGoodsAndServicesSold`（舊年度 `CostOfGoodsSold`）；XBRL 沒有毛利小計 |
| `opInc`、`om` | 4Q24 以前 `OperatingIncomeLoss`；**1Q25 起 XBRL 沒有標**，改用財報新聞稿 Table 6「Operating income on GAAP basis」（公司定義＝稅前淨利加回利息費用與其他業外收支）；FY2025、FY2026 全年也取新聞稿 |
| `ni` | `NetIncomeLoss`（歸屬 Coherent；2023 年底起碳化矽事業有少數股權） |
| `eps` | `EarningsPerShareDiluted`（歸屬普通股，已扣特別股股利，所以有些季度淨利為正、EPS 為負） |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`（部分年度只有 `…ContinuingOperations`；年初累計相減） |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（年初累計相減，正數） |
| `dps` | 不配息，留空 |
| `rd`、`rdB` | 季末後 5–120 天內、晚於上一季的**第一份**財報 8-K（Item 2.02）申報日，`rdB:"p"` |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季＝10-K 全年 − 前三季（四季加總＝全年，validate 已核對）；第四季 EPS 取第四季財報新聞稿（XBRL 沒有第四季單季 EPS）。股票分割：期間內沒有（2011 年的 1 拆 2 在本頁期間之前）。

### 選用區塊
`segments`：無（新聞稿有資料中心與通訊、工業兩部門，2025 年起口徑多次調整，之後再補）。`guidance.items[]`：下一季營收、非 GAAP 毛利率、非 GAAP EPS，另有年度與長期目標寫在 note；公司不給 GAAP 財測。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `cohr`（GitHub Actions bs-fetch 產生 `data/bs-raw/cohr.json`，`python3 tools/bs_merge.py cohr` 與 `--only sbc cohr` 合併）：`cash`＝`CashAndCashEquivalentsAtCarryingValue`＋`ShortTermInvestments`（多數季度沒有）；`debt`＝`LongTermDebtNoncurrent`＋`LongTermDebtCurrent`；`buyback`＝`PaymentsForRepurchaseOfCommonStock`；`sbc`＝`ShareBasedCompensation`；`shOut`＝`CommonStockSharesOutstanding`（缺時用封面 `dei:EntityCommonStockSharesOutstanding`）、`dilSh`＝`WeightedAverageNumberOfDilutedSharesOutstanding`（第四季多半沒有單季值）、`equity`＝`StockholdersEquity`、`pretax`、`tax` 同其他美股。沒有值的季度見 notes.unavailable。近似的業主盈餘＝自由現金流 − sbc。

## 電話會議（逐字稿）與非 GAAP
官方網路直播（investors.coherent.com）；第三方逐字稿尚未選定，讀不到時寫「待確認：逐字稿尚未取得」。公司**有非 GAAP EPS**（排除股票酬勞、併購無形資產攤銷、重組、出售事業利益、整合費用等），財測也只給非 GAAP EPS；本站 `eps` 一律用 GAAP 稀釋 EPS，市場預期比較時 `cons.actualAlt` 填新聞稿的非 GAAP EPS。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 cohr 財報 8-K 或 `python3 tools/daily.py inbox cohr`。沒有新財報 → 只查事件時間軸。
2. 讀新聞稿：營收、毛利、營業利益、GAAP 淨利與稀釋 EPS、營業現金流、資本支出、下一季財測。
3. 新增一季（`rd`＝新聞稿 8-K 申報日，`rdB:"p"`）；第四季數字＝10-K 全年 − 前三季、EPS 取新聞稿；舊 `guidance` append 進 `guidanceHistory`；更新 `waterfall`、`events`、`summary`。
4. `python3 tools/validate.py cohr` 通過才繼續。
5. 事件：AI 資料中心光收發模組（800G、1.6T）與 InP 雷射產能、光路交換器、碳化矽事業、出售非核心事業、經營團隊與長期毛利率目標。屬於核心故事線的事件 `cat` 用 `story.cats`（`python3 tools/daily.py story`）。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `COHR（NYSE，美元）` |
| 股價起點 | 2014-09（本頁資料起點；公司更早就已上市） |
| 股票分割 | 期間內沒有（2011 年的 1 拆 2 在本頁期間之前）。 |
| EPS 口徑 | GAAP 稀釋 EPS |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/cohr.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果：待確認：股價回補後抽查最早、中間、最新 3 個月底股價對第二個獨立來源（容器讀不到免費歷史股價網站時維持待確認）。

## 已知缺口
見 `data/cohr.json` 的 `notes.unavailable`。
