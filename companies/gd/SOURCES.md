# 通用動力（GD） 資料來源與更新步驟

- 資料檔：`data/gd.json`（schema `v1`）　頁面：`/gd/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**；每股數字（`eps`、`dps`）為美元。
- 頻率：每季。排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md），只補「上次資料之後」的新期間；沒有實質變動就不 commit。
- CIK：`0000040533`。

## 會計年度與期間

會計年度＝曆年（`fiscalYearEnd` 填 `12-31`），但第一到第三季在最接近季末的週日結帳（例：3Q26 結束於 2026-10-04），季度標籤用最接近的日曆季。 期間 1Q09–最新一季，共 71 季。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0000040533.json`（新增公司時由 GitHub Actions 的 sec-raw 分支下載，容器讀不到 SEC）。
2. **財報新聞稿（8-K Item 2.02 附件 99.1）：3Q26 `https://www.sec.gov/Archives/edgar/data/40533/000004053326000036/gd-20261004exhibit991.htm`；4Q25 `https://www.sec.gov/Archives/edgar/data/40533/000004053326000003/gd-20251231exhibit991.htm`。注意 2018-02-12 有兩份非財報的 8-K（CSRA 收購），rd 取季末後第一份 2.02。**
3. 投資人關係網站（新聞稿、財報日期、股利宣告）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`、note 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `Revenues`（2025 年以前）→ `RevenueFromContractWithCustomerExcludingAssessedTax`（2026 起）；同一期間取先有值的概念 |
| `gp`、`gm` | 損益表不列毛利。`gp`＝`OperatingIncomeLoss` ＋ `GeneralAndAdministrativeExpense`（＝營收 − 產品與服務營業成本） |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss`（歸屬母公司） |
| `eps` | `EarningsPerShareDiluted`；2026 年起改標 `IncomeLossFromContinuingOperationsPerDilutedShare`（當期沒有停業部門損益，兩者相同）。第四季取第四季財報新聞稿「Earnings per share—diluted」的淨利口徑（4Q09 取 4Q10 新聞稿的去年同期欄 1.57） |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`；2Q26 起只有繼續營業 `…ContinuingOperations` ＋ 停業部門 `CashProvidedByUsedInOperatingActivitiesDiscontinuedOperations`，相加後再年初累計相減 |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（年初累計相減） |
| `dps` | `CommonStockDividendsPerShareDeclared`（宣告基準，前三季單季值）。第四季：XBRL 沒有全年值，4Q20–4Q25 取投資人關係網站 12 月「General Dynamics Board Declares Dividend」新聞稿（1.10／1.19／1.26／1.32／1.42／1.50）；4Q09–4Q19 待確認 |
| `rd`、`rdB` | 季末後 5–90 天內**第一份**財報 8-K（Item 2.02）的申報日，`rdB:"p"` |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季＝10-K 全年 − 前三季（四季加總＝全年，validate 已核對）。沒有股票分割。

### 選用區塊
`segments`：航太、海事系統、作戰系統、科技（1Q21 起，取新聞稿部門營收表，四部門加總＝營收）。`guidance`：新聞稿沒有書面財測（全年展望只在電話會議口頭說明），items 留空。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `gd`（GitHub Actions bs-fetch 產生 `data/bs-raw/gd.json`，`python3 tools/bs_merge.py gd` 與 `--only sbc gd` 合併）：`cash`＝`CashAndCashEquivalentsAtCarryingValue`＋`MarketableSecurities`（有才加）；`debt`＝`LongTermDebtNoncurrent`＋`DebtCurrent`；`buyback`＝`PaymentsForRepurchaseOfCommonStock`；`sbc`＝`ShareBasedCompensation`（年初累計相減）；`shOut`＝`CommonStockSharesOutstanding`（缺時用封面 `dei:EntityCommonStockSharesOutstanding`）、`dilSh`＝`WeightedAverageNumberOfDilutedSharesOutstanding`（第四季多半沒有單季值）、`equity`＝`StockholdersEquity`、`pretax`、`tax` 同其他美股。沒有值的季度見 notes.unavailable。近似的業主盈餘＝自由現金流 − sbc。

## 電話會議（逐字稿）與非 GAAP
官方只有網路直播與簡報（investorrelations.gd.com）；第三方逐字稿尚未選定。公司**沒有非 GAAP EPS**（只有 2012、2017 年的一次性調整說明），本站一律用 GAAP。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 gd 財報 8-K 或 `python3 tools/daily.py inbox gd`。沒有新財報 → 只查事件時間軸。
2. 讀新聞稿：營收、營業利益、淨利、稀釋 EPS、營業現金流、資本支出、四個部門營收、訂單與在手訂單；毛利＝營業利益＋管理費用（從同季 10-Q XBRL 讀 G&A；第四季＝全年 − 前三季）。
3. 新增一季（`rd`＝新聞稿 8-K 申報日，`rdB:"p"`）；第四季數字＝10-K 全年 − 前三季、EPS 取新聞稿；舊 `guidance` append 進 `guidanceHistory`；更新 `waterfall`、`events`、`summary`（有 segments 的公司同時加 `segments.quarters[]`）。
4. `python3 tools/validate.py gd` 通過才繼續。
5. 事件：潛艦合約（維吉尼亞級、哥倫比亞級）、灣流新機型認證與交機、股利調整、庫藏股授權。屬於核心故事線的事件 `cat` 用 `story.cats`（`python3 tools/daily.py story`）。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `GD（NYSE，美元）` |
| 股價起點 | 2009-01 |
| 股票分割 | 期間內沒有 |
| EPS 口徑 | GAAP 稀釋 EPS |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/gd.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果：待確認：股價回補後抽查最早、中間、最新 3 個月底股價對第二個獨立來源（容器讀不到免費歷史股價網站時維持待確認）。

## 已知缺口
見 `data/gd.json` 的 `notes.unavailable`。
