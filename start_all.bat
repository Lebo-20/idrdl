@echo off
title iDrama Bot Launcher
echo [1/3] Migrating historical data if needed...
python migrate_history.py

echo [2/3] Starting Engine Process (Auto Scan & Worker)...
start "iDrama Engine" cmd /k "python engine.py"

timeout /t 2 /nobreak > nul

echo [3/3] Starting Admin Process (Commands & Panel)...
start "iDrama Admin" cmd /k "python admin.py"

echo.
echo All processes started! 
echo Engine: Automated scanning and downloading (No commands).
echo Admin: Command processing (/download, /cari, /panel).
echo.
pause
