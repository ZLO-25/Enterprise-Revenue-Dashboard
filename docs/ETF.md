# ETF 追蹤頁（etf/）

ETF 沒有季報，所以不走公司頁的流程（companies.json、財報、本益比、論點卡都不用）。只追「價格、報酬、費用率、前十大持股」。

```
data/etf/config.json（清單，Claude 可以改）
        │
        ▼  GitHub Actions：prices-daily（每天多班，和個股同一個 job，0 token）
tools/etf_update.py
  ├─ Yahoo 日線收盤（台股 ETF 最新一天對證交所）→ data/etf/daily/<代號>.json
  ├─ 價格報酬 1M／3M／今年／1Y／3Y／5Y（不含配息）
  └─ 每 7 天：Yahoo 基金資料 → 前十大持股、費用率、資產規模
        │                       └─ 持股是本站公司 → 連公司頁＋那家公司 1 年報酬
        ▼
data/etf/latest.json ──► etf/ 頁面打開時直接讀（不必重建網站）
data/etf/daily/      ──► tools/kbar_update.py 一併產生 ETF 的 K 棒（看盤頁「ETF」那一組）
```

## 新增或移除一檔 ETF
1. 改 `data/etf/config.json` 的 `etfs`：`code` 一律 `etf_` 開頭小寫；`group` 要在 `groups` 裡；台股加 `twse`（證交所代號）；上市不滿 5 年可加 `from`（YYYY-MM）。
2. `why` 是**觀點**（Claude 的整理），頁面會標「觀點」。`issuerUrl` 要是查證過的發行商或證交所頁面。
3. `python3 tools/validate.py`、`python3 tools/build.py`，開 PR。合併後手動觸發一次 prices-daily（或等下一班）就會有資料。

## 資料誠實
- `data/etf/latest.json`、`data/etf/daily/`、`data/kbar/etf_*` **只由 Actions 寫**，Claude 不手填。
- 持股、費用率、資產規模來自 Yahoo（第三方整理），頁面標「未對發行商原始檔」並附發行商連結；讀不到寫「待確認」，不從記憶補。
- 報酬是價格報酬（不含配息），頁面有寫。

## 持股代號對應本站公司
`aliases`：Yahoo 持股代號 → 本站公司代號（例如 `TSM` → `tsmc`、`005930.KS` → `samsung`）。其他的自動用 companies.json 的 `price.yahoo` 與 `ticker` 對。
