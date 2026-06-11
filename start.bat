@echo off
chcp 65001 >nul
echo ==========================================
echo   WordCloud System - Dev
echo ==========================================
echo.
echo [1/2] Checking Python venv...

set PYTHON_EXE=wordcloud_project\venv\Scripts\python.exe
if not exist %PYTHON_EXE% (
    echo [ERROR] wordcloud_project\venv\Scripts\python.exe not found.
    echo         Make sure venv is set up under D:\dev\wordcloud\wordcloud_project\
    pause
    exit /b 1
)

echo [OK] Python interpreter found.
echo.
echo [2/2] Starting Flask server...
echo        URL: http://127.0.0.1:5001
echo        Stop: Ctrl + C
echo.

cd wordcloud_project
%~dp0%PYTHON_EXE% -m web.app

pause
