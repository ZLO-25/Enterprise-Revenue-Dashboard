# CrowdStrike（CRWD）資料來源與更新步驟

- 資料檔：`data/crwd.json`（schema `v1`）　頁面：`/crwd/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`），原始單位是千美元，保留到小數 3 位；每股數字（`eps`）為美元。CrowdStrike 不配息，`dps` 一律 `null`。
- 頻率：每季。財報日約在 3 月初、6 月初、8 月底、12 月初（美股收盤後，美東下午 4:30 電話會議）。
- 排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md；公布日隔天先做「快報」，再「補完」「核對」）。排程只補「上次資料之後」的新期間，舊數字不重抓、不重核；**某個月沒有新財報時，只檢查事件時間軸與公布日**；沒有實質變動就不 commit。
- CIK：`0001535527`。

## 會計年度與季度標籤

會計年度在 **1 月 31 日**結束（固定月底，不是 52／53 週），**季度標籤用公司自己的會計年度**（和輝達、邁威爾一樣，`company.fiscalYearEnd` 填 `01-31`）：

```
FY2027 = 2026/2/1 ─ 2027/1/31
  1Q27 = 2026/2/1 ─ 2026/4/30
  2Q27 = 2026/5/1 ─ 2026/7/31    ← 目前最新一季（2026-08-26 公布）
  3Q27 = 2026/8/1 ─ 2026/10/31   ← 2026-12-01 公布（公司已公告）
```

`annual` 的鍵 `"2026"` 就是 FY2026（2025/2/1–2026/1/31）。

## 期間

1Q20（2019/2/1–2019/4/30）–最新一季，共 30 季。2019 年 6 月 Nasdaq 上市；1Q20 是上市後第一份財報（2019-07-18 新聞稿）。上市前的季度只在 S-1 出現，第四季單季 EPS 沒有 XBRL 值，上市前股數（含可轉換特別股）也和上市後不可比，所以不收。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0001535527.json`。
2. **財報新聞稿（8-K Item 2.02 附件 99.1）**：近年檔名慣例 `crwd-{yyyymmdd}xex991.htm`，例：
   - 2Q27 `https://www.sec.gov/Archives/edgar/data/1535527/000153552726000029/crwd-20260826xex991.htm`
   - 1Q27 `https://www.sec.gov/Archives/edgar/data/1535527/000153552726000022/crwd-20260603xex991.htm`
   - 4Q26 `https://www.sec.gov/Archives/edgar/data/1535527/000153552726000007/crwd-20260303xex991.htm`
   - 3Q26 `https://www.sec.gov/Archives/edgar/data/1535527/000153552725000030/crwd-20251202xex991.htm`
   - 1Q20 `https://www.sec.gov/Archives/edgar/data/1535527/000155837019006148/ex-99d1.htm`
   第四季 EPS、ARR、財測、損益拆解都從這裡讀。
3. 投資人關係 `https://ir.crowdstrike.com/`（財報日期公告、網路直播）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`，`note` 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `RevenueFromContractWithCustomerIncludingAssessedTax`（CrowdStrike 用「含稅」這個概念名稱，金額就是損益表總營收）；沒有時用 `…ExcludingAssessedTax`／`Revenues` |
| `gp`、`gm` | `GrossProfit`；`gm`＝`gp`÷`rev`×100 |
| `opInc`、`om` | `OperatingIncomeLoss`（GAAP，多數季度為虧損，主因股票酬勞） |
| `ni` | `NetIncomeLoss`（歸屬 CrowdStrike，扣除非控制權益） |
| `eps` | `EarningsPerShareDiluted`（GAAP 稀釋）；第四季見下；分割換算見下 |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`，年初累計相減 |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`，年初累計相減（正數；不含資本化軟體開發成本） |
| `fcf` | `ocf − capex`（公司自己的「自由現金流」另扣資本化軟體，本站不用公司口徑） |
| `dps` | 不配息，`null` |
| `rd`、`rdB` | 季末後 5–90 天內最後一份 8-K Item 2.02 的申報日，`rdB:"p"` |

### 每個會計年度只用一個版本（10-K 申報當時）＋ FY2026 例外
每個會計年度的季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本，第四季營收、毛利、營業利益、淨利、現金流＝10-K 全年 − 前三季。

**FY2026 例外**：FY2026 10-K 的全年數字已修正股票酬勞（公司稱不重大的前期調整，1Q26、2Q26 營業利益各差約 0.06、0.08 億美元），與前三季原始申報口徑不同。所以：
- 4Q26 直接用 4Q26 新聞稿的單季數字（營收 1,305.375、毛利 989.462、營業利益 −6.900、淨利 38.691、稅前 37.154、所得稅 −3.621）。
- `annual["2026"]` 的毛利、營業利益、淨利填 `null`（寫在待確認），營收照 10-K。

### 第四季 EPS
XBRL 沒有第四季單季 EPS，FY2020–FY2026 全部取第四季新聞稿（4Q20 −0.14、4Q21 −0.09、4Q22 −0.18、4Q23 −0.20、4Q24 0.22、4Q25 −0.37、4Q26 0.15 美元，分割前），再依下面的分割規則換算。第四季稀釋股數也取新聞稿。

### 股票分割（一拆四，2026-07-02 起以分割後價格交易）
- **以 EPS 第一次公開的日期判斷**：2026-07-02 以前公布的 EPS ÷4、稀釋股數 ×4，小數保留 4 位；之後公布的（2Q27 起）不換算。
- 1Q20–1Q27 共 29 季已換算；股價檔由 Yahoo 回補時也是分割調整後價格，兩邊口徑一致。

### 選用區塊
- `segments`：無（CrowdStrike 只有訂閱與專業服務兩類營收，本頁未收）。
- `extra`：**期末 ARR**（年度經常性收入），出自每季新聞稿第一段。4Q21 起新聞稿只寫到 0.01 億美元。
- `guidance.items[]`：下一季與全年營收、下一季與全年期末 ARR（新聞稿區間原文）。非 GAAP 營業利益、非 GAAP EPS 財測寫在 `guidance.note`，不列入。

## 核對規則（`python3 tools/validate.py crwd`）

1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年（FY2026 的毛利、營業利益、淨利例外，全年為 `null`）。
3. `waterfall` 每個小計 ＝ 前一個小計 ＋ 中間各項。
4. 淨利 ÷ 稀釋股數 ≈ EPS（虧損季度用基本股數，差距較大時看新聞稿）。
5. 財測區間上下限沒有顛倒；日期格式正確；`rd` 依季度遞增、在季末後 5～120 天內。

**任何一項沒過就不發佈**，回到來源修資料，不要放寬核對。

## 資產負債表欄位（shOut、dilSh、cash、debt、buyback、equity、pretax、tax）
配方在 `tools/bs_map.json` 的 `crwd`：
- `shOut`（百萬股）：`CommonStockSharesOutstanding`（只有 A、B 兩類合計時才有值）；**多數季度 XBRL 沒有總數**，3Q20、4Q20 申報值為 0（標記錯誤）→ 都填 `null`，見待確認。
- `dilSh`：`WeightedAverageNumberOfDilutedSharesOutstanding` 單季值（分割換算同 EPS）。
- `cash`：`CashAndCashEquivalentsAtCarryingValue` ＋ 短期投資（有才加）。
- `debt`：`LongTermDebtNoncurrent`（2021 年 1 月發行的 7.5 億美元優先票據）；3Q21 以前沒有債務 → `null`（照規則不填 0）。
- `buyback`：CrowdStrike 2025 年以前沒有回購，`null`。
- `equity`：`StockholdersEquity`；`pretax`、`tax`：單季值，第四季＝全年 − 前九月（4Q26 取新聞稿）。

## 電話會議（逐字稿）來源
- 官方：`https://ir.crowdstrike.com/`（網路直播與重播；官方沒有文字逐字稿）。
- 第三方逐字稿：尚未選定可穩定讀取的來源；讀不到時寫「待確認：逐字稿尚未取得」，不用新聞報導代替。口頭內容必附逐字稿連結與發言人。
- **公司有非 GAAP EPS**（新聞稿第一段就是非 GAAP；差距主要是股票酬勞）。本站 EPS 一律 GAAP 稀釋；和市場預期比較時，`cons.actualAlt` 填新聞稿的非 GAAP EPS、`basis` 寫「調整後」。

## 更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）

1. 查有沒有新財報：`data/sec-feed.json` 的 crwd 8-K Item 2.02，或 ir.crowdstrike.com 的「CrowdStrike Reports … Quarter Fiscal 20XX Financial Results」。**沒有新財報 → 跳到第 6 步。**
2. 有新財報：讀新聞稿，取單季營收、毛利、營業利益、稅前淨利、所得稅、淨利、GAAP 稀釋 EPS、稀釋股數、期末 ARR、營業現金流與資本支出（新聞稿現金流量表是年初累計，要相減）、現金、債務、股東權益、財測、非 GAAP EPS。
3. 新增一季到 `quarters[]`（`rd`＝新聞稿日，`rdB:"p"`）與 `extra.quarters[]`；第四季時新增 `annual`。舊 `guidance` 原封不動 append 進 `guidanceHistory` 再寫新的；`waterfall` 換成新一季；`events` 換成下一個公布日（公司公告前加 `est:1`）；`summary` 舊的精簡後移到 `summaryHistory`。
4. `python3 tools/validate.py crwd`；通過才繼續。
5. 10-Q 出來後用 XBRL 核對同一季的數字，有差異以 10-Q 為準並在 notes 記錄。
6. 查事件時間軸：併購、重大資安事件（例：2024-07 Channel File 291 當機）、回購授權、指數異動。
7. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `CRWD`（Nasdaq A 類普通股，美元） |
| 股價起點 | 2019-06（上市月份） |
| 股票分割 | 2026-07-02 一拆四（EPS 換算見上） |
| EPS 口徑 | GAAP 稀釋 EPS；多數年度 GAAP 虧損，本益比常為「不適用」 |
| 財報公布日 `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/crwd.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果見下表。

抽查 3 個月（最早 2019-06；分割前最後一個月 2026-06；最新 2026-10）。Yahoo 是分割調整後價格，2019-06 的 17.0725 對應當時未調整價約 68.29（×4）：

| 月份 | Yahoo 收盤價（分割調整後） | 第二來源 | 結果 |
|---|---|---|---|
| 2019-06（2019-06-28） | 17.0725 | — | 待確認：尚未對第二個獨立來源核對（這次沒有找到能讀到這一天的免費歷史股價來源） |
| 2026-06（2026-06-30） | 190.785 | — | 待確認：尚未對第二個獨立來源核對（這次沒有找到能讀到這一天的免費歷史股價來源） |
| 2026-10（2026-10-30） | 250.43 | — | 待確認：尚未對第二個獨立來源核對（這次沒有找到能讀到這一天的免費歷史股價來源） |

## 已知缺口（頁面「沒能取得的欄位」會列出）

- 上市前（FY2019 以前）：未收錄。
- FY2026 全年毛利、營業利益、淨利：口徑不一致，`null`。
- 期末流通股數多數季度、FY2022 以前的債務、回購：見 `notes.unavailable`。
