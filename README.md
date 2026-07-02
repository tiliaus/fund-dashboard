# 基金淨值走勢比較儀表板

四檔台灣基金（安聯台灣科技、安聯台灣大壩、統一奔騰、統一黑馬）與 ETF（00981A）淨值走勢比較網頁。
每個交易日自動更新淨值與每月自動更新前十大持股，任何人可直接開啟網址查看，無需登入。

**網址：** https://tiliaus.github.io/fund-dashboard/

---

## 功能

### 走勢比較
- 四檔基金淨值相對報酬走勢折線圖
- 自由勾選要比較的基金（最少保留一檔）
- 期間切換：3個月 / 6個月 / 1年
- 自訂日期區間

### 與ETF比較
- 四檔基金 + 00981A ETF 同框比較
- 自由勾選要顯示的基金與ETF
- 期間切換與自訂日期區間（同走勢比較）

### 持股分配
- 四檔基金前十大持股圓餅圖
- 資料來源：MoneyDJ，顯示各基金資料月份
- 每月自動更新

---

## 資料來源

| 資料 | 來源 | 更新頻率 |
|------|------|---------|
| 基金淨值 | MoneyDJ（`ya/yp010000.djhtm`）| 每個交易日 |
| ETF 淨值 | MoneyDJ（`ETF/X/Basic/Basic0003.xdjhtm`）| 每個交易日 |
| 前十大持股 | MoneyDJ（`yp/yp013000.djhtm`）| 每月 |

**基金代碼對照：**

| 基金名稱 | MoneyDJ 代碼 |
|---------|-------------|
| 安聯台灣科技 | ACDD04 |
| 安聯台灣大壩 | ACDD01 |
| 統一奔騰 | ACPS10 |
| 統一黑馬 | ACPS02 |
| 00981A ETF | 00981A.TW |

---

## 檔案結構

```
fund-dashboard/
├── index.html                         # 主網頁（圖表儀表板）
├── data/
│   └── nav.json                       # 淨值與持股資料（自動更新）
├── scripts/
│   └── fetch_nav.py                   # 抓取淨值與持股的 Python 腳本
├── .github/
│   └── workflows/
│       └── update-nav.yml             # GitHub Actions 排程設定
└── README.md
```

---

## nav.json 資料格式

```json
{
  "last_updated": "2026/05/14",
  "holdings_updated": "2026/05",
  "安聯台灣科技": {
    "2026/05/14": 781.76,
    "2026/05/13": 763.21,
    ...
  },
  "安聯台灣大壩": { ... },
  "統一奔騰": { ... },
  "統一黑馬": { ... },
  "00981A": { ... },
  "holdings": {
    "安聯台灣科技": {
      "date": "2026/05/08",
      "data": [
        { "name": "旺矽", "pct": 9.14 },
        ...
      ]
    },
    ...
  }
}
```

- 淨值保留**最近一年**，超過自動刪除
- 持股只保留**最新一期**

---

## 自動更新機制

### GitHub Actions
排程設定（`update-nav.yml`）：每週一至五 UTC 11:00 / 12:00 / 13:00 / 14:00 各執行一次。

> GitHub 免費方案排程可能延遲 30 分鐘至數小時，建議搭配 cron-job.org 使用。

### cron-job.org（外部觸發）
為確保準時執行，使用 cron-job.org 在台灣時間 19:00 / 20:00 / 21:00 / 22:00 呼叫 GitHub API 觸發 workflow，繞過 GitHub 排程佇列延遲。

---

## 設定步驟

### 1. Fork 這個 Repository
點右上角 **Fork** → 建立你自己的副本。

---

### 2. 啟用 GitHub Pages
**Settings** → **Pages** → Source 選 `Deploy from a branch` → Branch 選 `main`、`/ (root)` → **Save**

稍等 1–2 分鐘，網址出現在頁面上：
```
https://你的帳號.github.io/fund-dashboard/
```

---

### 3. 設定 cron-job.org（建議）

**① 建立 GitHub Personal Access Token**
- 右上角頭像 → Settings → Developer settings → Personal access tokens → Tokens (classic)
- Generate new token → 勾選 `workflow` → Expiration 選 **No expiration**
- 複製產生的 `ghp_xxxx...` token（只顯示一次）

**② 在 cron-job.org 建立排程（共 4 個）**

| Title | 執行時間（台灣）| Crontab |
|-------|--------------|---------|
| Fund Dashboard 19:00 | 週一至五 19:00 | `0 19 * * 1-5` |
| Fund Dashboard 20:00 | 週一至五 20:00 | `0 20 * * 1-5` |
| Fund Dashboard 21:00 | 週一至五 21:00 | `0 21 * * 1-5` |
| Fund Dashboard 22:00 | 週一至五 22:00 | `0 22 * * 1-5` |

每個 cronjob 設定：
- **URL：** `https://api.github.com/repos/你的帳號/fund-dashboard/actions/workflows/update-nav.yml/dispatches`
- **Request method：** `POST`
- **Request body：** `{"ref": "main"}`
- **Headers（ADVANCED 頁面）：**
  - `Authorization` → `Bearer ghp_你的token`
  - `Accept` → `application/vnd.github.v3+json`
  - `Content-Type` → `application/json`
- **Time zone：** Asia/Taipei

---

### 4. 匯入 00981A 歷史資料（一次性）

將 `add_etf_data.py` 上傳到 repo 根目錄，暫時修改 `update-nav.yml`：
```yaml
run: python add_etf_data.py
```
手動 Run workflow 執行一次後，再改回：
```yaml
run: python scripts/fetch_nav.py
```

---

## 手動測試

Actions → **updatanav** → **Run workflow** → 確認執行成功。

---

## 注意事項

- 基金淨值通常於台灣時間下午 4–6 點公布，腳本以 MoneyDJ 回傳的日期為準存入，不使用執行當天日期
- 若當日淨值尚未公布，腳本會略過並顯示警告，下次排程再試
- 持股資料為示意性質，實際配置請參閱各基金公司公告
