@echo off
title iDrama Bot Launcher (Single Main.py)
echo [1/2] Starting Engine Process (Auto Scan & Worker)...
start "iDrama Engine" cmd /k "python main.py --mode auto"

timeout /t 5 /nobreak > nul

echo [2/2] Starting Admin Process (Commands & Panel)...
start "iDrama Admin" cmd /k "python main.py --mode admin"

echo.
echo All processes started from main.py!
echo Engine: Automated scanning and downloading.
echo Admin: Command processing (/download, /cari, /status).
echo.
pause
