@echo off
title LeadPulse AI - B2B Lead Intelligence Platform
cd /d "D:\TS_Hunter_Intelligence_Pro"
echo ========================================================
echo        Starting LeadPulse AI Web Platform...
echo ========================================================
echo Web UI: http://localhost:5055
echo.
timeout /t 2 >nul
start http://localhost:5055
python app.py
pause
