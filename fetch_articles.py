import json
import os
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
import requests
from bs4 import BeautifulSoup


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

SWNN_FEED_URL = "https://www.starwarsnewsnet.com/feed/"


def format_date(entry):
    """
    RSS의 published 날짜를 YYYY-MM-DD 형식으로 변환한다.
    날짜가 없거나 변환에 실패하면 빈 문자열을 반환한다.
    """
    published = entry.get("published", "")

    if not published:
        return ""

    try:
        dt = parsedate_to_datetime(published)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def clean_summary(entry):
    """
    RSS summary에서 HTML 태그를 제거하고 카드 표시용 짧은 설명만 저장한다.
    기사 본문 전체를 저장하지 않고, 요약 일부만 사용한다.
    """
    summary = entry.get("summary", "")

    if not summary:
        return ""

    soup = BeautifulSoup(summary, "html.parser")
    text = soup.get_text(" ", strip=True)

    if len(text) > 300:
        text = text[:300].strip() + "..."

    return text


def extract_image_url(entry):
    """
    RSS entry에서 대표 이미지 URL을 추출한다.
    사이트마다 RSS 이미지 제공 방식이 다를 수 있으므로 여러 후보를 순서대로 확인한다.
    """
    # 1. media_content 확인
    media_content = entry.get("media_content", [])
    if media_content:
        image_url = media_content[0].get("url", "")
        if image_url:
            return image_url

    # 2. media_thumbnail 확인
    media_thumbnail = entry.get("media_thumbnail", [])
    if media_thumbnail:
        image_url = media_thumbnail[0].get("url", "")
        if image_url:
            return image_url

    # 3. links 중 image 타입 확인
    for link in entry.get("links", []):
        if link.get("type", "").startswith("image"):
            return link.get("href", "")

    # 4. summary HTML 안의 첫 번째 img 태그 확인
    summary = entry.get("summary", "")
    if summary:
        soup = BeautifulSoup(summary, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img.get("src")

    return ""

def fetch_image_from_article_page(url):
    """
    RSS에 이미지가 없을 경우, 기사 페이지의 og:image 메타태그에서 대표 이미지를 가져온다.
    기사 본문 전체를 저장하지 않고 대표 이미지 URL만 추출한다.
    """
    if not url:
        return ""

    try:
        response = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        og_image = soup.find("meta", property="og:image")
        if og_image and og_image.get("content"):
            return og_image.get("content")

        twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
        if twitter_image and twitter_image.get("content"):
            return twitter_image.get("content")

        return ""

    except requests.exceptions.RequestException:
        return ""


def guess_category(title):
    """
    제목 키워드를 기준으로 임시 카테고리를 부여한다.
    나중에 AI 분류나 관리자 검수로 고도화 가능하다.
    """
    title_lower = title.lower()

    if any(keyword in title_lower for keyword in ["game", "games", "gaming", "zero company", "jedi", "dlc"]):
        return "게임"

    if any(keyword in title_lower for keyword in ["mandalorian", "grogu", "movie", "box office", "imax", "film"]):
        return "영화"

    if any(keyword in title_lower for keyword in ["series", "season", "showrunner", "episode", "anime"]):
        return "드라마"

    if any(keyword in title_lower for keyword in ["book", "comic", "novel", "thrawn"]):
        return "도서"

    return "기타"


def guess_label(title, source_name):
    """
    출처와 제목 키워드를 기준으로 기사 성격 라벨을 붙인다.
    """
    title_lower = title.lower()

    if "rumor" in title_lower or "reportedly" in title_lower or "reported" in title_lower:
        return "루머/보도"

    if "interview" in title_lower or "commentary" in title_lower:
        return "인터뷰/코멘터리"

    if source_name == "Star Wars News Net":
        return "팬 뉴스/전문 매체"

    return "일반 보도"


def fetch_swnn_articles(limit=20):
    feed = feedparser.parse(SWNN_FEED_URL)

    articles = []

    for idx, entry in enumerate(feed.entries[:limit], start=1):
        title = entry.get("title", "").strip()
        url = entry.get("link", "").strip()

        if not title or not url:
            continue

        image_url = extract_image_url(entry)

        if not image_url:
            image_url = fetch_image_from_article_page(url)

        article = {
            "article_id": idx,
            "title": title,
            "title_ko": "",
            "source_name": "Star Wars News Net",
            "source_url": url,
            "image_url": image_url,
            "published_at": format_date(entry),
            "summary": clean_summary(entry),
            "summary_ko": "",
            "category": guess_category(title),
            "franchise": "Star Wars",
            "label": guess_label(title, "Star Wars News Net")
        }

        articles.append(article)

    return articles


def save_articles(articles):
    os.makedirs(DATA_DIR, exist_ok=True)

    output_path = os.path.join(DATA_DIR, "fetched_articles.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"저장 완료: {output_path}")
    print(f"수집 기사 수: {len(articles)}")


def main():
    print("Star Wars News Net RSS 기사 수집 시작")
    articles = fetch_swnn_articles(limit=20)

    if not articles:
        print("수집된 기사가 없습니다. RSS 주소나 네트워크 상태를 확인하세요.")
        return

    save_articles(articles)


if __name__ == "__main__":
    main()