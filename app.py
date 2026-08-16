# .\run.bat

#qwen2.5:3b (ollama 모델 이름)

#git 에러 발생 시 : git pull foss main --allow-unrelated-histories

import json
import os
import re
import subprocess
import sys
import requests

from flask import Flask, render_template, request, jsonify, redirect, url_for, session


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "holocron-archive-dev-secret-key")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

ADMIN_ID = os.environ.get("ADMIN_ID", "skywalker0805")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "1234")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:3b")
AI_ENABLED = os.environ.get("AI_ENABLED", "false").lower() == "true"


def load_json(filename):
    path = os.path.join(DATA_DIR, filename)

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_json_or_default(filename, default_value):
    path = os.path.join(DATA_DIR, filename)

    if not os.path.exists(path):
        return default_value

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default_value


def save_json(filename, data):
    os.makedirs(DATA_DIR, exist_ok=True)

    path = os.path.join(DATA_DIR, filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def normalize_url_for_admin(url):
    """
    관리자 제외/복구 비교용 URL 정규화 함수.
    """
    if not url:
        return ""

    url = url.strip()
    url = url.split("?")[0]
    url = url.split("#")[0]
    url = url.rstrip("/")

    return url


def load_article_overrides():
    overrides = load_json_or_default(
        "article_overrides.json",
        {
            "excluded_article_urls": [],
            "manual_topic_merges": [],
            "representative_article_urls": {},
            "pinned_top_article_urls": [],
            "hidden_top_article_urls": [],
            "restored_auto_excluded_urls": []
        }
    )

    if "restored_auto_excluded_urls" not in overrides:
        overrides["restored_auto_excluded_urls"] = []

    if "excluded_article_urls" not in overrides:
        overrides["excluded_article_urls"] = []

    if "manual_topic_merges" not in overrides:
        overrides["manual_topic_merges"] = []

    if "representative_article_urls" not in overrides:
        overrides["representative_article_urls"] = {}

    if "pinned_top_article_urls" not in overrides:
        overrides["pinned_top_article_urls"] = []

    if "hidden_top_article_urls" not in overrides:
        overrides["hidden_top_article_urls"] = []

    return overrides


def save_article_overrides(overrides):
    save_json("article_overrides.json", overrides)


def is_admin_logged_in():
    return session.get("is_admin") is True


def require_admin():
    if not is_admin_logged_in():
        return redirect(url_for("admin_login"))

    return None


def is_ai_enabled():
    return AI_ENABLED


def load_auto_excluded_articles():
    return load_json_or_default("auto_excluded_articles.json", [])


def save_auto_excluded_articles(articles):
    save_json("auto_excluded_articles.json", articles)


def save_fetched_articles(articles):
    save_json("fetched_articles.json", articles)


def collect_article_urls_from_topic(topic):
    """
    topic 안에 포함된 모든 기사 URL을 정규화해서 반환한다.
    수동 병합 기록 저장에 사용한다.
    """
    article_urls = []

    for article in topic.get("articles", []):
        article_url = normalize_url_for_admin(
            article.get("source_url") or article.get("url")
        )

        if article_url:
            article_urls.append(article_url)

    return article_urls


def annotate_topics_with_top_override_info(topics):
    """
    관리자 화면에서 topic별 TOP 고정/제외 상태를 보여주기 위해
    topic에 admin_is_pinned_top, admin_is_hidden_top 값을 붙인다.
    """
    overrides = load_article_overrides()

    pinned_urls = set(
        normalize_url_for_admin(url)
        for url in overrides.get("pinned_top_article_urls", [])
    )

    hidden_urls = set(
        normalize_url_for_admin(url)
        for url in overrides.get("hidden_top_article_urls", [])
    )

    for topic in topics:
        topic_urls = set(collect_article_urls_from_topic(topic))

        topic["admin_is_pinned_top"] = bool(topic_urls.intersection(pinned_urls))
        topic["admin_is_hidden_top"] = bool(topic_urls.intersection(hidden_urls))

    return topics


def build_manual_merge_list():
    """
    article_overrides.json에 저장된 수동 병합 목록을
    관리자 화면에서 보기 좋게 정리한다.
    """
    overrides = load_article_overrides()
    manual_merges = overrides.get("manual_topic_merges", [])

    articles = load_json_or_default("fetched_articles.json", [])

    article_map = {}

    for article in articles:
        article_url = normalize_url_for_admin(
            article.get("source_url") or article.get("url")
        )

        if article_url:
            article_map[article_url] = article

    merge_list = []

    for merge in manual_merges:
        merge_id = merge.get("merge_id", "")
        article_urls = merge.get("article_urls", [])

        merge_articles = []

        for url in article_urls:
            normalized_url = normalize_url_for_admin(url)

            if normalized_url in article_map:
                merge_articles.append(article_map[normalized_url])

        merge_list.append({
            "merge_id": merge_id,
            "article_count": len(merge_articles),
            "articles": merge_articles
        })

    return merge_list

def build_manual_merge_url_map():
    """
    수동 병합에 포함된 기사 URL이 어떤 merge_id에 속하는지 맵으로 만든다.
    index.html에서 기사별로 '병합에서 빼기' 버튼을 보여주기 위해 사용한다.
    """
    overrides = load_article_overrides()
    manual_merges = overrides.get("manual_topic_merges", [])

    merge_url_map = {}

    for merge in manual_merges:
        merge_id = merge.get("merge_id", "")

        for url in merge.get("article_urls", []):
            normalized_url = normalize_url_for_admin(url)

            if normalized_url:
                merge_url_map[normalized_url] = merge_id

    return merge_url_map


def annotate_topics_with_manual_merge_info(topics):
    """
    topic 안의 각 article에 수동 병합 정보(_manual_merge_id)를 임시로 붙인다.
    템플릿에서 수동 병합 기사인지 판단하는 용도다.
    """
    merge_url_map = build_manual_merge_url_map()

    if not merge_url_map:
        return topics

    for topic in topics:
        for article in topic.get("articles", []):
            article_url = normalize_url_for_admin(
                article.get("source_url") or article.get("url")
            )

            if article_url in merge_url_map:
                article["_manual_merge_id"] = merge_url_map[article_url]

    return topics


def regenerate_topics():
    """
    현재 fetched_articles.json과 article_overrides.json을 기준으로 topics.json을 다시 생성한다.
    """
    result = subprocess.run(
        [sys.executable, "group_topics.py"],
        cwd=BASE_DIR,
        check=False
    )

    return result.returncode == 0


def update_news_data():
    """
    기사 수집 후 topic 재생성.
    관리자 페이지의 '뉴스 갱신' 버튼에서 사용한다.
    """
    fetch_result = subprocess.run(
        [sys.executable, "fetch_articles.py", "--fast"],
        cwd=BASE_DIR,
        check=False
    )

    if fetch_result.returncode != 0:
        return False

    return regenerate_topics()


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

def expand_korean_keyword(keyword):
    """
    한국어 검색어를 영어 키워드 후보로 확장한다.
    영어 기사 제목만 있어도 기본적인 한국어 검색이 가능하게 한다.
    """
    if not keyword:
        return []

    keyword = keyword.lower().strip()

    keyword_map = {
        "게임": ["game", "games", "gaming", "gameplay", "interactive", "zero company", "galactic racer"],
        "영화": ["movie", "film", "films", "the mandalorian and grogu"],
        "드라마": ["series", "season", "show", "episode"],
        "애니": ["animation", "anime", "visions", "ninth jedi"],
        "애니메이션": ["animation", "anime", "visions", "ninth jedi"],
        "도서": ["book", "novel", "comic", "legacy"],
        "코믹스": ["comic", "comics"],
        "만달로리안": ["mandalorian", "mando"],
        "만도": ["mando", "mandalorian"],
        "그로구": ["grogu"],
        "제다이": ["jedi"],
        "나인스": ["ninth jedi"],
        "나인스 제다이": ["ninth jedi"],
        "비전스": ["visions"],
        "시스": ["sith"],
        "아소카": ["ahsoka"],
        "안도르": ["andor"],
        "쓰론": ["thrawn"],
        "보바": ["boba"],
        "몰": ["maul"],
        "레거시": ["legacy"],
        "제로": ["zero company"],
        "제로 컴퍼니": ["zero company"],
        "갤럭틱": ["galactic racer"],
        "갤럭틱 레이서": ["galactic racer"],
        "셀러브레이션": ["celebration"],
        "공식": ["official", "starwars.com"],
        "루머": ["rumor", "reportedly", "reported"],
    }

    expanded = [keyword]

    for korean_word, english_words in keyword_map.items():
        if korean_word in keyword:
            expanded.extend(english_words)

    return expanded

def filter_topics(topics, franchise="starwars", keyword="", category=""):
    filtered_topics = []

    for topic in topics:
        articles = topic.get("articles", [])

        # 프랜차이즈 필터
        if franchise:
            franchise_matched = any(
                article.get("franchise", "").lower().replace(" ", "") == franchise.lower().replace(" ", "")
                for article in articles
            )
            if not franchise_matched:
                continue

        # 카테고리 필터
        if category:
            category_matched = any(
                article.get("category") == category
                for article in articles
            )
            if not category_matched:
                continue

        # 검색어 필터
        if keyword:
            search_keywords = expand_korean_keyword(keyword)

            topic_text = " ".join([
                topic.get("topic_title", ""),
                topic.get("topic_summary", ""),
                topic.get("label", ""),
                " ".join(topic.get("sources", []))
            ]).lower()

            article_text = " ".join(
                [
                    " ".join([
                        article.get("title", ""),
                        article.get("title_ko", ""),
                        article.get("summary", ""),
                        article.get("summary_ko", ""),
                        article.get("source_name", ""),
                        article.get("category", "")
                    ])
                    for article in articles
                ]
            ).lower()

            combined_text = topic_text + " " + article_text

            if not any(search_word in combined_text for search_word in search_keywords):
                continue

        filtered_topics.append(topic)

    return filtered_topics


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


def extract_json_from_ai_response(text):
    """
    Ollama 응답에서 JSON 부분만 안전하게 추출한다.
    모델이 앞뒤 설명을 붙이는 경우를 대비한다.
    """
    if not text:
        return {}

    text = text.strip()

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, re.DOTALL)

    if not match:
        return {}

    try:
        return json.loads(match.group(0))
    except Exception:
        return {}

def clean_ai_summary_text(text):
    """
    Ollama가 요약 앞뒤에 붙일 수 있는 불필요한 표현을 정리한다.
    """
    if not text:
        return ""

    text = text.strip()
    text = text.strip('"').strip("'").strip()

    remove_prefixes = [
        "요약:",
        "한국어 요약:",
        "핵심 요약:",
        "summary_ko:",
        "Summary:",
        "-",
    ]

    for prefix in remove_prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):].strip()

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if lines:
        text = lines[0]

    # 너무 길게 나온 경우 120자 선에서 자름
    if len(text) > 120:
        text = text[:120].strip() + "..."

    return text


def generate_korean_summary_with_ollama(article):
    """
    기사 1개의 제목/원문 요약을 바탕으로
    한국어 핵심 요약 1문장만 생성한다.
    제목은 번역하지 않는다.
    """
    title = article.get("title", "").strip()
    summary = article.get("summary", "").strip()
    source_name = article.get("source_name", "").strip()

    if not title and not summary:
        return ""

    prompt = f"""
너는 스타워즈 뉴스 큐레이션 웹사이트의 한국어 요약 에디터다.
아래 영어 기사 정보를 바탕으로 한국어 핵심 요약 1문장을 작성해라.

중요 규칙:
1. 반드시 한국어 1문장만 출력한다.
2. 제목을 번역하지 말고, 기사 내용의 핵심만 요약한다.
3. 기사에 없는 사실을 추가하지 않는다.
4. 80자 이내로 쓴다.
5. 설명, 따옴표, JSON, 마크다운 없이 요약 문장만 출력한다.
6. 원문 요약이 부족하면 제목에 근거해서만 조심스럽게 요약한다.

[기사 정보]
제목: {title}
원문 요약: {summary}
출처: {source_name}
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

        ai_text = data.get("response", "").strip()
        return clean_ai_summary_text(ai_text)

    except requests.exceptions.RequestException as e:
        print(f"Ollama 요약 생성 실패: {title} / {e}")
        return ""


def generate_korean_summaries_for_articles(limit=100, force=False):
    """
    fetched_articles.json에서 summary_ko만 생성한다.

    force=False:
    - summary_ko가 이미 있으면 건너뜀

    force=True:
    - 기존 summary_ko가 있어도 다시 생성
    """
    articles = load_json_or_default("fetched_articles.json", [])

    updated_count = 0
    skipped_count = 0
    failed_count = 0

    for article in articles:
        if updated_count >= limit:
            break

        has_summary_ko = bool(article.get("summary_ko", "").strip())

        if not force and has_summary_ko:
            skipped_count += 1
            continue

        print(f"AI 요약 생성 중: {article.get('title', '')}")

        summary_ko = generate_korean_summary_with_ollama(article)

        if not summary_ko:
            failed_count += 1
            continue

        article["summary_ko"] = summary_ko
        updated_count += 1

    save_fetched_articles(articles)

    print(
        f"AI 요약 생성 완료: 생성 {updated_count}개, "
        f"건너뜀 {skipped_count}개, 실패 {failed_count}개"
    )

    return {
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "failed_count": failed_count
    }


@app.route("/")
def index():
    keyword = request.args.get("keyword", "")
    category = request.args.get("category", "")
    franchise = request.args.get("franchise", "starwars")

    requested_admin_mode = request.args.get("admin") == "1"

    if requested_admin_mode and not is_admin_logged_in():
        return redirect(url_for("admin_login"))

    admin_mode = requested_admin_mode and is_admin_logged_in()

    articles = load_json("articles.json")
    articles = filter_articles(
        articles=articles,
        franchise=franchise,
        keyword=keyword,
        category=category
    )

    topics = load_json("topics.json")
    topics = filter_topics(
        topics=topics,
        franchise=franchise,
        keyword=keyword,
        category=category
    )

    if admin_mode:
        topics = annotate_topics_with_manual_merge_info(topics)
        topics = annotate_topics_with_top_override_info(topics)
    

    excluded_articles = []
    manual_topic_merges = []
    auto_excluded_articles = []

    if admin_mode:
        fetched_articles = load_json_or_default("fetched_articles.json", [])
        overrides = load_article_overrides()

        excluded_urls = set(
            normalize_url_for_admin(url)
            for url in overrides.get("excluded_article_urls", [])
        )

        for article in fetched_articles:
            article_url = normalize_url_for_admin(
                article.get("source_url") or article.get("url")
            )

            if article_url in excluded_urls:
                excluded_articles.append(article)

        excluded_articles.sort(
            key=lambda article: article.get("published_at", ""),
            reverse=True
        )

        manual_topic_merges = build_manual_merge_list()

        auto_excluded_articles = load_auto_excluded_articles()
        auto_excluded_articles.sort(
            key=lambda article: article.get("published_at", ""),
            reverse=True
        )

    return render_template(
        "index.html",
        articles=articles,
        topics=topics,
        keyword=keyword,
        selected_category=category,
        selected_franchise=franchise,
        admin_mode=admin_mode,
        excluded_articles=excluded_articles,
        excluded_count=len(excluded_articles),
        manual_topic_merges=manual_topic_merges,
        auto_excluded_articles=auto_excluded_articles,
        auto_excluded_count=len(auto_excluded_articles),
        ai_enabled=is_ai_enabled()
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

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error_message = ""

    if request.method == "POST":
        admin_id = request.form.get("admin_id", "").strip()
        password = request.form.get("password", "").strip()

        if admin_id == ADMIN_ID and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            session["admin_id"] = admin_id
            return redirect(url_for("index", admin=1))

        error_message = "아이디 또는 비밀번호가 올바르지 않습니다."

    return render_template(
        "admin_login.html",
        error_message=error_message
    )


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    session.pop("admin_id", None)

    return redirect(url_for("index"))


@app.route("/admin")
def admin():
    admin_required = require_admin()
    if admin_required:
        return admin_required

    articles = load_json_or_default("fetched_articles.json", [])
    overrides = load_article_overrides()

    excluded_urls = set(
        normalize_url_for_admin(url)
        for url in overrides.get("excluded_article_urls", [])
    )

    visible_articles = []
    excluded_articles = []

    for article in articles:
        article_url = normalize_url_for_admin(
            article.get("source_url") or article.get("url")
        )

        if article_url in excluded_urls:
            excluded_articles.append(article)
        else:
            visible_articles.append(article)

    visible_articles.sort(
        key=lambda article: article.get("published_at", ""),
        reverse=True
    )

    excluded_articles.sort(
        key=lambda article: article.get("published_at", ""),
        reverse=True
    )

    return render_template(
        "admin.html",
        visible_articles=visible_articles,
        excluded_articles=excluded_articles,
        visible_count=len(visible_articles),
        excluded_count=len(excluded_articles),
        total_count=len(articles)
    )


@app.route("/admin/update", methods=["POST"])
def admin_update():
    admin_required = require_admin()
    if admin_required:
        return admin_required

    return_url = request.form.get("return_url") or url_for("admin")

    update_news_data()

    return redirect(return_url)


@app.route("/admin/generate-korean", methods=["POST"])
def admin_generate_korean():
    """
    Ollama로 기사 한국어 요약만 생성한다.
    제목은 원문 영어 제목을 유지한다.
    """
    admin_required = require_admin()
    if admin_required:
        return admin_required

    if not is_ai_enabled():
        return redirect(request.form.get("return_url") or url_for("index", admin=1))

    return_url = request.form.get("return_url") or url_for("index", admin=1)

    limit_text = request.form.get("limit", "100").strip()

    try:
        limit = int(limit_text)
    except ValueError:
        limit = 100

    if limit < 1:
        limit = 1

    if limit > 100:
        limit = 100

    force = request.form.get("force") == "1"

    generate_korean_summaries_for_articles(
        limit=limit,
        force=force
    )

    regenerate_topics()

    return redirect(return_url)


@app.route("/admin/exclude", methods=["POST"])
def admin_exclude_article():
    admin_required = require_admin()
    if admin_required:
        return admin_required

    article_url = normalize_url_for_admin(request.form.get("url", ""))

    if not article_url:
        return redirect(url_for("admin"))

    overrides = load_article_overrides()

    excluded_urls = [
        normalize_url_for_admin(url)
        for url in overrides.get("excluded_article_urls", [])
    ]

    if article_url not in excluded_urls:
        excluded_urls.append(article_url)

    overrides["excluded_article_urls"] = excluded_urls
    save_article_overrides(overrides)

    regenerate_topics()

    return_url = request.form.get("return_url") or url_for("admin")
    return redirect(return_url)


@app.route("/admin/restore", methods=["POST"])
def admin_restore_article():
    admin_required = require_admin()
    if admin_required:
        return admin_required

    article_url = normalize_url_for_admin(request.form.get("url", ""))

    if not article_url:
        return redirect(url_for("admin"))

    overrides = load_article_overrides()

    excluded_urls = [
        normalize_url_for_admin(url)
        for url in overrides.get("excluded_article_urls", [])
    ]

    excluded_urls = [
        url for url in excluded_urls
        if url != article_url
    ]

    overrides["excluded_article_urls"] = excluded_urls
    save_article_overrides(overrides)

    regenerate_topics()

    return_url = request.form.get("return_url") or url_for("admin")
    return redirect(return_url)


@app.route("/admin/restore-auto-excluded", methods=["POST"])
def admin_restore_auto_excluded_article():
    admin_required = require_admin()
    if admin_required:
        return admin_required

    """
    자동 제외된 기사를 수동으로 복구한다.
    - auto_excluded_articles.json에서 제거
    - fetched_articles.json에 추가
    - restored_auto_excluded_urls에 기록
    - topics.json 재생성
    """
    return_url = request.form.get("return_url") or url_for("index", admin=1)
    article_url = normalize_url_for_admin(request.form.get("url", ""))

    if not article_url:
        return redirect(return_url)

    auto_excluded_articles = load_auto_excluded_articles()
    fetched_articles = load_json_or_default("fetched_articles.json", [])

    target_article = None
    remaining_auto_excluded = []

    for article in auto_excluded_articles:
        current_url = normalize_url_for_admin(
            article.get("source_url") or article.get("url")
        )

        if current_url == article_url:
            target_article = article
        else:
            remaining_auto_excluded.append(article)

    if not target_article:
        return redirect(return_url)

    # 자동 제외 라벨을 일반 표시용으로 보정
    target_article["label"] = "수동 복구"
    target_article["source_url"] = article_url
    target_article["url"] = article_url

    existing_urls = set(
        normalize_url_for_admin(article.get("source_url") or article.get("url"))
        for article in fetched_articles
    )

    if article_url not in existing_urls:
        fetched_articles.append(target_article)

    # article_id 재부여
    for idx, article in enumerate(fetched_articles, start=1):
        article["article_id"] = idx

    save_fetched_articles(fetched_articles)
    save_auto_excluded_articles(remaining_auto_excluded)

    overrides = load_article_overrides()

    restored_urls = [
        normalize_url_for_admin(url)
        for url in overrides.get("restored_auto_excluded_urls", [])
    ]

    if article_url not in restored_urls:
        restored_urls.append(article_url)

    overrides["restored_auto_excluded_urls"] = restored_urls
    save_article_overrides(overrides)

    regenerate_topics()

    return redirect(return_url)


@app.route("/admin/merge-topics", methods=["POST"])
def admin_merge_topics():
    admin_required = require_admin()
    if admin_required:
        return admin_required

    return_url = request.form.get("return_url") or url_for("index")
    selected_topic_ids = request.form.getlist("topic_ids")

    if len(selected_topic_ids) < 2:
        return redirect(return_url)

    selected_topic_ids = set(
        int(topic_id)
        for topic_id in selected_topic_ids
        if topic_id.isdigit()
    )

    topics = load_json_or_default("topics.json", [])

    article_urls_to_merge = []

    for topic in topics:
        if int(topic.get("topic_id", 0)) in selected_topic_ids:
            article_urls_to_merge.extend(
                collect_article_urls_from_topic(topic)
            )

    article_urls_to_merge = list(dict.fromkeys(article_urls_to_merge))

    if len(article_urls_to_merge) < 2:
        return redirect(return_url)

    overrides = load_article_overrides()

    manual_merges = overrides.get("manual_topic_merges", [])

    manual_merges.append({
        "merge_id": f"merge_{len(manual_merges) + 1}",
        "article_urls": article_urls_to_merge
    })

    overrides["manual_topic_merges"] = manual_merges
    save_article_overrides(overrides)

    regenerate_topics()

    return redirect(return_url)


@app.route("/admin/unmerge-topic", methods=["POST"])
def admin_unmerge_topic():
    admin_required = require_admin()
    if admin_required:
        return admin_required

    return_url = request.form.get("return_url") or url_for("index", admin=1)
    merge_id = request.form.get("merge_id", "").strip()

    if not merge_id:
        return redirect(return_url)

    overrides = load_article_overrides()

    manual_merges = overrides.get("manual_topic_merges", [])
    excluded_urls = overrides.get("excluded_article_urls", [])

    # 해제할 병합 기록에 포함된 기사 URL들을 먼저 찾는다.
    merge_article_urls = []

    for merge in manual_merges:
        if merge.get("merge_id") == merge_id:
            merge_article_urls = [
                normalize_url_for_admin(url)
                for url in merge.get("article_urls", [])
            ]
            break

    merge_article_url_set = set(merge_article_urls)

    # 1. 병합 기록 삭제
    manual_merges = [
        merge for merge in manual_merges
        if merge.get("merge_id") != merge_id
    ]

    # 2. 해당 병합에 포함됐던 기사들이 제외 목록에 들어가 있다면 복구
    excluded_urls = [
        normalize_url_for_admin(url)
        for url in excluded_urls
    ]

    excluded_urls = [
        url for url in excluded_urls
        if url not in merge_article_url_set
    ]

    overrides["manual_topic_merges"] = manual_merges
    overrides["excluded_article_urls"] = excluded_urls

    save_article_overrides(overrides)

    regenerate_topics()

    return redirect(return_url)


@app.route("/admin/remove-article-from-merge", methods=["POST"])
def admin_remove_article_from_merge():
    """
    수동 병합된 topic에서 특정 기사 1개만 병합 목록에서 제거한다.
    기사를 숨기는 것이 아니라, 자동 분류 대상으로 다시 돌려보내는 기능이다.
    """
    admin_required = require_admin()
    if admin_required:
        return admin_required

    return_url = request.form.get("return_url") or url_for("index", admin=1)

    merge_id = request.form.get("merge_id", "").strip()
    article_url = normalize_url_for_admin(request.form.get("url", ""))

    if not merge_id or not article_url:
        return redirect(return_url)

    overrides = load_article_overrides()
    manual_merges = overrides.get("manual_topic_merges", [])

    updated_merges = []

    for merge in manual_merges:
        if merge.get("merge_id") != merge_id:
            updated_merges.append(merge)
            continue

        article_urls = [
            normalize_url_for_admin(url)
            for url in merge.get("article_urls", [])
        ]

        article_urls = [
            url for url in article_urls
            if url != article_url
        ]

        # 병합 그룹은 최소 2개 이상의 기사가 있을 때만 유지한다.
        # 1개 이하가 되면 수동 병합 기록 자체를 삭제한다.
        if len(article_urls) >= 2:
            merge["article_urls"] = article_urls
            updated_merges.append(merge)

    overrides["manual_topic_merges"] = updated_merges
    save_article_overrides(overrides)

    regenerate_topics()

    return redirect(return_url)


@app.route("/admin/set-representative", methods=["POST"])
def admin_set_representative_article():
    """
    특정 기사를 topic의 대표 기사로 지정한다.
    실제 적용은 group_topics.py가 topics.json을 재생성할 때 반영한다.
    """
    admin_required = require_admin()
    if admin_required:
        return admin_required

    return_url = request.form.get("return_url") or url_for("index", admin=1)
    article_url = normalize_url_for_admin(request.form.get("url", ""))

    if not article_url:
        return redirect(return_url)

    overrides = load_article_overrides()

    representative_article_urls = overrides.get("representative_article_urls", {})

    # 현재는 URL 기반으로 대표 기사 지정 여부를 저장한다.
    representative_article_urls[article_url] = True

    overrides["representative_article_urls"] = representative_article_urls
    save_article_overrides(overrides)

    regenerate_topics()

    return redirect(return_url)


@app.route("/admin/pin-top-topic", methods=["POST"])
def admin_pin_top_topic():
    """
    특정 topic을 TOP 3에 고정한다.
    topic_id는 재생성될 수 있으므로, topic 안의 기사 URL들을 저장한다.
    """
    admin_required = require_admin()
    if admin_required:
        return admin_required

    return_url = request.form.get("return_url") or url_for("index", admin=1)
    topic_id = request.form.get("topic_id", "").strip()

    if not topic_id.isdigit():
        return redirect(return_url)

    topics = load_json_or_default("topics.json", [])
    target_topic = None

    for topic in topics:
        if int(topic.get("topic_id", 0)) == int(topic_id):
            target_topic = topic
            break

    if not target_topic:
        return redirect(return_url)

    topic_urls = collect_article_urls_from_topic(target_topic)

    overrides = load_article_overrides()

    pinned_urls = [
        normalize_url_for_admin(url)
        for url in overrides.get("pinned_top_article_urls", [])
    ]

    hidden_urls = [
        normalize_url_for_admin(url)
        for url in overrides.get("hidden_top_article_urls", [])
    ]

    for url in topic_urls:
        if url not in pinned_urls:
            pinned_urls.append(url)

    # TOP 고정한 topic은 TOP 제외 목록에서는 제거
    hidden_urls = [
        url for url in hidden_urls
        if url not in topic_urls
    ]

    overrides["pinned_top_article_urls"] = pinned_urls
    overrides["hidden_top_article_urls"] = hidden_urls

    save_article_overrides(overrides)
    regenerate_topics()

    return redirect(return_url)


@app.route("/admin/hide-top-topic", methods=["POST"])
def admin_hide_top_topic():
    """
    특정 topic을 TOP 3 후보에서 제외한다.
    전체 이슈 목록에서는 계속 보인다.
    """
    admin_required = require_admin()
    if admin_required:
        return admin_required

    return_url = request.form.get("return_url") or url_for("index", admin=1)
    topic_id = request.form.get("topic_id", "").strip()

    if not topic_id.isdigit():
        return redirect(return_url)

    topics = load_json_or_default("topics.json", [])
    target_topic = None

    for topic in topics:
        if int(topic.get("topic_id", 0)) == int(topic_id):
            target_topic = topic
            break

    if not target_topic:
        return redirect(return_url)

    topic_urls = collect_article_urls_from_topic(target_topic)

    overrides = load_article_overrides()

    pinned_urls = [
        normalize_url_for_admin(url)
        for url in overrides.get("pinned_top_article_urls", [])
    ]

    hidden_urls = [
        normalize_url_for_admin(url)
        for url in overrides.get("hidden_top_article_urls", [])
    ]

    for url in topic_urls:
        if url not in hidden_urls:
            hidden_urls.append(url)

    # TOP 제외한 topic은 TOP 고정 목록에서는 제거
    pinned_urls = [
        url for url in pinned_urls
        if url not in topic_urls
    ]

    overrides["pinned_top_article_urls"] = pinned_urls
    overrides["hidden_top_article_urls"] = hidden_urls

    save_article_overrides(overrides)
    regenerate_topics()

    return redirect(return_url)


@app.route("/admin/clear-top-topic", methods=["POST"])
def admin_clear_top_topic():
    """
    특정 topic의 TOP 고정/제외 설정을 모두 해제한다.
    이후 자동 TOP 3 선정 기준으로 돌아간다.
    """
    admin_required = require_admin()
    if admin_required:
        return admin_required

    return_url = request.form.get("return_url") or url_for("index", admin=1)
    topic_id = request.form.get("topic_id", "").strip()

    if not topic_id.isdigit():
        return redirect(return_url)

    topics = load_json_or_default("topics.json", [])
    target_topic = None

    for topic in topics:
        if int(topic.get("topic_id", 0)) == int(topic_id):
            target_topic = topic
            break

    if not target_topic:
        return redirect(return_url)

    topic_urls = collect_article_urls_from_topic(target_topic)

    overrides = load_article_overrides()

    pinned_urls = [
        normalize_url_for_admin(url)
        for url in overrides.get("pinned_top_article_urls", [])
    ]

    hidden_urls = [
        normalize_url_for_admin(url)
        for url in overrides.get("hidden_top_article_urls", [])
    ]

    pinned_urls = [
        url for url in pinned_urls
        if url not in topic_urls
    ]

    hidden_urls = [
        url for url in hidden_urls
        if url not in topic_urls
    ]

    overrides["pinned_top_article_urls"] = pinned_urls
    overrides["hidden_top_article_urls"] = hidden_urls

    save_article_overrides(overrides)
    regenerate_topics()

    return redirect(return_url)


@app.route("/api/assistant", methods=["POST"])
def ai_assistant():
    if not is_ai_enabled():
        return jsonify({
            "answer": "현재 AI 기능은 비활성화되어 있습니다.",
            "articles": [],
            "works": []
        }), 403

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