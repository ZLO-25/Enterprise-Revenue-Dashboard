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
`{ "date": "2026-11-02", "t": "3Q26 財報", "est": 1 }`。只保留今天之後的；公司尚未公告的日期加 `est:1`，並在 `t` 註明「預估」。新鮮度判斷：**沒有 `est` 的公布日已過、資料卻沒更新 → 首頁顯示「待更新」**。

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
