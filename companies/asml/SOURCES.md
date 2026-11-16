# 艾司摩爾 ASML Holding（ASML）資料來源與更新步驟

- 資料檔：`data/asml.json`（schema `v1`）　頁面：`/asml/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬歐元**；`eps` 為歐元。ASML 用 **US GAAP** 編季報與 20-F。
- 頻率：每季。財報日約在 1 月底、4 月中、7 月中、10 月中（歐洲早上公布，台北下午）。
- 排程：週二至週六（台北）每日檢查（docs/SCHEDULE_PROMPT.md）。只補「上次資料之後」的新期間。
- CIK：`0000937966`。**外國發行人**：不申報 10-Q／10-K／8-K，每季申報 **6-K**（附財報新聞稿、簡報、US GAAP 財務報表與季度彙總表），每年申報 **20-F**。`data/sec-feed.json` 的 8-K 規則不適用，要看 6-K。

## 會計年度與季度標籤
曆年制（`fiscalYearEnd` = `12-31`；季末日其實是接近季末的星期日，例如 3Q26 結束於 2026-09-27）。最新一季 3Q26（2026-10-14 公布），4Q26 預估 2027-01 底公布。

## 期間
1Q09–最新一季，共 71 季。2008 年以前沒收：2009 年 1 月新聞稿的季度彙總表沒有單季稀釋 EPS；2007 年四季加總和後來 20-F 的全年對不上（後來重編）；XBRL 從 2009 年 20-F 才有。

## 來源（依可信度）
1. **6-K 季度彙總表**（Quarterly Summary US GAAP Consolidated Statements of Operations／Balance Sheets／Cash Flows）：五欄＝去年第四季＋今年四季（或最近五季）。容器讀不到 sec.gov，用 GitHub Actions `sec-raw` 分支下載（`raw/asml/pr/`；工具已支援 6-K：1、4、7、10 月 8 日以後申報、內容含 net sales／gross／quarter 的文件全收）。
   - 3Q26：`https://www.sec.gov/Archives/edgar/data/937966/000162828026065813/financial_statementsxusx.htm`、新聞稿 `…/000162828026065813/pressreleasefinancialresul.htm`
   - 4Q25：`https://www.sec.gov/Archives/edgar/data/937966/000162828026003701/pressreleasefinancialresul.htm`
   - 2025 年 7 月起檔案是新版（文字被攤平成一行），用 `label 數字×5` 的方式讀；2024 年以前是表格。2011–2014 年的表格欄位順序相反（最新在左），要用上一年第四季對齊判斷。
2. **20-F XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0000937966.json`，只用來核對全年（每年取首次申報版本，概念依申報日最早者，不依概念名稱優先）。
3. 投資人關係 `https://www.asml.com/en/investors`（財報日期、股利與買回明細、影片訪談與逐字稿）。
4. 可信媒體：只用於事件時間軸；公司未證實的 `unc:1`，`note` 以「待確定：」開頭。

## 欄位定義（`quarters[]`）
| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | Total net sales |
| `gp`、`gm` | Gross profit |
| `opInc`、`om` | Income from operations |
| `ni` | Net income |
| `eps` | Diluted net income per ordinary share（歐元，照公告值；公司未回溯調整） |
| `ocf` | Net cash provided by (used in) operating activities（單季欄） |
| `capex` | Purchase of property, plant and equipment（正數） |
| `dps` | 本次未收錄（`null`）：股利是「某年度的期中股利」在之後的季度發放，還沒決定逐季對應方式 |
| `rd`、`rdB` | 財報新聞稿 6-K 申報日，`rdB:"p"` |

### 版本規則
**每一年的四季取自隔年 1 月第四季 6-K 的季度彙總表**（前三季是當時更新過的版本）；2026 年前三季取 2026-10-14 的表。不需要用全年相減，第四季直接有單季值。四季加總的營收、毛利、營業利益、淨利、營業現金流、資本支出都和 20-F 全年核對過（2009–2025 全部通過）。2016、2017 年是舊營收準則（2018 年 20-F 把 2017 年重編成 89.6 億歐元，本站照當年 90.5 億歐元）。

### 選用區塊
- `segments`：系統銷售（Net system sales）＋裝機服務（Net service and field option sales＝Installed Base Management），1Q09 起每季都有，加總＝營收。
- `guidance.items[]`：下一季營收、毛利率；全年營收、毛利率（ASML 不給 EPS 財測）。另外的研發、銷管、稅率財測寫在 `note`。
- `guidanceHistory`：從 2026-07-15 開始累積。

## 核對規則（`python3 tools/validate.py asml`）
毛利率／營益率自洽、`fcf=ocf−capex`、四季加總＝全年、分部加總＝營收、waterfall 自洽、淨利÷稀釋股數≈EPS、`rd` 遞增在季末後 5–120 天。**沒過不發佈**，不放寬核對。

## 資產負債表欄位（都取自季度彙總表）
- `shOut`：季度表沒有 → 全部 `null`（20-F 附註才有，尚未讀）。
- `dilSh`：損益表下方「Diluted」加權股數（百萬股；早年單位是千股，已換算）。2009 年沒有。
- `cash`：Cash and cash equivalents ＋ Short-term investments（2011 年以前季度表沒有短期投資 → `null`）。
- `debt`：Long-term debt（不含一年內到期部分，季度表沒分開列）。
- `buyback`：Purchase of treasury shares（正數）。
- `equity`：Total shareholders' equity。
- `pretax`：Income before income taxes；`tax`：所得稅（正數＝費用）。
- 讀不到的見 `notes.unavailable`。

## 電話會議（逐字稿）來源
- 官方：ASML 每季在 `https://www.asml.com/en/investors` 放 CEO／CFO 影片訪談與**影片逐字稿**，另有投資人電話會議。尚未實測能否讀取；讀不到寫「待確認：逐字稿尚未取得」。
- **公司沒有非 GAAP EPS**，直接比 GAAP 稀釋 EPS。

## 更新步驟（快報）
1. 查 SEC EDGAR 6-K 清單（`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000937966&type=6-K`）或 ASML 新聞稿頁有沒有新一季財報。**沒有 → 第 6 步。**
2. 讀 6-K 季度彙總表最右一欄：營收（系統、服務）、毛利、營業利益、稅前、所得稅、淨利、稀釋 EPS、稀釋股數、營業現金流、資本支出、買回、現金＋短期投資、長期借款、股東權益；新聞稿的下一季與全年財測、股利、買回。
3. 新增一季到 `quarters[]`（`rd`＝6-K 申報日，`rdB:"p"`）與 `segments.quarters[]`；第四季時新增 `annual`（20-F 出來後核對）。舊 `guidance` 原封不動 append 進 `guidanceHistory` 再寫新的；換 `waterfall`、`events`、`summary`。
4. `python3 tools/validate.py asml` 通過才繼續。
5. 20-F 出來後核對四季加總。
6. 查事件時間軸：出口管制（荷蘭、美國、歐盟）、產能計畫、併購與策略投資、買回計畫（優先 6-K 與公司新聞稿）。
7. `asOf` 改成今天，`python3 tools/build.py`，commit、push。

## 股價與財報公布日（本益比用）
| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `ASML.AS`（Euronext Amsterdam，歐元；和 EPS 同幣別。Nasdaq 的 `ASML` 是美元，不用） |
| 股價起點 | 2009-03 |
| 股票分割 | 2009 年以來沒有一般分割；2012 年第四季客戶共同投資計畫搭配資本返還（合成式股票買回），公司沒有回溯調整 EPS。待確認：Yahoo 是否把它當成分割調整了股價 |
| EPS 口徑 | US GAAP 稀釋 EPS |
| `rd` 來源 | 財報新聞稿 6-K 申報日（歐洲早上公布，等於公布當天） |

股價檔 `data/prices/asml.json` 只由 GitHub Actions（prices-monthly）寫入。

抽查（2026-11-16 prices-monthly 回補後）：

| 月份 | Yahoo 收盤價（分割調整後） | 第二來源 | 結果 |
|---|---|---|---|
| 2009-03（2009-03-31） | 17.3377 | — | 待確認：尚未對第二個獨立來源核對（沒有找到能讀到這一天的免費歷史股價來源） |
| 2012-10（2012-10-31，資本返還前） | 55.1299 | — | 待確認：尚未對第二個獨立來源核對（沒有找到能讀到這一天的免費歷史股價來源） |
| 2026-10（2026-10-30） | 1412.8 | — | 待確認：尚未對第二個獨立來源核對（沒有找到能讀到這一天的免費歷史股價來源） |

## 已知缺口
- 2008 年以前未收錄；`shOut`、`dps` 全部未收錄；早年 `dilSh`、`cash`、`buyback`、`pretax`、`tax` 部分季度見 `notes.unavailable`。

本益比連續性：2012-09～2013-01 為 18.6、20.3、17.7、17.6、20.6 倍；2012-11 月底股價比 10 月底低約 13%，和資本返還同時發生。待確認：這是實際股價變動，還是 Yahoo 調整方式造成，要找第二來源核對。
