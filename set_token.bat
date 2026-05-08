@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo.
echo ========================================
echo   Telegram Bot Token 快速復原
echo ========================================
echo.

REM 確認 Python 可用
python --version > nul 2>&1
if errorlevel 1 (
    echo [!] 找不到 Python，請確認已安裝並加入 PATH
    pause
    exit /b 1
)

REM 安裝 requests（以防萬一）
pip install requests -q 2>nul

REM 執行復原工具
REM 可直接帶 Token 參數：set_token.bat 123456:ABCDEF...
if "%~1"=="" (
    python set_token.py
) else (
    python set_token.py %~1
)

echo.
pause
