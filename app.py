# python -m venv venv → 가상환경 만들기
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser → 파워쉘에서 실행 권한 설정
# .\venv\Scripts\Activate.ps1
# python app.py
# http://localhost:5000

import os

from flask import Flask, render_template, request
import psycopg2
import psycopg2.extras
import pandas as pd


app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE_URL = os.environ.get("DATABASE_URL")


def get_db_connection():
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL)
    else:
        conn = psycopg2.connect(
            host="localhost",
            database="db_project",
            user="postgres",
            password=os.environ.get("DB_PASSWORD", "darkk0729"),
            port=5432
        )
    return conn

def get_value(row, column, default=None):
    value = row[column] if column in row.index else default

    if pd.isna(value):
        return default

    return value


def import_csv_data():
    works_path = os.path.join(BASE_DIR, "data", "works.csv")
    articles_path = os.path.join(BASE_DIR, "data", "articles.csv")

    works_df = pd.read_csv(works_path)
    articles_df = pd.read_csv(articles_path)

    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # 기존 데이터 삭제
        cur.execute("DELETE FROM bookmarks;")
        cur.execute("DELETE FROM notes;")
        cur.execute("DELETE FROM article_tags;")
        cur.execute("DELETE FROM work_articles;")
        cur.execute("DELETE FROM articles;")
        cur.execute("DELETE FROM works;")
        cur.execute("DELETE FROM users;")

        # 기본 사용자 추가
        cur.execute("INSERT INTO users (username) VALUES (%s);", ("test_user",))

        # works.csv import
        for _, row in works_df.iterrows():
            cur.execute("""
                INSERT INTO works (
                    title,
                    type,
                    release_date,
                    status,
                    description,
                    source_url,
                    image_url,
                    franchise
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                get_value(row, "title"),
                get_value(row, "type"),
                get_value(row, "release_date"),
                get_value(row, "status"),
                get_value(row, "description"),
                get_value(row, "source_url"),
                get_value(row, "image_url", ""),
                get_value(row, "franchise", "Star Wars")
            ))

        # articles.csv import
        for _, row in articles_df.iterrows():
            cur.execute("""
                INSERT INTO articles (
                    title,
                    title_ko,
                    source_name,
                    source_url,
                    image_url,
                    published_at,
                    summary,
                    summary_ko,
                    category,
                    franchise
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
            """, (
                get_value(row, "title"),
                get_value(row, "title_ko"),
                get_value(row, "source_name"),
                get_value(row, "source_url"),
                get_value(row, "image_url", ""),
                get_value(row, "published_at"),
                get_value(row, "summary"),
                get_value(row, "summary_ko"),
                get_value(row, "category"),
                get_value(row, "franchise", "Star Wars")
            ))

        conn.commit()

    except Exception as e:
        conn.rollback()
        print("IMPORT 실패:", e)
        raise

    finally:
        cur.close()
        conn.close()


@app.route("/")
def index():
    keyword = request.args.get("keyword", "")
    category = request.args.get("category", "")
    franchise = request.args.get("franchise", "starwars")

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    query = """
        SELECT
            article_id,
            title,
            title_ko,
            source_name,
            source_url,
            image_url,
            published_at,
            summary,
            summary_ko,
            category,
            franchise
        FROM articles
        WHERE 1=1
    """
    params = []

    if franchise == "marvel":
        query += " AND franchise = %s"
        params.append("Marvel")
    else:
        query += " AND franchise = %s"
        params.append("Star Wars")

    if keyword:
        query += """
            AND (
                title ILIKE %s
                OR title_ko ILIKE %s
                OR summary ILIKE %s
                OR summary_ko ILIKE %s
                OR source_name ILIKE %s
            )
        """
        search_keyword = f"%{keyword}%"
        params.extend([
            search_keyword,
            search_keyword,
            search_keyword,
            search_keyword,
            search_keyword
        ])

    if category:
        query += " AND category = %s"
        params.append(category)

    query += " ORDER BY published_at DESC;"

    cur.execute(query, params)
    articles = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "index.html",
        articles=articles,
        keyword=keyword,
        selected_category=category,
        selected_franchise=franchise
    )

@app.route("/works")
def works():
    franchise = request.args.get("franchise", "starwars")
    selected_franchise_name = "Marvel" if franchise == "marvel" else "Star Wars"

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT
            work_id,
            title,
            type,
            release_date,
            status,
            description,
            source_url,
            image_url,
            franchise
        FROM works
        WHERE franchise = %s
        ORDER BY release_date DESC;
    """, (selected_franchise_name,))

    works = [dict(work) for work in cur.fetchall()]

    for work in works:
        news_keyword = work["title"]

        # 기사 검색이 잘 되도록 작품명에서 불필요한 접두어 제거
        news_keyword = news_keyword.replace("Star Wars: ", "")

        # 부제까지 너무 길면 검색 결과가 줄어들 수 있으므로 핵심 제목만 사용
        if " - " in news_keyword:
            news_keyword = news_keyword.split(" - ")[0]

        work["news_keyword"] = news_keyword

        # 극장 상영작 여부
        # 현재 프로토타입에서는 The Mandalorian and Grogu를 극장 예매 대상 작품으로 처리
        work["is_theater_release"] = (
            work["title"] == "Star Wars: The Mandalorian and Grogu"
        )

        # 극장 예매 사이트 URL
        work["theater_urls"] = {
            "CGV": "https://cgv.co.kr/cnm/movieBook/movie",
            "롯데시네마": "https://www.lottecinema.co.kr/NLCHS/Ticketing/Schedule",
            "메가박스": "https://www.megabox.co.kr/booking"
        }

    cur.close()
    conn.close()

    # 1. 가장 가까운 개봉 예정작
    upcoming_work = None
    for work in works:
        if work["status"] == "Upcoming":
            if upcoming_work is None or work["release_date"] < upcoming_work["release_date"]:
                upcoming_work = work

    # 2. 대표 작품: 우선 The Mandalorian and Grogu를 대표작으로 지정
    featured_work = None
    for work in works:
        if work["title"] == "Star Wars: The Mandalorian and Grogu":
            featured_work = work
            break

    # 3. 대표작이 없으면 최신 공개 완료 작품을 대표작으로 사용
    if featured_work is None:
        for work in works:
            if work["status"] == "Released":
                featured_work = work
                break

    # 4. 나머지 작품 목록
    other_works = []
    for work in works:
        if upcoming_work and work["work_id"] == upcoming_work["work_id"]:
            continue
        if featured_work and work["work_id"] == featured_work["work_id"]:
            continue
        other_works.append(work)

    return render_template(
        "works.html",
        upcoming_work=upcoming_work,
        featured_work=featured_work,
        other_works=other_works,
        selected_franchise=franchise
    )


@app.route("/import")
def import_data():
    import_csv_data()
    return "CSV 데이터가 PostgreSQL DB에 import 되었습니다."


if __name__ == "__main__":
    app.run(debug=True)