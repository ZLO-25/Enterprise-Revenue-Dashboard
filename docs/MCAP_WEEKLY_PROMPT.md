# 市值排名每週檢查（排程：每週六 台北 07:00 左右，建議模型 Sonnet 5.5、effort medium）

> 這份就是排程的指令全文。排程本身只是一句「照 docs/MCAP_WEEKLY_PROMPT.md 做」，所以改這份＝改排程，不用重建排程。
> 設計原則：**數字由 GitHub Actions（mcap-weekly，台北週六 05:37 起）抓，Claude 只檢查**。正常的一週只要 git pull ＋ 跑一個腳本＋回報幾行。

```
 台北週六 05:37～13:07   GitHub Actions mcap-weekly（6 班，這週抓過就跳過）
        │  companiesmarketcap（主）＋ Yahoo / CoinGecko / WGC（核對）
        ▼
   data/mcap/latest.json ＋ history/<日期>.json   ← 網頁直接讀這個檔，不用重建網站
        │
 台北週六 07:00          Claude（本指令）
        ▼
   python3 tools/mcap_check.py → 正常：回報 5～8 行，結束
                              → 有問題：照下面「有問題時」處理
```

## 步驟（照順序，不要多做）
1. 取得 repo `ZLO-25/Enterprise-Revenue-Dashboard` 最新 main（clone 或 `git pull`）。不能讀 repo：回報原因並結束。
2. 執行 `python3 tools/mcap_check.py`。
3. 結果「正常」：把它印出的「· 」行整理成回報（繁體中文、5～8 行），結束。**不要**開網頁、不要讀其他檔、不要改任何檔、不要 push。
4. 結果「有問題」（✗ 行）：
   - 「比本週六舊」：Actions 這週還沒成功。若有 GitHub 工具，看 mcap-weekly 最近一次執行的失敗訊息（只看最後 50 行），再用 workflow_dispatch 觸發一次 mcap-weekly（force=true）；不能觸發就在回報寫「待確認：mcap-weekly 本週未成功，原因 …」。週六 09:07、13:07 與週日 09:07、15:07 還有備援班次。
   - 列數、排序、來源有問題：多半是 companiesmarketcap 改版。回報原因與 Actions 錯誤訊息，**不要手改 data/mcap 的數字**。
   - 「全球資產榜沿用舊資料」：同上，只回報。
5. 出現「黃金地上存量…可能已公布新一季」時（約每季一次）：用 WebFetch 讀該網址，只找「Total above-ground stock (end-Qx 20xx)」那一行的公噸數。真的讀到而且比 config 新，才改 `data/mcap/config.json` 的 `goldStock`（tonnes、asOf＝那季最後一天、label、checked＝今天），commit「市值排名：更新黃金地上存量 <label>」並 push main。讀不到就在回報寫「待確認：WGC 地上存量本季未讀到」，不改檔。

## 資料誠實規則（摘要，完整見 CLAUDE.md）
- data/mcap 的數字只由 Actions 寫入；Claude 不手填、不估計、不從記憶補。
- 待確認（兩來源差 > 10%）照實回報，不為了讓它消失去改數字。

## 回報格式
```
市值排名每週檢查 <日期>：正常／有問題
· 資料抓取時間
· 三張榜前三
· 名次變動（各榜最多 5 筆）
· AI 相關金屬 1 週／52 週漲跌
· 待確認 N 筆（列名稱）
· 做了什麼（沒做事就寫「無需動作」）
```
