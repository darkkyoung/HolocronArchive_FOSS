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
echo [4/5] 뉴스 데이터 갱신 중...
python fetch_articles.py
python group_topics.py

echo.
echo [5/5] Flask 웹서버 실행 중...

timeout /t 2 > nul

start "" "http://127.0.0.1:5000"

python app.py

pause