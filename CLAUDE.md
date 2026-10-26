# 企業財報追蹤板：給 Claude 的專案規則

全程用繁體中文。說明要讓使用者能拿去教別人：先用自己的話重述目標，多用 ASCII 圖。

## 觸發句
使用者說「加入新公司：XXX」「新增公司 XXX」「add new company: XXX」（可一次多家）時：
照 [`docs/NEW_COMPANY_PROMPT.md`](docs/NEW_COMPANY_PROMPT.md) 的「完整模板」執行，等同使用者貼了整份模板並填了公司名稱。

## 資料誠實規則（所有工作都適用，包含每週排程）
- 每個數字都要能追到來源（主管機關申報文件或公司公告），而且真的讀到那個數字。
- 讀不到、算不出來、來源對不起來的數字：填 `null`，在 `notes.unavailable`（台積電、PLTR 舊格式則寫進回報）加一行，以「待確認：」開頭說明哪一季、哪個欄位、為什麼。
- 不估計、不內插、不從記憶補數字。
- 只有媒體報導、公司未證實的事件：`unc:1`，`note` 以「待確定：」開頭。
- `python3 tools/validate.py` 沒過就不發佈；不可以為了通過核對去改數字或放寬核對。

## 常用指令
```
python3 tools/validate.py       # 核對設定與所有啟用中的公司
python3 tools/build.py          # 產生網站與合併版 Artifact（dist/artifacts/all.html）
python3 tools/new_company.py …  # 新增公司腳手架
```

## 文件
- `docs/ADDING_A_COMPANY.md` 新增公司流程
- `docs/DATA_SCHEMA.md` 資料格式 v1
- `docs/SCHEDULE_PROMPT.md` 每週排程指令（改這份要同步更新排程，先問使用者）
- `companies/<代號>/SOURCES.md` 各公司來源與更新步驟
