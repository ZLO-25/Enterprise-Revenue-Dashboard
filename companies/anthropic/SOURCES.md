# Anthropic（ANT）資料來源與更新步驟

> **狀態（2026-11-02）：待上市，`enabled:false`，網站上不顯示。**
> 使用者 ZL 在 2026-11-02 選擇「先建骨架，上市後再上架」。上市後第一份季報出來，ZL 說「繼續 Anthropic」時，照下面「上架步驟」做。
> 每日排程只處理 `enabled:true` 的公司，所以**不會**自動上架。

- 資料檔：`data/anthropic.json`（schema `v1`）　頁面：`/anthropic/`　模板：`templates/generic.frag.html`（通用模板）
- 公司：Anthropic, PBC（公益公司），SEC CIK `0002130357`，會計年度 12 月 31 日結束。預計 A 類普通股在 Nasdaq Global Select 掛牌，代號 **ANT**。
- 單位：**百萬美元**；每股數字（`eps`）為美元，稀釋後（虧損時基本＝稀釋）。
- 產業分頁：`軟體與網路服務`（與 PLTR、MSFT、AMZN 同一頁；Anthropic 主要賣 Claude 模型的 API 與訂閱）。

## 上市進度（2026-11-02 查證）

```
2026-06-01 DRS（秘密送件）→ 7/13、8/10、9/4、10/1、10/9 DRS/A
2026-10-26 公開 S-1（accession 0001628280-26-067168）
          → 尚未定價、尚未交易（價格區間、股數空白）
之後：S-1/A → 424B4（最終公開說明書＝定價上市）→ 第一份 10-Q 或財報新聞稿
```

查最新進度：`https://data.sec.gov/submissions/CIK0002130357.json`（用 WebFetch，curl 會被擋）。看到 `424B4` 代表已上市。

## 為什麼現在不上架

1. 網站共用欄位 `rev`、`gm`、`om`、`eps` 每季都不能是 null。S-1 只有全年與上半年的每股虧損，**沒有單季 EPS**。
2. S-1 的季度表（六季）在 MD&A（約第 132 頁以後）。主檔 `anthropicpbc-sx1.htm` 約 14 MB，WebFetch 只讀得到前約 13 萬字（到公開說明書摘要的非 GAAP 段落），讀不到季度表與 F 頁。S-1 沒有財報 XBRL（只有申報費用附件）。
3. 不放寬核對規則、不用媒體數字補，所以等上市後的季報。

## 已讀到的官方數字（S-1 公開說明書摘要，百萬美元）

| 期間 | 營收 | Compute and infrastructure | 營業費用合計 | 營業損失 | 淨損 | 每股虧損（基本＝稀釋） |
| --- | --- | --- | --- | --- | --- | --- |
| 2023 | 41 | 433 | 592 | (551) | (1,531) | (1.42) |
| 2024 | 386 | 2,522 | 3,366 | (2,980) | (8,309) | (5.43) |
| 2025 | 4,585 | 7,326 | 12,645 | (8,060) | (41,965) | (23.04) |
| 1H25 | 1,163 | 2,334 | 3,298 | (2,135) | (12,969) | (7.25) |
| 1H26 | 16,286 | 8,945 | 16,979 | (693) | (80,748) | (39.88) |

- 1H26 淨損中 72,388 是可轉債等公允價值變動（非現金）。
- 2023–2025 已放進 `annual`（`gp`、`ocf`、`capex` 為 null）。

**注意毛利口徑**：S-1 損益表沒有「營業成本／毛利」這一行，費用是依性質分類（Compute and infrastructure 等）。上架時要看 10-Q 損益表怎麼列：如果仍沒有毛利，參考 SpaceX 的做法在 `notes.unavailable` 寫明 `gp` 的算法（例如 營收 − Compute and infrastructure），並在頁面註明這不是公司公布的毛利；口徑要先跟 ZL 確認。

## 來源（依可信度）

1. **SEC EDGAR**
   - 申報清單：`https://data.sec.gov/submissions/CIK0002130357.json`
   - XBRL（10-Q 申報後才有）：`https://data.sec.gov/api/xbrl/companyconcept/CIK0002130357/us-gaap/{概念}.json`
   - 10-Q／10-K 太長讀不到時，用 `FilingSummary.xml` → `R#.htm`。
2. 公司投資人關係網站與財報新聞稿（上市後才會有，網址待確認）。
3. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`，note 以「待確定：」開頭。

## 上架步驟（上市後第一份季報出來時）

1. 確認 424B4 已申報、已有第一份 10-Q 或財報新聞稿。
2. 從第一份有單季 EPS 的季度開始填 `quarters[]`（季度要連續）。10-Q 若附上一年同季（例 3Q25）的單季 EPS，也可以一起收，前提是中間季度都有。
3. 欄位口徑見下表；`waterfall` 換成最新一季；`events` 放下一次財報日（未公告加 `est:1`）；`milestones` 補 424B4 上市日。
4. 刪掉 `notes.unavailable` 裡已解決的「待確認」。
5. `python3 tools/validate.py anthropic` 通過 → `companies.json` 改 `enabled:true` → `python3 tools/validate.py && python3 tools/build.py` → 無頭瀏覽器檢查 → commit、push → 更新合併版 Artifact（`site.artifact`）。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | 損益表 Revenue |
| `gp`、`gm` | 見上面「毛利口徑」 |
| `opInc`、`om` | Income (loss) from operations |
| `ni` | Net income (loss) attributable to common stockholders |
| `eps` | Diluted net income (loss) per share；第四季取公司公布的 Q4 數字 |
| `ocf` | 營業活動現金流（10-Q 是年初累計，要相減得單季） |
| `capex` | Purchases of property and equipment（正數） |
| `fcf` | `ocf − capex` |
| `dps` | 不配息，`null` |

第四季：**4Q ＝ 全年 − 前三季**（EPS 除外）。

## 核對規則（`python3 tools/validate.py anthropic`）

毛利率、營業利益率與金額自洽；`fcf = ocf − capex`；四季加總 ＝ 全年；`waterfall` 小計正確。**沒過就不發佈**，回到來源修資料，不要放寬核對。

## 更新步驟（上架後的每日排程）

1. 查 SEC 或 IR 有沒有新財報。沒有 → 跳到第 4 步。
2. 新增一季，更新 `waterfall`、`events`、`guidance`。
3. `python3 tools/validate.py anthropic`；通過才繼續。
4. 查事件時間軸（公司證實的照收；只有媒體的加 `unc:1`）。
5. `asOf` 改成今天（台北時間），`python3 tools/build.py`，commit、push。

## 已知缺口

見 `data/anthropic.json` 的 `notes.unavailable`。
