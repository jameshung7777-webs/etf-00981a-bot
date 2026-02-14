@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".git" (
    echo [錯誤] 此資料夾不是 Git 倉庫
    echo 請在專案資料夾執行: git init
    echo 並設定遠端: git remote add origin https://github.com/jameshung7777-webs/etf-00981a-bot.git
    pause
    exit /b 1
)

echo ========================================
echo 上傳到 GitHub
echo ========================================
echo.

git add -A
git status

echo.
set /p msg=請輸入本次更新的說明（直接 Enter 使用預設）: 
if "%msg%"=="" set msg=更新程式碼

git commit -m "%msg%"
git push origin main

echo.
echo ========================================
if %ERRORLEVEL% EQU 0 (
    echo 已成功上傳到 GitHub
) else (
    echo 上傳失敗，請檢查網路或 git 設定
)
echo ========================================
pause
