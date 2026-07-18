import json
import os
import re
from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
import requests
from bs4 import BeautifulSoup


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

SWNN_FEED_URL = "https://www.starwarsnewsnet.com/feed/"
STARWARS_NEWS_URL = "https://www.starwars.com/news"
SWNN_HOME_URL = "https://www.starwarsnewsnet.com/"
SWNN_PAGE_URL = "https://www.starwarsnewsnet.com/page/{page_number}/"


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
    
def parse_starwars_date(text):
    """
    StarWars.com의 날짜 문자열을 YYYY-MM-DD 형식으로 변환한다.
    예: July 3, 2026 -> 2026-07-03
    """
    if not text:
        return ""

    text = text.strip()

    try:
        dt = datetime.strptime(text, "%B %d, %Y")
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

def fetch_starwars_article_metadata(url):
    """
    StarWars.com 개별 기사 페이지에서 날짜, 이미지, 요약 정보를 가져온다.
    목록 페이지에 날짜가 없는 대표 기사들을 보정하기 위한 함수.
    """
    metadata = {
        "published_at": "",
        "image_url": "",
        "summary": "",
    }

    if not url:
        return metadata

    try:
        response = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )
        response.raise_for_status()
    except requests.exceptions.RequestException:
        return metadata

    soup = BeautifulSoup(response.text, "html.parser")

    # 1. 대표 이미지 추출
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        metadata["image_url"] = og_image.get("content").strip()

    if not metadata["image_url"]:
        twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
        if twitter_image and twitter_image.get("content"):
            metadata["image_url"] = twitter_image.get("content").strip()

    # 2. 요약 추출
    og_description = soup.find("meta", property="og:description")
    if og_description and og_description.get("content"):
        metadata["summary"] = og_description.get("content").strip()

    # 3. 날짜 추출: article:published_time 우선
    published_meta = soup.find("meta", property="article:published_time")
    if published_meta and published_meta.get("content"):
        metadata["published_at"] = published_meta.get("content")[:10]

    # 4. time 태그 보조
    if not metadata["published_at"]:
        time_tag = soup.find("time")
        if time_tag:
            if time_tag.get("datetime"):
                metadata["published_at"] = time_tag.get("datetime")[:10]
            else:
                metadata["published_at"] = parse_starwars_date(time_tag.get_text(strip=True))

    # 5. 본문 텍스트에서 날짜 형식 보조 탐색
    if not metadata["published_at"]:
        page_text = soup.get_text(" ", strip=True)

        date_match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
            page_text
        )

        if date_match:
            metadata["published_at"] = parse_starwars_date(date_match.group(0))

    return metadata

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

def is_excluded_article(title, source_name=""):
    """
    최신 뉴스와 거리가 먼 리뷰/칼럼/기획성 글을 제외한다.
    단, 현재는 SWNN 기사에만 강하게 적용한다.
    """
    if not title:
        return False

    title_lower = title.lower()

    excluded_keywords = [
        "character spotlight",
        "review:",
        "review -",
        "review ",
        "this week",
        "who is",
        "gift guide",
        "father figures",
        "breakdown",
        "explained",
        "analysis",
        "opinion",
        "editorial",
        "recap",
    ]

    return any(keyword in title_lower for keyword in excluded_keywords)

def normalize_url(url):
    """
    중복 제거용 URL 정규화 함수.
    같은 기사인데 슬래시, 쿼리스트링, 앵커 차이 때문에
    다른 URL로 인식되는 문제를 막는다.
    """
    if not url:
        return ""

    url = url.strip()

    # ?utm_source=... 같은 쿼리스트링 제거
    url = url.split("?")[0]

    # #comments 같은 앵커 제거
    url = url.split("#")[0]

    # 끝의 / 제거
    url = url.rstrip("/")

    return url

def get_swnn_article_links_from_page(page_number=1):
    """
    Star Wars News Net 웹페이지에서 기사 링크를 수집한다.
    RSS에 나오지 않는 이전 기사까지 가져오기 위한 함수.
    """
    if page_number == 1:
        page_url = SWNN_HOME_URL
    else:
        page_url = SWNN_PAGE_URL.format(page_number=page_number)

    print(f"SWNN 페이지 수집 중: {page_url}")

    try:
        response = requests.get(
            page_url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=10
        )
        response.raise_for_status()
    except Exception as e:
        print(f"SWNN 페이지 수집 실패: {page_url} / {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    links = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "").strip()

        if not href.startswith("https://www.starwarsnewsnet.com/"):
            continue

        # 카테고리, 태그, 페이지, 댓글 링크 등 제외
        excluded_url_parts = [
            "/category/",
            "/tag/",
            "/author/",
            "/page/",
            "#comments",
            "/feed/",
            "/about",
            "/contact",
            "/privacy",
        ]

        if any(part in href for part in excluded_url_parts):
            continue

        # 실제 기사 URL은 보통 날짜 경로를 포함함
        # 예: /2026/07/...
        if not re.search(r"/20\d{2}/\d{2}/", href):
            continue

        normalized_href = normalize_url(href)

        if normalized_href not in links:
            links.append(normalized_href)

    return links

def fetch_swnn_article_from_page(url):
    """
    SWNN 개별 기사 페이지에서 기사 정보를 수집한다.
    """
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
            timeout=10
        )
        response.raise_for_status()
    except Exception as e:
        print(f"SWNN 기사 페이지 수집 실패: {url} / {e}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")

    title = ""

    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title.get("content").strip()

    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(strip=True)

    if not title:
        return None

    # 사이트명 같은 불필요한 꼬리 제거
    title = title.replace(" - Star Wars News Net", "").strip()

    if is_excluded_article(title, "Star Wars News Net"):
        print(f"제외됨: {title}")
        return None

    published_at = ""

    article_time = soup.find("time")
    if article_time:
        if article_time.get("datetime"):
            published_at = article_time.get("datetime")[:10]
        else:
            published_at = article_time.get_text(strip=True)

    if not published_at:
        published_meta = soup.find("meta", property="article:published_time")
        if published_meta and published_meta.get("content"):
            published_at = published_meta.get("content")[:10]

    summary = ""

    og_description = soup.find("meta", property="og:description")
    if og_description and og_description.get("content"):
        summary = og_description.get("content").strip()

    image_url = fetch_image_from_article_page(url)

    return {
        "title": title,
        "title_ko": "",
        "url": url,
        "source_url": url,
        "source_name": "Star Wars News Net",
        "published_at": published_at,
        "summary": summary,
        "summary_ko": "",
        "category": guess_category(title),
        "franchise": "starwars",
        "label": "일반 보도",
        "image_url": image_url,
    }

def fetch_swnn_articles_from_pages(max_pages=3, limit=20):
    """
    SWNN 메인/이전 페이지에서 기사들을 수집한다.
    """
    print("Star Wars News Net 웹페이지 기사 수집 시작")

    article_urls = []

    for page_number in range(1, max_pages + 1):
        links = get_swnn_article_links_from_page(page_number)

        for link in links:
            normalized_link = normalize_url(link)

            if normalized_link not in article_urls:
                article_urls.append(normalized_link)

    print(f"SWNN 웹페이지에서 발견한 후보 기사 수: {len(article_urls)}")

    articles = []

    for url in article_urls:
        if len(articles) >= limit:
            break

        article = fetch_swnn_article_from_page(url)

        if article:
            articles.append(article)

    print(f"SWNN 웹페이지 수집 기사 수: {len(articles)}")

    return articles

def fetch_swnn_articles(limit=20):
    feed = feedparser.parse(SWNN_FEED_URL)

    articles = []

    for idx, entry in enumerate(feed.entries[:limit], start=1):
        title = entry.get("title", "").strip()
        url = entry.get("link", "").strip()

        if is_excluded_article(title, "Star Wars News Net"):
            print(f"제외됨: {title}")
            continue

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

def fetch_starwars_official_articles(limit=20):
    """
    StarWars.com/news 페이지에서 공식 뉴스 메타데이터를 수집한다.
    기사 본문 전체를 저장하지 않고 제목, 링크, 요약, 날짜, 이미지 URL만 가져온다.
    """
    articles = []

    try:
        response = requests.get(
            STARWARS_NEWS_URL,
            timeout=15,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"StarWars.com 수집 실패: {e}")
        return articles

    soup = BeautifulSoup(response.text, "html.parser")

    links = soup.find_all("a", href=True)

    seen_urls = set()

    for link in links:
        if len(articles) >= limit:
            break

        title = link.get_text(" ", strip=True)
        href = link.get("href", "").strip()

        if not title or not href:
            continue

        # StarWars.com 뉴스 링크만 허용
        if href.startswith("https://www.starwars.com/news/"):
            url = href
        elif href.startswith("/news/"):
            url = "https://www.starwars.com" + href
        else:
            continue

        # 카테고리 페이지는 제외
        if "/news/category/" in url:
            continue

        if "/news/tag/" in url:
            continue

        # 뉴스 메인 페이지 자체는 제외
        if url.rstrip("/") == "https://www.starwars.com/news":
            continue

        if len(title) < 10:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        # 링크 주변 부모 요소에서 요약/날짜 후보를 찾는다.
        parent = link.find_parent()
        parent_text = parent.get_text(" ", strip=True) if parent else ""

        summary = ""
        published_at = ""

        # StarWars.com 페이지에는 날짜가 "July 3, 2026" 형식으로 들어간다.
        date_match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
            parent_text
        )

        if date_match:
            published_at = parse_starwars_date(date_match.group(0))

        # 목록 페이지에서 날짜가 없는 대표 기사들이 있으므로,
        # 개별 기사 페이지에 들어가 날짜/이미지/요약을 보정한다.
        metadata = fetch_starwars_article_metadata(url)

        if not published_at:
            published_at = metadata.get("published_at", "")

        summary = metadata.get("summary", "")
        image_url = metadata.get("image_url", "")

        if not image_url:
            image_url = fetch_image_from_article_page(url)

        article = {
            "article_id": 0,
            "title": title,
            "title_ko": "",
            "source_name": "StarWars.com",
            "source_url": url,
            "image_url": image_url,
            "published_at": published_at,
            "summary": summary,
            "summary_ko": "",
            "category": guess_category(title),
            "franchise": "Star Wars",
            "label": "공식"
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
    all_articles = []
    seen_urls = set()

    print("Star Wars News Net RSS 기사 수집 시작")
    swnn_rss_articles = fetch_swnn_articles(limit=20)
    print(f"SWNN RSS 수집 기사 수: {len(swnn_rss_articles)}")

    print("Star Wars News Net 웹페이지 기사 수집 시작")
    swnn_page_articles = fetch_swnn_articles_from_pages(max_pages=3, limit=20)
    print(f"SWNN 웹페이지 수집 기사 수: {len(swnn_page_articles)}")

    print("StarWars.com 공식 뉴스 수집 시작")
    official_articles = fetch_starwars_official_articles(limit=20)
    print(f"StarWars.com 수집 기사 수: {len(official_articles)}")

    for article in swnn_rss_articles + swnn_page_articles + official_articles:
        url = article.get("source_url") or article.get("url")
        normalized_url = normalize_url(url)

        if not normalized_url:
            continue

        if normalized_url in seen_urls:
            print(f"중복 제외됨: {article.get('title', '')}")
            continue

        seen_urls.add(normalized_url)

        # 저장되는 URL도 정규화된 URL로 통일
        article["source_url"] = normalized_url
        article["url"] = normalized_url

        all_articles.append(article)

    if not all_articles:
        print("수집된 기사가 없습니다. 네트워크 상태나 수집 대상 사이트 구조를 확인하세요.")
        return

    # article_id 재부여
    for idx, article in enumerate(all_articles, start=1):
        article["article_id"] = idx

    print(f"전체 기사 수: {len(all_articles)}")

    save_articles(all_articles)

if __name__ == "__main__":
    main()