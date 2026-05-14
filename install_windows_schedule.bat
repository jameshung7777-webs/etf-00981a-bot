@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 將以「目前 Windows 使用者」註冊每日 16:30 / 17:00 排程（本機時區，建議設為台北時間）。
echo 需能執行 python、git；Selenium 抓取建議在已登入、可開 Chrome 的環境執行。
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_windows_schedule.ps1"
echo.
pause
