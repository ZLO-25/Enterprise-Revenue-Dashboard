# 台積電（2330 / TSM）資料來源與更新步驟

- 資料檔：`data/tsmc.json`（schema `tsmc-legacy`）　頁面：`/tsmc/`　模板：`templates/tsmc.frag.html`
- 頻率：月營收（每月 10 日前）＋季報（1、4、7、10 月中旬法說會）
- 排程：每週一 08:00（台北）。**只有實質變動才 commit**；只有 `asOf` 變動不算。

## 欄位與單位

| 欄位 | 內容與單位 |
| --- | --- |
| `asOf` | 資料截至日（台北時間今天） |
| `monthly` | `{"2026":[一月,二月,…]}`，每月合併營收，**新台幣百萬元**（整數，例 511857），2015 起 |
| `provisional` | `{"2026-09":"說明"}`：官網尚無精確值、暫用新聞稿四捨五入數字的月份 |
| `yoy2015`、`yoy2015Total`、`yoy2020`、`yoy2020Total` | **不要動** |
| `quarters[]` | `q`（如 `3Q26`）、`rev`（百萬元）、`ni`（歸屬母公司淨利，百萬元）、`eps`（元）、`gm`、`om`（%）、`capex`（管理報告現金流量表 Capital Expenditures，正數，**新台幣十億元**）、`ocf`（Net Operating Sources，十億元）、`n2`、`n3`、`n5`、`n7`（各製程占晶圓營收 %）、`hpc`、`sp`（HPC、手機占營收 %）、`dps`（該季每股現金股利，董事會尚未核准填 `null`） |
| `epsOfficial` | `{"2025":66.25}` 各年度公司公布的全年 EPS |
| `capexUsd` | `{"2025":40.9}` 各年度全年資本支出（十億美元） |
| `dpsAnnual` | 2015–2018 年度股利，**不要動** |
| `capexBudget` | `{y, lo, hi, ytd, ytdLabel:"上半年"/"前三季", note}` 全年預算區間（十億美元） |
| `guidance` | 下一季財測 `{q, revUsdLo, revUsdHi, gmLo, gmHi, omLo, omHi}` |
| `events[]` | 之後的公布日 `{date, t}` |
| `waterfall` | 最新一季損益拆解 `{q, rows:[{n, v(新台幣億元，負數＝減項), t:1 小計}], note}`；rows 依序：營收、營業成本、毛利、研發費用、管理與行銷費用、其他營業收支、營業利益、業外收支、所得稅、非控制權益、淨利（歸屬母公司），取自 Quarterly Management Report |
| `milestones[]` | 技術里程碑 `{d, cat:"node"/"pkg", node, t, hvm:1（只有製程「量產」事件）, src, st:"p"/"f", unc:1（待確定）, note}` |
| `fabs[]` | 建廠 `{id（不可重複）, n, loc, c, tech, ms:[{k:"a"公布/"g"動工/"c"完工裝機開幕/"m"量產, d, t, src, st, unc, note}]}` |
| `fabNote` | 建廠區塊下方一句說明 |

日期格式只能是 `YYYY-MM-DD`、`YYYY-MM`、`YYYY-Qn`、`YYYY-Hn`、`YYYY`。`note` 只有來源是媒體時才以「媒體報導」開頭；待確定的以「待確定：」開頭。

## 來源（依可信度）

1. 台積電投資人關係網站：月營收 `https://investor.tsmc.com/english/monthly-revenue/{年}`、季報 `https://investor.tsmc.com/english/quarterly-results`（Quarterly Management Report）、財務行事曆 `https://investor.tsmc.com/english/financial-calendar`、法說會逐字稿、年報
2. 台積電新聞稿 `https://pr.tsmc.com/english/latest-news`（月營收新聞稿、季報新聞稿、董事會決議、技術論壇、建廠典禮）與官網 `https://www.tsmc.com/static/abouttsmcaz/index.htm`
3. 可信媒體（Reuters、Bloomberg、日經、中央社、經濟日報、工商時報、DigiTimes、TrendForce），**只用於技術與建廠事件**；公司未證實的一律 `unc:1`。論壇與社群貼文不收。

## 更新步驟

1. 月營收：讀官網當年度頁面；把官網已公布、JSON 還沒有的月份依序補進 `monthly`。`provisional` 的月份若官網已有精確值就換掉並刪除該筆。官網表格沒更新但新聞稿有「TSMC {Month} {Year} Revenue Report」時，用新聞稿億元數字換算成百萬元並在 `provisional` 加說明。一月時也讀去年頁面。
2. 季報：有新季報就新增 `quarters` 物件，並同步更新 `waterfall`（換成新一季）、`guidance`（換成再下一季）、`capexBudget`（公司調整預算才改）。第四季財報出來時：全年 EPS 加進 `epsOfficial`、全年美元資本支出加進 `capexUsd`、`capexBudget` 換成新年度。
3. 股利：董事會核准某季現金股利（新聞稿「Board of Directors Meeting Resolutions」）就把該季 `dps` 從 `null` 改成核准金額。
4. 公布日：用財務行事曆更新 `events`，只保留今天之後的。
5. 技術里程碑與建廠：查 `asOf` 之後（約 7–10 天）的新消息。
   - 一手來源證實的照一般方式寫；`src` 放一手來源。
   - 只有媒體報導、公司未證實的（含「據了解」「供應鏈指出」）：至少一家可信媒體才收，加 `unc:1`，`note` 以「待確定：」開頭說明哪家媒體、與公司說法有何不同。
   - 已有的待確定項目：公司證實後刪除 `unc`、`src` 換成一手來源；公司否認或明顯不會發生就刪除並在回報說明。
   - `st:"f"` 的事件日期已過且確認發生 → 改 `st:"p"`；時程改變 → 改日期並在 `note` 寫原時程。
   - 新廠區新增 `fabs` 物件；同廠區新事件加進它的 `ms`。**不要刪除已發生的歷史事件。**
6. 核對（`python3 tools/validate.py tsmc`）：JSON 可解析；每季 `rev` 與該季三個月 `monthly` 加總相差不超過 200（百萬元）；新數字、新增的里程碑與建廠事件都與來源逐一核對；日期格式正確、`fabs` 的 `id` 不重複。**沒過就不發佈，保留原值並在回報說明原因。**
7. 判斷實質變動：只有 `asOf` 變 ＝ 沒有新資料，不 commit、不發佈、不通知。

## 已知事項
- 季度營業現金流與資本支出（新台幣）3Q21 起來自 StockAnalysis（S&P Global）並與管理報告交叉核對；第四季淨利用台積電公布值。
- 月營收為自結數、未經會計師查核；季營收以季報為準。
