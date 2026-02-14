@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo 初始化 Git 並連結 GitHub
echo ========================================
echo.

if exist ".git" (
    echo [i] 已有 .git 資料夾，檢查遠端...
    git remote -v
    echo.
    echo 若遠端正確，請使用 upload.bat 上傳
    pause
    exit /b 0
)

git init
git remote add origin https://github.com/jameshung7777-webs/etf-00981a-bot.git
git add -A
git commit -m "初始提交"
git branch -M main
git pull origin main --rebase 2>nul
git push -u origin main

echo.
if %ERRORLEVEL% EQU 0 (
    echo [OK] 已初始化並推送到 GitHub
) else (
    echo [i] 若 push 失敗，可能是遠端已有內容，請嘗試:
    echo     git pull origin main --allow-unrelated-histories
    echo     git push -u origin main
)
echo ========================================
pause
