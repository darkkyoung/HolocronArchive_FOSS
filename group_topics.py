import json
import os
import re
from collections import Counter


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

INPUT_FILE = os.path.join(DATA_DIR, "fetched_articles.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "topics.json")


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


def choose_topic_title(articles):
    """
    topic 대표 제목을 선택한다.
    우선 공식 출처가 있으면 공식 기사 제목을 사용하고,
    없으면 가장 최신 기사 제목을 사용한다.
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


def calculate_importance(articles):
    """
    TOP 3 선정용 중요도 점수.
    여러 출처에서 다룬 주제일수록 점수를 높게 준다.
    """
    source_count = len(set(article.get("source_name", "") for article in articles))
    article_count = len(articles)

    has_official = any(
        article.get("source_name") == "StarWars.com"
        for article in articles
    )

    score = 0
    score += article_count * 10
    score += source_count * 20

    if has_official:
        score += 30

    return score


def build_topic(topic_id, articles):
    sources = sorted(set(article.get("source_name", "") for article in articles))

    latest_date = ""
    for article in articles:
        published_at = article.get("published_at", "")
        if published_at > latest_date:
            latest_date = published_at

    topic = {
        "topic_id": topic_id,
        "topic_title": choose_topic_title(articles),
        "topic_summary": "",
        "article_count": len(articles),
        "sources": sources,
        "source_count": len(sources),
        "label": choose_topic_label(articles),
        "importance": calculate_importance(articles),
        "latest_published_at": latest_date,
        "is_top": False,
        "articles": articles
    }

    return topic


def group_articles(articles, threshold=0.38):
    """
    기사들을 키워드 유사도 기반으로 자동 묶는다.
    threshold가 낮을수록 더 많이 묶이고, 높을수록 더 엄격하게 묶인다.
    """
    groups = []

    for article in articles:
        article_keywords = extract_keywords(article)
        article["_keywords"] = list(article_keywords)

        best_group = None
        best_score = 0

        for group in groups:
            group_keywords = group["keywords"]
            score = similarity(article_keywords, group_keywords)

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

    topics.sort(
        key=lambda topic: (
            topic["importance"],
            topic["latest_published_at"]
        ),
        reverse=True
    )

    # TOP 3 지정
    for idx, topic in enumerate(topics):
        topic["is_top"] = idx < 3

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

    topics = group_articles(articles)

    save_topics(topics)
    print_topic_preview(topics)


if __name__ == "__main__":
    main()