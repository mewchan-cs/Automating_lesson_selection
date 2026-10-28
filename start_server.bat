@echo off
cd /d "%~dp0"
python backend\server.py
if errorlevel 1 (
  echo.
  echo The Python server could not start. Check Python 3.10+ is installed.
  pause
)
