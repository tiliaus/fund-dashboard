# 基金淨值走勢比較儀表板

四檔台灣基金（安聯台灣科技、安聯台灣大壩、統一奔騰、統一黑馬）淨值走勢比較網頁，
每個交易日自動更新，任何人可直接開啟網址查看，無需登入。

---

## 設定步驟

### 1. Fork 這個 Repository

點右上角 **Fork** → 建立你自己的副本。

---

### 2. 設定 GitHub Secrets

GitHub Actions 需要 Anthropic API Key 才能自動搜尋每日淨值。

1. 前往你 fork 的 repo → **Settings** → **Secrets and variables** → **Actions**
2. 點 **New repository secret**
3. Name 填：`ANTHROPIC_API_KEY`
4. Value 填：你的 Anthropic API Key（從 [console.anthropic.com](https://console.anthropic.com) 取得）
5. 點 **Add secret**

---

### 3. 啟用 GitHub Pages

1. 前往 **Settings** → **Pages**
2. Source 選 **Deploy from a branch**
3. Branch 選 `main`，資料夾選 `/ (root)`
4. 點 **Save**

稍等 1–2 分鐘後，網址會出現在頁面上，格式為：
```
https://你的帳號.github.io/fund-dashboard/
```

---

### 4. 測試自動更新

1. 前往 **Actions** → **每日更新基金淨值**
2. 點 **Run workflow** 手動執行一次
3. 確認執行成功後，`data/nav.json` 的 `last_updated` 會更新為今日日期

---

## 檔案結構

```
fund-dashboard/
├── index.html                        # 主網頁（圖表儀表板）
├── data/
│   └── nav.json                      # 淨值資料（自動更新）
├── scripts/
│   └── fetch_nav.py                  # 抓取淨值的 Python 腳本
└── .github/
    └── workflows/
        └── update-nav.yml            # GitHub Actions 排程設定
```

---

## 自動更新時間

每週一至週五台灣時間 **18:30** 自動執行。
若基金淨值尚未公布，該日資料會在下次執行時補入。

如需臨時更新，可在 **Actions** 頁面手動觸發。

---

## 更新持股分配資料

`index.html` 中的持股資料為示意數據。若需更新實際持股，
編輯 `index.html` 內的 `HOLDINGS` 物件即可。
