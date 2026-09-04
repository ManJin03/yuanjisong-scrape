@echo off
rem ============================================
rem  YuanJiSong Desktop build script (PyInstaller)
rem  One-click: setup venv -> install deps -> build
rem  Output: dist\猿急送筛选系统\猿急送筛选系统.exe
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
)

echo [setup] Installing runtime + build dependencies...
"%PY%" -m pip install -r requirements.txt "pyinstaller>=6.0"
if errorlevel 1 (
    echo [error] Failed to install dependencies.
    pause
    exit /b 1
)

echo [build] Running PyInstaller...
"%PY%" -m PyInstaller --noconfirm --clean yuanjisong.spec
if errorlevel 1 (
    echo [error] PyInstaller build failed.
    pause
    exit /b 1
)

echo.
echo [done] Build succeeded:
echo   dist\猿急送筛选系统\猿急送筛选系统.exe
echo Distribute the whole "dist\猿急送筛选系统" folder (zip it for sharing).
pause
