# python -m venv venv
# .\venv\Scripts\Activate.ps1
# pip install -r requirements.txt
# python app.py
# http://localhost:5000

#qwen2.5:3b (ollama 모델 이름)

import json
import os
import re
import requests

from flask import Flask, render_template, request, jsonify


app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")


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

def extract_keywords(question):
    text = question.lower()

    # 너무 흔한 단어 제거
    stopwords = {
        "스타워즈", "마블", "영화", "작품", "기사", "소식",
        "보고", "싶어", "보고싶어", "추천", "알려줘", "뭐", "있어",
        "the", "a", "an", "star", "wars", "marvel"
    }

    # 한글/영문/숫자 단어 추출
    words = re.findall(r"[가-힣A-Za-z0-9]+", text)

    keywords = []

    for word in words:
        if len(word) < 2:
            continue

        if word in stopwords:
            continue

        keywords.append(word)

    return keywords


def score_item_by_question(item, question, fields):
    question_lower = question.lower()
    keywords = extract_keywords(question)

    text_parts = []

    for field in fields:
        value = item.get(field, "")
        if value:
            text_parts.append(str(value).lower())

    item_text = " ".join(text_parts)

    score = 0

    # 전체 질문 문자열 일부가 포함되면 가산
    if question_lower and question_lower in item_text:
        score += 5

    # 키워드별 점수
    for keyword in keywords:
        if keyword in item_text:
            score += 2

    return score


def find_related_articles(question, franchise, limit=3):
    articles = load_json("articles.json")
    selected_franchise_name = get_selected_franchise_name(franchise)

    candidates = []

    for article in articles:
        if article.get("franchise", "Star Wars") != selected_franchise_name:
            continue

        score = score_item_by_question(
            item=article,
            question=question,
            fields=[
                "title",
                "title_ko",
                "summary",
                "summary_ko",
                "source_name",
                "category"
            ]
        )

        if score > 0:
            candidates.append((score, article))

    candidates.sort(
        key=lambda pair: (
            pair[0],
            pair[1].get("published_at", "")
        ),
        reverse=True
    )

    return [article for score, article in candidates[:limit]]

def detect_question_intent(question):
    question_lower = question.lower()

    upcoming_keywords = [
        "개봉 예정",
        "공개 예정",
        "예정작",
        "앞으로 나올",
        "나올 작품",
        "출시 예정",
        "upcoming"
    ]

    watch_keywords = [
        "보고 싶",
        "어디서 봐",
        "보러 가",
        "감상",
        "시청",
        "볼 수",
        "watch"
    ]

    news_keywords = [
        "소식",
        "뉴스",
        "기사",
        "최근",
        "정보",
        "news"
    ]

    if any(keyword in question_lower for keyword in upcoming_keywords):
        return "upcoming"

    if any(keyword in question_lower for keyword in watch_keywords):
        return "watch"

    if any(keyword in question_lower for keyword in news_keywords):
        return "news"

    return "general"


def find_related_works(question, franchise, limit=3):
    works_data = load_json("works.json")
    selected_franchise_name = get_selected_franchise_name(franchise)
    intent = detect_question_intent(question)

    candidates = []

    for work in works_data:
        if work.get("franchise", "Star Wars") != selected_franchise_name:
            continue

        # 개봉 예정작 질문이면 Upcoming 작품을 우선적으로 반환
        if intent == "upcoming":
            if work.get("status") == "Upcoming":
                candidates.append((100, prepare_work(work)))
            continue

        score = score_item_by_question(
            item=work,
            question=question,
            fields=[
                "title",
                "type",
                "status",
                "description",
                "release_date"
            ]
        )

        if score > 0:
            candidates.append((score, prepare_work(work)))

    candidates.sort(
        key=lambda pair: (
            pair[0],
            pair[1].get("release_date", "")
        ),
        reverse=True
    )

    return [work for score, work in candidates[:limit]]

def build_ai_context(articles, works):
    context_lines = []

    if articles:
        context_lines.append("[관련 기사]")
        for idx, article in enumerate(articles, start=1):
            title = article.get("title_ko") or article.get("title") or "제목 없음"
            summary = article.get("summary_ko") or article.get("summary") or ""
            source = article.get("source_name", "")
            published_at = article.get("published_at", "")
            url = article.get("source_url", "")

            context_lines.append(
                f"{idx}. 제목: {title}\n"
                f"   출처: {source}\n"
                f"   날짜: {published_at}\n"
                f"   요약: {summary}\n"
                f"   링크: {url}"
            )

    if works:
        context_lines.append("\n[관련 작품]")
        for idx, work in enumerate(works, start=1):
            title = work.get("title", "제목 없음")
            work_type = work.get("type", "")
            release_date = work.get("release_date", "")
            status = work.get("status", "")
            description = work.get("description", "")
            source_url = work.get("source_url", "")

            context_lines.append(
                f"{idx}. 작품명: {title}\n"
                f"   유형: {work_type}\n"
                f"   공개일: {release_date}\n"
                f"   상태: {status}\n"
                f"   설명: {description}\n"
                f"   링크: {source_url}"
            )

    if not context_lines:
        return "현재 아카이브에서 직접적으로 관련된 기사나 작품 데이터를 찾지 못했습니다."

    return "\n".join(context_lines)


def ask_ollama(question, articles, works):
    context = build_ai_context(articles, works)

    prompt = f"""
너는 Holocron Archive 웹사이트의 AI 도우미다.
사용자는 스타워즈나 마블 같은 유명 프랜차이즈의 기사, 작품 정보, 감상 방법을 질문한다.

규칙:
1. 반드시 한국어로 답한다.
2. 아래 제공된 아카이브 데이터 안에서만 답한다.
3. 데이터에 없는 내용을 확정적으로 지어내지 않는다.
4. 관련 기사가 있으면 기사 제목과 핵심 내용을 안내한다.
5. 관련 작품이 있으면 작품명, 공개일, 보는 방법을 안내한다.
6. 사용자가 작품을 보고 싶다고 하면 작품 링크나 Disney+ / 예매 사이트로 이동하라고 안내한다.
7. 답변은 너무 길지 않게 5~8문장 정도로 한다.
8. 사용자가 개봉 예정작을 물어보면 status가 Upcoming인 작품만 개봉 예정작으로 안내한다.
9. status가 Released인 작품은 개봉 예정작이라고 말하지 않는다.

[사용자 질문]
{question}

[아카이브 데이터]
{context}
"""

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=60
        )

        response.raise_for_status()
        data = response.json()

        return data.get("response", "").strip()

    except requests.exceptions.RequestException:
        return (
            "Ollama 서버에 연결할 수 없습니다. "
            "AI 도우미 기능을 사용하려면 터미널에서 "
            f"`ollama run {OLLAMA_MODEL}`을 먼저 실행해 주세요."
        )


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

@app.route("/api/assistant", methods=["POST"])
def ai_assistant():
    data = request.get_json(silent=True) or {}

    question = data.get("question", "").strip()
    franchise = data.get("franchise", "starwars")

    if not question:
        return jsonify({
            "answer": "질문을 입력해 주세요.",
            "articles": [],
            "works": []
        })

    intent = detect_question_intent(question)

    related_works = find_related_works(question, franchise)

    if intent == "upcoming":
        related_articles = []
    else:
        related_articles = find_related_articles(question, franchise)

    answer = ask_ollama(
        question=question,
        articles=related_articles,
        works=related_works
    )

    article_links = []

    for article in related_articles:
        article_links.append({
            "title": article.get("title_ko") or article.get("title"),
            "url": article.get("source_url"),
            "source_name": article.get("source_name"),
            "published_at": article.get("published_at")
        })

    work_links = []

    for work in related_works:
        work_links.append({
            "title": work.get("title"),
            "type": work.get("type"),
            "release_date": work.get("release_date"),
            "status": work.get("status"),
            "source_url": work.get("source_url"),
            "is_theater_release": work.get("is_theater_release", False),
            "theater_urls": work.get("theater_urls", {})
        })

    return jsonify({
        "answer": answer,
        "articles": article_links,
        "works": work_links
    })


if __name__ == "__main__":
    app.run(debug=True)