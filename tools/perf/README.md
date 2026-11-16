# 換頁效能量測

```
python3 tools/perf/serve_like_pages.py . 8791 &          # 模擬 GitHub Pages（gzip、快取 10 分鐘、ETag）
B=http://127.0.0.1:8791/ SEQ=nvda,amd,msft,tsmc CPU=4 SB=1 node tools/perf/switch_timing.js
```
`CPU=4` 是模擬 4 倍慢的裝置；`SB=1` 側邊欄展開；`W=390` 手機寬度。
看三個數字：內容就緒（→DCL）、主執行緒最長卡頓、版面跳動 CLS。
需要 `playwright`（node）。`site.perf` 在 companies.json，設 false 回到舊行為。

## 首頁瘦身（site.homeSlim）
首頁只放它用得到的欄位（`tools/build.py` 的 `HOME_KEYS`）。查「首頁實際讀了哪些欄位」的方法：
把首頁的 `DATA[code]` 包一層 `Proxy`，記錄 get／has／ownKeys，再把首頁所有按鈕、表頭、列都點過一輪。
新增首頁功能若讀到新欄位，要加進 `HOME_KEYS`；懷疑瘦身壞了就把 `homeSlim` 設 false。
