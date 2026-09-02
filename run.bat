@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1

cd /d "%~dp0"
if errorlevel 1 (
    echo [오류] 프로젝트 폴더로 이동하지 못했습니다.
    pause
    exit /b 1
)

set "VENV_DIR=venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "BOOTSTRAP_PYTHON="

echo ============================================================
echo Holocron Archive 실행 준비
echo ============================================================
echo.

echo [1/5] Python 실행 환경 확인 중...

if exist "%VENV_PYTHON%" (
    echo 기존 가상환경을 사용합니다: %VENV_DIR%
) else (
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3 --version >nul 2>&1
        if not errorlevel 1 set "BOOTSTRAP_PYTHON=py -3"
    )

    if not defined BOOTSTRAP_PYTHON (
        where python >nul 2>&1
        if not errorlevel 1 (
            python --version >nul 2>&1
            if not errorlevel 1 set "BOOTSTRAP_PYTHON=python"
        )
    )

    if not defined BOOTSTRAP_PYTHON (
        where python3 >nul 2>&1
        if not errorlevel 1 (
            python3 --version >nul 2>&1
            if not errorlevel 1 set "BOOTSTRAP_PYTHON=python3"
        )
    )

    if not defined BOOTSTRAP_PYTHON (
        echo.
        echo [오류] Python 3을 찾을 수 없습니다.
        echo Python을 설치한 뒤 다시 run.bat을 실행하세요.
        echo 설치할 때 "Add Python to PATH" 옵션을 선택하는 것을 권장합니다.
        pause
        exit /b 1
    )

    echo 가상환경이 없습니다. 새로 생성합니다: %VENV_DIR%
    !BOOTSTRAP_PYTHON! -m venv "%VENV_DIR%"

    if errorlevel 1 (
        echo.
        echo [오류] 가상환경 생성에 실패했습니다.
        pause
        exit /b 1
    )
)

if not exist "%VENV_PYTHON%" (
    echo.
    echo [오류] 가상환경의 Python을 찾을 수 없습니다: %VENV_PYTHON%
    pause
    exit /b 1
)

echo.
echo [2/5] 패키지 설치 준비 중...

"%VENV_PYTHON%" -m pip --version >nul 2>&1
if errorlevel 1 (
    "%VENV_PYTHON%" -m ensurepip --upgrade
    if errorlevel 1 (
        echo.
        echo [오류] pip 설치에 실패했습니다.
        pause
        exit /b 1
    )
)

"%VENV_PYTHON%" -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo [오류] pip 업그레이드에 실패했습니다.
    echo 인터넷 연결을 확인한 뒤 다시 실행하세요.
    pause
    exit /b 1
)

echo.
echo [3/5] 프로젝트 패키지 설치 중...

if not exist "requirements.txt" (
    echo.
    echo [오류] requirements.txt를 찾을 수 없습니다.
    pause
    exit /b 1
)

"%VENV_PYTHON%" -m pip install -r "requirements.txt"
if errorlevel 1 (
    echo.
    echo [오류] 프로젝트 패키지 설치에 실패했습니다.
    echo 인터넷 연결과 위 오류 메시지를 확인하세요.
    pause
    exit /b 1
)

echo.
echo [4/5] 최신 기사 데이터 수집 및 토픽 생성 중...

if not exist "data" (
    mkdir "data"
)

if not exist "fetch_articles.py" (
    echo.
    echo [오류] fetch_articles.py를 찾을 수 없습니다.
    pause
    exit /b 1
)

if not exist "group_topics.py" (
    echo.
    echo [오류] group_topics.py를 찾을 수 없습니다.
    pause
    exit /b 1
)

echo 최신 기사를 수집합니다.
"%VENV_PYTHON%" "fetch_articles.py"

if errorlevel 1 (
    echo.
    echo [오류] 기사 수집에 실패했습니다.
    pause
    exit /b 1
)

echo.
echo 수집한 기사 기준으로 토픽을 재생성합니다.
"%VENV_PYTHON%" "group_topics.py"

if errorlevel 1 (
    echo.
    echo [오류] 토픽 생성에 실패했습니다.
    pause
    exit /b 1
)

echo.
echo [5/5] Flask 웹서비스 실행 중...

if not exist "app.py" (
    echo.
    echo [오류] app.py를 찾을 수 없습니다.
    pause
    exit /b 1
)

echo.
echo 접속 주소: http://127.0.0.1:5000/
echo 종료하려면 Ctrl+C를 누르세요.
echo ============================================================
echo.

set "AI_ENABLED=false"
set "SWNN_ENABLED=false"

start "" "http://127.0.0.1:5000"
"%VENV_PYTHON%" "app.py"
set "APP_EXIT_CODE=%ERRORLEVEL%"

if not "%APP_EXIT_CODE%"=="0" (
    echo.
    echo [오류] Flask 앱이 종료되었습니다. 종료 코드: %APP_EXIT_CODE%
)

pause
exit /b %APP_EXIT_CODE%