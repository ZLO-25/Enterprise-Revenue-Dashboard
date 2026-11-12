# 企業財報追蹤板：給 Claude 的專案規則

全程用繁體中文。說明要讓使用者能拿去教別人：先用自己的話重述目標，多用 ASCII 圖。

## 觸發句
使用者說「加入新公司：XXX」「新增公司 XXX」「add new company: XXX」（可一次多家）時：
照 [`docs/NEW_COMPANY_PROMPT.md`](docs/NEW_COMPANY_PROMPT.md) 的「完整模板」執行，等同使用者貼了整份模板並填了公司名稱。

## 資料誠實規則（所有工作都適用，包含每日排程）
- 每個數字都要能追到來源（主管機關申報文件或公司公告），而且真的讀到那個數字。
- 讀不到、算不出來、來源對不起來的數字：填 `null`，在 `notes.unavailable`（台積電、PLTR 舊格式則寫進回報）加一行，以「待確認：」開頭說明哪一季、哪個欄位、為什麼。
- 不估計、不內插、不從記憶補數字。
- 只有媒體報導、公司未證實的事件：`unc:1`，`note` 以「待確定：」開頭。
- `python3 tools/validate.py` 沒過就不發佈；不可以為了通過核對去改數字或放寬核對。

## 本益比與股價（新增）
- 股價檔 `data/prices/<代號>.json` **只由 GitHub Actions（prices-monthly）寫入**，Claude 不手填、不修改。本益比與預估本益比**不存檔、不手填**，由 `tools/pe.py` 在建置時算出。
- 每個季度都要有 `rd`（那一季 EPS 第一次公開的日期）與 `rdB`；讀不到填 `null` 並在 `notes.unavailable` 寫「待確認：<季度> 的財報公布日（rd）：原因」，不可用季度結束後幾天推算。
- 預估本益比（分析師預估）只有每月快照，**不回填**；它是網站上唯一不是財報／公司公告的數字，一律標「分析師預估」。

## 常用指令
```
python3 tools/validate.py       # 核對設定與所有啟用中的公司
python3 tools/build.py          # 產生網站與合併版 Artifact（dist/artifacts/all.html）
python3 tools/new_company.py …  # 新增公司腳手架（本益比需要 --yahoo/--price-from 或 --no-price）
python3 tools/pe.py             # 本益比計算的固定測試案例
python3 tools/prices_update.py --check  # 股價是否已到最新（只有 GitHub Actions 會真的抓）
python3 tools/daily.py          # 每日排程今天的工作清單與狀態（set／try／done 改 data/calendar.json）
```

## 文件
- `docs/ADDING_A_COMPANY.md` 新增公司流程
- `docs/DATA_SCHEMA.md` 資料格式 v1
- `docs/SCHEDULE_PROMPT.md` 每日排程指令（公司無關，新增公司不用改）。排程本身只是一句「照這份做」，所以改這份就等於改排程，改之前先問使用者
- `companies/<代號>/SOURCES.md` 各公司來源與更新步驟
