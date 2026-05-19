# GitHub Actions 自動執行設定

## 設定步驟

### 1. 設定 GitHub Secrets

在 GitHub 倉庫中設定以下 Secrets（Settings → Secrets and variables → Actions）：

1. **TELEGRAM_BOT_TOKEN**
   - 你的 Telegram Bot Token
   - 例如：`8118096050:AAFbIs3h1FmbqI4bgCkOCV1Ndtl9kQ7kYzo`

2. **TELEGRAM_CHAT_ID**
   - 你的 Telegram Chat ID
   - 取得方式：執行 `python get_chat_id.py`

### 2. 工作流程說明

- **自動執行時間**：每天台灣時間 **14:30**（UTC 06:30，同一 workflow 內抓取並發送；較原 16:30 提早 2 小時以吸收排程延遲）
- **手動觸發**：可以在 Actions 頁面手動觸發執行
- **數據保存**：執行結果會保存為 Artifact，保留 30 天

### 3. 查看執行結果

1. 前往 GitHub 倉庫的 **Actions** 標籤
2. 查看工作流程執行狀態
3. 下載 Artifact 查看數據檔案

## 注意事項

- 工作流程使用 UTC 時間，台灣時間 14:30 = UTC 06:30
- 如需修改執行時間，編輯 `.github/workflows/daily-pipeline.yml` 中的 cron 設定
- Bot token 若在 **GitHub Environment**：請在 `.github/workflows/daily-pipeline.yml` 的 `jobs.daily` 底下取消註解 `environment: <環境名>`（勿使用空白或動態 `environment` 表達式，否則可能讀不到 Repository 的 Secrets）
- 臨時除錯可設 Repository **Variable** `TELEGRAM_ACTIONS_BOT_TOKEN`（勿用於公開倉庫；正式請用 Secrets）
- 確保 Secrets 已正確設定，否則 Telegram 通知會失敗
