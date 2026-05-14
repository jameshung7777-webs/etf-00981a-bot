@echo off
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".git" (
    echo [錯誤] 此資料夾不是 Git 倉庫
    pause
    exit /b 1
)

git config core.hooksPath .githooks
echo [OK] 已啟用：此倉庫的 hook 目錄為 .githooks
echo     之後每次 git commit 成功後會自動執行 git push 到 origin（目前分支）。
echo.
echo 若希望「不必開著 run.bat」也能每天自動抓取：請執行 install_windows_schedule.bat
echo.
echo 若要關閉自動 push：
echo     git config --unset core.hooksPath
pause
