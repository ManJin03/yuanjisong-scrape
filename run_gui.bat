@echo off
rem ============================================
rem  YuanJiSong GUI launcher
rem  Uses project venv automatically; creates it
rem  and installs requirements on first run.
rem ============================================
cd /d "%~dp0"

set PY=.venv\Scripts\python.exe

if not exist "%PY%" (
    echo [setup] Virtual environment not found. Creating...
    python -m venv .venv
    if errorlevel 1 (
        echo [error] Failed to create venv. Please install Python 3.10+ first.
        pause
        exit /b 1
    )
    echo [setup] Installing requirements...
    "%PY%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [error] Failed to install requirements.
        pause
        exit /b 1
    )
)

echo [gui] Starting...
"%PY%" main.py gui %*
pause
