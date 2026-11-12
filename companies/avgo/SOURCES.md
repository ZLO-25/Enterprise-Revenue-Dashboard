# 博通 Broadcom（AVGO）資料來源與更新步驟

- 資料檔：`data/avgo.json`（schema `v1`）　頁面：`/avgo/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`）；每股數字（`eps`、`dps`）為美元，**已換算成 2024 年 10 比 1 股票分割後的股數基準**（見下）。
- CIK：`0001730168`（Broadcom Inc.）。頻率：每季。財報日約在 3、6、9、12 月上旬（美東盤後，台北隔天清晨）。
- 排程：週二至週六 08:30（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md；公布日隔天先做「快報」，再「補完」「核對」）。只補「上次資料之後」的新期間，舊數字不重抓、不重核；**某個月沒有新財報時，只檢查事件時間軸與公布日**；沒有實質變動就不 commit。

## 會計年度與季度標籤

博通的會計年度是 **52／53 週制，在最接近 10 月 31 日的星期日結束**，季度標籤用公司自己的會計年度：

```
FY2026 = 2025/11/3 ─ 2026/11/1
  1Q26 = 2025/11/3 – 2026/2/1    （3 月上旬公布）
  2Q26 = 2026/2/2  – 2026/5/3    （6 月上旬公布）
  3Q26 = 2026/5/4  – 2026/8/2    （9 月上旬公布）
  4Q26 = 2026/8/3  – 2026/11/1   （12 月上旬公布，含全年）
```

`annual` 的鍵 `"2025"` 就是 FY2025（2024/11/4–2025/11/2）。`company.fiscalYearEnd` 寫 `11-01`（名目值，只用來推季度結束日檢查 `rd`）。FY2018、FY2024 是 53 週年度（第一季多一週）。

## 期間

**1Q18（2017/10/30–2018/2/4）–最新一季。** 現在的申報主體 Broadcom Inc.（CIK 1730168）是 2018 年 4 月從新加坡遷冊（Broadcom Limited → Broadcom Inc.）後才成立的；它的 XBRL 裡 FY2017 只有全年營收（`RevenueFromContractWithCustomerExcludingAssessedTax` 與 `Revenues`），沒有 FY2017 單季營收與營業成本，所以 FY2017 的季度湊不齊 `rev／gm／om／eps`，從 1Q18 開始。1Q18 的數字來自後來 10-Q（2019-03-15）的比較欄位。更早的 Broadcom Limited（CIK 1649338）／Avago 申報不收（不同申報主體）。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyconcept/CIK0001730168/us-gaap/{概念}.json`（WebFetch 讀得到；容器 curl 會被擋）。讀法：每個 (start, end) 只看 form 10-Q／10-K；單季值取「約 3 個月」的區間，年初累計要相減。
   - 注意：3Q26 10-Q（2026-09-10 申報）的 XBRL 在部分概念（`CostOfRevenue`、`EarningsPerShareDiluted`、`WeightedAverageNumberOfDilutedSharesOutstanding`、`ProfitLoss`、`LongTermDebtNoncurrent`）讀取時還沒有 3Q26 的值，3Q26 這些欄位改用新聞稿（數字與 XBRL 有的欄位逐項一致：營收 29,591、營業利益 15,955、營業現金流 9 個月 32,950、股東權益 99,690）。
2. **財報新聞稿（8-K 附件 99.1）**：檔名慣例 `avgo-{季末日 MMDDYYYY}x8kxex99.htm`，例 3Q26 `https://www.sec.gov/Archives/edgar/data/0001730168/000173016826000076/avgo-08022026x8kxex99.htm`。accession 號碼用 WebSearch 找（搜尋「sec.gov Archives 1730168 avgo-08022026x8kxex99」）。新聞稿有損益表、分部營收（當季＋去年同季）、現金流量表摘要、下一季財測、季度股利。投資人關係同一份新聞稿：`https://investors.broadcom.com/news-releases/`。
3. **博通投資人關係** `https://investors.broadcom.com/`：財報日期公告（約財報前一個月）、電話會議錄音。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`。

## 欄位定義（`quarters[]`）

| 欄位 | XBRL 概念與口徑 |
| --- | --- |
| `rev` | `RevenueFromContractWithCustomerExcludingAssessedTax`（Net revenue） |
| `gp`、`gm` | `rev − CostOfRevenue`（Total cost of revenue，**含**收購無形資產攤銷與重組費用，所以 GAAP 毛利率比公司強調的非 GAAP 毛利率低很多）；`gm`＝`gp ÷ rev × 100` |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | 歸屬普通股股東淨利：1Q18–4Q18 `NetIncomeLoss`（已扣前身公司合夥單位的非控制權益）；FY2019–1Q24 `NetIncomeLossAvailableToCommonStockholdersBasic`（FY2019 第四季到 FY2022 有強制可轉換特別股，扣除特別股股利）；2Q24 起 `ProfitLoss`（之後沒有特別股、也沒有非控制權益，ProfitLoss＝歸屬普通股淨利；FY2023 起兩個概念重疊的季度數字相同）；3Q26 取新聞稿 Net income。FY2024 的淨利含已處分業務（終端用戶運算 EUC）的損益 |
| `eps` | `EarningsPerShareDiluted`，依申報日換算分割（見下）；第四季見下 |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`，年初累計相減 |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`（Purchases of property, plant and equipment），年初累計相減 |
| `fcf` | `ocf − capex` |
| `dps` | `CommonStockDividendsPerShareCashPaid`（當季**發放**的每股股利），依申報日換算分割；第四季＝全年 − 前三季。`CommonStockDividendsPerShareDeclared` 在 FY2021 以後沒有標，所以統一用 CashPaid |

### EPS、股利、股數的股票分割換算

博通 2024 年 6 月 12 日宣布 **10 比 1 股票分割**：2024-07-11 收盤後登記、2024-07-15 開盤起以分割後價格交易（2Q24 新聞稿）。XBRL 的每股數字是「申報當時」的股數基準：

```
2024-07-15 以前申報／公布的數字     EPS、股利 ÷10，股數 ×10
2024-07-15 以後申報／公布的數字     不換算（部分舊季度在後來的 10-Q／10-K 已重列成分割後，例 3Q23 EPS 0.77、FY2023 3.30）
```
小數保留 3 位（用原始申報值 ÷10，例 3Q23 原始 7.74 → 0.774，不用重列後四捨五入的 0.77）。驗證：淨利 ÷ 稀釋股數 ≈ EPS（validate 自動檢查）。期末流通股數（`CommonStockSharesOutstanding`）2024-08-04 以前的期末值 ×10，唯一例外 2023-10-29 的 4,139 已在 FY2024 10-K 重列成分割後，不再乘。

### 第四季推算
- 營收、營業成本、營業利益、淨利、稅前淨利、所得稅、營業現金流、資本支出、回購：**全年 − 前三季**。已與 4Q20–4Q25 第四季新聞稿逐項核對一致（例：4Q25 營收 18,015、淨利 8,518、營業現金流 7,703；4Q22 營收 8,930、歸屬普通股淨利 3,311）。
- EPS：FY2018–FY2020 取 XBRL 10-K 的第四季單季值（4Q18 2.64、4Q19 1.97、4Q20 2.93，分割前）；FY2021 以後 XBRL 沒有第四季單季值，取第四季財報新聞稿：4Q21 4.45（分割前）、4Q22 7.83（分割前）、4Q23 8.25（分割前）、4Q24 0.90、4Q25 1.74。
- 第四季稀釋股數：4Q20–4Q25 取新聞稿；4Q18、4Q19 沒讀到，留空。

## 分部（`segments`）

- 半導體解決方案（Semiconductor solutions）、基礎架構軟體（Infrastructure software），單位百萬美元，兩項加總＝該季 `rev`（逐季差 0）。
- 涵蓋 **1Q22–3Q26**：取自各季財報新聞稿的「Net revenue by segment」表。每份新聞稿同時列當季與去年同季，所以 1Q22–3Q22 取自 1Q23–3Q23 新聞稿、1Q23–3Q23 取自 1Q24–3Q24 新聞稿、1Q25–3Q25 取自 1Q26–3Q26 新聞稿；第四季取自 4Q22、4Q23、4Q24、4Q25 新聞稿。同一季在兩份新聞稿出現時數字一致（例 1Q23：7,107／1,808）。
- 1Q24 起軟體含 VMware（2023-11-22 完成收購），所以軟體營收從 1,969（4Q23）跳到 4,571（1Q24）。
- 1Q18–4Q21 尚未讀取（公司有揭露，之後要補就讀 FY2019–FY2022 的新聞稿；XBRL companyconcept 沒有分部維度）。
- 新增一季時：讀新聞稿分部表當季兩個數字，加進 `segments.quarters`。

## 核對規則（`python3 tools/validate.py avgo` 會自動做）

1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年（營收、毛利、營業利益、淨利、營業現金流、資本支出）。
3. `segments` 各分部加總 ＝ 營收。
4. `waterfall` 每個小計 ＝ 前一個小計 ＋ 中間各項；第一列營收＝最新一季 `rev`。
5. 財測區間上下限沒有顛倒；日期格式正確；`rd` 依季度遞增、與季度結束日相差 5～120 天。
6. 淨利 ÷ 稀釋股數 ≈ EPS（擋分割換算錯誤）。

**任何一項沒過就不發佈**，回到來源修資料，不要放寬核對。

## 資產負債表欄位（shOut、dilSh、cash、debt、buyback、equity、pretax、tax）

- `shOut` 期末流通股數（百萬股）：`CommonStockSharesOutstanding`（只有一類普通股），分割換算見上。1Q18 缺 2018-02-04 的值，留空。
- `dilSh` 稀釋加權股數：`WeightedAverageNumberOfDilutedSharesOutstanding` 三個月值（分割前 ×10）；3Q26 與 4Q20–4Q25 取新聞稿；4Q18、4Q19 留空（待確認）。3Q24 淨損，稀釋股數＝基本股數（4,663）。
- `cash` 現金與投資：**只有現金及約當現金**（`CashAndCashEquivalentsAtCarryingValue`）；博通的 XBRL 沒有短期投資／有價證券概念（`ShortTermInvestments`、`MarketableSecuritiesCurrent` 都查不到），所以不含投資。3Q26 取新聞稿資產負債表。
- `debt` 有息負債：`LongTermDebtCurrent`（一年內到期）＋資產負債表的長期負債（非流動）。非流動部分：1Q18–1Q22 用 `LongTermDebtNoncurrent`、4Q22–2Q26 用 `LongTermDebtAndCapitalLeaseObligations`（這段期間 `LongTermDebtNoncurrent` 沒有標）、3Q26 取新聞稿的 Long-term debt 57,167。不含營業租賃。`LongTermDebt` 概念有時是本金而不是帳面值（例 2020-11-01：40,994 ≠ 827＋40,235），不使用。4Q21、2Q22、3Q22 兩個概念對不起來，留空待確認；1Q18、2Q21 缺其中一項，留空。
- `buyback` 回購金額：`PaymentsForRepurchaseOfCommonStock`（回購計畫，不含員工股票扣稅代扣），年初累計相減。FY2020–FY2021 沒有回購（0）。
- `equity` 股東權益：FY2019 以前 `StockholdersEquity`；1Q20 起只標 `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest`（2Q18 以後博通沒有非控制權益，兩者相等；FY2019 年底兩概念重疊值相同 24,941）。FY2019–FY2022 的權益含強制可轉換特別股。1Q18 留空（當時有前身公司合夥單位的非控制權益）。
- `pretax` 持續營業單位稅前淨利、`tax` 所得稅費用（負數＝稅務利益），都取自 XBRL 單季值（概念名稱以 companyconcept 查詢時的損益表稅前淨利／所得稅概念為準；4Q20–4Q25 已與新聞稿核對一致）：第四季＝全年 − 前三季；3Q26 取新聞稿（15,275、2,187）。1Q18 的 −5,786 是美國稅改的一次性利益；3Q24 的 4,238 含約 45 億美元一次性非現金稅務費用；4Q25 的 −1,649 含約 21 億美元稅務利益（追溯期滿）。

## 電話會議（逐字稿）來源

- 官方：博通投資人關係網站只提供電話會議錄音重播（`https://investors.broadcom.com/`，事件頁例 `https://investors.broadcom.com/events/event-details/q4-2026-broadcom-earnings-conference-call`），**沒有官方逐字稿**。
- 第三方逐字稿：尚未選定可用來源；選定後在 `summary.*.src.n` 註明網站名稱。讀不到就寫「待確認：逐字稿尚未取得」，不用新聞報導代替。
- 公司有無非 GAAP EPS：**有**（新聞稿公布 Non-GAAP diluted EPS，例 3Q26 3.32 美元）。市場預期比較時 `cons.actualAlt` 填公司公布的非 GAAP EPS，`basis` 寫「調整後」。
- 財測口徑：新聞稿給「下一季營收（約數）」＋一個非 GAAP 利潤率（多數季度是調整後 EBITDA ÷ 營收；3Q26 新聞稿寫的是非 GAAP 營業利益 ÷ 營收）。`guidance.items` 收營收（`lo = hi`）與那個利潤率，`note` 寫清楚是哪一種，不和本站 GAAP 數字直接比較。

## 更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）

1. 查有沒有新的財報：WebSearch「Broadcom Inc. announces {first/second/third/fourth} quarter fiscal year {年} financial results」或 SEC 8-K 附件 99.1。**沒有新財報 → 跳到第 5 步。**
2. 有新財報：讀 8-K 附件 99.1 的損益表（Net revenue、Total cost of revenue、Operating income、Interest expense、Other income, net、Income before income taxes、Provision for income taxes、Net income、Diluted EPS、diluted shares）、分部營收表、現金流量表（Net cash provided by operating activities、Purchases of property, plant and equipment、Repurchases of common stock，都要注意是三個月還是年初累計）、資產負債表摘要（現金、短期與長期負債、股東權益）。新增一季到 `quarters[]`（第一～三季直接用三個月數字；第四季營收等用全年減前三季，EPS 用新聞稿第四季單季值），加 `segments.quarters`；第四季時新增 `annual`（全年欄）。`rd` 填新聞稿日、`rdB:"p"`。
3. 更新 `guidance`（先把舊的整份 append 到 `guidanceHistory`）、`waterfall`（換成新一季）、`events`（下一個公布日：博通約財報前一個月發新聞稿公告日期，公告前用 `est:1` 並在 `t` 寫「預估」）、`summary`（舊的精簡後放進 `summaryHistory`）。
4. `python3 tools/validate.py avgo`；通過才繼續。10-Q／10-K 的 XBRL 進 API 後用它核對上一季（核對步驟）。
5. 查事件時間軸：大型 AI 客戶合約、產品、併購、股利調整（每年第四季財報通常調高季度股利）、回購計畫、指數異動。公司證實的照常收錄；只有媒體報導的加 `unc:1`，`note` 以「待確定：」開頭。
6. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `AVGO`（Nasdaq 普通股，幣別 美元） |
| 股價起點 | 2017-11（第一季 1Q18 的季度起始月） |
| 股票分割 | 2024-07 十拆一（Yahoo Close 已依分割調整、不含股利調整，才跟本站已換算成今天股數的 EPS 對得上） |
| EPS 口徑 | GAAP 稀釋 EPS，不用公司的非 GAAP EPS |
| 財報公布日 `rd` 來源 | 有讀到新聞稿的季度用新聞稿日（`rdB:"p"`：4Q21、4Q22、1Q23–4Q24、4Q25–3Q26）；其餘用 SEC XBRL 該期 10-Q／10-K 的最早申報日（`rdB:"f"`，比新聞稿晚約一週，偏保守）。1Q18 只有 2019 年的比較欄位，留空待確認 |

**更新步驟**
1. 新增一季時，同時填該季 `rd`（那一季 EPS 第一次公開的日期）與 `rdB`。讀不到就填 `null`，在 `notes.unavailable` 加「待確認：<季度> 的財報公布日（rd）：原因」，**不可以用「季度結束後幾天」推算**。最新一季的 `rd` 不可為 null。
2. 股價檔 `data/prices/avgo.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填、不修改。**加入時尚未抓取**：要先手動觸發 prices-monthly，否則 `validate.py avgo` 會因找不到股價檔而失敗。
3. 本益比（`tools/pe.py`）與預估本益比不存檔，建置時算出；預估只有每月 1–6 日 Actions 存下的快照，**不回填**。
4. 抽查紀錄（股價回補後，每家人工對第二個獨立來源抽 3 個月：最早 2017-11、分割前一個月 2024-06、最新一個月）：待股價回補後填寫。

| 月份 | Yahoo 收盤價 | 第二來源 | 結果 |
|---|---|---|---|
| 2017-11 | — | — | 待確認：股價尚未回補 |
| 2024-06 | — | — | 待確認：股價尚未回補 |
| 最新月 | — | — | 待確認：股價尚未回補 |

## 已知缺口

- FY2017 以前：見「期間」。
- 待確認：1Q18 財報公布日（rd）、1Q18 期末股數與股東權益、4Q18／4Q19 稀釋股數、1Q18／2Q21／4Q21／2Q22／3Q22 有息負債（原因見 `notes.unavailable`）。
- 分部營收 1Q18–4Q21 尚未讀取。
- 4Q26（2026/8/3–11/1）與 FY2026 全年：2026-12-09 公布，本次加入時尚未公布。
