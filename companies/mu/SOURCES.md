# 美光 Micron Technology（MU）資料來源與更新步驟

- 資料檔：`data/mu.json`（schema `v1`）　頁面：`/mu/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`）；每股數字（`eps`、`dps`）為美元。期間沒有股票分割，EPS 不用換算。
- CIK：`0000723125`。頻率：每季。財報日約在 3、6、9、12 月下旬（美股收盤後）。
- 排程：週二至週六 08:30（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md；公布日隔天先做「快報」，再「補完」「核對」）。只補「上次資料之後」的新期間；沒有新財報的月份只檢查事件與公布日；沒有實質變動就不 commit。

## 會計年度與季度標籤

美光的會計年度是 **52／53 週制**，在 8 月底或 9 月初最接近的星期四結束，**季度標籤用公司自己的會計年度**：

```
FY2026 = 2025/8/29 ─ 2026/9/3（53 週，第四季 14 週）
  1Q26 = 2025/8/29 ─ 2025/11/27
  2Q26 = 2025/11/28 ─ 2026/2/26
  3Q26 = 2026/2/27 ─ 2026/5/28
  4Q26 = 2026/5/29 ─ 2026/9/3
FY2027 第一季 ≈ 2026/9–11（2026/12 中下旬公布）
```
53 週年度：FY2015、FY2020、FY2026。季度對應規則（程式用）：季底月份 11–12 月＝下一個 FY 的 Q1；2–3 月＝Q2；5–6 月＝Q3；8–9 月＝Q4。

## 期間

1Q10（FY2010 第一季，2009/9–12）–最新一季。FY2009 的 XBRL 只有第一季與全年，沒有第二、三季，所以從 FY2010 開始。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyconcept/CIK0000723125/us-gaap/{概念}.json`（WebFetch 讀得到；容器 curl 會被擋）。讀法：每個 (start, end) 取最近一次申報的值。
2. **財報新聞稿（8-K 附件 99.1）**：`https://www.sec.gov/Archives/edgar/data/723125/{accession}/a{年}q{季}ex991-pressrelease.htm`（例 `000072312526000018/a2026q4ex991-pressrelease.htm`）。第四季 EPS、下一季財測、股利都在這裡。
3. 投資人關係 `https://investors.micron.com/`。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`。

## 欄位定義（`quarters[]`）

| 欄位 | XBRL 概念與口徑 |
| --- | --- |
| `rev` | FY2017 以前 `SalesRevenueNet`；FY2018 起 `RevenueFromContractWithCustomerExcludingAssessedTax` |
| `gp`、`gm` | `GrossProfit` |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss`（歸屬美光） |
| `eps` | `EarningsPerShareDiluted`；第四季見下 |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`，年初累計相減；FY2013 全年與 FY2014–FY2016 改用 `NetCashProvidedByUsedInOperatingActivitiesContinuingOperations` |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（Expenditures for property, plant, and equipment），年初累計相減 |
| `dps` | `CommonStockDividendsPerShareDeclared`；2021 年 8 月開始配息 |

### 第四季推算
- 營收、毛利、淨利：FY2020 以前 XBRL 有第四季單季值；FY2021 以後用 **全年 − 前三季**，並與新聞稿核對（例：4Q24 營收 7,750、淨利 887）。
- EPS：FY2020 以前取 XBRL；FY2021 以後取新聞稿（FY2021 2.39、FY2022 1.35、FY2023 −1.31、FY2024 0.79、FY2025 2.83、FY2026 32.87）。
- 季度 EPS 加總不一定等於全年（股數變動、虧損季不計稀釋），這是正常的。

## 核對規則（`python3 tools/validate.py mu`）

1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年（營收、毛利、營業利益、淨利、營業現金流、資本支出）。
3. `waterfall` 小計加總；第一列營收＝最新一季 `rev`。
4. 財測區間上下限沒有顛倒。

**任何一項沒過就不發佈**，回到來源修資料，不要放寬核對。

## 更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）

1. 查有沒有新財報 8-K（WebSearch `Micron fiscal Q{季} {年} results`，或 SEC EDGAR 8-K 清單）。**沒有新財報 → 跳到第 6 步。**
2. 讀新聞稿：單季營收、營業成本、毛利、研發、銷管、其他營業、營業利益、利息、其他、所得稅、權益法損益、淨利、稀釋 EPS；現金流（新聞稿非 GAAP 對照表有單季營業現金流與資本支出）；下一季財測；股利。
3. 10-Q／10-K 進 XBRL API 後，用 API 核對（以 XBRL 為準）。第四季：營收等用全年減前三季，EPS 用新聞稿；新增 `annual`（`note` 寫 FY 結束日、是否 53 週）。
4. 更新 `guidance`（下一季營收、毛利率、營業費用、EPS）、`waterfall`、`events`。
5. `python3 tools/validate.py mu`；通過才繼續。
6. 查事件：股利調整、重大投資（新廠、補助）、產品（HBM 世代）；優先 8-K 與 investors.micron.com。
7. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 已知缺口

- FY2009 以前：見「期間」。
- FY2011 全年營業利益：XBRL 全年 761 與四季加總 755 差 6，全年留空。
- 每股股利 4Q21、1Q22、4Q22：沒有單季 XBRL 值，留空。
- 業務單位營收：尚未收錄。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `MU`（主要掛牌地普通股，幣別 美元） |
| 股價起點 | 2009-09 |
| 股票分割 | 無股票分割（2000 年代之後）（Yahoo Close 已依分割調整、不含股利調整，才跟本站已換算成今天股數的 EPS 對得上） |
| EPS 口徑 | 稀釋 EPS；多次虧損期間，本益比留白是正確行為；都是公認會計準則數字，不用調整後 EPS |
| 財報公布日 `rd` 來源 | SEC XBRL 的 10-Q／10-K 申報日（rdB:f）；4Q26 用 10-K 申報日 |

**更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）**
1. 新增一季時，同時填該季 `rd`（那一季 EPS 第一次公開的日期）與 `rdB`。讀不到就填 `null`，在 `notes.unavailable` 加「待確認：<季度> 的財報公布日（rd）：原因」，**不可以用「季度結束後幾天」推算**。最新一季的 `rd` 不可為 null。
2. 股價檔 `data/prices/mu.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填、不修改；排程只檢查上個月有沒有進來。
3. 本益比（`tools/pe.py`）與預估本益比不存檔，建置時算出；預估只有每月 1–6 日 Actions 存下的快照，**不回填**。
4. 若這家公司發生股票分割：同一次完成 EPS 重編與股價檔重抓（手動觸發 prices-monthly 並填 `accept=mu`），否則 validate 會因相鄰月份本益比跳動超過 3 倍而失敗。
5. 抽查紀錄（回補時每家人工對第二個獨立來源抽 3 個月：最早一個月、最近一次分割前一個月、最新一個月）：見下表。

| 月份 | Yahoo 收盤價 | 第二來源 | 結果 |
|---|---|---|---|
| 2009-09（2009-09-30） | 8.2 | — | 待確認：2026-11-12 嘗試的免費來源只提供最近約 50 個交易日，讀不到這一天，尚未完成第二來源核對 |
| 2018-06（2018-06-29） | 52.44 | — | 待確認：2026-11-12 嘗試的免費來源只提供最近約 50 個交易日，讀不到這一天，尚未完成第二來源核對 |
| 2026-10（2026-10-30） | 884.74 | stockanalysis.com/stocks/mu/history | 一致（884.74；2026-11-12 讀取，頁面標示已依分割調整） |


## 資產負債表欄位（shOut、dilSh、cash、debt、buyback、equity、pretax、tax）
- 來源：SEC EDGAR XBRL companyconcept API，由 GitHub Actions 的 `bs-fetch` 產生提案（`data/bs-raw/<代號>.json`），`tools/bs_merge.py` 合併進資料檔。各欄位用哪些 XBRL 概念組成，寫在 `tools/bs_map.json`（必要項缺任何一項就整格填 null，不做部分加總）。
- 口徑：shOut＝期末在外流通股數（百萬股，分割後）；dilSh＝當季稀釋加權股數；cash＝現金及約當現金（不含有價證券）；debt＝有息負債（短期＋長期）；buyback＝當季股票買回金額（正數；年度累計相減得單季）；equity＝股東權益；pretax／tax＝稅前淨利／所得稅費用。
- 讀不到的季度為 null，原因彙整在 `notes.unavailable` 以「待確認：資產負債表欄位」開頭的幾行。新一季快報時，重跑 bs-fetch 後再 merge，或直接讀 10-Q／10-K 手動補。
- 合併時自動擋下：淨利÷稀釋股數與 EPS 對不上、股數差一個數量級、買回／負債／現金為負。

## 核對紀錄
- 2026-11-12：FY2026／4Q26 對 10-K（2026-10-09 申報，accn 0000723125-26-000023，期末 2026-09-03）核對，**全年值一致**：營收 133,188、毛利 107,504、營業利益 99,340、淨利 84,969、稀釋 EPS 74.33、營業現金流 89,675、資本支出 30,712、股東權益 138,378、期末股數 1,131；4Q26 單季（全年 − 前三季）由 validate 的四季加總核對通過。來源：sec.gov/Archives/edgar/data/723125/000072312526000023/R3.htm、R4.htm、R7.htm。
- 2026-11-12：4Q26 debt 2,792 **正確**，不修改。10-K 債務附註（R55）：債務（票據）合計 2,792，融資租賃負債 2,387（流動 491＋長期 1,896），含融資租賃共 5,179（資產負債表 流動債務 491＋長期債務 4,688）。本站 debt 口徑一直是 XBRL `LongTermDebt`（票據，不含融資租賃）：前一年同口徑 4Q25 = 14,577 − 融資租賃 3,044 = 11,533，與資料檔 4Q25 完全一致。FY2026 現金流量表償還債務 10,043，票據由 11,533 降到 2,792 與此相符，所以 1Q26 8,844 到 4Q26 2,792 的掉落是真實還款。若日後要改成含融資租賃的資產負債表口徑（4Q26 = 5,179），需整條序列重算。
