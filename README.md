# 00981A ETF 持股變化追蹤

自動抓取 00981A ETF 的持股明細，比較前後兩天的變化，並自動發送到 Telegram。

## 功能特點

- ✅ 自動抓取 00981A ETF 持股明細
- ✅ 比較前後兩天的持股變化
- ✅ 自動格式化報告（新增、刪除、加碼、減碼）
- ✅ 自動發送到 Telegram Bot
- ✅ 自動更新日期
- ✅ **GitHub Actions 自動執行** - 每天晚上 6 點自動運行（無需本地電腦開機）

## 安裝步驟

### 1. 安裝 Python 依賴

```bash
pip install -r requirements.txt
```

### 2. 安裝 ChromeDriver（可選）

腳本會自動嘗試多種方法來啟動 ChromeDriver：

**方法一：使用系統 PATH 中的 ChromeDriver（最快）**
- 如果系統 PATH 中已有 ChromeDriver，會直接使用

**方法二：使用 webdriver-manager（自動下載）**

```bash
pip install webdriver-manager
```

腳本會自動使用 webdriver-manager 下載 ChromeDriver（可能需要一些時間）

**方法三：手動下載**

1. 訪問 https://chromedriver.chromium.org/
2. 下載與您的 Chrome 版本匹配的 ChromeDriver
3. 將 `chromedriver.exe` 放在：
   - 系統 PATH 中，或
   - 項目目錄中（與 main.py 同目錄）

**方法四：使用 requests 版本（不需要 ChromeDriver）**

如果 Selenium 無法使用，腳本會自動嘗試使用 `scraper_requests.py`（不需要 ChromeDriver，但可能無法處理動態載入的內容）

### 3. 設置 Telegram Bot

1. 發送任意消息給您的 Telegram Bot（使用 Bot Token）
2. 腳本會自動獲取 chat_id
3. 或者手動設置 chat_id（在 `send_to_telegram()` 函數中）

## 使用方法

### 首次運行

```bash
python main.py
```

首次運行會：
- 抓取當天的持股數據
- 保存到 `holdings_data.json`
- 不會發送報告（因為沒有前一天的數據可比較）

### 日常運行

每天運行一次腳本：

```bash
python main.py
```

腳本會：
1. 抓取當天的持股數據
2. 載入前一天的數據
3. 比較變化並生成報告
4. 發送到 Telegram

### 設置自動運行

#### 方法一：使用 GitHub Actions（推薦）⭐

**優點**：不需要本地電腦開機，完全自動化

1. 將程式碼上傳到 GitHub
2. 設定 GitHub Secrets（`TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`）
3. 工作流程會每天台灣時間 **18:00**（晚上6點）自動執行

詳細設定步驟請參考：**[GitHub設定指南.md](GitHub設定指南.md)**

#### 方法二：使用 Windows 任務計劃程序

1. 打開「任務計劃程序」
2. 創建基本任務
3. 設置觸發器：每天特定時間（例如：18:00）
4. 設置操作：啟動程序 `python.exe`
5. 添加參數：`main.py --now`
6. 設置起始於：專案目錄路徑

**注意**：此方法需要電腦持續開機

## 輸出格式

報告格式示例：

```
00981A 持股更新（1/28 → 1/29）

🆕 新增／刪除
・新增：無。
・刪除：無。

📈 主要加碼一覽（張數增加）
・南亞科技（2408）：＋700 張（5,300 → 6,000 張）。
・華新麗華（1605）：＋2,500 張（14,000 → 16,500 張）。
...

📉 主要減碼一覽（張數減少）
・無。

＊以上為「張數」變動整理（1 張＝1,000 股），僅為持股結構異動說明，未涉及股價或投資建議。
```

## 文件說明

- `main.py` - 主程序入口（自動選擇最佳爬蟲方法，支援排程）
- `scraper_selenium.py` - Selenium 版本的爬蟲（推薦，更可靠）
- `scraper_requests.py` - requests 版本的爬蟲（備用，不需要 ChromeDriver）
- `scraper.py` - 舊版本的 requests 爬蟲（已棄用）
- `config.py` - 配置文件（Telegram Bot Token 等，支援環境變數）
- `test_scraper.py` - 測試腳本
- `holdings_data.json` - 保存的持股數據（自動生成）
- `requirements.txt` - Python 依賴列表
- `run.bat` - Windows 快速啟動腳本
- `.github/workflows/daily-fetch.yml` - GitHub Actions 工作流程
- `GitHub設定指南.md` - GitHub Actions 詳細設定說明
- `使用說明.md` - 完整使用說明
- `快速開始.md` - 快速參考指南

## 故障排除

### 無法抓取數據

1. **檢查網絡連接**
2. **確認網站可訪問**：https://www.pocket.tw/etf/tw/00981A/fundholding
3. **ChromeDriver 問題**：
   - 如果 webdriver-manager 下載失敗，可以手動下載 ChromeDriver
   - 或將 `chromedriver.exe` 放在項目目錄中
   - 腳本會自動嘗試使用 requests 版本作為備用
4. **嘗試不使用 headless 模式**：修改 `scraper_selenium.py` 中的 `setup_driver()`，移除 `--headless` 參數來查看實際情況
5. **使用 requests 版本**：如果 Selenium 持續失敗，可以手動使用 `scraper_requests.py`

### Telegram 發送失敗

1. 確認 Bot Token 正確
2. 先發送一條消息給 Bot，讓腳本獲取 chat_id
3. 檢查網絡連接（Telegram API 可能需要代理）

### 數據格式錯誤

如果網站結構改變，可能需要更新 `fetch_holdings_selenium()` 函數中的解析邏輯。

## 注意事項

- 此腳本僅供學習和研究使用
- 數據來源：口袋證券
- 報告僅為持股結構異動說明，不涉及投資建議
- 請遵守網站的使用條款和 robots.txt
