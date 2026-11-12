# Palo Alto Networks（PANW）資料來源與更新步驟

- 資料檔：`data/panw.json`（schema `v1`）　頁面：`/panw/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`），早年原始單位是千美元，保留到小數 3 位；每股數字（`eps`）為美元。Palo Alto Networks 不配息，`dps` 一律 `null`。
- 頻率：每季。財報日約在 8 月中下旬（或 9 月初）、11 月中旬、2 月中旬、5 月下旬（或 6 月初）（美股收盤後，美東下午 4:30 電話會議）。
- 排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md；公布日隔天先做「快報」，再「補完」「核對」）。排程只補「上次資料之後」的新期間，舊數字不重抓、不重核；**某個月沒有新財報時，只檢查事件時間軸與公布日**；沒有實質變動就不 commit。
- CIK：`0001327567`。

## 會計年度與季度標籤

會計年度在 **7 月 31 日**結束（固定月底），**季度標籤用公司自己的會計年度**（`company.fiscalYearEnd` 填 `07-31`）：

```
FY2026 = 2025/8/1 ─ 2026/7/31
  1Q26 = 2025/8/1  ─ 2025/10/31
  2Q26 = 2025/11/1 ─ 2026/1/31
  3Q26 = 2026/2/1  ─ 2026/4/30
  4Q26 = 2026/5/1  ─ 2026/7/31   ← 目前最新一季（2026-09-01 公布）
FY2027
  1Q27 = 2026/8/1  ─ 2026/10/31  ← 2026-11-18 公布（公司已公告）
```

`annual` 的鍵 `"2026"` 就是 FY2026（2025/8/1–2026/7/31）。

## 期間

4Q12（2012/5/1–2012/7/31）–最新一季，共 57 季。2012 年 7 月 NYSE 上市（2021 年轉到 Nasdaq）；4Q12 是上市後第一份財報（2012-09-10 新聞稿）。FY2012 前三季只在 S-1 出現，當時有可轉換特別股、EPS 與上市後不可比，所以不收，FY2012 全年也不列。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0001327567.json`。
2. **財報新聞稿（8-K Item 2.02 附件 99.1）**：近年檔名慣例 `ex991q{季}{年}earningsrelease.htm`，例：
   - 4Q26 `https://www.sec.gov/Archives/edgar/data/1327567/000132756726000019/ex991q426earningsrelease.htm`
   - 3Q26 `https://www.sec.gov/Archives/edgar/data/1327567/000132756726000012/ex991q326earningsrelease.htm`
   - 2Q26 `https://www.sec.gov/Archives/edgar/data/1327567/000132756726000003/ex991q226earningsrelease.htm`
   - 1Q26 `https://www.sec.gov/Archives/edgar/data/1327567/000132756725000032/ex991q126earningsrelease.htm`
   - 4Q12 `https://www.sec.gov/Archives/edgar/data/1327567/000119312512386605/d408809dex991.htm`
   第四季 EPS（FY2021 起）、NGS ARR、財測、損益拆解都從這裡讀。
3. 投資人關係 `https://investors.paloaltonetworks.com/`（財報日期公告、網路直播）。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`，`note` 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | 依序 `SalesRevenueNet`、`Revenues`、`RevenueFromContractWithCustomerExcludingAssessedTax`（同一期間以前面的優先）。**不用 `SalesRevenueGoodsNet`**：那是只有產品的營收，不是總營收 |
| `gp`、`gm` | `GrossProfit`；`gm`＝`gp`÷`rev`×100 |
| `opInc`、`om` | `OperatingIncomeLoss`（GAAP） |
| `ni` | `NetIncomeLoss` |
| `eps` | `EarningsPerShareDiluted`（GAAP 稀釋）；第四季見下；分割換算見下 |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`，年初累計相減 |
| `capex` | `PaymentsToAcquirePropertyPlantAndEquipment`，年初累計相減（正數） |
| `fcf` | `ocf − capex`（公司「調整後自由現金流」口徑不同，本站不用） |
| `dps` | 不配息，`null` |
| `rd`、`rdB` | 季末後 5–90 天內最後一份 8-K Item 2.02 的申報日，`rdB:"p"` |

### 每個會計年度只用一個版本（10-K 申報當時）
Palo Alto Networks 曾在年度中途改會計準則（例：FY2017 提前採用 ASU 2016-09 股票酬勞稅務處理，FY2017 10-K 把 1Q17 改成新口徑）。為了讓「四季加總＝全年」，**每個會計年度的季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本**，全年取原始 10-K。FY2018 以前是舊收入準則 ASC 605、FY2019 起 ASC 606，未自行重編。

### 第四季推算
**4Q ＝ 10-K 全年 − 前三季**（營收、毛利、營業利益、淨利、稅前淨利、所得稅）；現金流、資本支出、回購＝全年 − 前九月累計。結果與第四季新聞稿核對（例：4Q26 營業利益 172、淨利 −282 百萬美元）。**EPS 不相減**：FY2020 以前用 10-K 季度表的第四季單季 XBRL 值；4Q21–4Q26 用第四季新聞稿。

### 股票分割（兩次）
- 2022-09-14 起以一拆三後價格交易；2024-12-16 起以一拆二後價格交易。
- **以 EPS 第一次公開的日期判斷**：2022-09-14 以前公布的 EPS ÷6、稀釋股數 ×6；2022-09-14 到 2024-12-16 之間公布的 ÷2、×2；之後公布的（2Q25 起）不換算。小數保留 4 位。共 50 季換算。

### 選用區塊
- `segments`：無（公司只有一個報導分部）。
- `extra`：**次世代資安 ARR（NGS ARR）**，出自新聞稿重點。只收 4Q24–最新一季；更早的新聞稿寫法不同，尚未讀取。3Q26 起含 CyberArk、Chronosphere（3Q26 新聞稿：併購貢獻 16 億美元）。
- `guidance.items[]`：下一季與全年營收、下一季與全年 NGS ARR（新聞稿區間原文）。RPO、非 GAAP 營業利益率、非 GAAP EPS、調整後自由現金流率寫在 `guidance.note`。

## 核對規則（`python3 tools/validate.py panw`）

1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年（營收、毛利、營業利益、淨利、營業現金流、資本支出）。
3. `waterfall` 每個小計 ＝ 前一個小計 ＋ 中間各項。
4. 淨利 ÷ 稀釋股數 ≈ EPS。
5. 財測區間上下限沒有顛倒；日期格式正確；`rd` 依季度遞增、在季末後 5～120 天內。

**任何一項沒過就不發佈**，回到來源修資料，不要放寬核對。

## 資產負債表欄位（shOut、dilSh、cash、debt、buyback、equity、pretax、tax）
配方在 `tools/bs_map.json` 的 `panw`：
- `shOut`（百萬股）：`CommonStockSharesOutstanding`；沒有時用 10-Q 封面 `dei:EntityCommonStockSharesOutstanding`。分割前的股數不換算（期末股數只作參考，不參與 EPS）。
- `dilSh`：`WeightedAverageNumberOfDilutedSharesOutstanding` 單季值（分割換算同 EPS）。
- `cash`：`CashAndCashEquivalentsAtCarryingValue` ＋ 短期投資（`ShortTermInvestments` 或 `AvailableForSaleSecuritiesCurrent`）。不含長期投資。
- `debt`：只計可轉換公司債：`ConvertibleDebtNoncurrent` ＋ `ConvertibleDebtCurrent`（有才加）。2014 年 6 月第一次發行；到期年度只剩流動部分時 XBRL 沒有非流動科目 → `null`（見待確認）。申報值為 0 的季度照申報值。3Q26 起金額增加，時間點與併入 CyberArk 相同（是否全為 CyberArk 的可轉債，待下次讀 10-Q 附註確認）。
- `buyback`：`PaymentsForRepurchaseOfCommonStock`，年初累計相減。
- `equity`：`StockholdersEquity`；`pretax`、`tax`：單季值，第四季＝全年 − 前九月。

## 電話會議（逐字稿）來源
- 官方：`https://investors.paloaltonetworks.com/`（網路直播與重播；官方沒有文字逐字稿）。
- 第三方逐字稿：尚未選定可穩定讀取的來源；讀不到時寫「待確認：逐字稿尚未取得」，不用新聞報導代替。口頭內容必附逐字稿連結與發言人。
- **公司有非 GAAP EPS**（新聞稿第一段就是非 GAAP；差距主要是股票酬勞、併購攤銷與相關費用）。本站 EPS 一律 GAAP 稀釋；和市場預期比較時，`cons.actualAlt` 填新聞稿的非 GAAP EPS、`basis` 寫「調整後」。

## 更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）

1. 查有沒有新財報：`data/sec-feed.json` 的 panw 8-K Item 2.02，或投資人關係的「Palo Alto Networks Reports Fiscal … Quarter … Financial Results」。**沒有新財報 → 跳到第 6 步。**
2. 有新財報：讀新聞稿，取單季營收、毛利、營業利益、稅前淨利、所得稅、淨利、GAAP 稀釋 EPS、稀釋股數、NGS ARR、營業現金流與資本支出（新聞稿現金流量表是年初累計，要相減）、回購、現金、可轉換公司債、股東權益、財測、非 GAAP EPS。
3. 新增一季到 `quarters[]`（`rd`＝新聞稿日，`rdB:"p"`）與 `extra.quarters[]`；第四季時新增 `annual`。舊 `guidance` 原封不動 append 進 `guidanceHistory` 再寫新的；`waterfall` 換成新一季；`events` 換成下一個公布日（公司公告前加 `est:1`）；`summary` 舊的精簡後移到 `summaryHistory`。
4. `python3 tools/validate.py panw`；通過才繼續。
5. 10-Q 出來後用 XBRL 核對同一季的數字，有差異以 10-Q 為準並在 notes 記錄。
6. 查事件時間軸：併購（CyberArk、Chronosphere 之後的整合）、股票分割、回購授權、指數異動。
7. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `PANW`（Nasdaq 普通股，美元） |
| 股價起點 | 2012-07（上市月份） |
| 股票分割 | 2022-09 一拆三、2024-12 一拆二（EPS 換算見上） |
| EPS 口徑 | GAAP 稀釋 EPS（不用非 GAAP） |
| 財報公布日 `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/panw.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。抽查結果見下表。

抽查 4 個月（最早 2012-07；兩次分割前最後一個月 2022-08、2024-11；最新 2026-10）。Yahoo 是分割調整後價格（2022-09 以前 ×6、2022-09～2024-11 ×2 才是當時的掛牌價）：

| 月份 | Yahoo 收盤價（分割調整後） | 第二來源 | 結果 |
|---|---|---|---|
| 2012-07（2012-07-31） | 9.5233 | — | 待確認：尚未對第二個獨立來源核對（這次沒有找到能讀到這一天的免費歷史股價來源） |
| 2022-08（2022-08-31） | 92.8017 | — | 待確認：尚未對第二個獨立來源核對（這次沒有找到能讀到這一天的免費歷史股價來源） |
| 2024-11（2024-11-29） | 193.91 | — | 待確認：尚未對第二個獨立來源核對（這次沒有找到能讀到這一天的免費歷史股價來源） |
| 2026-10（2026-10-30） | 365.87 | — | 待確認：尚未對第二個獨立來源核對（這次沒有找到能讀到這一天的免費歷史股價來源） |

## 已知缺口（頁面「沒能取得的欄位」會列出）

- 上市前（FY2012 前三季）：未收錄；FY2012 全年不列。
- NGS ARR 4Q24 以前未收錄。
- 可轉換公司債部分季度、少數季度的回購：見 `notes.unavailable`。
