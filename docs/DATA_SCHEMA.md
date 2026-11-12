# 資料格式 v1（`data/<代號>.json`）

每家公司一個 JSON。**共用欄位每家都一樣**，所以首頁、跨公司比較、長期指標、通用頁面模板都不用改程式就能用；**公司專屬的東西放在選用區塊**（`segments`、`extra`）或以代號命名的區塊。

```
data/<代號>.json
├─ asOf            資料截至日 YYYY-MM-DD
├─ company         代號、名稱、交易所、幣別、單位、公布節奏（頁面標頭用）
├─ quarters[]      ★ 共用季度資料（每家一樣的欄位）
├─ annual{}        公司公布的全年數字（鍵為年份）
├─ guidance        公司財測（items[] 形式）
├─ events[]        之後的公布日
├─ waterfall       最新一季從營收到淨利的拆解
├─ milestones[]    重要事件時間軸
├─ sources[]       頁面「資料來源」清單
├─ notes           取不到的欄位、一般注意事項
├─ segments        （選用）營收拆分：分部加總＝營收
├─ extra           （選用）公司專屬指標：表格＋圖
├─ monthly         （選用）月營收（目前只有台積電舊格式使用）
└─ fabs            （選用）建廠時程（台積電）
```

資料流：

```
data/<代號>.json ──► assets/adapters.js（轉接層：各種格式 → 標準季度序列 N）
                          │
                          ├─► assets/longterm.js  LT.metrics(N)：TTM、CAGR、利潤率變化、連續年增、FCF 率
                          │                        LT.freshness(D)：資料新鮮度
                          ├─► templates/home.frag.html   首頁卡片、記分板、比較圖、新鮮度表
                          └─► templates/generic.frag.html 通用公司頁（v1 直接可用）
```

## 共用欄位

### `asOf`
`"2026-10-25"`。排程每次執行都改成當天；只有 `asOf` 變動不算實質變動。

### `company`
| 欄位 | 說明 |
| --- | --- |
| `code` | 小寫代號，同 `companies.json` |
| `name`、`nameEn`、`ticker`、`exchange` | 顯示用 |
| `currency` | `USD`、`TWD`… |
| `unit` | 金額單位中文，例 `百萬美元`；所有金額欄位都用這個單位 |
| `epsUnit` | 每股單位，例 `美元` |
| `fiscalYearEnd` | `12-31`；會計年度不是曆年時請在 SOURCES.md 說明季度標籤的對應 |
| `lede` | （選用）頁面開頭一段說明 |
| `cadence[]` | （選用，最多 3 筆）`{when, what, which}` 公布節奏 |

### `quarters[]`（依時間排序，標籤 `nQyy`，例 `3Q26`）
| 欄位 | 必填 | 說明 |
| --- | --- | --- |
| `q` | ★ | 季度標籤 |
| `rev` | ★ | 營收 |
| `gp` | | 毛利 |
| `gm` | ★ | 毛利率 %（`gp ÷ rev × 100`，小數 1 位） |
| `opInc` | | 營業利益 |
| `om` | ★ | 營業利益率 % |
| `ni` | | 歸屬母公司淨利 |
| `eps` | ★ | 稀釋 EPS |
| `ocf` | | 營業現金流（單季） |
| `capex` | | 資本支出（正數） |
| `fcf` | | `ocf − capex`；沒填會自動算 |
| `dps` | | 每股現金股利；不配息 `null` |
| `shOut` | | 期末流通股數（百萬股，已換成今天的股數基準，2026-11 新增） |
| `dilSh` | | 稀釋加權股數（百萬股，同上；第四季多半沒有單季值） |
| `cash` | | 現金與投資（正數；口徑寫在 SOURCES.md） |
| `debt` | | 有息負債（正數；不含營業租賃） |
| `buyback` | | 當季回購金額（正數，現金流量表） |
| `equity` | | 股東權益（歸屬母公司，可為負） |
| `pretax` | | 稅前淨利 |
| `tax` | | 所得稅費用 |

取不到的欄位填 `null`，**不要估計**。驗證會檢查 `gm`、`om` 與金額自洽、`fcf = ocf − capex`、`capex ≥ 0`。

### `annual{}`
```json
"2025": { "rev": 1234.5, "gp": 800.0, "opInc": 300.0, "ni": 250.0, "eps": 1.23, "ocf": 400.0, "capex": 50.0 }
```
只放公司公布的全年數字；驗證會比對四季加總（誤差 ≤ 0.6 或 0.1%）。通用頁面的年度表以 `annual` 優先，沒有的欄位用四季加總。

### `guidance`
```json
{ "issued": "2026-08-01", "items": [
    { "label": "下一季營收", "period": "3Q26", "lo": 1500, "hi": 1520, "unit": "百萬美元", "note": "" },
    { "label": "全年營收", "period": "2026", "lo": 5900, "hi": 5950, "unit": "百萬美元", "note": "上修一次" } ],
  "note": "" }
```
`lo`、`hi` 相同代表單一數字；只有一端給 `null`。頁面會算中點。

### `events[]`
`{ "date": "2026-11-02", "t": "3Q26 財報", "est": 1 }`。公司尚未公告的日期加 `est:1`，並在 `t` 註明「預估」。**這是每日排程判斷「誰到期」的唯一依據**：日期早於今天、還在清單裡＝還沒處理；處理完要從 `events` 移除並加入下一個公布日（`validate.py` 會擋住早於 `asOf` 的舊項目）。新鮮度判斷：**確定的公布日已過，或預估日（`est`）已過 7 天，資料卻沒更新 → 首頁顯示「待更新」**。

### `waterfall`
```json
{ "q": "2Q26", "rows": [
  { "n": "營收", "v": 1935.5, "t": 1 }, { "n": "營業成本", "v": -296.9 }, { "n": "毛利", "v": 1638.6, "t": 1 },
  { "n": "營業費用", "v": -726.6 }, { "n": "營業利益", "v": 912.0, "t": 1 },
  { "n": "業外收支", "v": 169.3 }, { "n": "所得稅", "v": -15.4 }, { "n": "非控制權益", "v": -4.1 },
  { "n": "淨利（歸屬普通股股東）", "v": 1061.9, "t": 1 } ], "note": "" }
```
`t:1` 是小計；減項用負數。驗證會檢查每個小計 ＝ 前一個小計 ＋ 中間各項，以及第一列營收 ＝ 最新一季 `rev`。

### `milestones[]`
`{ "d", "cat", "t", "src", "st": "p"|"f", "unc"?: 1, "note"? }`
- `d` 只能是 `YYYY-MM-DD`、`YYYY-MM`、`YYYY-Qn`、`YYYY-Hn`、`YYYY`
- `cat` 建議：`contract`、`product`、`listing`、`index`、`profit`、`ma`、`capacity`、`mgmt`；可在頂層 `categories{}` 自訂中文名稱
- `st`：`p` 已發生、`f` 規劃中；`unc:1` 待確定（只有媒體報導），`note` 要以「待確定：」開頭
- `src` 必填（一手來源優先）

### `sources[]`、`notes`
```json
"sources": [ { "n": "SEC EDGAR", "url": "https://...", "note": "損益、現金流、EPS" } ],
"notes": { "unavailable": [ "總客戶數只在部分季度揭露" ], "general": "……" }
```

## 選用區塊

### `segments`（營收拆分，通用頁面畫堆疊長條）
```json
{ "title": "營收拆分：政府與商業", "unit": "百萬美元",
  "keys": [ { "k": "gov", "n": "政府" }, { "k": "com", "n": "商業" } ],
  "quarters": [ { "q": "3Q19", "gov": 96.8, "com": 93.7 } ], "note": "" }
```
驗證：各分部加總 ＝ 該季 `rev`（誤差 ≤ 0.15 或 0.2%）。

### `extra`（公司專屬指標，通用頁面畫表格＋圖）
```json
{ "title": "客戶與合約", "note": "公司於財報新聞稿揭露",
  "keys": [ { "k": "customers", "n": "客戶數", "chart": "bar", "zero": true },
            { "k": "nrr", "n": "淨留存率", "unit": "%", "pct": true, "chart": "line", "desc": "怎麼看這個指標" },
            { "k": "tcv", "n": "當季成交 TCV", "unit": "百萬美元", "dec": 1 } ],
  "quarters": [ { "q": "1Q26", "customers": 1007, "nrr": 124.0, "tcv": 1500.2 } ] }
```
`chart` 給 `"bar"` 或 `"line"` 才畫圖；`pct` 以 % 顯示；`dec` 小數位；`zero` Y 軸從 0 開始。沒揭露填 `null`。

### `glossary[]`（選用）
`[["名稱", "English", "說明", "公式"]]`，會接在通用小辭典後面。

## 舊格式
台積電用 `tsmc-legacy`（月營收百萬元、資本支出十億元等），由 `assets/adapters.js` 轉成標準序列；新公司一律用 v1，不要再新增格式。若真的需要新格式：在 `ADAPTERS` 加一個函式（約 15 行）、在 `tools/validate.py` 的 `SCHEMA_CHECKS` 加核對，其他都不用動。

## 本益比相關欄位（2026-11 新增）

```
 data/<代號>.json  quarters[].eps ─┐
 data/<代號>.json  quarters[].rd  ─┼─► tools/pe.py ─► valuation（建置時算出，放進頁面資料，不存檔）
 data/prices/<代號>.json          ─┘
   monthly[]  每月最後交易日收盤價（GitHub Actions 寫）
   forward[]  每月分析師預估快照（GitHub Actions 寫，不回填）
```

### `quarters[].rd` / `rdB`（財報公布日）
- `rd`：`YYYY-MM-DD`，那一季 EPS 第一次公開的日期；讀不到填 `null`，並在 `notes.unavailable` 加「待確認：<季度> 的財報公布日（rd）：原因」。最新一季不可為 `null`。
- `rdB`：`f` 10-Q／10-K 申報日（較晚、偏保守）、`p` 財報新聞稿日、`c` 公司法說會日、`t` 證交所 BWIBBU 財報生效日。
- 依季度遞增；與由 `fiscalYearEnd` 推得的季度結束日相差 5～120 天（`validate.py` 檢查）。台積電的 `quartersEarly` 不加。

### `data/prices/<代號>.json`
```json
{"symbol":"AAPL","currency":"USD","source":"Yahoo Finance …","fetched":"2026-11-12",
 "monthly":[{"m":"2026-10","d":"2026-10-30","c":123.45,"x":"twse"}],
 "forward":[{"m":"2026-11","asOf":"2026-12-02","fy1End":"2027-09-25","fy2End":"2028-09-25","eps1":8.1,"eps2":9.0,"n1":30,"n2":28}]}
```
- `c`：分割調整後、不含股利調整的收盤價；`c:null` 必須有 `why:"待確認：…"`。`x:"twse"` 表示已對證交所收盤價核對（差 ≤ 0.5%）。
- `forward[]`：`why` 有值代表那個月沒有可用預估（待確認）；一旦寫入不再覆寫。數字只是格式範例，不是真實股價。

### `companies.json` 的 `price`
`{"yahoo":"AAPL","from":"2008-10","currency":"USD","twse":"2330"}`（`twse` 只有台股填）；未上市填 `null`。

### valuation（`tools/pe.py` 輸出）
`monthly[] = {m,d,c,eps4,pe,why,ntm,fpe,fwhy,few}`；`why`：`loss` 近四季 EPS ≤ 0、`short` 已公布未滿四季、`missing` EPS 或公布日待確認、`price` 股價待確認。
`stats = {latest, med5, med10, pct10, fpeLatest, …}`：中位數與百分位只用有本益比的月份；少於 12 個月不算中位數、少於 24 個月不算百分位。
預估本益比：`NTM = w×eps1 + (1−w)×eps2`，`w = min(fy1End − 月底, 365) ÷ 365`；`NTM ≤ 0` 不計算；分析師少於 3 人照算但標「預估人數少」。

## 每日排程狀態（2026-11 新增）

```
 events[]（data/<代號>.json，公布日）──┐
 data/sec-feed.json（Actions 每天寫）──┼─► python3 tools/daily.py ─► 今天的工作清單
 data/calendar.json（狀態檔）──────────┘
```

`data/calendar.json`：`{"version":1,"lastRun","lastSuccess","companies":{"<代號>":{"state","target","tries","since","flashDate","note"}}}`。沒有紀錄的公司＝`waiting`。

| state | 意思 | 下一步 |
| --- | --- | --- |
| `waiting` | 沒有進行中的事 | 公布日隔天進入快報 |
| `flash` | 快報完成（書面數字、財測已上線，標「初版」） | 補完：電話會議重點、一頁總結定稿 |
| `completed` | 補完完成 | 核對：10-Q／XBRL，解除待確認；完成後 `set <代號> verified` 回到 `waiting` |
| `stuck` | 連續 5 次沒成功 | 停止自動重試、首頁標待更新、每日回報置頂，等使用者說「繼續 <代號>」 |

只用 `tools/daily.py`（`set`／`try`／`done`）改這個檔案，不手改。`companies.json` 每家有 `tz`（公布時區 US／TW／KR…），美股另有 `cik`（SEC 申報清單用）。

### `data/sec-feed.json`
`{"fetched","companies":{"<代號>":{"earnings8k":[{date,acc,doc}],"periodic":[{date,form,period,acc,doc}]}}}`：最近 3 筆 8-K Item 2.02（財報新聞稿）與 10-Q／10-K 申報，由 `.github/workflows/sec-feed.yml` 每週二至六 07:05（台北）寫入，Claude 不手填。已實測 GitHub Actions 讀得到 data.sec.gov（容器內讀不到）。

## 一頁季度摘要、財測歷史、市場預期（2026-11 新增，階段 2）

```
 公布日隔天（快報）          補完（1～3 天內）            核對（10-Q 出來後）
 ───────┬──────────────────┬──────────────────────────┬─────────────────────
        ▼                  ▼                          ▼
 summary.status="flash"   summary.status="final"      解除 notes.unavailable
 成績單、展望（書面）     ＋管理層說法、問答（口頭）   的待確認
 頁面標「初版 MM/DD」     頁面標「定稿 MM/DD」
```

### 四種來源標籤（每一句都要標，驗證會擋）
| tag | 名稱 | 意思 | 附帶要求 |
| --- | --- | --- | --- |
| `w` | 書面 | 申報文件或公司新聞稿 | 可附 `src:{n,url}` |
| `o` | 口頭 | 電話會議上講的 | **必附** `src:{n,url,speaker}`（逐字稿連結與發言人） |
| `e` | 分析師預估 | 市場共識 | 附快照日；只能用事前快照（`data/consensus/`），不可事後補 |
| `v` | 觀點 | Claude 的判斷，不是事實 | 不附來源；風險、論點燈號都用這個 |

口頭內容只放 `summary`（`mgmt`、`qa`、`outlook.items`），**不寫進 `guidance`（書面財測欄位）、不參與核對**。只摘要、不整段照抄，重要原話最多引一兩句。讀不到逐字稿：`pending` 寫「待確認：逐字稿尚未取得」，不用新聞報導代替。

### `summary`（只放最新一季；每家公司一份）
```json
"summary": {
  "q": "3Q27", "status": "flash|final", "flashDate": "2026-11-18", "finalDate": null,
  "headline": { "t": "一句話結論", "tag": "w" },
  "scorecard": [ { "k": "rev|gm|om|eps", "guideLabel": "下一季營收",
                   "cons": { "v": 109006.8, "snap": "2026-11-16", "n": 44, "basis": "調整後", "actualAlt": null } } ],
  "scorecardNote": "口徑說明",
  "outlook": { "dir": "up|flat|down|na", "items": [ { "t": "…", "tag": "w" } ] },
  "mgmt": [ { "t": "…", "tag": "o", "src": { "n": "逐字稿來源", "url": "https://…", "speaker": "CFO" } } ],
  "qa":   [ { "q": "分析師最在意的問題", "a": "回答摘要", "tag": "o", "src": { … } } ],
  "risks": [ { "t": "…", "tag": "v" } ], "next": "下一季要看什麼（觀點）",
  "pending": [ "待確認：逐字稿尚未取得" ]
}
```
- 「實際」直接讀 `quarters[]`；「公司上季財測」由程式從 `guidanceHistory` 找 `period == q` 的項目，**不用手填**；「市場預期」`cons` 從 `data/consensus/<代號>.json` 的快照抄，`snap` 必須是檔案裡存在的日期且不晚於 `flashDate`，`v` 的單位和 `quarters` 一樣（營收百萬）。
- 口徑：Yahoo 的 EPS 預估 `epsBasis` 是 `normalized`（調整後／非 GAAP）或 `gaap`。網站 EPS 是 GAAP 稀釋，所以 `normalized` 時要在 `cons.actualAlt` 填公司公布的非 GAAP EPS（新聞稿來的）來比，`basis` 寫「調整後」；沒有非 GAAP 數字的公司才直接比 GAAP，並在 `scorecardNote` 寫明。營收沒有口徑問題。
- 下一次財報進來時：把舊的 `summary` 精簡成 `{q,status,flashDate,finalDate,headline}` 放進 `summaryHistory[]`（由舊到新），再寫新的 `summary`。舊季度不回補。

### `guidanceHistory[]`
公司每次發布新財測時，**先把舊的整份 `guidance`（`issued`＋`items`）原封不動 append 進 `guidanceHistory`，再寫新的 `guidance`**。由舊到新排序，且每筆 `issued` 早於目前 `guidance.issued`。從 2026-11 開始累積，不回補更早的（資料檔原本只存最新一份，舊的已經找不回）。

### `data/consensus/<代號>.json`（GitHub Actions 寫，Claude 不手填）
`{"code","snapshots":[{date,period,epsAvg,epsLow,epsHigh,epsN,epsBasis,revAvg,revLow,revHigh,revN,cur}]}`。`tools/consensus.py` 每週二至六 07:40（台北，`consensus-daily.yml`）在「財報公布日前 14 天內」存一張；公布日（台北時間）當天早上為止。營收是原幣「元」（不是百萬）。舊快照不改、不補、不用今天的預估填過去。公司還沒公布但資料沒更新、或已有更新的 8-K Item 2.02 時不拍。分析師少於 3 位照存，頁面標「預估人數少」。已實測 Yahoo 有當季（`0q`）預估。

## 論點卡 data/thesis/<代號>.json
- `status`：`draft`（Claude 草稿，不上線）／`approved`（ZL 確認後才上線）。`build.py` 只注入 approved；approved 的每個 `metrics[].by` 必須是 `"ZL"`（validate 會擋）。
- 欄位：`oneLiner`、`metrics[{k,name,op,thr,note,by}]`（k 為 tools/thesis.py 認得的指標）、`breakWhen`、`risks[]`、`history[]`。
- 燈號 g／y／r／n 由 `python3 tools/thesis.py` 依最新資料算出，不手填；每日排程用 `--record` 把燈號變化寫進 history 並在回報提及。
- 新增公司：先寫 draft，等 ZL 確認再改 approved。

### 論點卡的分類與規則（2026-11-12 定案）
- 卡片 `type`：compounder（穩健複利）／growth（高成長）／cyclical（循環股）／turnaround（轉機／早期）；`caveat` 是固定加註（循環股：「綠燈代表景氣在上半場，不代表便宜或安全」；特斯拉：只檢查汽車與能源本業）。
- 每個指標有 `group`：`biz`（體質）或 `val`（估值）；卡片分兩區顯示，`breakWhen` 只引用體質指標。`by`：體質門檻 `ZL`；`analyst`（分析師建議，ZL 可改；估值門檻與分析師調整過的門檻都用它）。
- 新指標 key：`revYoyQ`（單季營收年增）、`gmQchg`（單季毛利率減前一季，百分點）。
- 估值門檻：本益比上限＝A、B 取低者（A＝近五年月本益比中位數，若 本益比÷g<1 放寬到 75 百分位；B＝g×1.5 高成長／g×2.5 穩健複利；g＝3、5 年 EPS CAGR 取低者、上限 25%）；循環股用 EV/Sales ≤ 近五年 75 百分位；轉機／早期不放估值指標。
