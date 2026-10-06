@echo off
title SoMeet - AI Speech Studio
echo Starting SoMeet Application...
cd /d "%~dp0"
echo Server starting at http://127.0.0.1:8000
start http://127.0.0.1:8000
".venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
pause
