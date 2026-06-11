@echo off
chcp 65001 >nul
echo ==========================================
echo   WordCloud System - Dev
echo ==========================================
echo.
echo [1/2] Checking Python venv...

set PYTHON_EXE=venv\Scripts\python.exe
if not exist %PYTHON_EXE% (
    echo [ERROR] venv\Scripts\python.exe not found.
    echo         Make sure venv is set up under D:\dev\wordcloud\
    pause
    exit /b 1
)

echo [OK] Python interpreter found.
echo.
echo [2/2] Starting Flask server...
echo        URL: http://127.0.0.1:5001
echo        Stop: Ctrl + C
echo.

%PYTHON_EXE% -m web.app

pause
