# Palantir Technologies（PLTR）資料來源與更新步驟

- 資料檔：`data/pltr.json`（schema `v1` ＋ `pltr` 專屬區塊）　頁面：`/pltr/`　模板：`templates/pltr.frag.html`
- 單位：**美元百萬元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf` 等）；每股數字（`eps`、`adjEps`）為美元。
- 頻率：每季。財報日約在 2、5、8、11 月的第一個週一（5:00 PM ET 開電話會議）。CIK：`0001321655`。
- 排程：每月 12 日 07:48（台北）。排程只補「上次資料之後」的新期間，舊數字不重抓、不重核；**某個月沒有新財報時，只檢查事件時間軸與公布日**；沒有實質變動就不 commit。

## 期間

3Q19–最新一季。再早的季度（1Q19、2Q19）取不到單季的政府／商業拆分，所以不收。（上市是 2020-09-30 直接上市。）

## 來源（依可信度）

1. **SEC EDGAR**
   - 8-K 附件 99.1「Palantir Reports Qx YYYY …」財報新聞稿（調整後數字、財測、客戶與合約指標都在這裡）。檔名慣例：`a{年}q{季}ex991pressrelease.htm`／`…earningsrelease.htm`，網址 `https://www.sec.gov/Archives/edgar/data/1321655/{accession 去掉連字號}/{檔名}`；2021–2022 年初的新聞稿檔名是 `d…dex991.htm`。
   - 10-Q／10-K 與其 XBRL：`https://data.sec.gov/api/xbrl/companyconcept/CIK0001321655/us-gaap/{概念}.json`。
   - 政府／商業拆分：每份申報的 `R*.htm`「Segment and Geographic Information – Summary of Financial Information for Each Reportable Segment (Detail)」（用 `FilingSummary.xml` 找檔名）。
   - 全文搜尋找申報清單：`https://efts.sec.gov/LATEST/search-index?q=%22Palantir%22&forms=8-K&ciks=0001321655`。
2. Palantir 投資人關係網站 `https://investors.palantir.com/`（新聞稿、簡報、股東信）
3. 法說會逐字稿
4. 可信媒體（Reuters、Bloomberg、CNBC 等）：**只用於事件時間軸**；公司未證實的一律 `unc:1`。

## 欄位定義

### 共用欄位（`quarters[]`，每季一筆，依時間排序）
| 欄位 | 來源 |
| --- | --- |
| `rev` | XBRL `RevenueFromContractWithCustomerExcludingAssessedTax`（單季） |
| `gp`、`gm` | XBRL `GrossProfit`；`gm`＝`gp`÷`rev`×100（取到小數 1 位） |
| `opInc`、`om` | XBRL `OperatingIncomeLoss`（GAAP 營業利益／損失） |
| `ni` | XBRL `NetIncomeLoss`（歸屬普通股股東） |
| `eps` | 稀釋後每股盈餘（GAAP）：XBRL `EarningsPerShareDiluted`；第四季取財報新聞稿的 Q4 欄 |
| `ocf` | XBRL `NetCashProvidedByUsedInOperatingActivities`，**年初累計相減得單季** |
| `capex` | XBRL `PaymentsToAcquirePropertyPlantAndEquipment`（現金流量表 purchases of property and equipment），累計相減，正數 |
| `fcf` | `ocf − capex`（GAAP 口徑，未加回雇主稅） |
| `dps` | 不配息，一律 `null` |

### 第四季推算
10-K 只有全年，所以：**4Q ＝ 全年 − 前三季累計**（收入、毛利、營業利益、淨利、現金流、資本支出、SBC 都一樣）。EPS 不能相減，取新聞稿 Q4 欄的數字。

### `annual{}`
全年數字：`rev`、`gp`、`opInc`、`ni`、`eps`（10-K 全年稀釋 EPS）、`ocf`、`capex`、`adjOpInc`、`adjOm`、`sbc`、`adjEps`、`adjFcf`。調整後的全年數字用公司新聞稿 Q4 欄的 FY 值。

### `pltr.quarters[]`（與 `quarters[]` 同序同長度）
| 欄位 | 內容 | 來源 |
| --- | --- | --- |
| `gov`、`com` | 政府、商業營收（`gov + com = rev`） | 10-Q／10-K segment 附註；4Q ＝ 全年 − 9M |
| `usCom`、`usGov` | 美國商業、美國政府營收（公司有揭露才填） | 新聞稿（以百萬美元揭露） |
| `usComCustomers` | 美國商業客戶數 | 新聞稿 |
| `customers`、`top20Avg` | 總客戶數、前 20 大客戶近 12 個月平均營收（百萬美元） | 10-Q／10-K MD&A 關鍵指標 |
| `tcv`、`usComTcv` | 當季成交 TCV、美國商業 TCV | 新聞稿 |
| `deals1m`、`deals5m`、`deals10m` | ≥100 萬／500 萬／1,000 萬美元合約數 | 新聞稿 |
| `usComRdv` | 美國商業剩餘交易價值（RDV） | 新聞稿 |
| `rpo` | 剩餘履約義務 | XBRL `RevenueRemainingPerformanceObligation`（期末，公司四捨五入到 0.1B） |
| `adjOpInc` | 調整後營業利益（排除 SBC 與相關雇主稅；3Q20 另排除直接上市費用） | 新聞稿調節表；3Q21 已與新聞稿核對（116.1）|
| `adjEps` | 調整後 EPS（長期稅率 23%） | 新聞稿；公司未公布者為 `null` |
| `adjFcf` | 調整後自由現金流＝營業現金流＋為 SBC 代繳的雇主稅−資本支出 | 新聞稿；3Q20、3Q21 已與新聞稿核對（116.1）|
| `sbc` | 股票酬勞費用 | XBRL `ShareBasedCompensation`，累計相減 |

**Rule of 40 不存**：頁面用「營收年增率＋調整後營業利益率」計算（公司自 1Q24 起公布的定義）。公司公布值與計算值差 ≤1 點屬四捨五入。沒揭露的欄位一律 `null`，**不要估計**。

### 其他區塊
- `guidance`：`issued`（財報日）、`nextQ{q, revLo, revHi, adjOpIncLo, adjOpIncHi}`、`year{y, revLo, revHi, usComRevMin, adjOpIncLo, adjOpIncHi, adjFcfLo, adjFcfHi, note}`；每季財報後整份換成最新一次。
- `events[]`：下一次財報日。公司尚未公告時用預估日（第一個週一）並加 `est:1`、`t` 註明「預估日期，公司尚未公告」；公司公告後改成實際日期並刪除 `est`。
- `waterfall`：最新一季損益拆解，單位百萬美元；rows 依序：營收、營業成本、毛利、銷售與行銷費用、研發費用、一般與行政費用、營業利益、利息與其他收益、所得稅、非控制權益、淨利（歸屬普通股股東）。取自 10-Q 損益表（利息收入＋其他收益淨額合併成一列，必須與 `ni` 對得起來）。
- `milestones[]`：`cat` 為 `listing`／`index`／`product`／`contract`／`profit`；格式、`unc` 規則同共用框架。
- `pltrNotes.unavailable[]`：目前取不到的欄位，頁面會列出。

## 核對規則（`python3 tools/validate.py pltr`）

1. 政府＋商業 ＝ 總營收（誤差 ≤ 0.15）。
2. 四季加總 ＝ 10-K 全年（營收、毛利、營業利益、淨利、營業現金流、資本支出、調整後營業利益、調整後自由現金流、SBC，誤差在四捨五入範圍內）。
3. EPS、淨利以財報為準；非 GAAP 數字要與新聞稿的調節表一致。
4. 毛利率、營業利益率與金額自洽。
5. 財測區間上下限沒有顛倒。

**任何一項沒過就不發佈該公司**，保留原值並在回報說明哪一項、差多少。

## 更新步驟（每月排程）

1. 查有沒有新的 8-K 財報新聞稿（EDGAR 全文搜尋，或看 `investors.palantir.com`）。**沒有新財報 → 跳到第 6 步。**
2. 有新財報：讀新聞稿，取得 Q 欄的營收、調整後數字、財測、TCV／deals／RDV 等。
3. 讀同季 10-Q（或 10-K）的 XBRL：用上表概念更新 `quarters[]`；政府／商業取自 segment 的 R 檔；第四季用全年減 9M。
4. 更新 `annual`（第四季時新增該年）、`guidance`、`waterfall`、`events`、`pltr.quarters[]`。
5. 執行核對；通過才繼續。
6. 查事件時間軸：搜尋 Palantir 新合約、指數異動、產品發表、交易所異動（優先 SEC 8-K、國防部／陸軍新聞稿、Nasdaq；媒體須是可信來源）。公司證實的照常收錄；只有媒體報導的加 `unc:1`；已有的「待確定」若公司證實就刪除 `unc` 並換成一手來源。
7. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 已知缺口（取不到或公司未揭露）

- 1Q19、2Q19 單季數字。
- 總客戶數：只有 1Q25（769）、1Q26（1,007）在已取得的 10-Q 找到；前 20 大客戶平均營收只有 4Q20、1Q25、1Q26。
- 總 RDV 公司未揭露，只有美國商業 RDV（4Q24 起在已取得的新聞稿中有數字）。
- TCV、大額合約數只在部分季度揭露。
- 調整後 EPS：3Q20 公司未公布。
- 3Q21、3Q22 的新聞稿檔名不符慣例（`d51038dex991.htm`、`a2022q3ex991pressrelease.htm`），要用 EDGAR 全文搜尋指定月份與 `forms=8-K` 才找得到。
