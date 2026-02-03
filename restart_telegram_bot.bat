@echo off
echo ========================================
echo RESTARTING TELEGRAM BOT
echo ========================================
echo.

echo Step 1: Stopping any running Python processes in this directory...
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO LIST ^| findstr "PID:"') do (
    for /f "tokens=*" %%b in ('wmic process where "ProcessId=%%a" get CommandLine /format:list ^| findstr "kite"') do (
        echo Killing process %%a
        taskkill /PID %%a /F >nul 2>&1
    )
)

echo.
echo Step 2: Waiting 2 seconds...
timeout /t 2 /nobreak >nul

echo.
echo Step 3: Starting telegram_bot.py...
echo.
echo ========================================
echo BOT IS STARTING...
echo ========================================
echo.
echo Commands available in Telegram:
echo   /start - Show all commands
echo   /segments - Segment management menu
echo   /status - Quick status with buttons
echo   /killswitch - Kill switch status
echo.
echo Press Ctrl+C to stop the bot
echo ========================================
echo.

python telegram_bot.py

pause
