# AXT（AXTI） 資料來源與更新步驟

- 資料檔：`data/axti.json`（schema `v1`）　頁面：`/axti/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（公司規模小，金額保留兩位小數）；每股數字（`eps`）為美元。不配發普通股現金股利，`dps` 全部留空。
- 頻率：每季。排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md），只補「上次資料之後」的新期間；沒有實質變動就不 commit。
- CIK：`0001051627`。

## 會計年度與期間

會計年度＝日曆年（12 月 31 日結束）。`3Q26`＝2026 年 7～9 月。SEC XBRL 的 2011 年季度資料不完整（第一、四季讀不到營收），所以期間從 1Q12 開始。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0001051627.json`（新增公司時由 GitHub Actions 的 sec-raw 分支下載，容器讀不到 SEC；原始檔在 sec-raw 分支 `raw/axti/`）。
2. **財報新聞稿（8-K Item 2.02 附件 99.1，有完整損益表與資產負債表，沒有現金流量表）**：最新一季 `https://www.sec.gov/Archives/edgar/data/1051627/000143774926033941/ex_1013304.htm`。2025 年 7 月起申報代理換人，附件檔名變成 `ex_數字.htm`（sec_raw.py 已能抓）。
3. 投資人關係網站 www.axt.com（新聞稿、電話會議）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`、note 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `Revenues`（2016 年底起 `RevenueFromContractWithCustomerExcludingAssessedTax`，同一期間取最新申報）；2Q13 例外見下方 |
| `gp`、`gm` | `GrossProfit` |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss`＝歸屬 AXT 股東（已扣少數股權） |
| `eps` | `EarningsPerShareDiluted`（2019 年有兩季用 `EarningsPerShareBasicAndDiluted`） |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`（年初累計相減） |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（年初累計相減，正數）；4Q22、4Q23 相減為負數 → 留空（見 notes.unavailable） |
| `dps` | 不配息，留空 |
| `rd`、`rdB` | 季末後 5–120 天內、晚於上一季、**新聞稿裡有稀釋 EPS** 的第一份財報 8-K（Item 2.02）申報日，`rdB:"p"`。公司常先發「營收預告」8-K（沒有 EPS，例如 2018-04-11、2019-01-14、2022-07-06、2024-04-08、2026-01-09、2026-04-20），那些不算。例外：3Q13 的 8-K 附件沒抓到，用 10-Q 申報日 2013-11-08（`rdB:"f"`） |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季＝10-K 全年 − 前三季（四季加總＝全年，validate 已核對）；第四季 EPS 取第四季財報新聞稿。例外：FY2013 10-K 把 2Q13 營收誤標為 22,831 千美元，10-Q 與新聞稿都是 23,831，本頁用 23.831（第四季因此是 18.603，與新聞稿一致）。股票分割：期間內沒有（2026 年 4 月增資 6.325 億美元，股數從約 4,400 萬增加到約 6,400 萬）。

全部 58 季（3Q13 除外）的營收、毛利、營業利益、歸屬淨利都和當季財報新聞稿逐一核對過（誤差 ≤ 0.06 百萬美元）。

### 選用區塊
`segments`：無（10-K 有依產品別：磷化銦、砷化鎵、鍺、原料，之後可補）。`guidance.items[]`：公司在新聞稿裡多半沒有數字財測（只在電話會議口頭說），沒有就留空。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `axti`（GitHub Actions bs-fetch 產生 `data/bs-raw/axti.json`，`python3 tools/bs_merge.py axti` 與 `--only sbc axti` 合併）：`cash`＝`CashAndCashEquivalentsAtCarryingValue`＋`ShortTermInvestments`；`debt`＝`ShortTermBorrowings`（中國子公司的銀行短期借款）＋`LongTermDebtNoncurrent`／`LongTermDebtCurrent`（有才加）；`buyback`＝`PaymentsForRepurchaseOfCommonStock`；`sbc`＝`ShareBasedCompensation`；`shOut`、`dilSh`、`equity`、`pretax`、`tax` 同其他美股。沒有值的季度見 notes.unavailable。

## 電話會議（逐字稿）與非 GAAP
官方網路直播（www.axt.com）；第三方逐字稿尚未選定，讀不到時寫「待確認：逐字稿尚未取得」。公司的非 GAAP 只排除股票酬勞；本站 `eps` 一律用 GAAP 稀釋 EPS。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 axti 財報 8-K 或 `python3 tools/daily.py inbox axti`。注意先分辨是「營收預告」還是完整財報。
2. 讀新聞稿：營收、毛利、營業利益、歸屬 AXT 淨利與稀釋 EPS；營業現金流與資本支出要等 10-Q／10-K（新聞稿沒有現金流量表）。
3. 新增一季（`rd`＝完整財報新聞稿 8-K 申報日，`rdB:"p"`）；第四季數字＝10-K 全年 − 前三季、EPS 取新聞稿；更新 `waterfall`、`events`、`summary`。
4. `python3 tools/validate.py axti` 通過才繼續。
5. 事件：中國出口許可（鎵、鍺、磷化銦）、磷化銦產能與 6 吋產品、北京通美科創板上市、募資。屬於核心故事線的事件 `cat` 用 `story.cats`（`python3 tools/daily.py story`）。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `AXTI（Nasdaq，美元）` |
| 股價起點 | 2012-01（本頁資料起點；1998 年上市） |
| 股票分割 | 期間內沒有。 |
| EPS 口徑 | GAAP 稀釋 EPS |
| `rd` 來源 | 見上方欄位表 |
