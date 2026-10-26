# SpaceX（SPCX）資料來源與更新步驟

- 資料檔：`data/spcx.json`（schema `v1`）　頁面：`/spcx/`　模板：`templates/generic.frag.html`（通用模板）
- 公司：Space Exploration Technologies Corp.，SEC CIK `0001181412`。A 類普通股在 Nasdaq 上市，代號 SPCX（424B4 最終公開說明書 2026-06-12 申報）。使用者確認「SPCX 是 SpaceX」。
- 單位：**百萬美元**（公司新聞稿就是百萬美元）；每股數字（`eps`）為美元，稀釋後。
- 頻率：每季。3Q26 財報在 2026-10-20 公布（季底後約 3 週），2Q26 在 2026-08-04。公司把新聞稿放在 IR 網站（`ir.spacex.com`，PDF 在 `s21.q4cdn.com/184289198/...`）與 X，不一定走新聞通訊社。
- 排程：每月 12 日 07:48（台北）。排程只補「上次資料之後」的新期間，舊數字不重抓、不重核；**某個月沒有新財報時，只檢查事件時間軸與公布日**；沒有實質變動就不 commit。

## 期間

2Q26（上市後第一季）–最新一季。

- 1Q25–1Q26：新聞稿與 S-1 摘要有營收與營業利益，但單季 EPS 只在 S-1 公開說明書的財務報表裡。SEC 上的 S-1／424B4 主檔約 12 MB，WebFetch 只讀得到前 13 萬字（到公開說明書摘要為止），讀不到財務報表，所以先不收（`notes.unavailable` 有「待確認」）。
- 補資料的方法：如果之後的 10-K 或 10-Q 附註列出這些季度的 EPS，或能用別的方式讀到 S-1 的 F 頁，就把 1Q25–1Q26 補進 `quarters[]`（季度要連續，不能跳季，否則年增率會算錯）。

## 來源（依可信度）

1. **SEC EDGAR**
   - XBRL：`https://data.sec.gov/api/xbrl/companyconcept/CIK0001181412/us-gaap/{概念}.json`（10-Q 申報後才有；S-1 沒有財報 XBRL）。
   - 10-Q／10-K、8-K：申報清單用 `https://data.sec.gov/submissions/CIK0001181412.json`。
2. **公司財報新聞稿 PDF**（IR 網站）：例 `https://s21.q4cdn.com/184289198/files/content_files/SpaceX-Reports-Third-Quarter-2026-Results.pdf`。內有當季、去年同季、年初累計的損益表、累計現金流、部門營收與資本支出、營運指標（Starlink 用戶、ARPU、發射次數、AI 運算容量）。
3. 投資人關係 `https://ir.spacex.com/`（財報日公告「SpaceX to Post … Results and Host Webcast on …」）
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | 新聞稿損益表 Revenue；XBRL `RevenueFromContractWithCustomerExcludingAssessedTax` 核對 |
| `gp`、`gm` | 損益表沒有毛利這一行：`gp` ＝ Revenue − Cost of revenue；`gm`＝`gp`÷`rev`×100 |
| `opInc`、`om` | Income (loss) from operations |
| `ni` | Net income (loss)。注意 9M26 的「歸屬股東淨利」（−1,084）和淨利（−413）不同；單季 2Q26、3Q26 兩者相同（差額落在上市前的 1Q26，原因待確認） |
| `eps` | Diluted net income (loss) per share |
| `ocf` | 新聞稿只給年初累計：單季 ＝ 本期累計 − 上期累計（3Q26 ＝ 9M 13,097 − 6M 3,466） |
| `capex` | 各部門資本支出合計（新聞稿表格）；與現金流量表「購置不動產、廠房及設備」累計相減核對 |
| `fcf` | `ocf − capex` |
| `dps` | 不配息，一律 `null` |

`segments`：太空（Space）、連線（Connectivity，含 Starlink）、超級智慧 SI（3Q26 起改名，原 AI；含 Grok、X、AI 運算與 Cursor）。三者加總 ＝ 營收。
`extra`：去年同季營收（用來看年增率，因為上市前的季度沒收進 `quarters[]`）、Starlink 消費者用戶（百萬）、ARPU（美元／月）、發射次數、名目運算容量（GW）。

### 第四季推算
10-K 出來後：**4Q ＝ 全年 − 前三季**（營收、營業成本、營業利益、淨利、現金流、資本支出）；EPS 取第四季新聞稿的單季數字。

## 核對規則（`python3 tools/validate.py spcx`）

1. 毛利率、營業利益率與金額自洽；`fcf = ocf − capex`。
2. 部門加總 ＝ 營收。
3. `waterfall` 每個小計 ＝ 前一個小計 ＋ 中間各項；第一列營收＝最新一季 `rev`。
4. 推算的季度要和新聞稿其他數字對得起來：例 1Q26 營收 ＝ 9M 27,083 − 2Q 7,814 − 3Q 14,575 ＝ 4,694，與 S-1 摘要一致。

**任何一項沒過就不發佈**，回到來源修資料，不要放寬核對。

## 更新步驟（每月排程）

1. 查 IR 網站或 SEC 有沒有新的財報新聞稿。**沒有 → 跳到第 6 步。**
2. 有新財報：讀新聞稿 PDF，取當季營收、營業成本、營業利益、淨利、稀釋 EPS、累計營業現金流、各部門資本支出、部門營收、營運指標。
3. 10-Q 出來後用 XBRL 核對（營收、EPS、累計現金流）。
4. 新增一季到 `quarters[]`、`segments.quarters`、`extra.quarters`；更新 `waterfall`、`events`（公司公告財報日後改成實際日期並刪除 `est`）、`guidance`（目前公司不給數字財測）。
5. `python3 tools/validate.py spcx`；通過才繼續。
6. 查事件時間軸：發債、併購、星艦里程碑、重大合約（優先 SEC 8-K 與公司新聞稿）。
7. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 已知缺口（頁面「沒能取得的欄位」會列出）

- 1Q25–1Q26 與 2023–2025 全年（見「期間」）。
- 2Q26 單季營業現金流（只有上半年累計 3,466）。
