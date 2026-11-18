# 每日排程附件：公司分析（財報更新後）

> 每日排程的附件（`python3 tools/daily.py brief` 的 ⑪ 列出「分析待寫」才讀）。舊版 docs/SCHEDULE_PROMPT.md 的「②b 公司分析」一節是同一份規則。
> ZL 2026-11-17 要求：每次財報更新都一起跑公司分析 skill，結論與重點放在個股頁標題下方，按 more 看全文。

```
 補完成功（completed）── 或補完卡了 3 次以上（用快報資料先寫）
   │
   ▼
 python3 tools/company_brief.py <代號>     ← 只讀這頁，不整份讀 data/<代號>.json
   │ ＋ 新聞搜尋 3 次（同一回合一起送出）
   ▼
 照 .claude/skills/long-term-company-analysis/SKILL.md 寫「快評」
   │
   ├─ 完整版（含作者視角）→ /mnt/project-files/analysis/<代號>/<日期>_快評.md   讀不到專案資料夾就跳過
   └─ 公開版 JSON（不含任何作者觀點）→ python3 tools/analysis_save.py <代號> <檔案>
                                         → 網站個股頁「分析結論」區塊
```

## 什麼時候做
- ⑪ 列出「分析待寫：<代號> <季度>」的公司，每家一次。規則寫在 `tools/daily_brief.py`：最新一季公布日 ≥ 2026-11-17、`data/analysis/<代號>.json` 還不是這一季，而且已補完（或補完重試 3 次以上）。
- 一天最多 3 家（省額度）；多的留到明天，⑪ 會再列出。
- 補完卡住時先寫的版本，`mode` 寫「快評（電話會議待補）」，電話會議相關的點寫「待確認：逐字稿尚未取得」。之後補完成功也**不重寫**，除非 ZL 指示。

## 怎麼做
0. 結論五選一，**沒有明確理由就是「不動」**；減碼要填 reason（A／B／C）、太難，跳過填 filters（規則在 skill 的「巴菲特＋蒙格結論規則」；analysis_save 會核對）。分析要引用 `company_brief.py` 的「檢查表摘要」（盈餘殖利率對公債、十年成績單、回購買在哪、反過來想一段）。
1. 讀 `.claude/skills/long-term-company-analysis/SKILL.md` 與它指定的那一份 `types/<類型>.md`，照「快評」格式寫（SKILL.md 第 6 節）。外部新聞只搜尋 3 次（不是 5 次），同一回合一起送出。
2. 數字只用 `company_brief.py` 印出來的（都是財報或公司公告）；沒有的寫「待確認（季度／欄位／原因）」。新聞標「媒體」，屬待確定。
3. 寫公開版 JSON（格式見 docs/DATA_SCHEMA.md「公司分析」），存到暫存檔，然後：
   `python3 tools/analysis_save.py <代號> <暫存檔>`（會自動把舊結論收進 history，並核對；沒過不寫入）。
   - **公開版不能出現「作者」兩個字、作者的預測或作者觀點檔的內容**（repo 公開、作者觀點是付費文章轉述；validate 會擋）。兩層輸出只留「校正後結論」，改寫成我們自己的判斷。
4. 完整版（含作者視角）寫到專案資料夾；排程環境讀不到 `/mnt/project-files/` 就只寫公開版，回報註明「未讀作者觀點檔」。
5. 分析失敗（skill 讀不到、analysis_save 沒過兩次）**不影響財報資料**：不 `try`、不改 calendar 狀態；回報 ⑤ 寫「<公司> 分析待補：原因」，明天 ⑪ 會再列。
6. 和其他變動一起 build、validate、commit（例「TSMC 4Q26 公司分析」）。

## 回報
- ② 今天做了什麼：「<公司> <季度> 分析：<結論五選一：不動／加碼／減碼／觀察／太難，跳過>，<一句話結論>」。
- 結論和上一季不同（例：不動 → 減碼）時，PushNotification 標題寫出來。
