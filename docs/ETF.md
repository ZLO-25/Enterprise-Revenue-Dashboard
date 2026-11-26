# ETF 追蹤頁（etf/）

ETF 沒有季報，所以不走公司頁的流程（companies.json、財報、論點卡都不用）。追「價格、報酬、費用率、前十大持股、ETF 本益比」。

```
data/etf/config.json（清單，Claude 可以改）
        │
        ▼  GitHub Actions：prices-daily（每天多班，和個股同一個 job，0 token）
tools/etf_update.py
  ├─ Yahoo 日線收盤，上市以來全部（台股 ETF 最新一天對證交所）→ data/etf/daily/<代號>.json
  ├─ 價格報酬 1M／3M／今年／1Y／3Y／5Y／10Y／上市以來（不含配息）
  └─ 每 7 天：Yahoo 基金資料 → 前十大持股、費用率、資產規模、本益比（trailingPE）
              證交所／櫃買中心公開資料 → 台股持股的中文簡稱（data/etf/twnames.json）
              quant/data/rates.json → 同幣別 10 年期公債利差（盈餘殖利率 − 公債殖利率）
        │                       └─ 持股是本站公司 → 連公司頁＋那家公司 1 年報酬＋個股本益比（data/daily/_pe.json）
        ▼
data/etf/latest.json ──► etf/ 頁面打開時直接讀（不必重建網站）；個股頁第 ④ 關也讀同幣別大盤 ETF 本益比
data/etf/daily/      ──► tools/kbar_update.py 一併產生 ETF 的 K 棒（看盤頁「ETF」那一組）
```

## 新增或移除一檔 ETF
1. 改 `data/etf/config.json` 的 `etfs`：`code` 一律 `etf_` 開頭小寫；`group` 要在 `groups` 裡；台股加 `twse`（證交所代號）；上市不滿 5 年可加 `from`（YYYY-MM）；循環型產業可加 `"cyclical": true`（頁面標註假便宜陷阱提醒）。
2. `why` 是**觀點**（Claude 的整理），頁面會標「觀點」。`issuerUrl` 要是查證過的發行商或證交所頁面。
3. `python3 tools/validate.py`、`python3 tools/build.py`，開 PR。合併後手動觸發一次 prices-daily（或等下一班）就會有資料。

## 頁面操作
- 主題：「全部」照分類分段顯示，也可只看一類。期間：1／3／6 個月、今年、1／3／5／10 年、上市以來、自訂起訖日；刻度可切對數。選擇記在網址（可分享）與這台裝置。
- 估值比較列：頂端顯示「大盤估值錨點」（`VOO`、`QQQ`、`0050`）與「主題估值對照」（依本益比由高到低排序），點選可跳到該 ETF 卡片。
- `kind: "commodity"`（實物黃金、期貨）沒有股票持股與盈餘，卡片顯示 `holdingsNote`，本益比顯示「商品／期貨不適用」。

## ETF 本益比與月度快照
- **來源**：Yahoo Finance 基金資料 `trailingPE`（加權過去 12 個月本益比），與持股、費用率同樣每 7 天更新（首次缺 `pe` 的股票型 ETF 會立即排程抓取）。
- **換算與門檻**：盈餘殖利率 ＝ `100 ÷ 本益比`（%）；對照 `quant/data/rates.json` 計算同幣別 10 年期公債利差（`USD → us_10y`、`TWD → tw_10y`）。非正數不採用；超過 200 倍標 `noisy: true`、頁面顯示「不適用」。
- **月度快照（`peHist`）**：自上線起，對有有效本益比（非商品、非 `noisy`、非 `stale`）的股票型 ETF，依 `YYYY-MM` 逐月留存當月最後快照（**不回填**）。
- **前十大持股本益比**：持股若是本站追蹤公司，讀 `data/daily/_pe.json` 附上該公司最新每日本益比（`pe`、`peD`），超過 200 倍顯示「不適用」。

## 資料誠實
- `data/etf/latest.json`、`data/etf/daily/`、`data/kbar/etf_*` **只由 Actions 寫**，Claude 不手填。
- 持股、費用率、資產規模、ETF 本益比來自 Yahoo（第三方整理），頁面標「未對發行商原始檔」並附發行商連結；讀不到寫「待確認」，不從記憶補。
- 報酬是價格報酬（不含配息），頁面有寫。

## 持股代號對應本站公司
`aliases`：Yahoo 持股代號 → 本站公司代號（例如 `TSM` → `tsmc`、`005930.KS` → `samsung`）。其他的自動用 companies.json 的 `price.yahoo` 與 `ticker` 對。
