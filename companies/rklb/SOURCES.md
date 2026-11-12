# 火箭實驗室 Rocket Lab（RKLB）資料來源與更新步驟

- 資料檔：`data/rklb.json`（schema `v1`）　頁面：`/rklb/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**（`rev`、`gp`、`opInc`、`ni`、`ocf`、`capex`、`fcf`），原始單位是千美元，保留到小數 3 位；每股數字（`eps`）為美元。不配息，`dps` 一律 `null`。
- 頻率：每季。財報日約在 2 月底、5 月上旬、8 月上旬、11 月上旬（美股收盤後，美東下午 5 點電話會議）。
- 排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md；公布日隔天先做「快報」，再「補完」「核對」）。排程只補「上次資料之後」的新期間，舊數字不重抓、不重核；沒有實質變動就不 commit。
- CIK：`0001819994`（原 SPAC Vector Acquisition 的 CIK，合併後沿用；2025 年間改組為 Rocket Lab Corporation，CIK 不變）。

## 會計年度與季度標籤

會計年度＝曆年（`company.fiscalYearEnd` 填 `12-31`）。3Q26＝2026/7/1–2026/9/30（2026-11-09 公布）。

## 期間

1Q22–最新一季，共 19 季。

```
2021-08-25  SPAC 合併，Nasdaq 掛牌
   3Q21     上市後第一季（但沒有 8-K 2.02 財報新聞稿，只有 10-Q）
   4Q21     當時新聞稿（2022-02-28）沒有單季 EPS → EPS 是必要欄位、季度要連續
   1Q22  ← 本頁從這裡開始
```

4Q21 的稀釋 EPS（−0.05 美元）要到 4Q22 新聞稿比較欄才公布，而且和淨利 ÷ 稀釋股數對不上（認股權證公允價值變動調整分子），所以不收 2021 年。

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0001819994.json`（容器的 curl 被擋；新增公司時用 repo `sec-raw` 分支的 GitHub Actions 抓）。
2. **財報新聞稿（8-K Item 2.02 附件 99.1）**：近年檔名 `rklb-{mmddyyyy}ex991.htm`，例：
   - 3Q26 `https://www.sec.gov/Archives/edgar/data/1819994/000181999426000073/rklb-11092026ex991.htm`
   - 2Q26 `https://www.sec.gov/Archives/edgar/data/1819994/000181999426000061/rklb-08102026ex991.htm`
   - 4Q25 `https://www.sec.gov/Archives/edgar/data/1819994/000181999426000012/rklb-02262026ex991.htm`
   - 4Q22 `https://www.sec.gov/Archives/edgar/data/1819994/000095017023005103/rklb-ex99_1.htm`
3. 投資人關係 `https://investors.rocketlabcorp.com/`。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`，`note` 以「待確定：」開頭。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `RevenueFromContractWithCustomerExcludingAssessedTax`（產品＋服務營收合計） |
| `gp`、`gm` | `GrossProfit`；GAAP 毛利率（公司另給非 GAAP 毛利率，較高） |
| `opInc`、`om` | `OperatingIncomeLoss`（上市以來每季都是虧損） |
| `ni` | `NetIncomeLoss` |
| `eps` | `EarningsPerShareDiluted`（GAAP；虧損時基本＝稀釋）；第四季取新聞稿 |
| `ocf`、`capex` | 年初累計相減；`capex`＝`PaymentsToAcquirePropertyPlantAndEquipment` |
| `rd`、`rdB` | 季末後 5–90 天內最後一份 8-K Item 2.02 的申報日，`rdB:"p"` |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季營收、毛利、營業利益、淨利、現金流＝10-K 全年 − 前三季（四季加總＝全年已核對）。第四季 EPS 與稀釋股數取新聞稿：4Q22 −0.08、4Q23 −0.10、4Q24 −0.10、4Q25 −0.09 美元。

上市以來沒有股票分割，EPS 不換算。

### 選用區塊
- `segments`：無。10-Q 有發射服務／太空系統兩個分部，這次尚未讀取（見待確認）。
- `extra`：無。在手訂單（backlog）每份新聞稿寫法不同，尚未整理。
- `guidance.items[]`：下一季營收、下一季 GAAP 毛利率；其餘（非 GAAP 毛利率、營業費用、調整後 EBITDA、股數）寫在 `guidance.note`。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `rklb`：
- `shOut`：`CommonStockSharesOutstanding`（不含可轉換特別股）；`dilSh`：`WeightedAverageNumberOfDilutedSharesOutstanding`，第四季取新聞稿。
- `cash`：`CashAndCashEquivalentsAtCarryingValue` ＋ `MarketableSecuritiesCurrent`（不含長期有價證券）。
- `debt`：**全部 null**。`LongTermDebt` 與「一年內到期＋長期」加總對不起來（2024 年底 345 vs 56 百萬），2024 年發行的可轉換公司債疑似用公司自訂科目；要讀 10-Q 附註才能補。
- `buyback`：沒有回購 → null；`equity`：`StockholdersEquity`；`pretax`、`tax`：單季值。

## 電話會議（逐字稿）
- 官方只有網路直播與重播；第三方逐字稿尚未選定。讀不到時寫「待確認：逐字稿尚未取得」。
- 公司有非 GAAP 毛利率、調整後 EBITDA，但**沒有非 GAAP EPS**；本站 EPS 一律 GAAP 稀釋。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 rklb 8-K Item 2.02，或投資人關係「Rocket Lab Announces … Quarter … Financial Results」。沒有新財報 → 只查事件時間軸。
2. 讀新聞稿：營收、毛利、營業利益、稅前、所得稅、淨利、EPS、加權股數、現金與有價證券、股東權益、下一季財測、在手訂單；現金流量表是年初累計要相減。
3. 新增一季（`rd`＝新聞稿日，`rdB:"p"`）；舊 `guidance` 原封不動 append 進 `guidanceHistory`；更新 `waterfall`、`events`（公告前 `est:1`）、`summary`。
4. `python3 tools/validate.py rklb` 通過才繼續；10-Q 出來後用 XBRL 核對。
5. 事件：Neutron 首飛、Iridium 收購完成、增資（ATM）、合約。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `RKLB`（Nasdaq，美元） |
| 股價起點 | 2021-08（SPAC 合併掛牌） |
| 股票分割 | 沒有 |
| EPS 口徑 | GAAP 稀釋 EPS；一直虧損，本益比多數月份算不出來 |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/rklb.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。

<!-- PRICE_CHECK -->

## 已知缺口
- 2021 年以前：不收（見「期間」）。
- 有息負債全部、回購（沒有回購）、分部營收、在手訂單：見 `notes.unavailable`。
