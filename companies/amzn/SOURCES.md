# 亞馬遜 Amazon（AMZN）資料來源與更新步驟

- 資料檔：`data/amzn.json`（schema `v1`）　頁面：`/amzn/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`）；`eps` 為美元，**已換算成 2022 年分割後股數基準**。亞馬遜不發放現金股利，`dps` 一律 `null`。
- CIK：`0001018724`。頻率：每季。會計年度＝日曆年。財報日約在 2 月初、4 月底、7 月底、10 月底（美股收盤後）。
- 排程：每月 12 日 07:48（台北）。只補「上次資料之後」的新期間，舊數字不重抓；沒有新財報的月份只檢查事件與公布日；沒有實質變動就不 commit。

## 期間

1Q09（2009/1–3）–最新一季。XBRL 的 2008 年只有第二、三季與全年，缺第一季，第四季推不出來，所以從 2009 年開始；2007 年以前沒有 XBRL。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyconcept/CIK0001018724/us-gaap/{概念}.json`（WebFetch 讀得到；容器 curl 會被擋；概念不存在時回 client_error）。讀法：每個 (start, end) 取最近一次申報的值，只看 10-K／10-Q。**例外：2011 年各季見「已知 XBRL 錯誤」。**
2. **財報新聞稿**：`https://ir.aboutamazon.com/news-release/news-release-details/{公布年}/Amazon-com-Announces-{First|Second|Third|Fourth}-Quarter-Results/`（WebFetch 讀得到，含完整損益表、現金流量表、分部與下一季財測）；同內容在 SEC 8-K 附件 99.1（`amzn-{季末日YYYYMMDD}xex991.htm`，有時 WebFetch 讀不到）。
3. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`。

## 欄位定義（`quarters[]`）

| 欄位 | XBRL 概念與口徑 |
| --- | --- |
| `rev` | 2017 起 `RevenueFromContractWithCustomerExcludingAssessedTax`；2016 以前 `SalesRevenueNet`（重疊年度數字相同） |
| `gp`、`gm` | **營收 − `CostOfGoodsAndServicesSold`（Cost of sales）**。亞馬遜損益表沒有「毛利」這一行；營業成本不含履約（fulfillment）、技術與基礎設施等費用，所以毛利率（約 50%）不能和一般零售商直接比較 |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss` |
| `eps` | `EarningsPerShareDiluted`，依申報日換算分割（見下）；第四季見下 |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`，年初累計（start＝1/1 的那幾筆，**不要用滾動十二個月的那幾筆**）相減 |
| `capex` | 2016 起 `PaymentsToAcquireProductiveAssets`、2016 以前 `PaymentsToAcquirePropertyPlantAndEquipment`（Purchases of property and equipment，**未扣除處分與獎勵收入**），年初累計相減。所以本頁 `fcf` 會比亞馬遜自己公布的 Free cash flow 低 |
| `dps` | 不配息，`null` |

### EPS 股票分割換算
2022-06-06 起 1 股分割為 20 股。XBRL 的 EPS 依 **申報日** 換算：2022-06-06 以前申報 ÷20，之後不換算；小數保留 4 位。

### 第四季推算
- 營收、營業成本、營業利益、淨利：**全年 − 前三季**，已與 2021–2025 年第四季新聞稿逐項核對一致。早期年度可能與公司公布單季差 1（四捨五入）。
- EPS：2020 年以前取 XBRL 10–12 月單季值；2021 年以後 XBRL 沒有單季值，取第四季新聞稿（4Q21 1.39、4Q22 0.03、4Q23 1.00、4Q24 1.86、4Q25 1.95，皆為分割後基準）。

### 已知 XBRL 錯誤（不要「修正」回去）
2012 年 10-K（2013-01-30 申報）把 **2012 年各季** 的營收、淨利、EPS 標成 2011 年的期間，所以「取最近申報值」會拿到錯的 2011 年數字。本頁 2011 年各季改用 2011 年當期 10-Q 與 2011 年 10-K（2012-02-01 申報）的值：營收 9,857／9,913／10,876／17,431（加總＝全年 48,077）、淨利 201／191／63／（第四季推算 176）、EPS 0.44／0.41／0.14／0.38（分割前）。

### 其他推算
- 2Q17 上半年累計資本支出 XBRL 沒有：用「前三季累計 8,336 − 第三季單季 3,074」＝ 5,262。

## 核對規則（`python3 tools/validate.py amzn`）

1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年（營收、毛利、營業利益、淨利、營業現金流、資本支出）。
3. `waterfall` 小計加總；第一列營收＝最新一季 `rev`。
4. 財測區間上下限沒有顛倒。

**任何一項沒過就不發佈**，回到來源修資料，不要放寬核對。

## 更新步驟（每月排程）

1. 查有沒有新財報：上面 ir.aboutamazon.com 的網址（換季別與年份），或 WebSearch「Amazon.com Announces {季別} Quarter Results {年}」。**沒有新財報 → 跳到第 6 步。**
2. 讀新聞稿：損益表（Total net sales、Cost of sales、Operating income、Other income、Provision for income taxes、Equity-method、Net income、Diluted EPS）、現金流量表（Net cash provided by operating activities、Purchases of property and equipment 的年初累計欄）、下一季財測（Net sales、Operating income 區間）。
3. 新增一季；第四季用全年減前三季、EPS 用新聞稿，並新增 `annual`。10-Q 的 XBRL 進 API 後核對上一季，刪掉 notes 裡對應的「待確認」。
4. 更新 `guidance`（下一季營收、營業利益區間）、`waterfall`、`events`（亞馬遜約在財報前兩週公告日期，公告後刪 `est`）。
5. `python3 tools/validate.py amzn`；通過才繼續。
6. 查事件：AWS 重大合約、併購、股票分割或買回、重大投資損益（優先 8-K 與 ir.aboutamazon.com）。
7. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 已知缺口

- 2008 年以前：見「期間」。
- 待確認：3Q26 全部數字取自新聞稿，等 10-Q XBRL 核對。
- 分部營收（北美、國際、AWS）歷史資料：尚未收錄（companyconcept API 不含分部維度）。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `AMZN`（主要掛牌地普通股，幣別 美元） |
| 股價起點 | 2009-01 |
| 股票分割 | 2022-06 一拆二十（Yahoo Close 已依分割調整、不含股利調整，才跟本站已換算成今天股數的 EPS 對得上） |
| EPS 口徑 | 稀釋 EPS；都是公認會計準則數字，不用調整後 EPS |
| 財報公布日 `rd` 來源 | SEC XBRL 的 10-Q／10-K 申報日（rdB:f）；最新一季用新聞稿日（rdB:p） |

**更新步驟（每月排程）**
1. 新增一季時，同時填該季 `rd`（那一季 EPS 第一次公開的日期）與 `rdB`。讀不到就填 `null`，在 `notes.unavailable` 加「待確認：<季度> 的財報公布日（rd）：原因」，**不可以用「季度結束後幾天」推算**。最新一季的 `rd` 不可為 null。
2. 股價檔 `data/prices/amzn.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填、不修改；排程只檢查上個月有沒有進來。
3. 本益比（`tools/pe.py`）與預估本益比不存檔，建置時算出；預估只有每月 1–6 日 Actions 存下的快照，**不回填**。
4. 若這家公司發生股票分割：同一次完成 EPS 重編與股價檔重抓（手動觸發 prices-monthly 並填 `accept=amzn`），否則 validate 會因相鄰月份本益比跳動超過 3 倍而失敗。
5. 抽查紀錄（回補時每家人工對第二個獨立來源抽 3 個月：最早一個月、最近一次分割前一個月、最新一個月）：見下表。

| 月份 | Yahoo 收盤價 | 第二來源 | 結果 |
|---|---|---|---|
| （待填） | | | |

