@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo 00981A 完整流程（一次執行）
echo ========================================
echo.
echo 1. 抓取持股數據
echo 2. 儲存 JSON 檔（holdings_data.json + 帶日期的檔）
echo 3. 比較昨日變化
echo 4. 發送到 Telegram
echo.
echo ========================================
echo.
echo 檢查依賴...
pip install -r requirements.txt -q
echo.

python main.py --now

echo.
echo ========================================
echo 已產生的檔案：
echo ========================================
dir /b holdings_data*.json 2>nul || echo （無）
echo.
echo 完成
pause
