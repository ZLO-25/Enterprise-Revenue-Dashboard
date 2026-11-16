# 換頁效能量測

```
python3 tools/perf/serve_like_pages.py . 8791 &          # 模擬 GitHub Pages（gzip、快取 10 分鐘、ETag）
B=http://127.0.0.1:8791/ SEQ=nvda,amd,msft,tsmc CPU=4 SB=1 node tools/perf/switch_timing.js
```
`CPU=4` 是模擬 4 倍慢的裝置；`SB=1` 側邊欄展開；`W=390` 手機寬度。
看三個數字：內容就緒（→DCL）、主執行緒最長卡頓、版面跳動 CLS。
需要 `playwright`（node）。`site.perf` 在 companies.json，設 false 回到舊行為。
