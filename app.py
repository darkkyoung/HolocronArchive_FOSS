#python -m venv venv → 가상환경 만들기
#Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser → 파워쉘에서 실행 권한 설정
#.\venv\Scripts\Activate.ps1
#python app.py
#위 두 개 실행하면 다시 로컬 브라우저 볼 수 있음

from flask import Flask, render_template, request
import psycopg2
import pandas as pd

app = Flask(__name__)

import os
from flask import Flask, render_template, request
import psycopg2
import pandas as pd

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

def get_db_connection():
    if DATABASE_URL:
        conn = psycopg2.connect(DATABASE_URL)
    else:
        conn = psycopg2.connect(
            host="localhost",
            database="db_project",
            user="postgres",
            password="darkk0729",
            port=5432
        )
    return conn


def get_db_connection():
    conn = psycopg2.connect(**DB_CONFIG)
    return conn


def import_csv_data():
    conn = get_db_connection()
    cur = conn.cursor()

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
    works_df = pd.read_csv("data/works.csv")

    for _, row in works_df.iterrows():
        cur.execute("""
            INSERT INTO works (title, type, release_date, status, description, source_url)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (
            row["title"],
            row["type"],
            row["release_date"],
            row["status"],
            row["description"],
            row["source_url"]
        ))

    # articles.csv import
    articles_df = pd.read_csv("data/articles.csv")

    for _, row in articles_df.iterrows():
        cur.execute("""
            INSERT INTO articles (title, source_name, source_url, published_at, summary, category)
            VALUES (%s, %s, %s, %s, %s, %s);
        """, (
            row["title"],
            row["source_name"],
            row["source_url"],
            row["published_at"],
            row["summary"],
            row["category"]
        ))

    conn.commit()
    cur.close()
    conn.close()


@app.route("/")
def index():
    keyword = request.args.get("keyword", "")
    category = request.args.get("category", "")

    conn = get_db_connection()
    cur = conn.cursor()

    query = """
        SELECT article_id, title, source_name, published_at, summary, category
        FROM articles
        WHERE 1=1
    """
    params = []

    if keyword:
        query += """
            AND (
                title ILIKE %s
                OR summary ILIKE %s
                OR source_name ILIKE %s
            )
        """
        search_keyword = f"%{keyword}%"
        params.extend([search_keyword, search_keyword, search_keyword])

    if category:
        query += " AND category = %s"
        params.append(category)

    query += " ORDER BY published_at DESC;"

    cur.execute(query, params)
    articles = cur.fetchall()

    cur.execute("""
        SELECT DISTINCT category
        FROM articles
        WHERE category IS NOT NULL
        ORDER BY category;
    """)
    categories = cur.fetchall()

    cur.close()
    conn.close()

    return render_template(
        "index.html",
        articles=articles,
        categories=categories,
        keyword=keyword,
        selected_category=category
    )


@app.route("/works")
def works():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT work_id, title, type, release_date, status, description
        FROM works
        ORDER BY release_date DESC;
    """)

    works = cur.fetchall()

    cur.close()
    conn.close()

    return render_template("works.html", works=works)


@app.route("/import")
def import_data():
    import_csv_data()
    return "CSV 데이터가 PostgreSQL DB에 import 되었습니다."


if __name__ == "__main__":
    app.run(debug=True)