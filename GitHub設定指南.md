# GitHub Actions 自動執行設定指南

## 📋 設定步驟

### 步驟 1：上傳程式碼到 GitHub

1. 在 GitHub 創建新的倉庫（Repository）
2. 將所有程式碼上傳到 GitHub

```bash
git init
git add .
git commit -m "初始提交：00981A ETF 自動追蹤系統"
git branch -M main
git remote add origin https://github.com/你的用戶名/你的倉庫名.git
git push -u origin main
```

### 步驟 2：設定 GitHub Secrets

1. 前往你的 GitHub 倉庫
2. 點擊 **Settings**（設定）
3. 左側選單選擇 **Secrets and variables** → **Actions**
4. 點擊 **New repository secret** 新增以下兩個 Secrets：

#### Secret 1: `TELEGRAM_BOT_TOKEN`
- **Name**: `TELEGRAM_BOT_TOKEN`
- **Value**: 你的 Telegram Bot Token
  - 例如：`8118096050:AAFbIs3h1FmbqI4bgCkOCV1Ndtl9kQ7kYzo`

#### Secret 2: `TELEGRAM_CHAT_ID`
- **Name**: `TELEGRAM_CHAT_ID`
- **Value**: 你的 Telegram Chat ID
  - 取得方式：在本地執行 `python get_chat_id.py`
  - 或直接填寫數字，例如：`123456789`

####（選用）`TELEGRAM_CHAT_IDS`：多個接收者
- 若倉庫的 `config.py` 已內建群組 ID（如招生報名專區），**仍建議**在 Secret 加你的私聊 ID 等，格式：`-1001234567890,123456789`（逗號分隔）。
- **行為說明**：CI 的 `TELEGRAM_CHAT_IDS` 與 `config.py` 裡的 `TELEGRAM_CHAT_IDS` 會**合併、去重**後再發送，不會因為只設了 Secret 就覆寫掉檔案裡的群組。

### 步驟 3：啟用 GitHub Actions

1. 前往倉庫的 **Actions** 標籤
2. 如果第一次使用，點擊 **I understand my workflows, enable them**
3. 工作流程會自動啟用

## ⏰ 執行時間

- **自動執行時間**：每天台灣時間 **16:30**（同一個 workflow 內依序：抓取 → 提交 JSON → 發送 Telegram）
- **時區換算**：台灣 16:30 = UTC **08:30**（cron：`30 8 * * *`）
- **手動觸發**：Actions → **00981A ETF 每日流程** → Run workflow，可選 `full` / `fetch_only` / `send_only`

## 🔍 查看執行結果

### 方法 1：在 GitHub 查看
1. 前往 **Actions** 標籤
2. 點擊左側的 **00981A ETF 每日流程**
3. 查看最新的執行記錄
4. 點擊執行記錄可以查看詳細日誌

### 方法 2：下載數據檔案
1. 在執行記錄頁面，找到 **Artifacts** 區塊
2. 點擊 **holdings-data** 下載
3. 解壓縮後可查看 JSON 數據檔案

### 方法 3：在 Telegram 接收通知
- 如果設定正確，排程跑完後會自動收到兩則訊息：
  1. 今日持股明細
  2. 與前日比較的變化報告

## ⚙️ 修改執行時間

如果需要修改執行時間，編輯 `.github/workflows/daily-pipeline.yml`：

```yaml
schedule:
  # cron 格式：分 時 日 月 星期
  # 台灣時間 16:30 = UTC 08:30
  - cron: '30 8 * * *'
```

**常用時間對照表（台灣時間 → UTC）：**
- 06:00 → `0 22 * * *`（前一天 22:00 UTC）
- 12:00 → `0 4 * * *`
- 16:30 → `30 8 * * *`（目前設定：抓取+發送同一趟）
- 18:00 → `0 10 * * *`
- 20:00 → `0 12 * * *`

## 🛠️ 故障排除

### 問題 1：工作流程沒有執行
- **檢查**：確認 Actions 已啟用
- **檢查**：確認 cron 語法正確
- **檢查**：GitHub Actions 可能有延遲（最多 15 分鐘）

### 問題 2：Telegram 通知失敗
- **檢查**：確認 Secrets 已正確設定
- **檢查**：確認 Bot Token 和 Chat ID 正確
- **檢查**：查看 Actions 日誌中的錯誤訊息

### 問題 3：無法抓取數據
- **檢查**：查看 Actions 日誌
- **檢查**：確認網站可訪問
- **注意**：程式會自動嘗試 requests 和 Selenium 兩種方法

### 問題 4：Chrome/ChromeDriver 錯誤
- **解決**：工作流程已自動安裝 Chromium 和 ChromeDriver
- **檢查**：查看 Actions 日誌確認安裝是否成功

## 📝 注意事項

1. **免費額度**：GitHub Actions 免費方案每月有 2000 分鐘額度
   - 每天執行一次約需 2-5 分鐘
   - 足夠使用

2. **數據保存**：
   - Artifacts 會保留 30 天
   - 建議定期下載重要數據

3. **安全性**：
   - 不要將 Bot Token 和 Chat ID 直接寫在程式碼中
   - 使用 GitHub Secrets 保護敏感資訊

4. **時區**：
   - GitHub Actions 使用 UTC 時間
   - 目前排程為台灣時間 **16:30**（抓取與發送同一 workflow）

## 🎯 測試工作流程

### 手動觸發測試
1. 前往 **Actions** 標籤
2. 選擇 **00981A ETF 每日流程**
3. 點擊右側 **Run workflow**
4. 選擇分支（通常是 `main`）
5. 點擊 **Run workflow** 按鈕

### 檢查執行結果
- 查看日誌確認是否成功
- 檢查 Telegram 是否收到訊息
- 下載 Artifact 檢查數據檔案

## 📚 相關文件

- `使用說明.md` - 本地執行的詳細說明
- `快速開始.md` - 快速參考指南
- `.github/README.md` - GitHub Actions 簡要說明
