# 每日排程附件：補完

> 每日排程的附件（由 docs/schedule/core.md 指示才讀）。內容與舊版 docs/SCHEDULE_PROMPT.md 同一節一字不改，只是拆出來，安靜日不用讀。

### ② 補完（狀態 flash 的公司，快報的隔天起）
- 讀電話會議逐字稿（SOURCES.md 的「逐字稿來源」；公司官方優先，其次第三方並在 `src.n` 註明網站），寫 `mgmt`（3～5 點）、`qa`（2～3 題）、`outlook.items` 補口頭展望、`risks`、`next`；把 `status` 改 `final`、填 `finalDate`、清掉 `pending`。內容規則見 DATA_SCHEMA「summary」：每句標來源類別，口頭內容附逐字稿連結與發言人，只摘要不整段照抄，口頭數字不寫進 `guidance`。
- 讀不到逐字稿：該格寫「待確認：逐字稿尚未取得」，`try` 一次，明天再試；**不要用新聞報導代替**。
- 成功：`python3 tools/daily.py set <代號> completed`。
- 補完成功後，⑪ 會列「分析待寫」→ 讀 docs/schedule/analysis.md（當天就可以做）。
