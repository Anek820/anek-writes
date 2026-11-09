@echo off
cd /d "%~dp0"
rem The server no longer opens a browser, so open it here after a short wait
start "" cmd /c "timeout /t 2 /nobreak >nul & start http://localhost:8000"
python server.py
pause
