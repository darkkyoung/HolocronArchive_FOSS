import json
import os
import re
from datetime import datetime
from collections import Counter


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

INPUT_FILE = os.path.join(DATA_DIR, "fetched_articles.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "topics.json")
OVERRIDES_FILE = os.path.join(DATA_DIR, "article_overrides.json")


STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "will", "into",
    "star", "wars", "new", "official", "review", "revealed", "release",
    "releasing", "announced", "gets", "get", "has", "have", "about",
    "after", "before", "more", "first", "look", "watch", "trailer",
    "news", "features", "feature", "story", "still", "remains",
    "스타워즈", "공개", "소식", "기사", "공식", "발표", "새로운"
}


IMPORTANT_PHRASES = [
    "mandalorian",
    "grogu",
    "bad batch",
    "rogue agents",
    "zero company",
    "powerwash simulator",
    "legacy",
    "rey",
    "leia",
    "ahsoka",
    "andor",
    "thrawn",
    "boba fett",
    "lego",
    "jedi",
    "sith",
    "maul",
    "visions",
    "starfighter",
    "old republic",
    "the mandalorian and grogu",
    "star wars the mandalorian and grogu",
    "ninth jedi",
    "the ninth jedi",
    "star wars visions",
    "galactic racer",
    "star wars celebration",
    "father's day",
    "fathers day",
    "razor crest",
    "embo",
    "zeb"
]


def load_articles():
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def normalize_url(url):
    """
    관리자 제외/복구 비교용 URL 정규화 함수.
    쿼리스트링, 앵커, 끝 슬래시 차이를 제거한다.
    """
    if not url:
        return ""

    url = url.strip()
    url = url.split("?")[0]
    url = url.split("#")[0]
    url = url.rstrip("/")

    return url


def load_overrides():
    """
    관리자 수동 수정 기록을 불러온다.
    파일이 없으면 기본 구조를 반환한다.
    """
    default_overrides = {
        "excluded_article_urls": [],
        "manual_topic_merges": [],
        "representative_article_urls": {},
        "pinned_top_article_urls": [],
        "hidden_top_article_urls": []
    }

    if not os.path.exists(OVERRIDES_FILE):
        return default_overrides

    try:
        with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "excluded_article_urls" not in data:
            data["excluded_article_urls"] = []
        
        if "manual_topic_merges" not in data:
            data["manual_topic_merges"] = []

        if "representative_article_urls" not in data:
            data["representative_article_urls"] = {}

        if "pinned_top_article_urls" not in data:
            data["pinned_top_article_urls"] = []

        if "hidden_top_article_urls" not in data:
            data["hidden_top_article_urls"] = []

        return data

    except Exception:
        return default_overrides


def apply_article_overrides(articles):
    """
    관리자 모드에서 제외한 기사를 topic 생성 대상에서 제거한다.
    """
    overrides = load_overrides()

    excluded_urls = set(
        normalize_url(url)
        for url in overrides.get("excluded_article_urls", [])
    )

    if not excluded_urls:
        return articles

    filtered_articles = []

    for article in articles:
        article_url = normalize_url(
            article.get("source_url") or article.get("url")
        )

        if article_url in excluded_urls:
            print(f"관리자 제외 기사 건너뜀: {article.get('title', '')}")
            continue

        filtered_articles.append(article)

    return filtered_articles


def save_topics(topics):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(topics, f, ensure_ascii=False, indent=2)

    print(f"저장 완료: {OUTPUT_FILE}")
    print(f"생성된 topic 수: {len(topics)}")


def normalize_text(text):
    if not text:
        return ""

    text = text.lower()
    text = re.sub(r"[^a-z0-9가-힣\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def extract_keywords(article):
    """
    기사 제목/요약에서 주제 묶기에 사용할 핵심 키워드를 추출한다.
    """
    text_parts = [
    article.get("title", ""),
    article.get("title_ko", "")
    ]  

    text = normalize_text(" ".join(text_parts))

    keywords = set()

    # 1. 중요 구문 우선 추출
    for phrase in IMPORTANT_PHRASES:
        if phrase in text:
            keywords.add(phrase)

    # 2. 일반 단어 추출
    words = text.split()

    for word in words:
        if len(word) < 3:
            continue

        if word in STOPWORDS:
            continue

        # 숫자만 있는 단어 제외
        if word.isdigit():
            continue

        keywords.add(word)

    return keywords


def similarity(keywords_a, keywords_b):
    """
    두 기사 키워드의 유사도를 계산한다.
    Jaccard similarity 기반.
    """
    if not keywords_a or not keywords_b:
        return 0

    intersection = keywords_a.intersection(keywords_b)
    union = keywords_a.union(keywords_b)

    return len(intersection) / len(union)

def article_similarity(article_a, article_b):
    """
    키워드 유사도에 사건 유형과 날짜 차이를 반영한다.
    같은 사건 유형이고 날짜가 2일 이내면 같은 이슈일 가능성을 높게 본다.
    """
    if is_same_news_issue(article_a, article_b):
        return 1.0

    keywords_a = set(article_a.get("_keywords", []))
    keywords_b = set(article_b.get("_keywords", []))

    base_score = similarity(keywords_a, keywords_b)

    event_a = article_a.get("event_type", "general")
    event_b = article_b.get("event_type", "general")

    days = date_diff_days(article_a, article_b)

    # 사건 유형이 같으면 가산점
    if event_a == event_b and event_a != "general":
        base_score += 0.18

    # 날짜가 2일 이내면 가산점
    if days is not None and days <= 2:
        base_score += 0.12

    # 사건 유형이 다르면 너무 쉽게 묶이지 않게 감점
    if event_a != event_b and event_a != "general" and event_b != "general":
        base_score -= 0.18

    # 리뷰/분석/칼럼은 일반 뉴스와 섞이지 않게 감점
    content_a = article_a.get("content_type", "news")
    content_b = article_b.get("content_type", "news")

    if content_a != content_b:
        if "review" in [content_a, content_b] or "analysis" in [content_a, content_b] or "column" in [content_a, content_b]:
            base_score -= 0.20

    return max(base_score, 0)

def is_same_news_issue(article_a, article_b):
    """
    제목 표현은 다르지만 같은 뉴스 이슈인 경우를 보정한다.
    조건:
    - main_entity가 같음
    - 날짜 차이가 0~2일
    - 둘 다 뉴스성 기사
    - 적어도 하나는 공식 출처 또는 발표/출시 계열
    """
    entity_a = article_a.get("main_entity", "")
    entity_b = article_b.get("main_entity", "")

    if not entity_a or not entity_b:
        return False

    if entity_a != entity_b:
        return False

    days = date_diff_days(article_a, article_b)

    if days is None or days > 2:
        return False

    content_a = article_a.get("content_type", "news")
    content_b = article_b.get("content_type", "news")

    # 리뷰/분석/칼럼은 같은 작품이어도 뉴스와 섞지 않음
    non_news_types = ["review", "analysis", "column", "interview"]

    if content_a in non_news_types or content_b in non_news_types:
        return False

    event_a = article_a.get("event_type", "general")
    event_b = article_b.get("event_type", "general")

    source_a = article_a.get("source_name", "")
    source_b = article_b.get("source_name", "")

    has_official = source_a == "StarWars.com" or source_b == "StarWars.com"

    has_news_event = (
        event_a in ["announcement", "release", "trailer", "event"]
        or event_b in ["announcement", "release", "trailer", "event"]
    )

    if has_official and has_news_event:
        return True

    return False


def choose_topic_title(articles):
    """
    topic 대표 제목을 선택한다.
    제목은 원문 영어 제목을 유지한다.
    """
    official_articles = [
        article for article in articles
        if article.get("source_name") == "StarWars.com"
    ]

    if official_articles:
        official_articles.sort(
            key=lambda article: article.get("published_at", ""),
            reverse=True
        )
        return official_articles[0].get("title", "Untitled Topic")

    articles.sort(
        key=lambda article: article.get("published_at", ""),
        reverse=True
    )

    return articles[0].get("title", "Untitled Topic")


def choose_topic_label(articles):
    labels = [article.get("label", "") for article in articles]

    if "공식" in labels:
        return "공식 포함"

    if any("루머" in label for label in labels):
        return "루머/보도"

    if any("인터뷰" in label for label in labels):
        return "인터뷰/코멘터리"

    return "일반 보도"

def detect_content_type(article):
    """
    기사 제목을 기준으로 뉴스/리뷰/분석/칼럼/인터뷰를 구분한다.
    """
    title = article.get("title", "").lower()

    if any(keyword in title for keyword in [
        "review",
    ]):
        return "review"

    if any(keyword in title for keyword in [
        "breakdown", "explained", "analysis"
    ]):
        return "analysis"

    if any(keyword in title for keyword in [
        "character spotlight", "this week", "who is", "gift guide", "father figures"
    ]):
        return "column"

    if any(keyword in title for keyword in [
        "interview", "talk", "creators talk", "filmmaker interview"
    ]):
        return "interview"

    return "news"


def detect_event_type(article):
    """
    기사 제목을 기준으로 사건 유형을 분류한다.
    같은 작품명이라도 trailer/release/review/interview 등은 다른 topic으로 분리하기 위함.
    """
    title = article.get("title", "").lower()

    if any(keyword in title for keyword in [
        "trailer", "teaser", "preview", "gameplay trailer", "story trailer"
    ]):
        return "trailer"

    if any(keyword in title for keyword in [
        "announced", "officially announced", "confirmed", "revealed", "debut"
    ]):
        return "announcement"

    if any(keyword in title for keyword in [
        "release date", "releasing", "available", "buy on digital", "blu-ray", "4k ultra hd", "launch"
    ]):
        return "release"

    if any(keyword in title for keyword in [
        "review"
    ]):
        return "review"

    if any(keyword in title for keyword in [
        "breakdown", "explained", "analysis"
    ]):
        return "analysis"

    if any(keyword in title for keyword in [
        "interview", "talk", "creators talk", "filmmaker interview"
    ]):
        return "interview"

    if any(keyword in title for keyword in [
        "celebration", "d23", "comic-con", "anime expo"
    ]):
        return "event"

    return "general"

def detect_main_entity(article):
    """
    기사 제목에서 핵심 대상/작품명을 감지한다.
    같은 작품이어도 사건 유형이 다르면 나중에 event_type으로 분리한다.
    """
    title = article.get("title", "").lower()

    if "lego star wars" in title and "mandalorian" in title:
        return "lego_star_wars_the_mandalorian"

    if "mando and grogu" in title and "lego star wars" in title:
        return "lego_star_wars_the_mandalorian"

    if "the mandalorian and grogu" in title:
        return "the_mandalorian_and_grogu"

    if "ninth jedi" in title:
        return "the_ninth_jedi"

    if "galactic racer" in title:
        return "galactic_racer"

    if "zero company" in title:
        return "zero_company"

    if "powerwash simulator" in title and "star wars" in title:
        return "powerwash_simulator_star_wars"

    return ""


def parse_date(date_text):
    """
    YYYY-MM-DD 문자열을 datetime으로 변환한다.
    날짜가 없거나 잘못된 경우 None 반환.
    """
    if not date_text:
        return None

    try:
        return datetime.strptime(date_text, "%Y-%m-%d")
    except Exception:
        return None


def date_diff_days(article_a, article_b):
    """
    두 기사 발행일 차이를 일 단위로 계산한다.
    둘 중 하나라도 날짜가 없으면 None 반환.
    """
    date_a = parse_date(article_a.get("published_at", ""))
    date_b = parse_date(article_b.get("published_at", ""))

    if not date_a or not date_b:
        return None

    return abs((date_a - date_b).days)

def calculate_importance(articles):
    """
    TOP 3 선정용 중요도 점수.
    조회수 데이터가 없으므로 복수 출처, 관련 기사 수, 공식 출처 포함 여부를 기준으로 계산한다.
    단, 리뷰/분석/칼럼성 글은 TOP 3에서 불리하게 처리한다.
    """
    source_count = len(set(article.get("source_name", "") for article in articles))
    article_count = len(articles)

    has_official = any(
        article.get("source_name") == "StarWars.com"
        for article in articles
    )

    content_types = [article.get("content_type", "news") for article in articles]

    score = 0

    # 여러 출처가 다룬 주제를 가장 중요하게 평가
    score += source_count * 100

    # 같은 주제 관련 기사 수
    score += article_count * 20

    # 공식 출처 포함 시 가산점
    if has_official:
        score += 30

    # 리뷰/분석/칼럼성 글은 TOP 3에서 후순위
    if all(content_type in ["review", "analysis", "column"] for content_type in content_types):
        score -= 80

    # 일반 뉴스가 하나라도 있으면 유지
    if any(content_type == "news" for content_type in content_types):
        score += 20

    return score


def choose_representative_article(articles):
    """
    topic 카드에 대표로 보여줄 기사 1개를 선택한다.

    우선순위:
    1. 관리자가 수동 지정한 대표 기사
    2. 발행일이 가장 빠른 기사
    3. 이미지가 있는 기사
    4. 첫 번째 기사
    """
    if not articles:
        return {}

    overrides = load_overrides()
    representative_map = overrides.get("representative_article_urls", {})

    article_urls = [
        normalize_url(article.get("source_url") or article.get("url"))
        for article in articles
    ]

    article_url_set = set(article_urls)

    # representative_article_urls 구조:
    # {
    #   "대표기사URL": true
    # }
    # 또는 나중에 topic_key 기반으로 확장 가능
    for representative_url in representative_map.keys():
        normalized_representative_url = normalize_url(representative_url)

        if normalized_representative_url in article_url_set:
            for article in articles:
                article_url = normalize_url(
                    article.get("source_url") or article.get("url")
                )

                if article_url == normalized_representative_url:
                    return article

    dated_articles = [
        article for article in articles
        if article.get("published_at")
    ]

    if dated_articles:
        dated_articles.sort(
            key=lambda article: article.get("published_at", "")
        )
        return dated_articles[0]

    image_articles = [
        article for article in articles
        if article.get("image_url")
    ]

    if image_articles:
        return image_articles[0]

    return articles[0]


def build_topic(topic_id, articles):
    sources = sorted(set(article.get("source_name", "") for article in articles))

    latest_date = ""
    for article in articles:
        published_at = article.get("published_at", "")
        if published_at > latest_date:
            latest_date = published_at

    representative_article = choose_representative_article(articles)

    representative_title = (
        representative_article.get("title")
        or choose_topic_title(articles)
    )

    representative_summary = (
        representative_article.get("summary_ko")
        or ""
    )

    topic = {
        "topic_id": topic_id,
        "topic_title": representative_title,
        "topic_summary": representative_summary,
        "article_count": len(articles),
        "sources": sources,
        "source_count": len(sources),
        "label": choose_topic_label(articles),
        "importance": calculate_importance(articles),
        "latest_published_at": latest_date,
        "is_top": False,
        "representative_article": representative_article,
        "articles": articles
    }

    return topic

def get_article_url(article):
    """
    기사 URL을 비교용으로 정규화해서 반환한다.
    """
    return normalize_url(
        article.get("source_url") or article.get("url")
    )


def deduplicate_articles(articles):
    """
    병합 과정에서 같은 기사가 중복으로 들어가는 것을 막는다.
    """
    seen_urls = set()
    unique_articles = []

    for article in articles:
        article_url = get_article_url(article)

        if not article_url:
            continue

        if article_url in seen_urls:
            continue

        seen_urls.add(article_url)
        unique_articles.append(article)

    return unique_articles


def recalculate_topic_flags(topics):
    """
    수동 병합 이후 TOP 3, 정렬, topic_id를 다시 계산한다.
    """
    for topic in topics:
        topic["is_top"] = False
        topic["article_count"] = len(topic.get("articles", []))
        topic["sources"] = sorted(
            set(article.get("source_name", "") for article in topic.get("articles", []))
        )
        topic["source_count"] = len(topic["sources"])
        topic["label"] = choose_topic_label(topic.get("articles", []))
        topic["importance"] = calculate_importance(topic.get("articles", []))

        latest_date = ""
        for article in topic.get("articles", []):
            published_at = article.get("published_at", "")
            if published_at > latest_date:
                latest_date = published_at

        topic["latest_published_at"] = latest_date

        representative_article = choose_representative_article(topic.get("articles", []))

        representative_title = (
            representative_article.get("title")
            or choose_topic_title(topic.get("articles", []))
        )

        representative_summary = (
            representative_article.get("summary_ko")
            or ""
        )

        topic["representative_article"] = representative_article
        topic["topic_title"] = representative_title
        topic["topic_summary"] = representative_summary

    topics_by_importance = sorted(
        topics,
        key=lambda topic: (
            topic.get("importance", 0),
            topic.get("latest_published_at", "")
        ),
        reverse=True
    )

    top_topic_ids = set(id(topic) for topic in topics_by_importance[:3])

    for topic in topics:
        topic["is_top"] = id(topic) in top_topic_ids

    topics.sort(
        key=lambda topic: topic.get("latest_published_at", ""),
        reverse=True
    )

    for idx, topic in enumerate(topics, start=1):
        topic["topic_id"] = idx

    return topics


def apply_manual_topic_merges(topics):
    """
    관리자 모드에서 수동 병합한 topic 기록을 적용한다.
    article_overrides.json의 manual_topic_merges를 기준으로
    해당 기사들이 포함된 topic들을 하나로 합친다.
    """
    overrides = load_overrides()
    manual_merges = overrides.get("manual_topic_merges", [])

    if not manual_merges:
        return topics

    for merge in manual_merges:
        merge_urls = set(
            normalize_url(url)
            for url in merge.get("article_urls", [])
        )

        if not merge_urls:
            continue

        merged_articles = []
        remaining_topics = []

        for topic in topics:
            topic_articles = topic.get("articles", [])

            topic_urls = set(
                get_article_url(article)
                for article in topic_articles
            )

            # 이 topic 안의 기사 중 하나라도 병합 대상 URL과 겹치면 병합 대상
            if topic_urls.intersection(merge_urls):
                merged_articles.extend(topic_articles)
            else:
                remaining_topics.append(topic)

        if not merged_articles:
            topics = remaining_topics
            continue

        merged_articles = deduplicate_articles(merged_articles)

        merged_topic = build_topic(
            topic_id=0,
            articles=merged_articles
        )

        remaining_topics.append(merged_topic)
        topics = remaining_topics

    topics = recalculate_topic_flags(topics)

    return topics


def get_topic_article_url_set(topic):
    """
    topic 안의 기사 URL set을 만든다.
    TOP 고정/제외 판단에 사용한다.
    """
    urls = set()

    for article in topic.get("articles", []):
        article_url = normalize_url(
            article.get("source_url") or article.get("url")
        )

        if article_url:
            urls.add(article_url)

    return urls


def apply_top_topic_overrides(topics):
    """
    관리자 모드에서 지정한 TOP 3 고정/제외 설정을 반영한다.

    pinned_top_article_urls:
    - 이 URL이 포함된 topic은 TOP 3에 우선 포함

    hidden_top_article_urls:
    - 이 URL이 포함된 topic은 TOP 3 후보에서 제외
    """
    overrides = load_overrides()

    pinned_urls = set(
        normalize_url(url)
        for url in overrides.get("pinned_top_article_urls", [])
    )

    hidden_urls = set(
        normalize_url(url)
        for url in overrides.get("hidden_top_article_urls", [])
    )

    # 기존 TOP 상태 초기화
    for topic in topics:
        topic["is_top"] = False

    visible_candidates = []
    pinned_topics = []

    for topic in topics:
        topic_urls = get_topic_article_url_set(topic)

        # TOP 제외 대상이면 후보에서 제거
        if topic_urls.intersection(hidden_urls):
            continue

        # TOP 고정 대상이면 우선 후보로 분리
        if topic_urls.intersection(pinned_urls):
            pinned_topics.append(topic)
        else:
            visible_candidates.append(topic)

    pinned_topics.sort(
        key=lambda topic: (
            topic.get("latest_published_at", ""),
            topic.get("importance", 0)
        ),
        reverse=True
    )

    visible_candidates.sort(
        key=lambda topic: (
            topic.get("importance", 0),
            topic.get("latest_published_at", "")
        ),
        reverse=True
    )

    final_top_topics = []

    for topic in pinned_topics:
        if len(final_top_topics) >= 3:
            break

        final_top_topics.append(topic)

    for topic in visible_candidates:
        if len(final_top_topics) >= 3:
            break

        final_top_topics.append(topic)

    final_top_ids = set(id(topic) for topic in final_top_topics)

    for topic in topics:
        topic["is_top"] = id(topic) in final_top_ids

    return topics


def group_articles(articles, threshold=0.42):
    """
    기사들을 키워드 유사도 기반으로 자동 묶는다.
    threshold가 낮을수록 더 많이 묶이고, 높을수록 더 엄격하게 묶인다.
    """
    groups = []

    for article in articles:
        article_keywords = extract_keywords(article)

        article["content_type"] = detect_content_type(article)
        article["event_type"] = detect_event_type(article)
        article["main_entity"] = detect_main_entity(article)
        article["_keywords"] = list(article_keywords)

        best_group = None
        best_score = 0

        for group in groups:
            scores = []

            for grouped_article in group["articles"]:
                score = article_similarity(article, grouped_article)
                scores.append(score)

            if scores:
                score = max(scores)
            else:
                score = 0

            if score > best_score:
                best_score = score
                best_group = group

        if best_group and best_score >= threshold:
            best_group["articles"].append(article)
            best_group["keywords"].update(article_keywords)
        else:
            groups.append({
                "keywords": set(article_keywords),
                "articles": [article]
            })

    topics = []

    for idx, group in enumerate(groups, start=1):
        topic_articles = group["articles"]

        # 내부 작업용 키워드 필드는 최종 JSON에서 제거
        for article in topic_articles:
            article.pop("_keywords", None)

        topic = build_topic(idx, topic_articles)
        topics.append(topic)

    # TOP 3는 importance 기준으로 따로 선정
    top_topic_ids = set()

    topics_by_importance = sorted(
        topics,
        key=lambda topic: (
            topic["importance"],
            topic["latest_published_at"]
        ),
        reverse=True
    )

    for topic in topics_by_importance[:3]:
        top_topic_ids.add(id(topic))

    for topic in topics:
        topic["is_top"] = id(topic) in top_topic_ids

    # 전체 이슈 목록은 최신 날짜순으로 정렬
    topics.sort(
        key=lambda topic: topic.get("latest_published_at", ""),
        reverse=True
    )

    # 정렬 이후 topic_id 재부여
    for idx, topic in enumerate(topics, start=1):
        topic["topic_id"] = idx

    return topics


def print_topic_preview(topics):
    print("\n생성된 Topic 미리보기")
    print("-" * 50)

    for topic in topics[:10]:
        print(f"[{topic['topic_id']}] {topic['topic_title']}")
        print(f"  기사 수: {topic['article_count']}")
        print(f"  출처: {', '.join(topic['sources'])}")
        print(f"  라벨: {topic['label']}")
        print(f"  중요도: {topic['importance']}")
        print()


def main():
    print("기사 주제 자동 묶기 시작")

    articles = load_articles()

    if not articles:
        print("fetched_articles.json에 기사가 없습니다.")
        return

    articles = apply_article_overrides(articles)

    if not articles:
        print("관리자 제외 설정 적용 후 남은 기사가 없습니다.")
        save_topics([])
        return

    topics = group_articles(articles)

    topics = apply_manual_topic_merges(topics)

    topics = apply_top_topic_overrides(topics)

    save_topics(topics)
    print_topic_preview(topics)


if __name__ == "__main__":
    main()