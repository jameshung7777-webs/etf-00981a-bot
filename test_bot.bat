@echo off
chcp 65001 > nul
cd /d "%~dp0"
echo.
python test_bot.py
echo.
pause
