# python -m venv venv
# .\venv\Scripts\Activate.ps1
# pip install -r requirements.txt
# python app.py
# http://localhost:5000

import json
import os

from flask import Flask, render_template, request


app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_selected_franchise_name(franchise):
    if franchise == "marvel":
        return "Marvel"

    return "Star Wars"


def normalize_text(value):
    if value is None:
        return ""

    return str(value).lower()


def filter_articles(articles, franchise, keyword="", category=""):
    selected_franchise_name = get_selected_franchise_name(franchise)

    filtered = []

    for article in articles:
        if article.get("franchise", "Star Wars") != selected_franchise_name:
            continue

        if category and article.get("category") != category:
            continue

        if keyword:
            keyword_lower = keyword.lower()

            searchable_text = " ".join([
                normalize_text(article.get("title")),
                normalize_text(article.get("title_ko")),
                normalize_text(article.get("summary")),
                normalize_text(article.get("summary_ko")),
                normalize_text(article.get("source_name")),
            ])

            if keyword_lower not in searchable_text:
                continue

        filtered.append(article)

    filtered.sort(
        key=lambda article: article.get("published_at", ""),
        reverse=True
    )

    return filtered


def prepare_work(work):
    work = dict(work)

    news_keyword = work.get("title", "")

    # 기사 검색이 잘 되도록 작품명에서 불필요한 접두어 제거
    news_keyword = news_keyword.replace("Star Wars: ", "")

    # 부제까지 너무 길면 검색 결과가 줄어들 수 있으므로 핵심 제목만 사용
    if " - " in news_keyword:
        news_keyword = news_keyword.split(" - ")[0]

    work["news_keyword"] = news_keyword

    # 현재 프로토타입에서는 The Mandalorian and Grogu를 극장 예매 대상 작품으로 처리
    work["is_theater_release"] = (
        work.get("title") == "Star Wars: The Mandalorian and Grogu"
    )

    work["theater_urls"] = {
        "CGV": "https://cgv.co.kr/cnm/movieBook/movie",
        "롯데시네마": "https://www.lottecinema.co.kr/NLCHS/Ticketing/Schedule",
        "메가박스": "https://www.megabox.co.kr/booking"
    }

    return work


def filter_works(works, franchise):
    selected_franchise_name = get_selected_franchise_name(franchise)

    filtered = []

    for work in works:
        # works.json에 franchise가 없으면 Star Wars로 간주
        if work.get("franchise", "Star Wars") != selected_franchise_name:
            continue

        filtered.append(prepare_work(work))

    filtered.sort(
        key=lambda work: work.get("release_date", ""),
        reverse=True
    )

    return filtered


@app.route("/")
def index():
    keyword = request.args.get("keyword", "")
    category = request.args.get("category", "")
    franchise = request.args.get("franchise", "starwars")

    articles = load_json("articles.json")
    articles = filter_articles(
        articles=articles,
        franchise=franchise,
        keyword=keyword,
        category=category
    )

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

    works_data = load_json("works.json")
    works = filter_works(works_data, franchise)

    # 1. 가장 가까운 개봉 예정작
    upcoming_work = None

    for work in works:
        if work.get("status") == "Upcoming":
            if upcoming_work is None or work.get("release_date", "") < upcoming_work.get("release_date", ""):
                upcoming_work = work

    # 2. 대표 작품: 우선 The Mandalorian and Grogu를 대표작으로 지정
    featured_work = None

    for work in works:
        if work.get("title") == "Star Wars: The Mandalorian and Grogu":
            featured_work = work
            break

    # 3. 대표작이 없으면 최신 공개 완료 작품을 대표작으로 사용
    if featured_work is None:
        for work in works:
            if work.get("status") == "Released":
                featured_work = work
                break

    # 4. 나머지 작품 목록
    other_works = []

    for work in works:
        if upcoming_work and work.get("work_id") == upcoming_work.get("work_id"):
            continue

        if featured_work and work.get("work_id") == featured_work.get("work_id"):
            continue

        other_works.append(work)

    return render_template(
        "works.html",
        upcoming_work=upcoming_work,
        featured_work=featured_work,
        other_works=other_works,
        selected_franchise=franchise
    )


if __name__ == "__main__":
    app.run(debug=True)