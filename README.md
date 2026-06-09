# StarTrack

StarTrack은 Star Wars 관련 작품 정보와 최신 소식을 제공하는 데이터베이스 기반 큐레이션 웹서비스입니다.  
Star Wars 콘텐츠를 주제로 한 뉴스, 작품 정보, 카테고리 정보를 저장하고, 사용자가 원하는 정보를 검색 및 필터링할 수 있도록 지원합니다.

## 프로젝트 개요

본 프로젝트는 데이터베이스를 사용하는 웹 서비스 프로토타입 개발을 목표로 합니다.  
Star Wars 관련 작품 정보와 최신 소식 데이터를 PostgreSQL에 저장하고, Flask 기반 웹 애플리케이션을 통해 사용자에게 제공합니다.

사용자는 다음 기능을 이용할 수 있습니다.

- 최신 소식 조회
- 작품 정보 조회
- 키워드 검색
- 카테고리 필터링
- CSV 기반 데이터 import
- PostgreSQL 기반 데이터 저장 및 조회

## 주요 기능

### 1. 최신 소식 조회

Star Wars 관련 기사와 소식을 최신순으로 확인할 수 있습니다.

### 2. 작품 정보 조회

영화, 시리즈, 애니메이션 등 Star Wars 작품 정보를 확인할 수 있습니다.

### 3. 검색 기능

사용자가 입력한 키워드를 기준으로 기사 제목, 요약, 출처 정보를 검색할 수 있습니다.

### 4. 카테고리 필터

Movie, Series, Animation 등 카테고리별로 소식을 필터링할 수 있습니다.

### 5. CSV 데이터 import

`data/works.csv`, `data/articles.csv` 파일에 저장된 데이터를 PostgreSQL 데이터베이스로 import할 수 있습니다.

## 프로젝트 구조

```text
starwarsArchive/
├─ app.py
├─ schema.sql
├─ requirements.txt
├─ data/
│  ├─ articles.csv
│  └─ works.csv
├─ static/
│  └─ style.css
├─ templates/
│  ├─ index.html
│  ├─ works.html
│  ├─ article_detail.html
│  └─ bookmarks.html
└─ README.md
