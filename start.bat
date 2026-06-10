@echo off
chcp 65001 >nul
echo ==========================================
echo   WordCloud System - Internal Offline
echo ==========================================
echo.
echo [1/2] Python  venv 확인...

set PYTHON_EXE=venv\Scripts\python.exe
if not exist %PYTHON_EXE% (
    echo [ERROR] venv\Scripts\python.exe 를 찾을 수 없습니다.
    echo         이 폴더를 D:\dev\wordcloud\ 에 압축 해제했는지 확인하세요.
    pause
    exit /b 1
)

echo [OK] Python 인터프리터 확인 완료
echo.
echo [2/2] Flask 서버 기동...
echo        주소: http://127.0.0.1:5001
echo        종료: Ctrl + C
echo.

%PYTHON_EXE% -m web.app

pause
