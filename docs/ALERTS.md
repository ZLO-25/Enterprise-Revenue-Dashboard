# 到價提醒（price alerts）

給 ZL 的設定步驟（Cloudflare、token、通知管道）在 SOP 文件：https://claude.ai/artifact/4DYc81V319Gu9scHSMvS72 。這份是給維護的人（Claude）看的架構說明。

## 做什麼
- 標的：所有個股、ETF、指數期貨（ym／nq／tx）。當天**最高價碰到（漲破）或最低價碰到（跌破）**就算到價，不是只看收盤。
- 只有 ZL 能設定：沿用「看盤密碼」。瀏覽器解鎖後存在 localStorage 的 AES 金鑰，同時是加密提醒檔的金鑰，也是 Worker 驗證本人的依據。
- 每天台北 08:00：Gmail 寄「每日行情報告」（提醒在最上方＋全部追蹤標的總表）；ntfy、Telegram 只在有到價中的提醒時發。到價後每天提醒，直到 ZL 在網站按「關閉提醒」。

## 架構
```
 瀏覽器（已解鎖）  ──加密的操作──▶  Cloudflare Worker（worker/）  ──Contents API──▶  data/alerts/rules.enc.json
        ▲                             │ 每天 UTC 00:00 叫醒
        │讀（加密）                    ▼
        └──────────────  GitHub Actions alerts-daily（tools/alerts.py）──▶ data/alerts/state.enc.json ＋ ntfy／Gmail／Telegram
```
| 檔案 | 誰寫 | 內容 |
|---|---|---|
| `data/alerts/rules.enc.json` | 只有 Worker | 提醒規則（加密） |
| `data/alerts/state.enc.json` | 只有 `tools/alerts.py`（Actions） | 到價紀錄、最新收盤、lastSent、最近 30 次發送（加密） |
| `data/alerts/config.json` | 部署 workflow | `{"worker": 網址 \| null}`；null＝小幫手還沒設好，前端停用新增 |

兩個加密檔格式與 `data/kbar`、`data/futures` 相同（AES-256-GCM，明文 = zlib(JSON)）。檔案不存在＝沒有提醒／沒有紀錄；**不要**手動建立這兩個檔（要有真密碼才加得出來）。

## 到價判斷（Python 與 JS 同一套）
K 棒日期 > `since` 的第一根，`dir=up`：最高價 ≥ 目標；`dir=down`：最低價 ≤ 目標。缺最高／最低價的 K 棒略過。共用測試案例：`tools/tests/alerts_cases.json`（`test_alerts.py` 與 `alerts_js.test.js` 都跑）。
改價（拖曳）、改方向、重新開啟 → `since` 重設成最新 K 棒日期，舊的到價作廢（`state.hits` 的 `t ≤ since`、`p ≠ 目標價`或方向不符就無效）。

## 隱私
公開 repo 的 Actions log 只印數量與管道結果，不印代號、價格、金鑰；ntfy 只寫名稱與方向、不寫價格（主題名稱等於密碼）；Worker 的 commit 訊息固定為「到價提醒設定更新」。

## 測試
`python3 -m unittest tools/tests/test_alerts.py`、`node --test tools/tests/worker_core.test.mjs tools/tests/alerts_js.test.js`、瀏覽器：`node tools/tests/alerts_browser.cjs [--shots 資料夾]`（真的 Worker 核心＋假 GitHub＋合成資料）。
