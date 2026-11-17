# Google（Alphabet，GOOGL）資料來源與更新步驟

- 資料檔：`data/googl.json`（schema `v1`）　頁面：`/googl/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**；`eps`、`dps` 為美元（已換算成今天的股數基準，見「股票分割」）。
- 頻率：每季。財報日約在 2 月初、4 月底、7 月底、10 月底（美股收盤後）。
- 排程：週二至週六（台北）每日檢查（docs/SCHEDULE_PROMPT.md）。只補「上次資料之後」的新期間。
- CIK：Alphabet `0001652044`（2015-10 重組後）；2015 年以前的申報主體是 Google Inc. `0001288776`。

## 會計年度與季度標籤
曆年制（`fiscalYearEnd` = `12-31`）：1Q＝1–3 月……4Q＝10–12 月。目前最新一季 3Q26（2026-10-28 公布），4Q26 預估 2027-02 初公布。

## 期間
1Q09–最新一季，共 71 季。Google Inc. 2009 年第二季才開始用 XBRL；1Q09 全部取自 2009-04-16 財報新聞稿。

## 來源（依可信度）
1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0001652044.json`（2015 起）與 `CIK0001288776.json`（2009–2015）。容器 curl 被擋，用 GitHub Actions `sec-raw` 分支下載（`raw/googl/`、`raw/googinc/`）。
2. **財報新聞稿（8-K Item 2.02 附件 99.1）**，近年檔名 `googexhibit991q{季}{年}.htm`：
   - 3Q26 `https://www.sec.gov/Archives/edgar/data/1652044/000165204426000080/googexhibit991q32026.htm`
   第四季 EPS、分部營收、2012–2013 毛利、2015–2016 EPS、稀釋股數從這裡讀。
3. 投資人關係 `https://abc.xyz/investor/`。
4. 可信媒體：只用於事件時間軸；公司未證實的 `unc:1`，`note` 以「待確定：」開頭。

## 欄位定義（`quarters[]`）
| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `RevenueFromContractWithCustomerExcludingAssessedTax`（2018 起）、`Revenues`／`SalesRevenueNet` |
| `gp`、`gm` | `GrossProfit`；2Q12–4Q13 XBRL 沒有合併毛利 → 新聞稿營收 − 營業成本（`CostOfRevenue`） |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss`（全部淨利；公司已發行強制可轉換特別股（3Q26 新聞稿列有特別股股利），新聞稿另列「歸屬普通股淨利」，本站 `ni` 不扣特別股股利） |
| `eps` | GAAP 稀釋 EPS；2015–2016 年 XBRL 只有分股類值 → 取新聞稿 A 股稀釋 EPS；第四季見下 |
| `ocf`、`capex` | 營業現金流、`PaymentsToAcquirePropertyPlantAndEquipment`，年初累計相減 |
| `dps` | 每季普通股現金股利（2Q24 開始配息） |
| `rd`、`rdB` | 季末後 5–90 天內最後一份 8-K Item 2.02 申報日，`rdB:"p"` |

### 版本與第四季
每年季度數字取「該年 10-K 首次申報當時」的版本；**4Q ＝ 10-K 全年 − 前三季**，現金流＝全年 − 前九月；EPS 不相減，取第四季新聞稿（全年 EPS 與 10-K 一致才用）。例外：2012 年 Motorola Home 在 10-K 改列停業單位，2012 年改用之後重編過的季度數字（詳見 `notes.general`）。

### 股票分割（EPS 換算）
- 2014-04-03 發行 C 股（等同 2 換 1）：該日以前申報的 EPS ÷2 再 ÷20（合計 ÷40）。
- 2022-07-18 二十分之一分割（20 換 1）：該日以前申報的 EPS ÷20。
- 判斷依「數字的申報日」，不是季度。

### 選用區塊
- `segments`：Google Services、Google Cloud、Other Bets、避險損益（公司層級，可正可負），4Q20 起（新聞稿開始列三分部）。更早尚未讀取。
- `guidance`：**Alphabet 不給書面財測**，`items` 為空不是漏抓。

## 核對規則（`python3 tools/validate.py googl`）
毛利率／營益率自洽、`fcf=ocf−capex`、四季加總＝全年、分部加總＝營收、waterfall 自洽、淨利÷稀釋股數≈EPS、`rd` 遞增在季末後 5–120 天。**沒過不發佈**，不放寬核對。

## 資產負債表欄位
- `shOut`：`CommonStockSharesOutstanding`（各類股合計，換算到今天股數），缺時用封面 `dei`。
- `dilSh`：`WeightedAverageNumberOfDilutedSharesOutstanding` 單季值；缺的 49 季取新聞稿。
- `cash`：現金及約當現金 ＋ `MarketableSecuritiesCurrent`（或 `ShortTermInvestments`）。
- `debt`：`LongTermDebtNoncurrent`／`LongTermDebtAndCapitalLeaseObligations` ＋ 一年內到期 ＋ 商業本票。
- `buyback`：`PaymentsForRepurchaseOfCommonStock`（或 `…OfEquity`），年初累計相減；2015 年以前讀不到。
- `equity`：`StockholdersEquity`；`pretax`、`tax`：稅前淨利、`IncomeTaxExpenseBenefit`。
- 季度對齊用曆年季末日（Alphabet 有重編季度）。XBRL 沒有的改讀申報文件：1Q09、2Q14、3Q14、1Q15–3Q15 `shOut` 取 10-Q 資產負債表股東權益列的季底各類股合計（換算到今天股數）；1Q09 `cash`、`equity` 與 2009–2011 `debt` 取新聞稿資產負債表（2Q10 以前沒有借款科目＝0）；1Q09–3Q09、1Q12–4Q14 `buyback`＝0（新聞稿籌資活動沒有買回科目、各項加總等於合計）。2Q15 `dilSh` 公司沒有合併數字（A／B 與 C 股 EPS 不同），維持 `null`。

## 電話會議（逐字稿）來源
- 官方：`https://abc.xyz/investor/`（網路直播；公司有時會放文字稿）。讀不到寫「待確認：逐字稿尚未取得」。
- **公司沒有非 GAAP EPS**，可直接比 GAAP EPS（市場預期若為調整後要在 `scorecardNote` 寫明）。

## 更新步驟（快報）
1. 查 `data/sec-feed.json` 的 googl 8-K Item 2.02。**沒有新財報 → 第 6 步。**
2. 讀新聞稿：營收（分部、避險）、營業成本、營業利益、其他收支、稅前、所得稅、淨利、稀釋 EPS、稀釋股數、現金流、資本支出、回購、股利、現金、債務、股東權益。
3. 新增一季到 `quarters[]`（`rd`＝新聞稿日）與 `segments.quarters[]`；第四季時 10-K 出來後新增 `annual`。換 `waterfall`、`events`、`summary`（舊的移到 `summaryHistory`）。
4. `python3 tools/validate.py googl` 通過才繼續。
5. 10-Q／10-K 出來後用 XBRL 核對。
6. 查事件時間軸：反壟斷判決、Waymo、雲端大合約、股票分割（優先 8-K 與公司新聞稿）。
7. `asOf` 改成今天，`python3 tools/build.py`，commit、push。

## 股價與財報公布日（本益比用）
| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `GOOGL`（Nasdaq A 股，美元） |
| 股價起點 | 2009-03 |
| 股票分割 | 2014-04（C 股）與 2022-07（20 換 1）；Yahoo 股價已分割調整，EPS 依申報日換算，兩邊同一基準 |
| EPS 口徑 | GAAP 稀釋 EPS（2015–2016 為 A 股） |
| `rd` 來源 | 財報新聞稿的 8-K 申報日 |

股價檔 `data/prices/googl.json` 只由 GitHub Actions（prices-monthly）寫入。

抽查（2026-11-16 prices-monthly 回補後；最早、最近一次分割前、最新）：

| 月份 | Yahoo 收盤價（分割調整後） | 第二來源 | 結果 |
|---|---|---|---|
| 2009-03（2009-03-31） | 8.7102 | — | 待確認：尚未對第二個獨立來源核對（沒有找到能讀到這一天的免費歷史股價來源） |
| 2022-06（2022-06-30，20 換 1 分割前最後月底） | 108.963 | — | 待確認：尚未對第二個獨立來源核對（沒有找到能讀到這一天的免費歷史股價來源） |
| 2026-10（2026-10-30） | 279.84 | — | 待確認：尚未對第二個獨立來源核對（沒有找到能讀到這一天的免費歷史股價來源） |

## 已知缺口
- 2008 年以前未收錄；分部營收 4Q20 以前未讀取。
- 2Q15 稀釋加權股數：公司沒有合併數字，`null`。

本益比連續性：2014-02～05 為 31.9、29.3、28.0、29.9 倍，2022-05～08 為 20.6、19.7、21.6、20.1 倍，兩次分割前後沒有斷崖。注意 1Q26、2Q26 淨利含 377 億、980 億美元未實現投資利得，近四季 GAAP 本益比因此偏低（2026-10 為 14.6 倍）。

第二來源核對（2026-11-17 再試一次）：Stooq 的月線 CSV 擋自動讀取（robots），Macrotrends 只有年資料或擋讀取，ASML 頁也擋。三個抽查月份仍是「待確認」。股價本身照 Yahoo（prices-monthly）保留，不改成 null，因為股價有讀到，只是還沒有第二來源可以比對。
