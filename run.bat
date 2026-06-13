@echo off
chcp 65001 > nul

echo ============================================================
echo Holocron Archive 실행 스크립트
echo ============================================================

cd /d "%~dp0"

echo.
echo [1/5] Python 가상환경 확인 중...

if not exist venv (
    echo 가상환경이 없습니다. 새로 생성합니다.
    python -m venv venv
) else (
    echo 기존 가상환경을 사용합니다.
)

echo.
echo [2/5] 가상환경 활성화 중...
call venv\Scripts\activate.bat

echo.
echo [3/5] 필요한 패키지 설치 중...
python -m pip install -r requirements.txt

echo.
echo [4/5] Ollama 실행 확인 중...

set OLLAMA_MODEL=qwen2.5:3b

where ollama >nul 2>nul

if %errorlevel%==0 (
    echo Ollama가 설치되어 있습니다.
    echo AI 도우미용 모델을 실행합니다: %OLLAMA_MODEL%
    start "Ollama AI Model" cmd /k "ollama run %OLLAMA_MODEL%"
) else (
    echo Ollama가 설치되어 있지 않습니다.
    echo 기본 웹서비스는 실행되지만 AI 도우미 기능은 사용할 수 없습니다.
)

echo.
echo [5/5] Flask 웹서버 실행 중...

timeout /t 3 > nul

start "" "http://127.0.0.1:5000"

python app.py

pause