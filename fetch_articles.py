import json
import os
import re
import sys
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
THEDIRECT_STARWARS_URL = "https://thedirect.com/StarWars/"
THEDIRECT_STARWARS_PAGE_URL = "https://thedirect.com/StarWars/?page={page_number}"
COLLIDER_LUCASFILM_URL = "https://collider.com/tag/lucasfilm/"
COLLIDER_LUCASFILM_PAGE_URL = "https://collider.com/tag/lucasfilm/{page_number}/"

AUTO_EXCLUDED_FILE = os.path.join(DATA_DIR, "auto_excluded_articles.json")
ARTICLE_OVERRIDES_FILE = os.path.join(DATA_DIR, "article_overrides.json")

AUTO_EXCLUDED_ARTICLES = []

# 빠른 갱신 최적화 기준
# 기존 기사 URL이 연속으로 이 횟수 이상 나오면 더 오래된 목록 탐색을 중단한다.
FAST_UPDATE_EXISTING_STOP_COUNT = 10


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


def get_exclusion_reason(title):
    """
    제목을 기준으로 자동 제외 사유를 반환한다.
    제외 대상이 아니면 빈 문자열 반환.
    """
    if not title:
        return ""

    title_lower = title.lower()

    exclusion_rules = {
        "character spotlight": "character_spotlight",
        "review:": "review",
        "review -": "review",
        "review ": "review",
        "this week": "weekly_roundup",
        "who is": "profile_article",
        "gift guide": "gift_guide",
        "father figures": "feature_column",
        "breakdown": "analysis",
        "explained": "analysis",
        "analysis": "analysis",
        "opinion": "opinion",
        "editorial": "editorial",
        "recap": "recap",

        # The Direct / feature성 글 필터
        "ranked": "ranking_list",
        "ranking": "ranking_list",
        "best ": "ranking_list",
        "worst ": "ranking_list",
        "every ": "list_article",
        "all ": "list_article",
        "all 5": "list_article",
        "all 10": "list_article",
        "all 11": "list_article",
        "all 12": "list_article",
        "all 14": "list_article",
        "why ": "essay_column",
        "where is": "essay_column",
        "what happened": "essay_column",
        "could have": "essay_column",
        "should have": "essay_column",
        "theory": "theory",
        "proof": "theory",
        "most powerful": "ranking_list",
        "timeline explained": "analysis",
    }

    for keyword, reason in exclusion_rules.items():
        if keyword in title_lower:
            return reason

    return ""


def is_excluded_article(title, source_name=""):
    """
    최신 뉴스와 거리가 먼 리뷰/칼럼/기획성 글을 제외한다.
    """
    return bool(get_exclusion_reason(title))

def is_collider_starwars_related(title, summary=""):
    """
    Collider의 Lucasfilm 태그에는 Star Wars 외 글도 섞일 수 있으므로,
    Star Wars 관련 키워드가 있는 기사만 통과시킨다.
    """
    text = f"{title} {summary}".lower()

    starwars_keywords = [
        "star wars",
        "lucasfilm",
        "mandalorian",
        "grogu",
        "ahsoka",
        "andor",
        "jedi",
        "sith",
        "skywalker",
        "rey",
        "finn",
        "poe",
        "kylo",
        "ben solo",
        "darth",
        "taika waititi",
        "shawn levy",
        "daisy ridley",
        "kathleen kennedy",
    ]

    return any(keyword in text for keyword in starwars_keywords)

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


def load_article_overrides_for_fetch():
    """
    fetch_articles.py에서 관리자 복구 기록을 확인하기 위한 함수.
    """
    if not os.path.exists(ARTICLE_OVERRIDES_FILE):
        return {
            "restored_auto_excluded_urls": []
        }

    try:
        with open(ARTICLE_OVERRIDES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "restored_auto_excluded_urls" not in data:
            data["restored_auto_excluded_urls"] = []

        return data

    except Exception:
        return {
            "restored_auto_excluded_urls": []
        }


def is_restored_auto_excluded_article(url):
    """
    관리자가 자동 제외 목록에서 복구한 기사는
    이후 수집 시 다시 자동 제외하지 않기 위한 함수.
    """
    normalized_url = normalize_url(url)

    if not normalized_url:
        return False

    overrides = load_article_overrides_for_fetch()

    restored_urls = set(
        normalize_url(url)
        for url in overrides.get("restored_auto_excluded_urls", [])
    )

    return normalized_url in restored_urls


def load_auto_excluded_articles():
    """
    기존 자동 제외 기사 목록을 불러온다.
    """
    if not os.path.exists(AUTO_EXCLUDED_FILE):
        return []

    try:
        with open(AUTO_EXCLUDED_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def add_auto_excluded_article(
    title,
    url,
    source_name="Star Wars News Net",
    published_at="",
    summary="",
    image_url="",
    category="",
    franchise="Star Wars"
):
    """
    자동 제외된 기사를 메모리에 저장한다.
    나중에 save_auto_excluded_articles()에서 파일로 저장한다.
    """
    normalized_url = normalize_url(url)

    if not title or not normalized_url:
        return

    # 관리자가 복구한 기사는 자동 제외 목록에 다시 넣지 않음
    if is_restored_auto_excluded_article(normalized_url):
        return

    reason = get_exclusion_reason(title)

    if not reason:
        return

    AUTO_EXCLUDED_ARTICLES.append({
        "title": title,
        "title_ko": "",
        "source_name": source_name,
        "source_url": normalized_url,
        "url": normalized_url,
        "image_url": image_url,
        "published_at": published_at,
        "summary": summary,
        "summary_ko": "",
        "category": category or guess_category(title),
        "franchise": franchise,
        "label": "자동 제외",
        "exclude_reason": reason
    })


def save_auto_excluded_articles(new_excluded_articles):
    """
    자동 제외 기사 목록을 저장한다.
    기존 목록과 새 목록을 URL 기준으로 합친다.
    """
    os.makedirs(DATA_DIR, exist_ok=True)

    existing_articles = load_auto_excluded_articles()
    combined_articles = existing_articles + new_excluded_articles

    seen_urls = set()
    unique_articles = []

    for article in combined_articles:
        url = normalize_url(article.get("source_url") or article.get("url"))

        if not url:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        article["source_url"] = url
        article["url"] = url

        unique_articles.append(article)

    unique_articles.sort(
        key=lambda article: article.get("published_at", ""),
        reverse=True
    )

    with open(AUTO_EXCLUDED_FILE, "w", encoding="utf-8") as f:
        json.dump(unique_articles, f, ensure_ascii=False, indent=2)

    print(f"자동 제외 기사 저장 완료: {AUTO_EXCLUDED_FILE}")
    print(f"자동 제외 기사 수: {len(unique_articles)}")


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


def clean_swnn_candidate_title(title):
    """
    SWNN 목록 페이지에서 가져온 제목 후보를 정리한다.
    목록 카드의 텍스트에는 공백/줄바꿈/불필요한 사이트명이 섞일 수 있다.
    """
    if not title:
        return ""

    title = re.sub(r"\s+", " ", title).strip()
    title = title.replace(" - Star Wars News Net", "").strip()

    return title


def get_swnn_article_candidates_from_page(page_number=1):
    """
    SWNN 웹페이지에서 기사 URL과 제목 후보를 함께 수집한다.
    빠른 갱신에서 제외 대상 글을 상세 페이지 접속 전에 거르기 위한 함수.
    """
    if page_number == 1:
        page_url = SWNN_HOME_URL
    else:
        page_url = SWNN_PAGE_URL.format(page_number=page_number)

    print(f"SWNN 후보 페이지 수집 중: {page_url}")

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
        print(f"SWNN 후보 페이지 수집 실패: {page_url} / {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    candidates = []
    seen_urls = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "").strip()

        if not href.startswith("https://www.starwarsnewsnet.com/"):
            continue

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
        if not re.search(r"/20\d{2}/\d{2}/", href):
            continue

        normalized_url = normalize_url(href)

        if not normalized_url:
            continue

        if normalized_url in seen_urls:
            continue

        seen_urls.add(normalized_url)

        title_candidate = clean_swnn_candidate_title(
            a_tag.get_text(" ", strip=True)
        )

        # a 태그 텍스트가 비어 있으면 이미지 alt도 후보로 확인
        if not title_candidate:
            img_tag = a_tag.find("img")
            if img_tag and img_tag.get("alt"):
                title_candidate = clean_swnn_candidate_title(
                    img_tag.get("alt", "")
                )

        candidates.append({
            "url": normalized_url,
            "title_candidate": title_candidate
        })

    return candidates


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

    if is_excluded_article(title, "Star Wars News Net") and not is_restored_auto_excluded_article(url):
        print(f"제외됨: {title}")

        add_auto_excluded_article(
            title=title,
            url=url,
            source_name="Star Wars News Net",
            published_at="",
            summary="",
            image_url="",
            category=guess_category(title),
            franchise="Star Wars"
        )

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

        if is_excluded_article(title, "Star Wars News Net") and not is_restored_auto_excluded_article(url):
            print(f"제외됨: {title}")

            add_auto_excluded_article(
                title=title,
                url=url,
                source_name="Star Wars News Net",
                published_at=format_date(entry),
                summary=clean_summary(entry),
                image_url=extract_image_url(entry),
                category=guess_category(title),
                franchise="Star Wars"
            )

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


def load_existing_articles():
    """
    기존 fetched_articles.json을 불러온다.
    빠른 갱신에서 이미 수집한 기사를 다시 상세 수집하지 않기 위해 사용한다.
    """
    input_path = os.path.join(DATA_DIR, "fetched_articles.json")

    if not os.path.exists(input_path):
        return []

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def get_existing_url_set(articles):
    """
    기존 기사들의 URL set을 만든다.
    URL 정규화를 적용해 중복 판단 정확도를 높인다.
    """
    existing_urls = set()

    for article in articles:
        url = article.get("source_url") or article.get("url")
        normalized_url = normalize_url(url)

        if normalized_url:
            existing_urls.add(normalized_url)

    return existing_urls


def deduplicate_articles(articles):
    """
    기존 기사와 새 기사를 합친 뒤 URL 기준으로 중복 제거한다.
    """
    seen_urls = set()
    unique_articles = []

    for article in articles:
        url = article.get("source_url") or article.get("url")
        normalized_url = normalize_url(url)

        if not normalized_url:
            continue

        if normalized_url in seen_urls:
            continue

        seen_urls.add(normalized_url)

        article["source_url"] = normalized_url
        article["url"] = normalized_url

        unique_articles.append(article)

    return unique_articles


def fetch_swnn_articles_incremental(existing_urls, rss_limit=20, page_limit=20, max_pages=3):
    """
    SWNN 빠른 갱신.
    기존에 수집한 URL은 건너뛰고, 새 URL만 상세 수집한다.

    최적화:
    - RSS나 목록 페이지에서 기존 기사 URL이 연속으로 많이 나오면
      더 오래된 기사라고 판단하고 탐색을 중단한다.
    - SWNN 목록 페이지에서 제목 후보를 먼저 확인해
      Review / Character Spotlight / Recap 등은 상세 페이지 접속 전에 제외한다.
    """
    print("Star Wars News Net 빠른 갱신 시작")

    new_articles = []
    seen_candidate_urls = set()

    # 1. RSS에서 새 기사 확인
    feed = feedparser.parse(SWNN_FEED_URL)

    consecutive_existing_count = 0

    for entry in feed.entries[:rss_limit]:
        title = entry.get("title", "").strip()
        url = normalize_url(entry.get("link", "").strip())

        if not title or not url:
            continue

        if url in existing_urls:
            consecutive_existing_count += 1

            if consecutive_existing_count >= FAST_UPDATE_EXISTING_STOP_COUNT:
                print("SWNN RSS 기존 기사 연속 발견으로 RSS 탐색 중단")
                break

            continue

        consecutive_existing_count = 0

        if url in seen_candidate_urls:
            continue

        seen_candidate_urls.add(url)

        if is_excluded_article(title, "Star Wars News Net"):
            print(f"제외됨: {title}")
            continue

        image_url = extract_image_url(entry)

        if not image_url:
            image_url = fetch_image_from_article_page(url)

        article = {
            "article_id": 0,
            "title": title,
            "title_ko": "",
            "source_name": "Star Wars News Net",
            "source_url": url,
            "url": url,
            "image_url": image_url,
            "published_at": format_date(entry),
            "summary": clean_summary(entry),
            "summary_ko": "",
            "category": guess_category(title),
            "franchise": "Star Wars",
            "label": guess_label(title, "Star Wars News Net")
        }

        new_articles.append(article)

    # 2. SWNN 웹페이지에서 새 기사 확인
    article_candidates = []
    should_stop_page_scan = False
    prefiltered_excluded_count = 0

    for page_number in range(1, max_pages + 1):
        if should_stop_page_scan:
            break

        candidates = get_swnn_article_candidates_from_page(page_number)

        page_new_count = 0
        page_existing_count = 0
        page_prefiltered_excluded_count = 0

        for candidate in candidates:
            normalized_link = normalize_url(candidate.get("url", ""))
            title_candidate = candidate.get("title_candidate", "")

            if not normalized_link:
                continue

            if normalized_link in existing_urls:
                page_existing_count += 1
                continue

            if normalized_link in seen_candidate_urls:
                continue

            # 목록 페이지 제목만으로 제외 가능하면 상세 페이지 접속 전에 제외
            if (
                title_candidate
                and is_excluded_article(title_candidate, "Star Wars News Net")
                and not is_restored_auto_excluded_article(normalized_link)
            ):
                print(f"사전 제외됨: {title_candidate}")

                add_auto_excluded_article(
                    title=title_candidate,
                    url=normalized_link,
                    source_name="Star Wars News Net",
                    published_at="",
                    summary="",
                    image_url="",
                    category=guess_category(title_candidate),
                    franchise="Star Wars"
                )

                page_prefiltered_excluded_count += 1
                prefiltered_excluded_count += 1
                seen_candidate_urls.add(normalized_link)
                continue

            seen_candidate_urls.add(normalized_link)
            article_candidates.append(candidate)
            page_new_count += 1

        print(
            f"SWNN page/{page_number} 신규 후보 {page_new_count}개, "
            f"기존 기사 {page_existing_count}개, "
            f"사전 제외 {page_prefiltered_excluded_count}개"
        )

        if page_new_count == 0 and page_existing_count >= FAST_UPDATE_EXISTING_STOP_COUNT:
            print("SWNN 웹페이지 기존 기사 중심으로 판단되어 이전 페이지 탐색 중단")
            should_stop_page_scan = True

    print(f"SWNN 웹페이지 신규 후보 기사 수: {len(article_candidates)}")
    print(f"SWNN 웹페이지 사전 제외 기사 수: {prefiltered_excluded_count}")

    for candidate in article_candidates:
        if len(new_articles) >= page_limit:
            break

        url = candidate.get("url", "")
        title_candidate = candidate.get("title_candidate", "")

        if (
            title_candidate
            and is_excluded_article(title_candidate, "Star Wars News Net")
            and not is_restored_auto_excluded_article(url)
        ):
            print(f"사전 제외됨: {title_candidate}")

            add_auto_excluded_article(
                title=title_candidate,
                url=url,
                source_name="Star Wars News Net",
                published_at="",
                summary="",
                image_url="",
                category=guess_category(title_candidate),
                franchise="Star Wars"
            )

            continue

        article = fetch_swnn_article_from_page(url)

        if article:
            new_articles.append(article)

    print(f"SWNN 빠른 갱신 신규 기사 수: {len(new_articles)}")

    return new_articles
    

def parse_thedirect_date(date_text):
    """
    The Direct 날짜 문자열을 YYYY-MM-DD로 변환한다.
    예:
    - August 06, 2026
    - 5 HOURS AGO
    """
    if not date_text:
        return ""

    date_text = date_text.strip()

    # 5 HOURS AGO, 2 DAYS AGO 같은 상대 시간은 오늘 날짜로 처리
    if "AGO" in date_text.upper():
        return datetime.now().strftime("%Y-%m-%d")

    try:
        dt = datetime.strptime(date_text, "%B %d, %Y")
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return ""


def fetch_thedirect_article_metadata(url):
    """
    The Direct 개별 기사 페이지에서 이미지/요약/날짜를 보정한다.
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
    except requests.exceptions.RequestException as e:
        print(f"The Direct 기사 페이지 수집 실패: {url} / {e}")
        return metadata

    soup = BeautifulSoup(response.text, "html.parser")

    og_description = soup.find("meta", property="og:description")
    if og_description and og_description.get("content"):
        metadata["summary"] = og_description.get("content").strip()

    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        metadata["image_url"] = og_image.get("content").strip()

    if not metadata["image_url"]:
        twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
        if twitter_image and twitter_image.get("content"):
            metadata["image_url"] = twitter_image.get("content").strip()

    published_meta = soup.find("meta", property="article:published_time")
    if published_meta and published_meta.get("content"):
        metadata["published_at"] = published_meta.get("content")[:10]

    if not metadata["published_at"]:
        page_text = soup.get_text(" ", strip=True)

        date_match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
            page_text
        )

        if date_match:
            metadata["published_at"] = parse_thedirect_date(date_match.group(0))

    return metadata


def parse_collider_date(date_text):
    """
    Collider 날짜 문자열을 YYYY-MM-DD로 변환한다.
    상대 시간이나 파싱 실패 시 빈 문자열 반환.
    """
    if not date_text:
        return ""

    date_text = date_text.strip()

    if "AGO" in date_text.upper():
        return datetime.now().strftime("%Y-%m-%d")

    for date_format in ["%B %d, %Y", "%b %d, %Y"]:
        try:
            dt = datetime.strptime(date_text, date_format)
            return dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    return ""


def clean_collider_title(title):
    """
    Collider 제목에서 사이트명/불필요한 공백을 제거한다.
    """
    if not title:
        return ""

    title = re.sub(r"\s+", " ", title).strip()
    title = title.replace(" - Collider", "").strip()

    return title


def is_collider_article_url(url):
    """
    Collider 실제 기사 URL인지 검사한다.
    tag/category/author/static 페이지는 제외한다.
    """
    if not url:
        return False

    if url.startswith("/"):
        url = "https://collider.com" + url

    if not url.startswith("https://collider.com/"):
        return False

    excluded_parts = [
        "/tag/",
        "/tags/",
        "/category/",
        "/author/",
        "/page/",
        "/news/",
        "/reviews/",
        "/features/",
        "/about",
        "/contact",
        "/privacy",
        "/sitemap",
        "#",
    ]

    if any(part in url for part in excluded_parts):
        return False

    # Collider 기사 URL은 보통 https://collider.com/article-slug/ 형태
    path = url.replace("https://collider.com/", "").strip("/")

    if not path:
        return False

    if "/" in path:
        return False

    if len(path) < 8:
        return False

    return True


def fetch_collider_article_metadata(url):
    """
    Collider 개별 기사 페이지에서 이미지/요약/날짜/제목을 보정한다.
    """
    metadata = {
        "title": "",
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
    except requests.exceptions.RequestException as e:
        print(f"Collider 기사 페이지 수집 실패: {url} / {e}")
        return metadata

    soup = BeautifulSoup(response.text, "html.parser")

    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        metadata["title"] = clean_collider_title(
            og_title.get("content").strip()
        )

    if not metadata["title"]:
        h1 = soup.find("h1")
        if h1:
            metadata["title"] = clean_collider_title(
                h1.get_text(" ", strip=True)
            )

    og_description = soup.find("meta", property="og:description")
    if og_description and og_description.get("content"):
        metadata["summary"] = og_description.get("content").strip()

    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        metadata["image_url"] = og_image.get("content").strip()

    if not metadata["image_url"]:
        twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
        if twitter_image and twitter_image.get("content"):
            metadata["image_url"] = twitter_image.get("content").strip()

    published_meta = soup.find("meta", property="article:published_time")
    if published_meta and published_meta.get("content"):
        metadata["published_at"] = published_meta.get("content")[:10]

    if not metadata["published_at"]:
        time_tag = soup.find("time")
        if time_tag:
            if time_tag.get("datetime"):
                metadata["published_at"] = time_tag.get("datetime")[:10]
            else:
                metadata["published_at"] = parse_collider_date(
                    time_tag.get_text(" ", strip=True)
                )

    if not metadata["published_at"]:
        page_text = soup.get_text(" ", strip=True)

        date_match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
            page_text
        )

        if date_match:
            metadata["published_at"] = parse_collider_date(date_match.group(0))

    return metadata


def get_collider_article_candidates_from_page(page_number=1):
    """
    Collider Lucasfilm 태그 페이지에서 기사 URL과 제목 후보를 수집한다.
    """
    if page_number == 1:
        page_url = COLLIDER_LUCASFILM_URL
    else:
        page_url = COLLIDER_LUCASFILM_PAGE_URL.format(page_number=page_number)

    print(f"Collider 후보 페이지 수집 중: {page_url}")

    try:
        response = requests.get(
            page_url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Collider 페이지 수집 실패: {page_url} / {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    candidates = []
    seen_urls = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "").strip()

        if href.startswith("/"):
            href = "https://collider.com" + href

        href = normalize_url(href)

        if not is_collider_article_url(href):
            continue

        if href in seen_urls:
            continue

        seen_urls.add(href)

        title_candidate = clean_collider_title(
            a_tag.get_text(" ", strip=True)
        )

        if not title_candidate:
            img_tag = a_tag.find("img")
            if img_tag and img_tag.get("alt"):
                title_candidate = clean_collider_title(
                    img_tag.get("alt", "")
                )

        if len(title_candidate) < 10:
            continue

        candidates.append({
            "url": href,
            "title_candidate": title_candidate
        })

    print(f"Collider page/{page_number} 후보 수: {len(candidates)}")

    return candidates


def fetch_collider_article_from_page(url, title_candidate=""):
    """
    Collider 개별 기사 페이지에서 기사 정보를 수집한다.
    """
    metadata = fetch_collider_article_metadata(url)

    title = clean_collider_title(title_candidate)

    if not title:
        title = metadata.get("title", "")

    if not title:
        return None

    summary = metadata.get("summary", "")

    # Collider는 Lucasfilm 태그 기반이므로 Star Wars 관련성 필터를 반드시 적용
    if not is_collider_starwars_related(title, summary):
        print(f"Collider Star Wars 관련성 부족 제외: {title}")

        add_auto_excluded_article(
            title=title,
            url=url,
            source_name="Collider",
            published_at=metadata.get("published_at", ""),
            summary=summary,
            image_url=metadata.get("image_url", ""),
            category=guess_category(title),
            franchise="Star Wars"
        )

        return None

    if is_excluded_article(title, "Collider") and not is_restored_auto_excluded_article(url):
        print(f"Collider 제외됨: {title}")

        add_auto_excluded_article(
            title=title,
            url=url,
            source_name="Collider",
            published_at=metadata.get("published_at", ""),
            summary=summary,
            image_url=metadata.get("image_url", ""),
            category=guess_category(title),
            franchise="Star Wars"
        )

        return None

    return {
        "article_id": 0,
        "title": title,
        "title_ko": "",
        "source_name": "Collider",
        "source_url": url,
        "url": url,
        "image_url": metadata.get("image_url", ""),
        "published_at": metadata.get("published_at", ""),
        "summary": summary,
        "summary_ko": "",
        "category": guess_category(title),
        "franchise": "Star Wars",
        "label": guess_label(title, "Collider")
    }


def fetch_collider_articles_incremental(existing_urls, limit=20, max_pages=2):
    """
    Collider 빠른 갱신.
    기존 URL은 건너뛰고, 새 후보만 상세 수집한다.
    """
    print("Collider 빠른 갱신 시작")

    new_articles = []
    seen_candidate_urls = set()

    for page_number in range(1, max_pages + 1):
        candidates = get_collider_article_candidates_from_page(page_number)

        page_new_count = 0
        page_existing_count = 0
        page_excluded_count = 0

        for candidate in candidates:
            url = normalize_url(candidate.get("url", ""))
            title_candidate = candidate.get("title_candidate", "")

            if not url:
                continue

            if url in existing_urls:
                page_existing_count += 1
                continue

            if url in seen_candidate_urls:
                continue

            seen_candidate_urls.add(url)

            if (
                title_candidate
                and is_excluded_article(title_candidate, "Collider")
                and not is_restored_auto_excluded_article(url)
            ):
                print(f"Collider 사전 제외됨: {title_candidate}")

                add_auto_excluded_article(
                    title=title_candidate,
                    url=url,
                    source_name="Collider",
                    published_at="",
                    summary="",
                    image_url="",
                    category=guess_category(title_candidate),
                    franchise="Star Wars"
                )

                page_excluded_count += 1
                continue

            article = fetch_collider_article_from_page(
                url=url,
                title_candidate=title_candidate
            )

            if article:
                new_articles.append(article)
                page_new_count += 1

            if len(new_articles) >= limit:
                break

        print(
            f"Collider page/{page_number} 신규 {page_new_count}개, "
            f"기존 {page_existing_count}개, "
            f"사전 제외 {page_excluded_count}개"
        )

        if len(new_articles) >= limit:
            break

        if page_new_count == 0 and page_existing_count >= FAST_UPDATE_EXISTING_STOP_COUNT:
            print("Collider 기존 기사 중심으로 판단되어 이전 페이지 탐색 중단")
            break

    print(f"Collider 빠른 갱신 신규 기사 수: {len(new_articles)}")

    return new_articles


def fetch_collider_articles(limit=20, max_pages=2):
    """
    Collider 전체 수집.
    fetched_articles.json을 새로 만들 때 사용한다.
    """
    print("Collider 기사 수집 시작")

    articles = []
    seen_urls = set()

    for page_number in range(1, max_pages + 1):
        candidates = get_collider_article_candidates_from_page(page_number)

        for candidate in candidates:
            if len(articles) >= limit:
                break

            url = normalize_url(candidate.get("url", ""))
            title_candidate = candidate.get("title_candidate", "")

            if not url or url in seen_urls:
                continue

            seen_urls.add(url)

            if (
                title_candidate
                and is_excluded_article(title_candidate, "Collider")
                and not is_restored_auto_excluded_article(url)
            ):
                print(f"Collider 사전 제외됨: {title_candidate}")

                add_auto_excluded_article(
                    title=title_candidate,
                    url=url,
                    source_name="Collider",
                    published_at="",
                    summary="",
                    image_url="",
                    category=guess_category(title_candidate),
                    franchise="Star Wars"
                )

                continue

            article = fetch_collider_article_from_page(
                url=url,
                title_candidate=title_candidate
            )

            if article:
                articles.append(article)

        if len(articles) >= limit:
            break

    print(f"Collider 수집 기사 수: {len(articles)}")

    return articles


def clean_thedirect_title(title):
    """
    The Direct 제목에서 사이트명/불필요한 공백을 제거한다.
    """
    if not title:
        return ""

    title = re.sub(r"\s+", " ", title).strip()
    title = title.replace(" - The Direct", "").strip()

    return title


def is_thedirect_article_url(url):
    """
    The Direct 실제 기사 URL인지 검사한다.
    카테고리/태그/페이지/정적 페이지를 제외한다.
    """
    if not url:
        return False

    if url.startswith("/"):
        url = "https://thedirect.com" + url

    if not url.startswith("https://thedirect.com/article/"):
        return False

    excluded_parts = [
        "/tags/",
        "/StarWars/",
        "/page/",
        "/about",
        "/contact",
        "/privacy",
        "/sitemap",
    ]

    if any(part in url for part in excluded_parts):
        return False

    return True


def get_thedirect_article_candidates_from_page(page_number=1):
    """
    The Direct Star Wars 페이지에서 기사 URL과 제목 후보를 수집한다.
    """
    if page_number == 1:
        page_url = THEDIRECT_STARWARS_URL
    else:
        page_url = THEDIRECT_STARWARS_PAGE_URL.format(page_number=page_number)

    print(f"The Direct 후보 페이지 수집 중: {page_url}")

    try:
        response = requests.get(
            page_url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"The Direct 페이지 수집 실패: {page_url} / {e}")
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    candidates = []
    seen_urls = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "").strip()

        if href.startswith("/"):
            href = "https://thedirect.com" + href

        href = normalize_url(href)

        if not is_thedirect_article_url(href):
            continue

        if href in seen_urls:
            continue

        seen_urls.add(href)

        title_candidate = clean_thedirect_title(
            a_tag.get_text(" ", strip=True)
        )

        if not title_candidate:
            img_tag = a_tag.find("img")
            if img_tag and img_tag.get("alt"):
                title_candidate = clean_thedirect_title(
                    img_tag.get("alt", "")
                )

        if len(title_candidate) < 10:
            continue

        candidates.append({
            "url": href,
            "title_candidate": title_candidate
        })

    print(f"The Direct page/{page_number} 후보 수: {len(candidates)}")

    return candidates


def fetch_thedirect_article_from_page(url, title_candidate=""):
    """
    The Direct 개별 기사 페이지에서 기사 정보를 수집한다.
    """
    metadata = fetch_thedirect_article_metadata(url)

    title = clean_thedirect_title(title_candidate)

    if not title:
        try:
            response = requests.get(
                url,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"The Direct 기사 제목 수집 실패: {url} / {e}")
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            title = clean_thedirect_title(og_title.get("content"))

        if not title:
            h1 = soup.find("h1")
            if h1:
                title = clean_thedirect_title(h1.get_text(" ", strip=True))

    if not title:
        return None

    if is_excluded_article(title, "The Direct") and not is_restored_auto_excluded_article(url):
        print(f"The Direct 제외됨: {title}")

        add_auto_excluded_article(
            title=title,
            url=url,
            source_name="The Direct",
            published_at=metadata.get("published_at", ""),
            summary=metadata.get("summary", ""),
            image_url=metadata.get("image_url", ""),
            category=guess_category(title),
            franchise="Star Wars"
        )

        return None

    return {
        "article_id": 0,
        "title": title,
        "title_ko": "",
        "source_name": "The Direct",
        "source_url": url,
        "url": url,
        "image_url": metadata.get("image_url", ""),
        "published_at": metadata.get("published_at", ""),
        "summary": metadata.get("summary", ""),
        "summary_ko": "",
        "category": guess_category(title),
        "franchise": "Star Wars",
        "label": guess_label(title, "The Direct")
    }


def fetch_thedirect_articles_incremental(existing_urls, limit=20, max_pages=2):
    """
    The Direct 빠른 갱신.
    기존 URL은 건너뛰고, 새 후보만 상세 수집한다.
    """
    print("The Direct 빠른 갱신 시작")

    new_articles = []
    seen_candidate_urls = set()

    for page_number in range(1, max_pages + 1):
        candidates = get_thedirect_article_candidates_from_page(page_number)

        page_new_count = 0
        page_existing_count = 0
        page_excluded_count = 0

        for candidate in candidates:
            url = normalize_url(candidate.get("url", ""))
            title_candidate = candidate.get("title_candidate", "")

            if not url:
                continue

            if url in existing_urls:
                page_existing_count += 1
                continue

            if url in seen_candidate_urls:
                continue

            seen_candidate_urls.add(url)

            if (
                title_candidate
                and is_excluded_article(title_candidate, "The Direct")
                and not is_restored_auto_excluded_article(url)
            ):
                print(f"The Direct 사전 제외됨: {title_candidate}")

                add_auto_excluded_article(
                    title=title_candidate,
                    url=url,
                    source_name="The Direct",
                    published_at="",
                    summary="",
                    image_url="",
                    category=guess_category(title_candidate),
                    franchise="Star Wars"
                )

                page_excluded_count += 1
                continue

            article = fetch_thedirect_article_from_page(
                url=url,
                title_candidate=title_candidate
            )

            if article:
                new_articles.append(article)
                page_new_count += 1

            if len(new_articles) >= limit:
                break

        print(
            f"The Direct page/{page_number} 신규 {page_new_count}개, "
            f"기존 {page_existing_count}개, "
            f"사전 제외 {page_excluded_count}개"
        )

        if len(new_articles) >= limit:
            break

        if page_new_count == 0 and page_existing_count >= FAST_UPDATE_EXISTING_STOP_COUNT:
            print("The Direct 기존 기사 중심으로 판단되어 이전 페이지 탐색 중단")
            break

    print(f"The Direct 빠른 갱신 신규 기사 수: {len(new_articles)}")

    return new_articles


def fetch_thedirect_articles(limit=20, max_pages=2):
    """
    The Direct 전체 수집.
    fetched_articles.json을 새로 만들 때 사용한다.
    """
    print("The Direct 기사 수집 시작")

    articles = []
    seen_urls = set()

    for page_number in range(1, max_pages + 1):
        candidates = get_thedirect_article_candidates_from_page(page_number)

        for candidate in candidates:
            if len(articles) >= limit:
                break

            url = normalize_url(candidate.get("url", ""))
            title_candidate = candidate.get("title_candidate", "")

            if not url or url in seen_urls:
                continue

            seen_urls.add(url)

            if (
                title_candidate
                and is_excluded_article(title_candidate, "The Direct")
                and not is_restored_auto_excluded_article(url)
            ):
                print(f"The Direct 사전 제외됨: {title_candidate}")

                add_auto_excluded_article(
                    title=title_candidate,
                    url=url,
                    source_name="The Direct",
                    published_at="",
                    summary="",
                    image_url="",
                    category=guess_category(title_candidate),
                    franchise="Star Wars"
                )

                continue

            article = fetch_thedirect_article_from_page(
                url=url,
                title_candidate=title_candidate
            )

            if article:
                articles.append(article)

        if len(articles) >= limit:
            break

    print(f"The Direct 수집 기사 수: {len(articles)}")

    return articles


def fetch_starwars_official_articles_incremental(existing_urls, limit=20):
    """
    StarWars.com 빠른 갱신.
    목록 페이지에서 URL만 먼저 확인하고,
    기존 URL이면 상세 페이지 접근을 생략한다.

    최적화:
    - 기존 기사 URL이 연속으로 많이 나오면
      더 이상 새 기사가 없다고 보고 탐색을 중단한다.
    """
    print("StarWars.com 빠른 갱신 시작")

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
    consecutive_existing_count = 0

    for link in links:
        if len(articles) >= limit:
            break

        title = link.get_text(" ", strip=True)
        href = link.get("href", "").strip()

        if not title or not href:
            continue

        if href.startswith("https://www.starwars.com/news/"):
            url = href
        elif href.startswith("/news/"):
            url = "https://www.starwars.com" + href
        else:
            continue

        url = normalize_url(url)

        if "/news/category/" in url:
            continue

        if "/news/tag/" in url:
            continue

        if url.rstrip("/") == "https://www.starwars.com/news":
            continue

        if len(title) < 10:
            continue

        if url in seen_urls:
            continue

        seen_urls.add(url)

        if url in existing_urls:
            consecutive_existing_count += 1

            if consecutive_existing_count >= FAST_UPDATE_EXISTING_STOP_COUNT:
                print("StarWars.com 기존 기사 연속 발견으로 탐색 중단")
                break

            continue

        consecutive_existing_count = 0

        # 새 기사일 때만 상세 페이지에 들어가 메타데이터 보정
        metadata = fetch_starwars_article_metadata(url)

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
            "url": url,
            "image_url": image_url,
            "published_at": published_at,
            "summary": summary,
            "summary_ko": "",
            "category": guess_category(title),
            "franchise": "Star Wars",
            "label": "공식"
        }

        articles.append(article)

    print(f"StarWars.com 빠른 갱신 신규 기사 수: {len(articles)}")

    return articles


def save_articles(articles):
    os.makedirs(DATA_DIR, exist_ok=True)

    output_path = os.path.join(DATA_DIR, "fetched_articles.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"저장 완료: {output_path}")
    print(f"수집 기사 수: {len(articles)}")


def incremental_update():
    """
    빠른 갱신.
    기존 fetched_articles.json을 유지하면서 새 기사만 추가한다.
    """
    print("빠른 뉴스 갱신 시작")

    AUTO_EXCLUDED_ARTICLES.clear()

    existing_articles = load_existing_articles()
    existing_urls = get_existing_url_set(existing_articles)

    print(f"기존 기사 수: {len(existing_articles)}")
    print(f"기존 URL 수: {len(existing_urls)}")

    new_swnn_articles = fetch_swnn_articles_incremental(
        existing_urls=existing_urls,
        rss_limit=20,
        page_limit=20,
        max_pages=3
    )

    # SWNN에서 새로 추가된 URL도 StarWars.com 중복 판단에 반영
    for article in new_swnn_articles:
        url = normalize_url(article.get("source_url") or article.get("url"))
        if url:
            existing_urls.add(url)

    new_official_articles = fetch_starwars_official_articles_incremental(
        existing_urls=existing_urls,
        limit=20
    )

    # StarWars.com에서 새로 추가된 URL도 The Direct 중복 판단에 반영
    for article in new_official_articles:
        url = normalize_url(article.get("source_url") or article.get("url"))
        if url:
            existing_urls.add(url)

    new_thedirect_articles = fetch_thedirect_articles_incremental(
        existing_urls=existing_urls,
        limit=20,
        max_pages=2
    )

    # The Direct에서 새로 추가된 URL도 Collider 중복 판단에 반영
    for article in new_thedirect_articles:
        url = normalize_url(article.get("source_url") or article.get("url"))
        if url:
            existing_urls.add(url)

    new_collider_articles = fetch_collider_articles_incremental(
        existing_urls=existing_urls,
        limit=20,
        max_pages=2
    )

    all_articles = (
        existing_articles
        + new_swnn_articles
        + new_official_articles
        + new_thedirect_articles
        + new_collider_articles
    )

    all_articles = deduplicate_articles(all_articles)

    all_articles.sort(
        key=lambda article: article.get("published_at", ""),
        reverse=True
    )

    for idx, article in enumerate(all_articles, start=1):
        article["article_id"] = idx

    print(f"신규 SWNN 기사 수: {len(new_swnn_articles)}")
    print(f"신규 StarWars.com 기사 수: {len(new_official_articles)}")
    print(f"신규 The Direct 기사 수: {len(new_thedirect_articles)}")
    print(f"신규 Collider 기사 수: {len(new_collider_articles)}")
    print(f"갱신 후 전체 기사 수: {len(all_articles)}")

    save_articles(all_articles)
    save_auto_excluded_articles(AUTO_EXCLUDED_ARTICLES)


def main():
    all_articles = []
    seen_urls = set()

    AUTO_EXCLUDED_ARTICLES.clear()

    print("Star Wars News Net RSS 기사 수집 시작")
    swnn_rss_articles = fetch_swnn_articles(limit=20)
    print(f"SWNN RSS 수집 기사 수: {len(swnn_rss_articles)}")

    print("Star Wars News Net 웹페이지 기사 수집 시작")
    swnn_page_articles = fetch_swnn_articles_from_pages(max_pages=3, limit=20)
    print(f"SWNN 웹페이지 수집 기사 수: {len(swnn_page_articles)}")

    print("StarWars.com 공식 뉴스 수집 시작")
    official_articles = fetch_starwars_official_articles(limit=20)
    print(f"StarWars.com 수집 기사 수: {len(official_articles)}")

    print("The Direct 기사 수집 시작")
    thedirect_articles = fetch_thedirect_articles(limit=20, max_pages=2)
    print(f"The Direct 수집 기사 수: {len(thedirect_articles)}")

    print("Collider 기사 수집 시작")
    collider_articles = fetch_collider_articles(limit=20, max_pages=2)
    print(f"Collider 수집 기사 수: {len(collider_articles)}")

    for article in swnn_rss_articles + swnn_page_articles + official_articles + thedirect_articles + collider_articles:
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
    save_auto_excluded_articles(AUTO_EXCLUDED_ARTICLES)
    

if __name__ == "__main__":
    if "--fast" in sys.argv:
        incremental_update()
    else:
        main()