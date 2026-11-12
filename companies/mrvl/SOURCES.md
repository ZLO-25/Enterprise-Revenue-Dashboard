# 邁威爾 Marvell Technology（MRVL）資料來源與更新步驟

- 資料檔：`data/mrvl.json`（schema `v1`）　頁面：`/mrvl/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`），FY2010–FY2022 的原始單位是千美元，所以保留到小數 3 位；每股數字（`eps`、`dps`）為美元。EPS 不做分割換算（FY2010 起的 XBRL 淨利 ÷ 稀釋股數都與 EPS 一致，validate 會擋股數基準錯誤；分割紀錄待股價回補時一併確認）。
- 頻率：每季。財報日約在 3 月初、5 月底、8 月底、12 月初（美股收盤後，太平洋時間下午 1:30／1:45 電話會議）。
- 排程：週二至週六 08:30（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md；公布日隔天先做「快報」，再「補完」「核對」）。排程只補「上次資料之後」的新期間，舊數字不重抓、不重核；**某個月沒有新財報時，只檢查事件時間軸與公布日**；沒有實質變動就不 commit。

## 兩個申報主體（CIK）

```
2021-04-20 完成收購 Inphi，同時改組：
  Marvell Technology Group Ltd.（百慕達）  CIK 0001058057   FY2010 ─ FY2021（申報到 2021-03-16 的 FY2021 10-K）
                     │
                     ▼
  Marvell Technology, Inc.（美國德拉瓦州）  CIK 0001835632   FY2022 起（1Q22 10-Q，2021-06-09 起）；
                                                           它的 10-Q／10-K 也列 FY2020–FY2021 的比較數字
代號始終是 Nasdaq MRVL。
```

- 本頁把兩個 CIK 接起來：**FY2010–FY2021 用舊 CIK 的原始申報**（`rd` 也是舊 CIK 的申報日），**FY2022 起用新 CIK**。兩者重疊的 FY2020–FY2021 數字已比對一致（例如 FY2021 營收 2,968.9、淨利 −277.298）。
- `companies.json` 的 `cik` 填新 CIK（每日排程用來看最新 8-K／10-Q），舊 CIK 只在回補歷史時用。

## 會計年度與季度標籤

邁威爾的會計年度在**最接近 1 月 31 日的星期六**結束（有些年度是 53 週），**季度標籤用公司自己的會計年度**（和輝達一樣，`company.fiscalYearEnd` 填 `01-31`）：

```
FY2027 = 2026/2/1 ─ 2027/1/30（預計）
  1Q27 = 2026/2/1 ─ 2026/5/2
  2Q27 = 2026/5/3 ─ 2026/8/1     ← 目前最新一季
  3Q27 = 2026/8/2 ─ 2026/10/31   ← 2026-12-01 公布
```

`annual` 的鍵 `"2026"` 就是 FY2026（2025/2/2–2026/1/31），`note` 寫明起訖日。

## 期間

1Q10（FY2010 第一季，2009/2/1–2009/5/2）–最新一季，共 70 季。FY2010 是第一個「四季單季數字與全年都能從 SEC XBRL 推得」的會計年度（1Q10 的單季值出現在 2010-06 申報的 1Q11 10-Q 比較欄，2Q10、3Q10 是原始 10-Q，第四季用 FY2010 10-K 全年減前九月）。FY2009 以前沒有 XBRL，未收錄。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyconcept/CIK{10 位 CIK}/us-gaap/{概念}.json`（容器的 curl 被擋，用 WebFetch 讀，請它把每個 (start,end) 的「第一次申報值、申報日、最後一次申報值」列成 CSV）。
2. **財報新聞稿（8-K 附件 99.1）**：新 CIK 檔名慣例 `q{季}{年}_8kx{期末月日年}ex-991.htm`，例：
   - 2Q27 `https://www.sec.gov/Archives/edgar/data/0001835632/000183563226000022/q227_8kx812026ex-991.htm`
   - 1Q27 `https://investor.marvell.com/news-events/press-releases/detail/1023/marvell-technology-inc-reports-first-quarter-of-fiscal-year-2027-financial-results`
   - 4Q26 `https://www.sec.gov/Archives/edgar/data/1835632/000183563226000006/q426_8kx1312026ex-991.htm`
   - 3Q26 `https://sec.gov/Archives/edgar/data/1835632/000183563225000193/q326_8kx1112025ex-991.htm`
   - 4Q25 `https://www.sec.gov/Archives/edgar/data/1835632/000183563225000051/q425_8kx212025ex-991.htm`
   - 4Q23 `https://www.sec.gov/Archives/edgar/data/1835632/000183563223000007/q423_8kx1282023ex-991.htm`（同時列 4Q22）
   - 4Q22 `https://www.sec.gov/Archives/edgar/data/1835632/000183563222000006/q422_8kx1292022ex-991.htm`（同時列 4Q21）
   - 4Q20 `https://investor.marvell.com/sec-filings/all-sec-filings/content/0001058057-20-000007/q4208k212020ex-991.htm`（同時列 4Q19）
   - 4Q19 `https://investor.marvell.com/sec-filings/all-sec-filings/content/0001058057-19-000007/q419_8kx222019ex-991.htm`（同時列 4Q18）
   - 4Q17 `https://investor.marvell.com/sec-filings/all-sec-filings/content/0001193125-17-067657/d354163dex991.htm`
   第四季 EPS、第四季稀釋股數、財測、損益拆解、終端市場營收都從這裡讀。
3. 投資人關係 `https://investor.marvell.com/`（「Announces Conference Call」新聞稿＝下一個公布日；網路直播）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`，`note` 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | 舊 CIK：`Revenues`（到 2Q19）＋`RevenueFromContractWithCustomerExcludingAssessedTax`（FY2017 起的申報）；新 CIK：`RevenueFromContractWithCustomerExcludingAssessedTax` |
| `gp`、`gm` | `GrossProfit`；`gm`＝`gp`÷`rev`×100（小數 1 位）。FY2010–FY2016 的 XBRL 只有 10-K 季度表的單季毛利（沒有前九月、全年），第四季直接用 10-K 的第四季單季值。營業成本概念是 `CostOfGoodsAndServicesSold`（只用來核對；`CostOfRevenue` 不存在） |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss`（含停業單位） |
| `eps` | `EarningsPerShareDiluted`（GAAP 稀釋，含停業單位）；第四季見下 |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`，年初累計相減；舊 CIK 在 FY2014–FY2017 部分期間改用 `NetCashProvidedByUsedInOperatingActivitiesContinuingOperations`（同一張現金流量表的總數） |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`，年初累計相減 |
| `fcf` | `ocf − capex` |
| `dps` | `CommonStockDividendsPerShareDeclared` 單季值；第四季＝全年 − 前三季。股利從 2Q13 開始（每季 0.06 美元，至 2Q27 未變）；1Q13 以前是 `null`（不配息） |

### 第四季推算
**4Q ＝ 全年 − 前九月累計**（營收、毛利、營業利益、淨利、稅前淨利、所得稅）；現金流、資本支出、回購＝全年 − 前九月累計。**EPS 不相減**：FY2010–FY2016 用 10-K 的第四季單季 XBRL 值；FY2017 起 XBRL 沒有第四季單季 EPS，用第四季財報新聞稿（上面的連結）。第四季稀釋加權股數（`dilSh`）FY2017 起也取自新聞稿，FY2010–FY2016 未讀取（null）。

### 重編口徑（停業單位）——每個會計年度只用一個版本
邁威爾在 FY2015–FY2018 間把多個結束或出售的業務改列停業單位，後來的申報會重編前一兩年的營收、毛利、營業利益（淨利、EPS、現金流總數不變）。為了讓「四季加總＝全年」，每個會計年度固定用同一份申報版本：

| 會計年度 | 用哪個版本 | 說明 |
| --- | --- | --- |
| FY2010–FY2016 | 原始申報（第一次申報的值） | FY2016 的 10-Q／10-K 延到 2016-07-21 才申報；FY2018 10-K 曾把 FY2015、FY2016 全年重編（營收 3,637.2、2,602.5），但沒有重編季度，本頁不用 |
| FY2017 | FY2018 申報文件的重編版（最後一次申報值） | 原始 10-Q 沒有毛利 XBRL，且 FY2017 10-K 全年（2,317.7）與原始季度口徑不同。1Q17＝2Q18 10-Q 比較欄的上半年 − 2Q17；第四季＝FY2018 10-K 的 FY2017 全年 − 3Q18 10-Q 的前九月 |
| FY2018 | 最後一次申報值 | 1Q18 原始 579.18 在 2Q18 10-Q 已改為 572.709（上半年 1,177.459 也是新口徑）；第四季推算值 615.409／毛利 373.482／營業利益 54.011 與 4Q19 新聞稿的 4Q18 比較欄一致 |
| FY2019 起 | 第一次申報值 | 新 CIK 後來的比較欄四捨五入到 0.1 百萬，數字相同 |

### 選用區塊
- `segments`：終端市場營收（新聞稿「Net revenue by end market」）。**4Q26 起公司改成兩類**：資料中心、通訊與其他（企業網通＋電信基礎建設＋消費性＋車用／工業），並在 3Q26 起的新聞稿列出新分類的比較季度。本頁只收公司以新分類公布的 4Q25–最新一季，舊的五類不自行加總。新增一季時從新聞稿抄兩個數字，加總要等於 `rev`。
- `guidance.items[]`：只放下一季營收區間（新聞稿寫「X ±5%」，區間由 ±5% 換算，`note` 寫原文）；GAAP／非 GAAP 毛利率、營業費用、稀釋股數、EPS 寫在 `guidance.note`。
- `extra`：無。

## 核對規則（`python3 tools/validate.py mrvl`）

1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年（營收、毛利、營業利益、淨利、營業現金流、資本支出）；`annual` 只放同一版本的全年數字（FY2010–FY2016 沒有全年毛利 XBRL，不填）。
3. `segments` 各分部加總 ＝ 營收；`waterfall` 每個小計 ＝ 前一個小計 ＋ 中間各項。
4. 淨利 ÷ 稀釋股數 ≈ EPS（資產負債表欄位核對）。
5. 財測區間上下限沒有顛倒；日期格式正確；`rd` 依季度遞增、在季末後 5～120 天內。

**任何一項沒過就不發佈**，回到來源修資料，不要放寬核對。

## 資產負債表欄位（shOut、dilSh、cash、debt、buyback、equity、pretax、tax）
- `shOut`（百萬股）：10-K 年底用資產負債表 `CommonStockSharesOutstanding`；其他季度用 10-Q 封面 `dei:EntityCommonStockSharesOutstanding`（期末後 100 天內最早的一筆，日期是封面日不是期末日）。
- `dilSh`（百萬股）：`WeightedAverageNumberOfDilutedSharesOutstanding` 單季值；第四季見上。
- `cash`：`CashAndCashEquivalentsAtCarryingValue` ＋ `ShortTermInvestments`（到 FY2019 年底；3Q19（2018-11-03）起短期投資為 0，FY2020 起資產負債表沒有短期投資，cash＝現金及約當現金）。不含長期投資。
- `debt`：2Q19（2018-08-04）–FY2021：舊 CIK `LongTermDebtNoncurrent` ＋ `LongTermDebtCurrent`；FY2022 起新 CIK `LongTermDebt`（＝一年內到期＋長期，已用 `LongTermDebtCurrent`＋`LongTermDebtNoncurrent` 的年底值核對）。不含營業租賃。2Q19 以前 XBRL 沒有債務科目 → null。
- `buyback`：`PaymentsForRepurchaseOfCommonStock`，年初累計相減（正數）。
- `equity`：`StockholdersEquity`。
- `pretax`：`IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`（只有 FY2015–FY2019 有完整季度）；FY2020 起 XBRL 只有全年值，季度從新聞稿補（目前補了 4Q25、2Q26、4Q26、1Q27、2Q27），其餘 null。
- `tax`：`IncomeTaxExpenseBenefit`，第四季＝全年 − 前九月。
- 讀不到的季度為 null，原因彙整在 `notes.unavailable` 以「待確認：資產負債表欄位」開頭的幾行。

## 電話會議（逐字稿）來源
- 官方：`https://investor.marvell.com/`（網路直播與重播；官方頁面沒有提供文字逐字稿）。
- 第三方逐字稿：尚未選定可穩定讀取的來源；讀不到時 `summary.pending` 寫「待確認：逐字稿尚未取得」，不用新聞報導代替。口頭內容（`mgmt`、`qa`）必附逐字稿連結與發言人。
- **公司有非 GAAP EPS**（新聞稿第一段就是非 GAAP，例 2Q27 非 GAAP 0.94 美元、GAAP 0.33 美元；差距主要是併購無形資產攤銷等調整）。本站 EPS 一律 GAAP 稀釋；市場預期（Yahoo 多為 normalized）比較時，`cons.actualAlt` 填新聞稿的非 GAAP EPS、`basis` 寫「調整後」。

## 更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）

1. 查有沒有新的財報：`data/sec-feed.json` 的 mrvl 8-K Item 2.02，或 investor.marvell.com 的「Reports … Quarter of Fiscal Year …」新聞稿。**沒有新財報 → 跳到第 6 步。**
2. 有新財報：讀新聞稿（8-K 附件 99.1），取得單季營收、毛利、營業利益、稅前淨利、所得稅、淨利、GAAP 稀釋 EPS、稀釋股數、終端市場營收、營業現金流與資本支出（新聞稿現金流量表是年初累計，要相減）、回購、股利、現金、債務、股東權益、下一季財測、非 GAAP EPS。
3. 新增一季到 `quarters[]`（`rd`＝新聞稿日，`rdB:"p"`）與 `segments.quarters[]`；第四季時新增 `annual`（第四季＝全年 − 前九月，EPS 用新聞稿第四季值）。舊的 `guidance` 原封不動 append 進 `guidanceHistory` 再寫新的；`waterfall` 換成新一季；`events` 換成下一個公布日（公司發「Announces Conference Call」新聞稿前加 `est:1`）；`summary` 舊的精簡後移到 `summaryHistory`。
4. `python3 tools/validate.py mrvl`；通過才繼續。
5. 10-Q 出來後（通常新聞稿後 1–2 天）用 XBRL API 核對同一季的數字，有差異以 10-Q 為準並在 notes 記錄；可把 `rd` 保留新聞稿日。注意：2Q27 10-Q 的營收、營業利益、淨利在 companyconcept API 讀不到（2026-11-12），下次再查。
6. 查事件時間軸：併購、出售業務、股利變動、回購授權、指數異動（優先 SEC 8-K 與公司新聞稿）。
7. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `MRVL`（Nasdaq 普通股，美元） |
| 股價起點 | 2009-05（第一季資料 1Q10 的季度起始月是 2009-02，companies.json 設 2009-05） |
| 股票分割 | 待確認：股價回補時檢查 Yahoo 分割紀錄；FY2010 起的 EPS 與淨利÷稀釋股數一致，未見換算問題 |
| EPS 口徑 | GAAP 稀釋 EPS（不用非 GAAP） |
| 財報公布日 `rd` 來源 | 回補的歷史季度：SEC XBRL 的 10-Q／10-K 第一次申報日（`rdB:"f"`，比新聞稿晚幾天，偏保守）；最新一季：財報新聞稿日（`rdB:"p"`） |

- `rd` 讀不到的季度（null，`notes.unavailable` 有待確認）：1Q10（原始 10-Q 早於 XBRL）、2Q16、3Q16、4Q16（審計委員會調查期間延遲申報，10-Q／10-K 都在 2016-07-21 才申報；2015-12-07 的 2Q16 初步新聞稿 GAAP EPS −0.78 與申報的 −1.49 不同）。1Q17 的 10-Q 也延到 2016-08-10（期末後 102 天）申報，仍用該日（f）。
- 股價檔 `data/prices/mrvl.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。**2026-11-12 尚未回補**：要手動觸發 prices-monthly，完成後在下表填 3 個月的抽查（最早 2009-05、最近一次分割前一個月（若有）、最新一個月）。

| 月份 | Yahoo 收盤價 | 第二來源 | 結果 |
|---|---|---|---|
| 2009-05 | — | — | 待確認：股價尚未回補 |
| （中間月份） | — | — | 待確認：股價尚未回補 |
| 最新月份 | — | — | 待確認：股價尚未回補 |

## 已知缺口（頁面「沒能取得的欄位」會列出）

- FY2000–FY2009：沒有 XBRL，未收錄。
- `rd`：1Q10、2Q16、3Q16、4Q16（見上）。
- 2Q27 營收、營業利益、淨利等：companyconcept API 沒有 2Q27 10-Q 的這些事實，暫用新聞稿數字（與 XBRL 已有的毛利、營業成本一致）。
- FY2017 用重編口徑，與當時新聞稿（第四季營收 571.4）不同；1Q17 營業現金流用修正後的 −658.024（原始 10-Q 為 −609.601）。
- 第四季稀釋股數 FY2010–FY2016、多數季度的稅前淨利、FY2010–1Q19 的有息負債、部分季度的回購：見 `notes.unavailable`。
- 終端市場營收 4Q25 以前（舊五類）未收錄。
