@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
  echo Алғашқы іске қосу: кітапханалар орнатылуда...
  py -m venv .venv || python -m venv .venv
  .venv\Scripts\pip install -q -r requirements.txt
  .venv\Scripts\python seed_demo.py
)
start "" http://localhost
.venv\Scripts\python app.py
pause
