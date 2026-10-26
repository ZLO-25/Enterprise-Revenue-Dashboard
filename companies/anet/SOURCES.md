# Arista Networks（ANET）資料來源與更新步驟

- 資料檔：`data/anet.json`（schema `v1`）　頁面：`/anet/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`），XBRL 原始單位是美元，除以 100 萬後取到小數 1 位；每股數字（`eps`）為美元，**已換算成今天的股數**，保留小數 4 位。
- CIK：`0001596532`。交易所：NYSE（2014-06-06 上市）。頻率：每季。財報日約在 2、5、8、11 月上旬（美股收盤後）。
- 排程：每月 12 日 07:48（台北）。排程只補「上次資料之後」的新期間，舊數字不重抓、不重核；**某個月沒有新財報時，只檢查事件時間軸與公布日**；沒有實質變動就不 commit。

## 期間

1Q14（上市那一年的第一季）–最新一季。

- 2013 年：XBRL 只有 2Q13、3Q13 單季數字，1Q13 與 4Q13 的單季 EPS 在任何 SEC 申報文件都沒有揭露（2014 年 10-K 沒有季度表），EPS 是必要欄位，所以 2013 年整年不收。
- 2012 年以前：未上市，沒有季度財報。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyconcept/CIK0001596532/us-gaap/{概念}.json`（WebFetch 讀得到；容器與使用者電腦的 curl 都會被擋）
   - 讀法：每個 (start, end) 取最近一次申報（filed 最晚）的值；單季（約 90 天）直接用，沒有單季的用年初累計相減。
2. **財報新聞稿（8-K 附件 99.1）**：`https://www.sec.gov/Archives/edgar/data/1596532/{accession}/ex991q{季}{年兩碼}-earningsrelease.htm`，例：`000159653226000174/ex991q226-earningsrelease.htm`（2Q26）。第四季 EPS、財測、損益拆解都在這裡。2023 年的新聞稿在 SEC 上表格是圖片，改用公司網站 `https://www.arista.com/en/company/news/press-release/...` 的文字版。
3. 投資人關係 `https://investors.arista.com/`（財報日公告：「Arista Networks to Announce Qx YYYY Financial Results」）
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | 2014–2016：XBRL `SalesRevenueNet`；2017 起：`RevenueFromContractWithCustomerExcludingAssessedTax`（兩個概念在 2016–2017 重疊期間數字相同） |
| `gp`、`gm` | `GrossProfit`；`gm`＝`gp`÷`rev`×100 |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss`。注意：2021–2025 全年值在 API 裡最新一筆是 DEF 14A（委託書）以「百萬」為單位申報的數字，要只取 `form = 10-K` 的那筆 |
| `eps` | `EarningsPerShareDiluted`，再除以分割倍數（見下） |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`，年初累計相減 |
| `capex` | 10-Q：`PaymentsToAcquirePropertyPlantAndEquipment`；2020 年以後 10-K 全年值改用 `PaymentsToAcquireProductiveAssets`（同一行「購置不動產與設備」，2019 年兩個概念數字相同） |
| `fcf` | `ocf − capex` |
| `dps` | 不配息，一律 `null` |

### EPS 的股票分割換算

```
那個數字的申報日期             要除的倍數
2021-11-18 以前                ÷ 16  （之後有 2021-11、2024-12 兩次 1 拆 4）
2021-11-18 ～ 2024-12-04       ÷ 4   （之後還有 2024-12 的 1 拆 4）
2024-12-04 以後                ÷ 1
```
看的是「數字是哪一天申報的」，不是季度本身（XBRL 會在後來的申報重新以新股數申報舊季度）。

### 第四季推算
**4Q ＝ 全年 − 前三季單季數字**（營收、毛利、營業利益、淨利、現金流、資本支出）。2014–2020 年的 10-K 另有單季數字，推算結果與之一致。EPS 不能相減：

| 季度 | 來源 | 原始值 | 換算 |
| --- | --- | --- | --- |
| 4Q14–4Q19 | 10-K XBRL 季度數字 | 依申報日 | ÷16 |
| 4Q20 | 2020 10-K XBRL（2021-02-19） | 2.31 | ÷16 |
| 4Q21 | 4Q21 新聞稿（2022-02-14，已反映 2021 分割） | 0.75 | ÷4 |
| 4Q22、4Q23 | 4Q23 新聞稿（2024-02-12） | 1.35、1.92 | ÷4 |
| 4Q24、4Q25 | 4Q25 新聞稿（2026-02-12） | 0.62、0.75 | ÷1 |

## 核對規則（`python3 tools/validate.py anet`）

1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年（營收、毛利、營業利益、淨利、營業現金流、資本支出）。
3. `waterfall` 每個小計 ＝ 前一個小計 ＋ 中間各項；第一列營收＝最新一季 `rev`。
4. 推算的第四季與新聞稿核對過：4Q21–4Q25 的淨利都一致，4Q21、4Q23、4Q24、4Q25 的營收也一致（差 ≤ 0.1，四捨五入；4Q22 新聞稿文字版沒有列營收）。

**任何一項沒過就不發佈**，回到來源修資料，不要放寬核對。

## 更新步驟（每月排程）

1. 查有沒有新的財報 8-K（investors.arista.com 或 SEC EDGAR）。**沒有新財報 → 跳到第 6 步。**
2. 有新財報：讀新聞稿，取得單季營收、毛利、營業利益、淨利、稀釋 EPS、下一季財測（營收、非 GAAP 營業利益率、非 GAAP EPS）。
3. 10-Q 出來後，用 XBRL API 核對同一季（以 XBRL 為準）；現金流與資本支出用年初累計相減。第四季用全年減前三季，EPS 取新聞稿。
4. 新增一季到 `quarters[]`；第四季時新增 `annual`。更新 `guidance`、`waterfall`、`events`（公司公告財報日後改成實際日期並刪除 `est`）。
5. `python3 tools/validate.py anet`；通過才繼續。
6. 查事件時間軸：併購、股票分割、買回、指數異動、重大產品（優先 SEC 8-K 與公司新聞稿）。
7. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 已知缺口（頁面「沒能取得的欄位」會列出）

- 2013 年各季（見「期間」）。
- 產品／服務營收拆分：新聞稿有，尚未收錄；要加就放 `segments`（`product`、`service`）。
