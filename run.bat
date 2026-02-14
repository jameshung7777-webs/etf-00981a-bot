@echo off
chcp 65001 >nul
echo ========================================
echo 00981A ETF 持股變化追蹤
echo ========================================
echo.
echo 選擇執行模式:
echo 1. 立即執行一次
echo 2. 啟動排程器（每天18:00抓取、18:30發送）
echo.
set /p choice=請選擇 (1 或 2，直接按 Enter 預設為排程器): 

if "%choice%"=="1" (
    echo.
    echo 立即執行一次...
    python main.py --now
) else (
    echo.
    echo 啟動排程器（每天18:00抓取、18:30發送）...
    echo 按 Ctrl+C 可停止程式
    python main.py
)

echo.
echo 按任意鍵退出...
pause >nul
