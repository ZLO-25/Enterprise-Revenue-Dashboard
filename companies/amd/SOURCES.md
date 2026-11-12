# 超微 Advanced Micro Devices（AMD）資料來源與更新步驟

- 資料檔：`data/amd.json`（schema `v1`）　頁面：`/amd/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`）；每股數字（`eps`）為美元。超微不配息，`dps` 一律 `null`。
- 頻率：每季。財報日約在 1 月底／2 月初、5 月初、8 月初、11 月初（美股收盤後，美東下午 5 點電話會議）。
- 排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md；公布日隔天先做「快報」，再「補完」「核對」）。排程只補「上次資料之後」的新期間，舊數字不重抓、不重核；**某個月沒有新財報時，只檢查事件時間軸與公布日**；沒有實質變動就不 commit。
- CIK：`0000002488`（始終同一個申報主體）。

## 會計年度與季度標籤

超微的會計年度是 52／53 週，在**最接近 12 月 31 日的最後一個星期六**結束，季度標籤用曆年（`company.fiscalYearEnd` 填 `12-31`）：

```
2026 年度 = 2025/12/28 ─ 2026/12/26（預計）
  1Q26 = 2025/12/28 ─ 2026/3/28
  2Q26 = 2026/3/29  ─ 2026/6/27
  3Q26 = 2026/6/28  ─ 2026/9/26   ← 目前最新一季（2026-11-03 公布）
  4Q26 = 2026/9/27  ─ 2026/12/26  ← 預估 2027-02 初公布
```

## 期間

1Q09–最新一季，共 71 季。超微 2009 年 6 月（2Q09 10-Q）才開始用 XBRL 申報，2008 年以前沒有可機器讀取的單季數字，所以從 2009 年開始。1Q09 的營收、毛利、營業利益、淨利＝ 2Q09 10-Q 的上半年 − 2Q09 單季；1Q09 的 EPS 與稀釋股數取 1Q09 財報新聞稿。1Q09、2Q09 的營業現金流與資本支出無法拆出單季（`null`，見待確認）。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0000002488.json`（容器的 curl 被擋，用 GitHub Actions 的 `sec-raw` 分支工作流程或 WebFetch 讀）。
2. **財報新聞稿（8-K Item 2.02 附件 99.1）**：近年檔名慣例 `q{季}{年}991.htm`，例：
   - 3Q26 `https://www.sec.gov/Archives/edgar/data/2488/000000248826000188/q32026991.htm`
   - 2Q26 `https://www.sec.gov/Archives/edgar/data/2488/000000248826000121/q22026991.htm`
   - 1Q26 `https://www.sec.gov/Archives/edgar/data/2488/000000248826000072/q12026991.htm`
   - 4Q25 `https://www.sec.gov/Archives/edgar/data/2488/000000248826000014/q42025991.htm`
   - 1Q09 `https://www.sec.gov/Archives/edgar/data/2488/000119312509083507/dex991.htm`
   第四季 EPS（2021 年起）、分部營收、財測、損益拆解都從這裡讀。
3. 投資人關係 `https://ir.amd.com/`（財報日期公告、網路直播）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`，`note` 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `RevenueFromContractWithCustomerExcludingAssessedTax`（2018 年起）、`Revenues`／`SalesRevenueNet`（2017 年以前），同一期間以名單前面的概念優先 |
| `gp`、`gm` | `GrossProfit`；`gm`＝`gp`÷`rev`×100（小數 1 位）。GAAP 毛利含併購無形資產攤銷，所以低於公司強調的非 GAAP 毛利率 |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss`（2009 年合併 GlobalFoundries 期間取歸屬超微普通股股東的淨利；2025 年起含 ZT Systems 製造業務停業單位） |
| `eps` | `EarningsPerShareDiluted`（GAAP 稀釋，含停業單位）；第四季見下 |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`，年初累計相減 |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`，年初累計相減（正數） |
| `fcf` | `ocf − capex` |
| `dps` | 不配息，`null` |
| `rd`、`rdB` | 季末後 5–90 天內最後一份 8-K Item 2.02（財報新聞稿）的申報日，`rdB:"p"`。3Q16 的附件沒有抓到，手動填 8-K 申報日 2016-10-20 |

### 每個會計年度只用一個版本（10-K 申報當時）
超微後來的申報會重編前期（例如 2018 年採用 ASC 606、2025 年 ZT Systems 製造業務改列停業單位）。為了讓「四季加總＝全年」，**每個會計年度的季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本**，全年取原始 10-K。所以 2017 年是 ASC 605 口徑、2018 年起是 ASC 606，未自行重編。

### 第四季推算
**4Q ＝ 10-K 全年 − 前三季**（營收、毛利、營業利益、淨利、稅前淨利、所得稅）；現金流、資本支出、回購＝全年 − 前九月累計。**EPS 不相減**：2010–2020 年用 10-K 季度表的第四季單季 XBRL 值；4Q09 與 2021 年起用第四季財報新聞稿（4Q21、4Q22 由程式從新聞稿讀出，4Q23 0.41、4Q24 0.29、4Q25 0.92 美元已人工核對新聞稿）。第四季稀釋股數同樣取新聞稿。

### 選用區塊
- `segments`：分部營收（新聞稿「Segment」表）：資料中心、個人電腦（Client）、遊戲、嵌入式。只收 1Q24–最新一季，更早的季度尚未讀取（不是公司未揭露）。目前的新聞稿把個人電腦與遊戲合併為「Client and Gaming」報導分部，並在文字中分列兩者營收，本頁照新聞稿分開列（合併分部開始的季度未查）。新增一季時抄四個數字，加總要等於 `rev`。
- `guidance.items[]`：下一季營收（新聞稿寫「約 X ± Y」，區間由此換算，`note` 寫原文）與非 GAAP 毛利率（標明非 GAAP）。超微不給全年財測。
- `extra`：無。

## 核對規則（`python3 tools/validate.py amd`）

1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年（營收、毛利、營業利益、淨利、營業現金流、資本支出）。
3. `segments` 各分部加總 ＝ 營收；`waterfall` 每個小計 ＝ 前一個小計 ＋ 中間各項。
4. 淨利 ÷ 稀釋股數 ≈ EPS。
5. 財測區間上下限沒有顛倒；日期格式正確；`rd` 依季度遞增、在季末後 5～120 天內。

**任何一項沒過就不發佈**，回到來源修資料，不要放寬核對。

## 資產負債表欄位（shOut、dilSh、cash、debt、buyback、equity、pretax、tax）
配方在 `tools/bs_map.json` 的 `amd`：
- `shOut`（百萬股）：`CommonStockSharesOutstanding`；沒有時用 10-Q 封面 `dei:EntityCommonStockSharesOutstanding`。
- `dilSh`（百萬股）：`WeightedAverageNumberOfDilutedSharesOutstanding` 單季值；第四季見上。
- `cash`：`CashAndCashEquivalentsAtCarryingValue` ＋ `ShortTermInvestments`（或 `MarketableSecuritiesCurrent`）。不含長期投資。
- `debt`：`LongTermDebtNoncurrent`（或 `LongTermDebtAndCapitalLeaseObligations`）＋ 一年內到期部分 ＋ `ShortTermBorrowings`（有才加）。不含營業租賃。
- `buyback`：`PaymentsForRepurchaseOfCommonStock`（或 `PaymentsForRepurchaseOfEquity`），年初累計相減。2021 年 5 月才宣布回購計畫，2Q20 以前沒有科目 → `null`。
- `equity`：`StockholdersEquity`。
- `pretax`：`IncomeLossFromContinuingOperationsBeforeIncomeTaxes…`；`tax`：`IncomeTaxExpenseBenefit`，第四季＝全年 − 前九月。
- 讀不到的季度為 `null`，原因彙整在 `notes.unavailable` 以「待確認：資產負債表欄位」開頭的幾行。

## 電話會議（逐字稿）來源
- 官方：`https://ir.amd.com/`（網路直播與重播；官方沒有文字逐字稿）。
- 第三方逐字稿：尚未選定可穩定讀取的來源；讀不到時 `summary.pending` 寫「待確認：逐字稿尚未取得」，不用新聞報導代替。口頭內容（`mgmt`、`qa`）必附逐字稿連結與發言人。
- **公司有非 GAAP EPS**（新聞稿第一段同時列 GAAP 與非 GAAP；差距主要是 Xilinx 等併購無形資產攤銷與股票酬勞）。本站 EPS 一律 GAAP 稀釋；和市場預期（多為調整後）比較時，`cons.actualAlt` 填新聞稿的非 GAAP EPS、`basis` 寫「調整後」。

## 更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）

1. 查有沒有新財報：`data/sec-feed.json` 的 amd 8-K Item 2.02，或 ir.amd.com 的「AMD Reports … Quarter … Financial Results」。**沒有新財報 → 跳到第 6 步。**
2. 有新財報：讀新聞稿（8-K 附件 99.1），取單季營收、毛利、營業利益、稅前淨利、所得稅、淨利、GAAP 稀釋 EPS、稀釋股數、四個分部營收、營業現金流與資本支出（新聞稿是單季或累計要看清楚）、回購、現金、債務、股東權益、下一季財測、非 GAAP EPS 與毛利率。
3. 新增一季到 `quarters[]`（`rd`＝新聞稿日，`rdB:"p"`）與 `segments.quarters[]`；第四季時新增 `annual`（第四季＝全年 − 前三季，EPS 用新聞稿第四季值）。舊 `guidance` 原封不動 append 進 `guidanceHistory` 再寫新的；`waterfall` 換成新一季；`events` 換成下一個公布日（公司公告前加 `est:1`）；`summary` 舊的精簡後移到 `summaryHistory`。
4. `python3 tools/validate.py amd`；通過才繼續。
5. 10-Q／10-K 出來後用 XBRL 核對同一季的數字，有差異以申報文件為準並在 notes 記錄。
6. 查事件時間軸：併購（ZT Systems、World Labs、Taalas）、出口管制、回購授權、指數異動（優先 SEC 8-K 與公司新聞稿）。
7. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `AMD`（Nasdaq 普通股，美元） |
| 股價起點 | 2009-03（第一季 1Q09 結束的月份） |
| 股票分割 | 2009 年以來沒有股票分割，EPS 不換算 |
| EPS 口徑 | GAAP 稀釋 EPS（不用非 GAAP） |
| 財報公布日 `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`，美股盤後公布，等於公布當天） |

股價檔 `data/prices/amd.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果見下表。

<!-- PRICE_CHECK -->

## 已知缺口（頁面「沒能取得的欄位」會列出）

- 2008 年以前：沒有 XBRL，未收錄。
- 1Q09、2Q09 營業現金流與資本支出：沒有單季或可相減的累計值。
- 分部營收 1Q24 以前未收錄。
- 回購 2Q20 以前、少數早期季度的股數、現金、債務、股東權益、稅前淨利、所得稅：見 `notes.unavailable`。
