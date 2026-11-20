# 星座能源（CEG） 資料來源與更新步驟

- 資料檔：`data/ceg.json`（schema `v1`）　頁面：`/ceg/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**；每股數字（`eps`、`dps`）為美元。
- 頻率：每季。排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md），只補「上次資料之後」的新期間；沒有實質變動就不 commit。
- CIK：`0001868275`。

## 會計年度與期間

會計年度＝曆年（`12-31`）。2022-02-01 自 Exelon 分拆，1Q22 是第一份財報（1 月仍在 Exelon 旗下）。2026-01-07 完成收購 Calpine，2026 年起營收規模不能直接和過去比。 期間 1Q22–最新一季，共 19 季。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0001868275.json`（新增公司時由 GitHub Actions 的 sec-raw 分支下載，容器讀不到 SEC）。
2. **財報新聞稿（8-K Item 2.02 附件 99.1，檔名 `ceg-YYYYMMDD991.htm`）：3Q26 `https://www.sec.gov/Archives/edgar/data/1868275/000186827526000116/ceg-20261109991.htm`。新聞稿有完整損益表與現金流量表。3Q26 的 10-Q XBRL 到 2026-11-20 還沒進 SEC companyfacts，所以 3Q26 全部數字取新聞稿。**
3. 投資人關係網站（新聞稿、財報日期、股利宣告）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`、note 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `Revenues`（含非客戶合約營收，例如衍生性商品） |
| `gp`、`gm` | 電力公司損益表不列毛利。`gp`＝營收 − 新聞稿損益表的「Purchased power and fuel」（XBRL 的 `CostDirectMaterial` 在 1Q22 少了 5 百萬的關係人購電，所以用新聞稿） |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss`（歸屬母公司） |
| `eps` | `EarningsPerShareDiluted`（GAAP，含公允價值變動）；第四季取第四季財報新聞稿（0.10／−0.11／2.71／1.38）。公司另有非 GAAP「Adjusted Operating Earnings」每股，本站不收進 eps |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`（年初累計相減）。2022–2024 年多為負值：應收帳款出售後的遞延收款回收列在投資活動 |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（年初累計相減） |
| `dps` | `CommonStockDividendsPerShareDeclared` 單季值；10-K 的全年欄標的是單季金額，所以第四季待確認 |
| `rd`、`rdB` | 季末後 5–90 天內**第一份**財報 8-K（Item 2.02）的申報日，`rdB:"p"` |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季＝10-K 全年 − 前三季（四季加總＝全年，validate 已核對）。沒有股票分割。

### 選用區塊
`segments`：無（報告部門是地區別，新聞稿只有發電量 GWh，沒有地區營收表）。`guidance.items[]`：全年調整後營運 EPS（非 GAAP）；不給營收財測。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `ceg`（GitHub Actions bs-fetch 產生 `data/bs-raw/ceg.json`，`python3 tools/bs_merge.py ceg` 與 `--only sbc ceg` 合併）：`cash`＝`CashAndCashEquivalentsAtCarryingValue`（不含受限現金）；`debt`＝`LongTermDebtNoncurrent`＋`LongTermDebtAndCapitalLeaseObligationsCurrent`＋`ShortTermBorrowings`（有才加）；`buyback`＝`PaymentsForRepurchaseOfCommonStock`；`sbc`＝`AllocatedShareBasedCompensationExpense`（只有全年值，季度多半讀不到）；`shOut`＝`CommonStockSharesOutstanding`（缺時用封面 `dei:EntityCommonStockSharesOutstanding`）、`dilSh`＝`WeightedAverageNumberOfDilutedSharesOutstanding`（第四季多半沒有單季值）、`equity`＝`StockholdersEquity`、`pretax`、`tax` 同其他美股。沒有值的季度見 notes.unavailable。近似的業主盈餘＝自由現金流 − sbc。

## 電話會議（逐字稿）與非 GAAP
官方只有網路直播（investors.constellationenergy.com）；第三方逐字稿尚未選定。公司**有非 GAAP EPS**（Adjusted Operating Earnings），市場預估多半是這個口徑：比對預估時 `cons.actualAlt` 要填新聞稿的調整後 EPS。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 ceg 財報 8-K 或 `python3 tools/daily.py inbox ceg`。沒有新財報 → 只查事件時間軸。
2. 讀新聞稿：損益表（營收、購電與燃料、營業利益、稅前、所得稅、淨利、稀釋 EPS 與股數）、現金流量表（九個月累計相減）、調整後營運 EPS、全年財測、新長約與併購。
3. 新增一季（`rd`＝新聞稿 8-K 申報日，`rdB:"p"`）；第四季數字＝10-K 全年 − 前三季、EPS 取新聞稿；舊 `guidance` append 進 `guidanceHistory`；更新 `waterfall`、`events`、`summary`（有 segments 的公司同時加 `segments.quarters[]`）。
4. `python3 tools/validate.py ceg` 通過才繼續。
5. 事件：資料中心購電長約（Microsoft、Meta、Amazon、Google）、核電增容／重啟（Crane）、併購（Calpine、RISEC）、政府貸款。屬於核心故事線的事件 `cat` 用 `story.cats`（`python3 tools/daily.py story`）。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `CEG（Nasdaq，美元）` |
| 股價起點 | 2022-02 |
| 股票分割 | 期間內沒有 |
| EPS 口徑 | GAAP 稀釋 EPS |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/ceg.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果：待確認：股價回補後抽查最早、中間、最新 3 個月底股價對第二個獨立來源（容器讀不到免費歷史股價網站時維持待確認）。

## 已知缺口
見 `data/ceg.json` 的 `notes.unavailable`。
