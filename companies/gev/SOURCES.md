# GE Vernova（GEV）資料來源與更新步驟

- 資料檔：`data/gev.json`（schema `v1`）　頁面：`/gev/`　模板：`templates/generic.frag.html`（通用模板）
- 單位：**百萬美元**；每股數字（`eps`、`dps`）為美元。
- 頻率：每季。財報日約在 1、4、7、10 月下旬（美股開盤前，美東上午 7:30 電話會議）。
- 排程：週二至週六（台北）每日檢查（見 docs/SCHEDULE_PROMPT.md）。排程只補「上次資料之後」的新期間；沒有實質變動就不 commit。
- CIK：`0001996810`。

## 會計年度與期間

會計年度＝曆年（`company.fiscalYearEnd` 填 `12-31`）。期間 1Q24–最新一季，共 11 季。

```
2024-04-02  自奇異（GE）分拆，NYSE 掛牌 GEV
   1Q24     分拆後第一份財報（2024-04-25）← 本頁從這裡開始
            （1Q24 大部分期間仍在 GE 旗下；EPS 用分拆時發行的 2.74 億股計算）
2023 年以前 只在分拆文件（Form 10）與比較欄，EPS 是擬制數字 → 不收
```

## 來源（依可信度）

1. **SEC EDGAR XBRL**：`https://data.sec.gov/api/xbrl/companyfacts/CIK0001996810.json`。
2. **財報新聞稿（8-K 附件 EX-99，檔名沒有「99」）**：
   - 3Q26 `https://www.sec.gov/Archives/edgar/data/1996810/000199681026000162/gevpressrelease3q26.htm`
   - 2Q26 `https://www.sec.gov/Archives/edgar/data/1996810/000199681026000147/gevpressrelease2q26.htm`
   - 1Q26 `https://www.sec.gov/Archives/edgar/data/1996810/000199681026000063/gevpressrelease1q26.htm`
   - 4Q25 `https://www.sec.gov/Archives/edgar/data/1996810/000199681026000012/gevpressrelease4q25.htm`
   - 4Q24 `https://www.sec.gov/Archives/edgar/data/1996810/000199681025000004/gev4q2024earningsrelease.htm`
   - 注意：2Q25 的財報 8-K（2025-07-23）申報項目標成 Item 2.01，不是 2.02；自動找「8-K 2.02」會漏掉。
   - **第一到第三季的新聞稿沒有完整損益表**（只有營收、淨利、EPS、現金流與部門表），瀑布圖用 10-Q 的 XBRL 數字。
3. 投資人關係 `https://www.gevernova.com/investors`。
4. 可信媒體：**只用於事件時間軸**；公司未證實的一律 `unc:1`。

## 欄位定義（`quarters[]`）

| 欄位 | 來源與口徑 |
| --- | --- |
| `rev` | `RevenueFromContractWithCustomerExcludingAssessedTax`（設備＋服務營收合計） |
| `gp`、`gm` | `GrossProfit` |
| `opInc`、`om` | `OperatingIncomeLoss` |
| `ni` | `NetIncomeLoss`（歸屬 GE Vernova；新聞稿的「Net income」含非控制權益，差 1–2 百萬） |
| `eps` | `EarningsPerShareDiluted`；第四季取新聞稿（4Q24 1.73、4Q25 13.39 美元） |
| `ocf`、`capex` | 年初累計相減 |
| `dps` | `CommonStockDividendsPerShareDeclared`，**宣告基準**：1Q24–3Q24 0；4Q24 0.25；1Q25 0；2Q25 0.50（同季宣告兩次）；3Q25 0.25；4Q25 起每季 0.50 |
| `rd`、`rdB` | 季末後 5–90 天內最後一份財報 8-K 的申報日，`rdB:"p"`（2Q25 手動填 2025-07-23） |

**每個會計年度只用一個版本**：季度數字取「該年 10-K 第一次申報當天以前最後一次申報」的版本；第四季＝10-K 全年 − 前三季（四季加總＝全年已核對）。沒有股票分割。

**一次性大額項目**（看 EPS、本益比要注意）：4Q25 美國遞延所得稅備抵迴轉 29 億美元所得稅利益；1Q26 Prolec GE 重新評價等約 45 億美元稅前利益。

### 選用區塊
- `segments`：電力、電氣化、風電＋「公司其他與部門間抵銷」（＝總營收 − 三部門，自行相減）。2026-01-01 起部門重劃，只收 1Q26 起；2025 年新口徑的比較數字在 2026 年新聞稿裡，但 4Q25 新口徑沒有公布，所以不往回補。
- `guidance.items[]`：全年營收、全年自由現金流（非 GAAP，標明）。GE Vernova 不給單季財測。
- `extra`：無（訂單、在手訂單可考慮之後加）。

## 資產負債表欄位
配方在 `tools/bs_map.json` 的 `gev`：
- `cash`：資產負債表只有「現金、約當現金與受限現金」一行（`CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents`），所以**含受限現金**。
- `debt`：`LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities`（＋短期借款）；4Q25 起才有值，之前 null（待確認）。2026 年 1Q 發行 26 億美元優先票據。
- `shOut`、`dilSh`、`buyback`（`PaymentsForRepurchaseOfCommonStock`，2024-12 起）、`equity`、`pretax`、`tax`：同其他美股。

## 電話會議（逐字稿）
- 官方只有網路直播與重播；第三方逐字稿尚未選定，讀不到時寫「待確認：逐字稿尚未取得」。
- 公司**沒有非 GAAP EPS**，但有調整後 EBITDA、自由現金流、內生營收等非 GAAP 指標；本站一律用 GAAP。

## 更新步驟（每日排程「快報」）
1. 查 `data/sec-feed.json` 的 gev 財報 8-K（注意可能標成 2.01），或投資人關係。沒有新財報 → 只查事件時間軸。
2. 讀新聞稿：營收、淨利、EPS、營業現金流、部門營收、訂單、全年財測；毛利、營業利益、稅前、所得稅等從同日 10-Q 的 XBRL 讀（第四季新聞稿有完整損益表）。
3. 新增一季（`rd`＝新聞稿日，`rdB:"p"`）與 `segments.quarters[]`；舊 `guidance` append 進 `guidanceHistory`；更新 `waterfall`、`events`、`summary`。
4. `python3 tools/validate.py gev` 通過才繼續。
5. 事件：Trench Group 收購、配息調整、庫藏股授權、風電訴訟。

## 股價與財報公布日（本益比用）

| 項目 | 內容 |
|---|---|
| Yahoo 代碼 | `GEV`（NYSE，美元） |
| 股價起點 | 2024-04（分拆掛牌） |
| 股票分割 | 沒有 |
| EPS 口徑 | GAAP 稀釋 EPS（含一次性利益，見上） |
| `rd` 來源 | 財報新聞稿的 8-K 申報日（`rdB:"p"`） |

股價檔 `data/prices/gev.json` 只由 GitHub Actions（prices-monthly）寫入，Claude 不手填。

<!-- PRICE_CHECK -->

## 已知缺口
- 2023 年以前（分拆前）：不收。
- 有息負債 1Q24–3Q25、部門營收 2025 年以前：見 `notes.unavailable`。
