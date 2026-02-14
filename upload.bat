@echo off
chcp 65001 >nul
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
