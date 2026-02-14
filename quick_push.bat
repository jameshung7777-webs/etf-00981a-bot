@echo off
chcp 65001 >nul
git add -A
git commit -m "更新程式碼" 2>nul || echo 無變更需提交
git push origin main
if %ERRORLEVEL% EQU 0 (echo [OK] 已上傳) else (echo [FAIL] 上傳失敗 & pause)
