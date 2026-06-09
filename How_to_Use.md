# StarTrack 프로젝트 사용 방법

이 문서는 StarTrack 프로젝트를 여러 컴퓨터에서 GitHub/GitLab을 통해 가져오고, 실행하고, 수정한 뒤 다시 업로드하는 방법을 정리한 문서입니다.

---

## 1. 프로젝트 기본 정보

### GitHub 저장소

```bash
https://github.com/darkkyoung/starwarsArchive.git
```

### 아주 GitLab 저장소

```bash
https://git.ajou.ac.kr/darkk0729/db-project.git
```

### 로컬 프로젝트 위치 예시

```powershell
D:\아주대\3학년 1학기(2026)\데이터베이스\디비 프로젝트
```

또는 Git Bash 기준:

```bash
/d/아주대/3학년 1학기(2026)/데이터베이스/디비 프로젝트
```

---

## 2. 처음 한 번만 하는 작업: GitHub에서 프로젝트 가져오기

처음 사용하는 컴퓨터에서는 프로젝트를 clone 한다.

### PowerShell 기준

```powershell
cd "D:\아주대\3학년 1학기(2026)\데이터베이스"
git clone https://github.com/darkkyoung/starwarsArchive.git "디비 프로젝트"
cd "디비 프로젝트"
code .
```

이미 같은 이름의 폴더가 있으면 clone이 실패할 수 있다.
그 경우 기존 폴더를 삭제하거나 다른 이름으로 clone한다.

```powershell
git clone https://github.com/darkkyoung/starwarsArchive.git starwarsArchive-copy
```

---

## 3. 매일 작업 시작할 때 하는 일

이미 로컬에 프로젝트 폴더가 있다면 매번 clone하지 않는다.
대신 기존 폴더를 열고 GitHub의 최신 변경사항을 가져온다.

### 1단계: 프로젝트 폴더 열기

```powershell
cd "D:\아주대\3학년 1학기(2026)\데이터베이스\디비 프로젝트"
code .
```

### 2단계: GitHub 최신 내용 가져오기

```powershell
git pull origin main
```

아주 GitLab 기준으로 가져오고 싶다면:

```powershell
git pull ajou main
```

보통은 GitHub를 기준으로 `pull`하면 된다.

---

## 4. 가상환경 설정

GitHub에는 `venv` 폴더가 올라가지 않는다.
따라서 새 컴퓨터에서 처음 프로젝트를 가져오면 가상환경을 다시 만들어야 한다.

### 1단계: 가상환경 생성

```powershell
python -m venv venv
```

만약 `python` 명령어가 안 되면:

```powershell
py -m venv venv
```

### 2단계: PowerShell 실행 정책 임시 허용

PowerShell에서 가상환경 활성화가 막히는 경우 아래 명령어를 먼저 실행한다.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### 3단계: 가상환경 활성화

```powershell
.\venv\Scripts\Activate.ps1
```

성공하면 터미널 앞에 `(venv)`가 붙는다.

예:

```powershell
(venv) PS D:\아주대\3학년 1학기(2026)\데이터베이스\디비 프로젝트>
```

### Git Bash를 사용할 경우

```bash
source venv/Scripts/activate
```

---

## 5. 필요한 패키지 설치

가상환경이 활성화된 상태에서 아래 명령어를 실행한다.

```powershell
pip install -r requirements.txt
```

만약 `requirements.txt`가 없거나 오류가 나면 직접 설치한다.

```powershell
pip install flask psycopg2-binary pandas gunicorn
```

---

## 6. PostgreSQL 설정

이 프로젝트는 PostgreSQL 데이터베이스를 사용한다.

### 1단계: PostgreSQL Server 실행 확인

Windows에서:

```text
Win + R → services.msc
```

서비스 목록에서 아래와 비슷한 이름을 찾는다.

```text
postgresql-x64-18
postgresql-x64-17
postgresql-x64-16
```

상태가 실행 중이 아니면 우클릭 후 **시작**한다.

### 2단계: pgAdmin에서 서버 등록

pgAdmin을 열고:

```text
Servers 우클릭 → Register → Server...
```

General 탭:

```text
Name: startrack
```

Connection 탭:

```text
Host name/address: localhost
Port: 5432
Maintenance database: postgres
Username: postgres
Password: PostgreSQL 설치 시 설정한 비밀번호
```

### 3단계: 데이터베이스 생성

pgAdmin에서:

```text
Databases 우클릭 → Create → Database
```

Database 이름:

```text
db_project
```

### 4단계: 테이블 생성

1. `db_project` 데이터베이스 클릭
2. Query Tool 열기
3. VS Code의 `schema.sql` 내용 전체 복사
4. Query Tool에 붙여넣기
5. 실행 버튼 클릭

생성되어야 하는 테이블:

```text
users
works
articles
work_articles
tags
article_tags
bookmarks
notes
```

---

## 7. app.py 비밀번호 확인

`app.py`에서 PostgreSQL 비밀번호가 현재 컴퓨터의 PostgreSQL 비밀번호와 일치해야 한다.

예:

```python
DB_CONFIG = {
    "host": "localhost",
    "database": "db_project",
    "user": "postgres",
    "password": "내_PostgreSQL_비밀번호",
    "port": 5432
}
```

비밀번호가 다르면 Flask 실행 시 DB 연결 오류가 발생한다.

---

## 8. 서버 실행

프로젝트 루트 폴더에서 가상환경을 활성화한 뒤 실행한다.

```powershell
python app.py
```

정상 실행되면 터미널에 다음과 비슷하게 출력된다.

```text
Running on http://127.0.0.1:5000
```

브라우저에서 접속:

```text
http://localhost:5000
```

또는:

```text
http://127.0.0.1:5000
```

---

## 9. CSV 데이터를 DB에 반영하는 방법

`data/works.csv` 또는 `data/articles.csv`를 수정했다면, 서버 실행 상태에서 아래 주소에 접속한다.

```text
http://localhost:5000/import
```

그러면 CSV 데이터가 PostgreSQL DB에 다시 import 된다.

그 다음 메인 페이지로 이동한다.

```text
http://localhost:5000
```

작품 정보 페이지:

```text
http://localhost:5000/works
```

---

## 10. 매일 작업 끝날 때 GitHub에 올리는 방법

작업이 끝나면 아래 순서대로 진행한다.

### 1단계: 변경사항 확인

```powershell
git status
```

### 2단계: 변경 파일 추가

```powershell
git add .
```

### 3단계: 커밋

커밋 메시지는 작업 내용에 맞게 작성한다.

예:

```powershell
git commit -m "Update Star Wars data"
```

또는:

```powershell
git commit -m "Improve UI design"
```

또는:

```powershell
git commit -m "Add README and usage guide"
```

### 4단계: GitHub에 push

```powershell
git push origin main
```

### 5단계: 아주 GitLab에도 push

```powershell
git push ajou main
```

GitHub와 아주 GitLab 둘 다 올리고 싶으면:

```powershell
git push origin main
git push ajou main
```

---

## 11. 원격 저장소 확인 및 추가

현재 연결된 원격 저장소 확인:

```powershell
git remote -v
```

GitHub 원격 저장소가 없으면 추가:

```powershell
git remote add origin https://github.com/darkkyoung/starwarsArchive.git
```

아주 GitLab 원격 저장소가 없으면 추가:

```powershell
git remote add ajou https://git.ajou.ac.kr/darkk0729/db-project.git
```

이미 remote가 있는데 주소를 바꾸고 싶으면:

```powershell
git remote set-url origin https://github.com/darkkyoung/starwarsArchive.git
```

```powershell
git remote set-url ajou https://git.ajou.ac.kr/darkk0729/db-project.git
```

---

## 12. 절대 GitHub에 올리면 안 되는 것

아래 파일과 폴더는 GitHub에 올리면 안 된다.

```text
venv/
.env
__pycache__/
*.pyc
```

`.gitignore`에 아래 내용이 들어 있어야 한다.

```gitignore
venv/
.env
__pycache__/
*.pyc
.vscode/
.DS_Store
Thumbs.db
```

DB 비밀번호가 들어간 파일은 공개 저장소에 올리지 않는 것이 좋다.

---

## 13. 자주 발생하는 오류

### 1. `ModuleNotFoundError: No module named 'flask'`

가상환경에 Flask가 설치되지 않은 상태이다.

해결:

```powershell
pip install -r requirements.txt
```

또는:

```powershell
pip install flask psycopg2-binary pandas
```

---

### 2. `Activate.ps1 cannot be loaded`

PowerShell 실행 정책 때문에 가상환경 활성화가 막힌 것이다.

해결:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

---

### 3. `psycopg2.OperationalError: connection refused`

PostgreSQL 서버가 실행 중이 아니거나 DB 설정이 잘못된 상태이다.

확인할 것:

* PostgreSQL 서비스가 실행 중인지
* `db_project` 데이터베이스가 있는지
* `schema.sql`을 실행했는지
* `app.py`의 비밀번호가 맞는지
* 포트가 5432인지

---

### 4. `localhost:5000` 접속이 안 됨

Flask 서버가 꺼져 있을 가능성이 크다.

해결:

```powershell
python app.py
```

서버가 실행 중이어야 브라우저에서 접속할 수 있다.

---

## 14. 기본 작업 루틴 요약

### 하루 시작

```powershell
cd "D:\아주대\3학년 1학기(2026)\데이터베이스\디비 프로젝트"
git pull origin main
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
python app.py
```

### CSV 수정 후 반영

```text
http://localhost:5000/import
```

### 하루 종료

```powershell
git status
git add .
git commit -m "Update project"
git push origin main
git push ajou main
```
