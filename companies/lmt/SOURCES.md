# 洛克希德馬丁（LMT） 資料來源與更新步驟

- 資料檔：`data/lmt.json`（schema `v1`）　頁面：`/lmt/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**；每股數字（`eps`、`dps`）為美元。
- 頻率：每季。排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md），只補「上次資料之後」的新期間；沒有實質變動就不 commit。
- CIK：`0000936468`。

## 會計年度與期間

會計年度＝曆年（`12-31`），但第一到第三季在最接近季末的週日結帳（例：3Q26 結束於 2026-09-27），季度標籤用最接近的日曆季。 期間 1Q09–最新一季，共 71 季。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0000936468.json`（新增公司時由 GitHub Actions 的 sec-raw 分支下載，容器讀不到 SEC）。
2. **財報新聞稿（8-K Item 2.02 附件 99.1，檔名 `ex991qNyyyy.htm`）：3Q26 `https://www.sec.gov/Archives/edgar/data/936468/000162828026066780/ex991q32026.htm`。注意 2022-06-27 有一份非季報的 2.02 8-K，rd 取季末後第一份。**
3. 投資人關係網站（新聞稿、財報日期、股利宣告）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`、note 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `SalesRevenueNet`（2017 年以前）→ `Revenues`；同一期間取先有值的概念 |
| `gp`、`gm` | `GrossProfit`（公司損益表的 Gross profit）；營業利益另含「其他營業收入淨額」，偶爾高於毛利 |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss`（歸屬母公司） |
| `eps` | `EarningsPerShareDiluted`；2009–2020 年第四季取 10-K XBRL 的單季值，2021 年起取第四季財報新聞稿（7.47／7.40／7.58／2.22／5.80） |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`（年初累計相減） |
| `capex` | `PaymentsToAcquireProductiveAssets`（2010 起）→ `PaymentsToAcquirePropertyPlantAndEquipment`（較早）（年初累計相減） |
| `dps` | `CommonStockDividendsPerShareCashPaid`（**實際發放**基準；洛克希德常在第三季宣告第四季股利，用宣告基準會出現某季兩次、某季零次）。2013 年起第四季＝全年 − 前三季；4Q09–4Q12 XBRL 沒有全年值，待確認 |
| `rd`、`rdB` | 季末後 5–90 天內**第一份**財報 8-K（Item 2.02）的申報日，`rdB:"p"` |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季＝10-K 全年 − 前三季（四季加總＝全年，validate 已核對）。沒有股票分割。

### 選用區塊
`segments`：航空、飛彈與火控、旋翼與任務系統、太空（1Q18 起，取新聞稿部門營收表）。`guidance.items[]`：全年營收、稀釋 EPS、營業現金流、資本支出、自由現金流（非 GAAP，標明）；不給單季財測。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `lmt`（GitHub Actions bs-fetch 產生 `data/bs-raw/lmt.json`，`python3 tools/bs_merge.py lmt` 與 `--only sbc lmt` 合併）：`cash`＝`CashAndCashEquivalentsAtCarryingValue`；`debt`＝`LongTermDebtNoncurrent`＋`LongTermDebtCurrent`＋`CommercialPaperAtCarryingValue`（有才加）；`buyback`＝`PaymentsForRepurchaseOfCommonStock`；`sbc`＝`ShareBasedCompensation`；`shOut`＝`CommonStockSharesOutstanding`（缺時用封面 `dei:EntityCommonStockSharesOutstanding`）、`dilSh`＝`WeightedAverageNumberOfDilutedSharesOutstanding`（第四季多半沒有單季值）、`equity`＝`StockholdersEquity`、`pretax`、`tax` 同其他美股。沒有值的季度見 notes.unavailable。近似的業主盈餘＝自由現金流 − sbc。

## 電話會議（逐字稿）與非 GAAP
官方只有網路直播（investors.lockheedmartin.com）；第三方逐字稿尚未選定。新聞稿有「調整後」EPS 說明（排除專案虧損、退休金結算等），本站一律用 GAAP 稀釋 EPS。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 lmt 財報 8-K 或 `python3 tools/daily.py inbox lmt`。沒有新財報 → 只查事件時間軸。
2. 讀新聞稿：營收、毛利、營業利益、淨利、稀釋 EPS、營業現金流、資本支出、四個部門營收與營業利益、在手訂單、全年財測（新舊兩欄，舊的放 guidanceHistory）。
3. 新增一季（`rd`＝新聞稿 8-K 申報日，`rdB:"p"`）；第四季數字＝10-K 全年 − 前三季、EPS 取新聞稿；舊 `guidance` append 進 `guidanceHistory`；更新 `waterfall`、`events`、`summary`（有 segments 的公司同時加 `segments.quarters[]`）。
4. `python3 tools/validate.py lmt` 通過才繼續。
5. 事件：F-35 批次合約、飛彈多年期合約、機密專案虧損、股利調升（每年 9～10 月）、庫藏股授權。屬於核心故事線的事件 `cat` 用 `story.cats`（`python3 tools/daily.py story`）。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `LMT（NYSE，美元）` |
| 股價起點 | 2009-01 |
| 股票分割 | 期間內沒有 |
| EPS 口徑 | GAAP 稀釋 EPS |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/lmt.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果：待確認：股價回補後抽查最早、中間、最新 3 個月底股價對第二個獨立來源（容器讀不到免費歷史股價網站時維持待確認）。

## 已知缺口
見 `data/lmt.json` 的 `notes.unavailable`。
