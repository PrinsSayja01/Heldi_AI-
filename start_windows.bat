@echo off
cd /d %~dp0
where python >nul 2>nul || (echo Python 3.10+ is required & pause & exit /b 1)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env
echo Starting Heidi Lead Intelligence Agent at http://127.0.0.1:8787
python -m uvicorn app.main:app --host 127.0.0.1 --port 8787
pause
