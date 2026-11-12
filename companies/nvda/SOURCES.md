# 輝達 NVIDIA（NVDA）資料來源與更新步驟

- 資料檔：`data/nvda.json`（schema `v1`）　頁面：`/nvda/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`），早年數字原始單位是千美元，所以保留到小數 3 位；每股數字（`eps`、`dps`）為美元，**已換算成今天的股數**。
- CIK：`0001045810`。頻率：每季。財報日約在 2、5、8、11 月下旬的週三（美股收盤後）。
- 排程：週二至週六 08:30（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md；公布日隔天先做「快報」，再「補完」「核對」）。排程只補「上次資料之後」的新期間，舊數字不重抓、不重核；**某個月沒有新財報時，只檢查事件時間軸與公布日**；沒有實質變動就不 commit。

## 會計年度與季度標籤

輝達的會計年度在 1 月最後一個週日結束，**季度標籤用公司自己的會計年度**：

```
FY2027 = 2026/1/26 ─ 2027/1/31
  1Q27 = 2026/1/26 ─ 2026/4/26
  2Q27 = 2026/4/27 ─ 2026/7/26
  3Q27 = 2026/7/27 ─ 2026/10/25
  4Q27 = 2026/10/26 ─ 2027/1/31
```

`annual` 的鍵 `"2026"` 就是 FY2026（2025/1/27–2026/1/25）。

## 期間

1Q10（FY2010 第一季，2009/2–2009/4）–最新一季。這是 SEC XBRL 結構化資料最早有完整單季數字的一季。FY2009 以前（1999–2009）只有舊式 HTML 財報，沒有收錄。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyconcept/CIK0001045810/us-gaap/{概念}.json`（WebFetch 讀得到；容器的 curl 會被擋）
   - 讀法：每個 (start, end) 取最近一次申報的值；單季（約 90 天）直接用，沒有單季的用年初累計相減。
2. **10-K 現金流量表 R 頁**：XBRL 缺漏的全年資本支出。輝達 10-K 用自訂概念 `nvda_PurchasesOfPropertyAndEquipmentAndIntangibleAssets`，API 讀不到，要開 R 頁：先讀 `…/{accession}/FilingSummary.xml` 找「Consolidated Statements of Cash Flows」的 `R#.htm`。已用過：FY2013 10-K `000104581013000008/R9.htm`、FY2016 `000104581016000205/R7.htm`、FY2019 `000104581019000023/R8.htm`、FY2021 `000104581021000010/R8.htm`。
3. **財報新聞稿（8-K 附件 99.1）**：`…/{accession}/q{季}fy{年}pr.htm`，CFO 說明是 `q{季}fy{年}cfocommentary.htm`。第四季 EPS、財測、損益拆解、股利都在這裡。8-K 主文件沒有附件連結時，開資料夾 `https://www.sec.gov/Archives/edgar/data/1045810/{accession}/` 看檔名。
4. 投資人關係 `https://investor.nvidia.com/`（財報日公告）
5. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | XBRL `Revenues`；FY2019 用 `RevenueFromContractWithCustomerExcludingAssessedTax` |
| `gp`、`gm` | `GrossProfit`；`gm`＝`gp`÷`rev`×100 |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss` |
| `eps` | `EarningsPerShareDiluted`，再除以分割倍數（見下） |
| `ocf` | `NetCashProvidedByUsedInOperatingActivities`，年初累計相減 |
| `capex` | 「購置不動產、設備與無形資產」：FY2020 以前 `PaymentsToAcquirePropertyPlantAndEquipment`，之後 `PaymentsToAcquireProductiveAssets`；缺的全年值用 10-K R 頁，缺的單季用新聞稿 |
| `fcf` | `ocf − capex` |
| `dps` | `CommonStockDividendsPerShareDeclared`，再除以分割倍數；第四季＝全年－前三季（10-K 股東權益表附註的「每股宣告並發放股利」） |

### EPS 與股利的股票分割換算

```
申報日期                     要除的倍數
2021-07-20 以前              ÷ 40  （之後有 4 比 1 與 10 比 1 兩次分割）
2021-07-20 ～ 2024-06-10     ÷ 10  （之後還有 10 比 1）
2024-06-10 以後              ÷ 1
```
看的是「那個數字是哪一天申報的」，不是季度本身。換算後保留小數 4 位。

### 第四季推算
**4Q ＝ 全年 − 前三季單季數字**（營收、毛利、營業利益、淨利、現金流、資本支出）。EPS 不能相減：FY2010–FY2020 取 XBRL 第四季值，FY2021 以後取下一年度第四季新聞稿（例如 FY2022 新聞稿同時列 4Q22 與 4Q21）。

## 核對規則（`python3 tools/validate.py nvda`）

1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 四季加總 ＝ 全年（營收、毛利、營業利益、淨利、營業現金流、資本支出）。
3. `waterfall` 每個小計 ＝ 前一個小計 ＋ 中間各項；第一列營收＝最新一季 `rev`。
4. 財測區間上下限沒有顛倒；日期格式正確。

**任何一項沒過就不發佈**，回到來源修資料，不要放寬核對。

## 更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）

1. 查有沒有新的財報 8-K（`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=1045810&type=8-K` 或 investor.nvidia.com）。**沒有新財報 → 跳到第 6 步。**
2. 有新財報：讀新聞稿，取得單季營收、毛利、營業利益、淨利、稀釋 EPS、現金流、資本支出、下一季財測、股利。
3. 10-Q 出來後，用 XBRL API 核對同一季的數字（以 XBRL 為準）；第四季用全年減前三季。
4. 新增一季到 `quarters[]`；第四季時新增 `annual`（`note` 寫會計年度起訖）。更新 `guidance`、`waterfall`、`events`（公司公告「Sets Conference Call」後改成實際日期並刪除 `est`）。
5. `python3 tools/validate.py nvda`；通過才繼續。
6. 查事件時間軸：併購、股票分割、股利變動、指數異動、重大產品（優先 SEC 8-K 與新聞稿）。
7. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 已知缺口（頁面「沒能取得的欄位」會列出）

- 1Q10–4Q11 單季資本支出：XBRL 只有 FY2010、FY2011 全年。
- 2Q16 營業利益（待確認，2026/11/12 再查仍無結論）：1Q16 10-Q 單季 176、2Q16 10-Q 單季 76、上半年累計 250（176＋76＝252，差 2 百萬美元）；2Q17 10-Q、1Q17 10-Q 的比較欄數字不變，皆無重編註記，FY2016 10-K 季度表沒有營業利益。本頁用單季 76，第四季用全年減前三季單季數字（250）。
- 2Q27 每股股利（已核對，2026/11/12）：2Q27 10-Q（`0001045810-26-000075`，2026-08-26 申報）股東權益表 Common Stock Dividends Per Share Declared 三個月 0.25 美元（上半年 0.26）；現金股利 6,047 百萬美元；2Q27 `dps` 填 0.25（申報日在 2024-06-10 之後，不用除分割倍數）。
- FY2000–FY2009：沒有 XBRL，未收錄。
- 市場平台營收（資料中心、遊戲、專業視覺化、車用）：CFO 說明有表格，但公司分類多次調整（FY27 起改為資料中心＋邊緣運算），尚未收錄。之後要加就放 `segments`，一季一份 CFO 說明，每份有當季、上一季與去年同季。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `NVDA`（主要掛牌地普通股，幣別 美元） |
| 股價起點 | 2009-02 |
| 股票分割 | 2021-07 一拆四、2024-06 一拆十（Yahoo Close 已依分割調整、不含股利調整，才跟本站已換算成今天股數的 EPS 對得上） |
| EPS 口徑 | 稀釋 EPS；都是公認會計準則數字，不用調整後 EPS |
| 財報公布日 `rd` 來源 | SEC XBRL 的 10-Q／10-K 申報日（rdB:f） |

**更新步驟（每日排程「快報」步驟；補完、核對見 docs/SCHEDULE_PROMPT.md）**
1. 新增一季時，同時填該季 `rd`（那一季 EPS 第一次公開的日期）與 `rdB`。讀不到就填 `null`，在 `notes.unavailable` 加「待確認：<季度> 的財報公布日（rd）：原因」，**不可以用「季度結束後幾天」推算**。最新一季的 `rd` 不可為 null。
2. 股價檔 `data/prices/nvda.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填、不修改；排程只檢查上個月有沒有進來。
3. 本益比（`tools/pe.py`）與預估本益比不存檔，建置時算出；預估只有每月 1–6 日 Actions 存下的快照，**不回填**。
4. 若這家公司發生股票分割：同一次完成 EPS 重編與股價檔重抓（手動觸發 prices-monthly 並填 `accept=nvda`），否則 validate 會因相鄰月份本益比跳動超過 3 倍而失敗。
5. 抽查紀錄（回補時每家人工對第二個獨立來源抽 3 個月：最早一個月、最近一次分割前一個月、最新一個月）：見下表。

| 月份 | Yahoo 收盤價 | 第二來源 | 結果 |
|---|---|---|---|
| 2009-02（2009-02-27） | 0.207 | — | 待確認：2026-11-12 嘗試的免費來源只提供最近約 50 個交易日，讀不到這一天，尚未完成第二來源核對 |
| 2024-05（2024-05-31） | 109.633 | — | 待確認：2026-11-12 嘗試的免費來源只提供最近約 50 個交易日，讀不到這一天，尚未完成第二來源核對 |
| 2026-10（2026-10-30） | 204.64 | stockanalysis.com/stocks/nvda/history | 一致（204.64；2026-11-12 讀取，頁面標示已依分割調整） |


## 資產負債表欄位（shOut、dilSh、cash、debt、buyback、equity、pretax、tax）
- 來源：SEC EDGAR XBRL companyconcept API，由 GitHub Actions 的 `bs-fetch` 產生提案（`data/bs-raw/<代號>.json`），`tools/bs_merge.py` 合併進資料檔。各欄位用哪些 XBRL 概念組成，寫在 `tools/bs_map.json`（必要項缺任何一項就整格填 null，不做部分加總）。
- 口徑：shOut＝期末在外流通股數（百萬股，分割後）；dilSh＝當季稀釋加權股數；cash＝現金及約當現金（不含有價證券）；debt＝有息負債（短期＋長期）；buyback＝當季股票買回金額（正數；年度累計相減得單季）；equity＝股東權益；pretax／tax＝稅前淨利／所得稅費用。
- 讀不到的季度為 null，原因彙整在 `notes.unavailable` 以「待確認：資產負債表欄位」開頭的幾行。新一季快報時，重跑 bs-fetch 後再 merge，或直接讀 10-Q／10-K 手動補。
- 合併時自動擋下：淨利÷稀釋股數與 EPS 對不上、股數差一個數量級、買回／負債／現金為負。
