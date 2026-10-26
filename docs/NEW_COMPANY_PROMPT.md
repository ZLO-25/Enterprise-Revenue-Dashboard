# 新增公司的 Prompt 模板

## 最短用法（一句話就好）

在專案的主對話框直接說下面任何一種，Claude 會自動找到這份文件並照做：

```
加入新公司：NVDA
加入新公司：輝達、聯發科、Microsoft
add new company: NVDA, AMD
```

這是因為 repo 根目錄的 `CLAUDE.md` 和專案記憶都寫了「聽到『加入新公司／add new company』就照 `docs/NEW_COMPANY_PROMPT.md` 做」。如果哪一次 Claude 沒有照做，就把下面「完整模板」整段貼給它。

## 一次加入多家公司

可以。一句話列出多家公司，用頓號、逗號或換行分隔都可以。流程是：

```
加入新公司：A、B、C
        │
        ▼
① 先列一張表：每家的代號、交易所、幣別、會計年度、預計資料期間 ──► 你確認（或直接用預設）
        │
        ▼
② 每家各自跑完：腳手架 → SOURCES.md → 填資料 → 核對
        │            （一家沒過核對，不影響其他家）
        ▼
③ 通過核對的公司一起 enabled:true → build → 一次 commit / push → 更新一次 Artifact
        │
        ▼
④ 回報：每家的結果，沒過的公司寫清楚卡在哪裡
```

建議一次 **3 家以內**。每家要查好幾年的財報，家數越多越容易做不完或出錯；超過 3 家時，Claude 會先做前 3 家，其餘列在回報裡等你說「繼續」。

## 完整模板

把下面整段複製給 Claude，**只要填第一段**（公司名稱必填，其餘可留空讓 Claude 查）。其餘文字不用改。

```
請在「企業財報追蹤板」加入新公司。

公司（可一次多家，每行一家）：
- ＿＿＿＿＿＿（例：輝達 / NVDA）
- ＿＿＿＿＿＿
期間：＿＿＿＿（例：2019 年起；留空＝公司公開財報可取得的最早一季）
公司專屬指標（選填）：＿＿＿＿（例：資料中心營收拆分、客戶數；留空＝你依財報判斷）

## 最重要的規則：不確定就寫「待確認」，絕對不能捏造
- 每一個數字都要有可以點開的來源（主管機關申報文件或公司公告），而且你要真的讀到那個數字。
- 讀不到、算不出來、或兩個來源對不起來的數字：填 null，並在 notes.unavailable 加一行，以「待確認：」開頭，寫清楚是哪一季、哪個欄位、為什麼不確定（例：「待確認：2Q21 資本支出，10-Q 與新聞稿差 3.2 百萬美元」）。
- 不要估計、不要內插、不要用「大約」的數字補空格，不要從記憶裡拿數字。
- 只有媒體報導、公司沒證實的事件：加 unc:1，note 以「待確定：」開頭，寫是哪家媒體報的。
- 回報時把所有「待確認」與「待確定」的項目列成一張表，讓我知道哪些還沒查清楚。

## 專案
- GitHub repo：ZLO-25/Enterprise-Revenue-Dashboard（main 分支，GitHub Pages 從根目錄發佈）
- 先用 add_repo（owner ZLO-25、repo Enterprise-Revenue-Dashboard、access push）附加 repo 並 clone。
- 讀這三份文件再動手，照著做：docs/ADDING_A_COMPANY.md（流程）、docs/DATA_SCHEMA.md（資料格式）、companies/pltr/SOURCES.md（範例）。
- 全程用繁體中文；先用你自己的話重述要加哪幾家公司，並列一張表：代號、交易所、幣別、會計年度、公布頻率、預計資料期間、專屬指標。會影響做法的問題一次問完；能用合理預設就直接做，最後告訴我選了什麼。
- 超過 3 家時，先做前 3 家，其餘列在回報裡等我說「繼續」。

## 步驟（每家公司各做一次 1–4，全部做完再做 5–8）
1. 腳手架：python3 tools/new_company.py <代號> --name <中文名> --name-en <英文名> --ticker <代號> --exchange "<交易所 代號>" --currency <幣別>
   （代號用小寫英數字，同時是網址路徑；不要手動建檔。）
2. 寫 companies/<代號>/SOURCES.md：來源依可信度排序（主管機關申報文件 → 公司 IR → 法說會 → 可信媒體只用於事件）、欄位定義與單位、第四季推算方式、核對規則、每月排程的更新步驟（只補上次資料之後的新期間）、已知缺口。要寫到沒看過這個專案的人也能照做，因為每月排程會照這份執行。
3. 蒐集資料填進 data/<代號>.json（schema v1）：
   - 共用欄位每季都要有：rev、gm、om、eps 不能是 null；這四個欄位如果某一季讀不到，那一季就先不要收，並寫進「待確認」。gp、opInc、ni、ocf、capex、fcf、dps 讀不到填 null。
   - 單位：美股用「百萬美元」、台股用「百萬元新台幣」（或在 company.unit 寫明）；每股用美元／元。
   - 第四季 = 全年 − 前三季累計（EPS 除外，取公司公布的 Q4）。
   - annual 只放公司公布的全年數字；guidance 用 items[] 形式；events 放下一個公布日（公司未公告的加 est:1）；waterfall 換成最新一季；milestones 列上市、重大產品、合約、併購、指數納入；sources 列頁面要顯示的來源連結；notes.unavailable 列「待確認」與取不到的欄位。
   - 有分部營收就放 segments（分部加總＝營收）；公司專屬指標放 extra（keys 指定哪些要畫圖）。
4. 核對：python3 tools/validate.py <代號>。沒過就回到來源修資料，不要放寬核對、不要改數字去湊。修不好的公司保持 enabled:false，在回報說明卡在哪一項、差多少。
5. 通過核對的公司：companies.json 把 enabled 改成 true，確認 primarySource {n, url}；python3 tools/validate.py && python3 tools/build.py。
6. 用無頭瀏覽器（Playwright）開首頁與每家公司的頁面：桌機 1280、手機 390、深色模式；沒有 JavaScript 錯誤、沒有水平捲動、沒有 undefined／NaN。容器的 curl 多半被擋，讀網頁用 WebFetch／WebSearch；Chart.js 在 repo 的 assets/vendor/ 有本地副本。
7. 一次 commit（繁體中文訊息，例「加入輝達（NVDA）、超微（AMD）財報追蹤板」）、git push -u origin main。
8. 更新合併版 Artifact：先用 Artifact 工具 read companies.json 的 site.artifact 網址，再 publish dist/artifacts/all.html 到同一個 url。不要建立新的 Artifact。
9. 不要動 assets/、tools/build.py、其他公司的檔案與任何排程；每月排程下次執行（每月 12 日）會自動把新公司納入（它只看 companies.json 的 enabled）。

## 最後回報（繁體中文，先用自己的話重述目標，多用 ASCII 圖）
- 每家公司：成功或沒過核對；網址（首頁與 /<代號>/）
- 資料涵蓋期間、單位、資料來源連結
- 「待確認」與「待確定」項目一覽表：公司、季度或日期、欄位、原因
- 選了哪些預設
- 用小 ASCII 表列出每家最新一季與近四季的營收、毛利率、營益率、EPS、自由現金流
- Artifact 是否更新成功、下一個公布日、下一次排程（每月 12 日 07:48 台北）會做什麼
```

## 這份模板為什麼這樣設計

```
你只說：加入新公司：NVDA（可多家）
            │
            ▼
Claude 照固定流程：腳手架 → SOURCES.md → 填資料 → 驗證 → 建置 → 瀏覽器檢查 → push → Artifact
            │                              │
            │                              └─ 讀不到的數字 → null ＋「待確認：…」，不估計
            ▼
每月排程（12 日）自動納入（只看 companies.json 的 enabled）
```

- **共用程式不用改**：資料符合 v1 就直接用通用頁面 `templates/generic.frag.html`，首頁卡片、記分板、比較圖、長期指標自動納入。
- **錯不了的地方交給程式**：`tools/validate.py` 檢查設定完整、毛利率與金額自洽、四季＝全年、分部加總、損益拆解加總、財測區間；沒過就不發佈。
- **不確定的地方交給人**：所有「待確認」都寫進資料檔的 `notes.unavailable`，頁面會列在「沒能取得或公司未揭露的欄位」，回報也會列一張表。
