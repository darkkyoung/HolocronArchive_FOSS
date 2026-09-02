import html
import json
import os
import re
import sys
from datetime import datetime
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

SWNN_FEED_URL = "https://www.starwarsnewsnet.com/feed/"
STARWARS_NEWS_URL = "https://www.starwars.com/news"
SWNN_HOME_URL = "https://www.starwarsnewsnet.com/"
SWNN_PAGE_URL = "https://www.starwarsnewsnet.com/page/{page_number}/"
SWNN_ENABLED = os.environ.get("SWNN_ENABLED", "false").lower() == "true"
THEDIRECT_STARWARS_URL = "https://thedirect.com/StarWars/"
THEDIRECT_STARWARS_PAGE_URL = "https://thedirect.com/StarWars/?page={page_number}"
COLLIDER_STARWARS_URL = "https://collider.com/tag/star-wars/"
COLLIDER_STARWARS_PAGE_URL = "https://collider.com/tag/star-wars/{page_number}/"
SCREENRANT_STARWARS_URL = "https://screenrant.com/tag/star-wars/"
SCREENRANT_STARWARS_PAGE_URL = "https://screenrant.com/tag/star-wars/{page_number}/"
SCREENRANT_SEARCH_URL = "https://screenrant.com/search/?q=star+wars"
SCREENRANT_GOOGLE_NEWS_SITEMAP_URL = "https://screenrant.com/post_google_news.xml"

SCREENRANT_SEED_URLS = [
    "https://screenrant.com/ahsoka-season-2-trailer-release-date/",
]

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
    media 태그뿐 아니라 summary/content HTML 안의 이미지도 확인한다.
    """
    # 1. media_content 확인
    media_content = entry.get("media_content", [])
    if media_content:
        image_url = clean_image_url(media_content[0].get("url", ""), entry.get("link", ""))
        if is_probable_article_image(image_url):
            return image_url

    # 2. media_thumbnail 확인
    media_thumbnail = entry.get("media_thumbnail", [])
    if media_thumbnail:
        image_url = clean_image_url(media_thumbnail[0].get("url", ""), entry.get("link", ""))
        if is_probable_article_image(image_url):
            return image_url

    # 3. links 중 image 타입 확인
    for link in entry.get("links", []):
        if link.get("type", "").startswith("image"):
            image_url = clean_image_url(link.get("href", ""), entry.get("link", ""))
            if is_probable_article_image(image_url):
                return image_url

    # 4. summary / description / content HTML 내부 확인
    html_candidates = [
        entry.get("summary", ""),
        entry.get("description", ""),
    ]

    for content_item in entry.get("content", []):
        if isinstance(content_item, dict):
            html_candidates.append(content_item.get("value", ""))

    for html_text in html_candidates:
        if not html_text:
            continue

        soup = BeautifulSoup(html_text, "html.parser")
        image_url = extract_image_from_soup(soup, entry.get("link", ""))

        if image_url:
            return image_url

    return ""


def clean_image_url(image_url, base_url=""):
    """
    이미지 URL 후보를 정리한다.
    상대 경로는 절대 경로로 변환하고, HTML escape도 정리한다.
    """
    if not image_url:
        return ""

    image_url = str(image_url).strip()
    image_url = html.unescape(image_url)
    image_url = image_url.replace("\\/", "/")
    image_url = image_url.strip("'\" ")

    if not image_url:
        return ""

    if image_url.startswith("data:"):
        return ""

    if image_url.startswith("//"):
        image_url = "https:" + image_url

    if base_url and image_url.startswith("/"):
        image_url = urljoin(base_url, image_url)

    return image_url


def is_probable_article_image(image_url):
    """
    로고/아이콘/아바타 같은 이미지를 대표 이미지로 잘못 잡지 않기 위한 필터.
    """
    if not image_url:
        return False

    image_lower = image_url.lower()

    bad_keywords = [
        "logo",
        "icon",
        "avatar",
        "profile",
        "placeholder",
        "default",
        "sprite",
        "favicon",
        "author",
        "comment",
        "tracking",
        "pixel",
        "blank",
        "transparent",
        "loading",
    ]

    if any(keyword in image_lower for keyword in bad_keywords):
        return False

    image_extensions = [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".avif",
    ]

    if any(ext in image_lower for ext in image_extensions):
        return True

    if "wp-content/uploads" in image_lower:
        return True

    if "image" in image_lower or "images" in image_lower or "cdn" in image_lower:
        return True

    return False


def extract_image_from_srcset(srcset, base_url=""):
    """
    srcset 문자열에서 가장 큰 이미지 후보를 추출한다.
    """
    if not srcset:
        return ""

    parts = [part.strip() for part in srcset.split(",") if part.strip()]

    for part in reversed(parts):
        image_url = part.split(" ")[0].strip()
        image_url = clean_image_url(image_url, base_url)

        if is_probable_article_image(image_url):
            return image_url

    return ""


def extract_image_from_style(style_text, base_url=""):
    """
    style 속성의 background-image: url(...)에서 이미지 URL을 추출한다.
    """
    if not style_text:
        return ""

    matches = re.findall(
        r"url\((['\"]?)(.*?)\1\)",
        style_text,
        flags=re.IGNORECASE
    )

    for _, raw_url in matches:
        image_url = clean_image_url(raw_url, base_url)

        if is_probable_article_image(image_url):
            return image_url

    return ""


def extract_image_from_img_tag(img_tag, base_url=""):
    """
    img 태그에서 실제 대표 이미지 후보를 추출한다.
    WordPress/lazy-load 환경에서는 src가 placeholder이고
    data-src, data-lazy-src, data-orig-file, srcset 쪽에 실제 이미지가 있을 수 있다.
    """
    if not img_tag:
        return ""

    image_attrs = [
        "data-src",
        "data-lazy-src",
        "data-original",
        "data-orig-file",
        "data-medium-file",
        "data-large-file",
        "data-full-url",
        "src",
    ]

    for attr in image_attrs:
        image_url = clean_image_url(img_tag.get(attr, ""), base_url)

        if is_probable_article_image(image_url):
            return image_url

    srcset_attrs = [
        "data-srcset",
        "data-lazy-srcset",
        "srcset",
    ]

    for attr in srcset_attrs:
        image_url = extract_image_from_srcset(img_tag.get(attr, ""), base_url)

        if image_url:
            return image_url

    return ""


def extract_image_from_any_tag(tag, base_url=""):
    """
    img 태그뿐 아니라 일반 태그의 style/data 속성에서도 이미지 URL을 찾는다.
    SWNN 목록 카드처럼 background-image를 쓰는 경우를 처리하기 위한 함수.
    """
    if not tag:
        return ""

    if tag.name == "img":
        image_url = extract_image_from_img_tag(tag, base_url)

        if image_url:
            return image_url

    # style="background-image: url(...)" 처리
    image_url = extract_image_from_style(tag.get("style", ""), base_url)
    if image_url:
        return image_url

    # lazy background 계열 속성 처리
    image_attrs = [
        "data-bg",
        "data-bg-url",
        "data-background",
        "data-background-image",
        "data-img",
        "data-img-url",
        "data-image",
        "data-image-url",
        "data-src",
        "data-lazy-src",
        "poster",
        "content",
        "href",
    ]

    for attr in image_attrs:
        image_url = clean_image_url(tag.get(attr, ""), base_url)

        if is_probable_article_image(image_url):
            return image_url

    srcset_attrs = [
        "data-bgset",
        "data-srcset",
        "data-lazy-srcset",
        "srcset",
    ]

    for attr in srcset_attrs:
        image_url = extract_image_from_srcset(tag.get(attr, ""), base_url)

        if image_url:
            return image_url

    return ""


def extract_image_from_json_data(data, base_url=""):
    """
    JSON-LD 데이터에서 image / thumbnailUrl / ImageObject URL을 재귀적으로 찾는다.
    WordPress Yoast SEO의 @graph 구조까지 대응한다.
    """
    if isinstance(data, str):
        image_url = clean_image_url(data, base_url)

        if is_probable_article_image(image_url):
            return image_url

        return ""

    if isinstance(data, list):
        for item in data:
            image_url = extract_image_from_json_data(item, base_url)

            if image_url:
                return image_url

        return ""

    if not isinstance(data, dict):
        return ""

    preferred_keys = [
        "image",
        "thumbnail",
        "thumbnailUrl",
        "contentUrl",
        "url",
    ]

    for key in preferred_keys:
        if key not in data:
            continue

        image_url = extract_image_from_json_data(data.get(key), base_url)

        if image_url:
            return image_url

    if "@graph" in data:
        image_url = extract_image_from_json_data(data.get("@graph"), base_url)

        if image_url:
            return image_url

    for value in data.values():
        image_url = extract_image_from_json_data(value, base_url)

        if image_url:
            return image_url

    return ""


def extract_image_from_raw_html(raw_html, base_url=""):
    """
    최후 fallback.
    HTML 원문 안에서 wp-content/uploads 이미지 URL을 직접 찾는다.
    """
    if not raw_html:
        return ""

    raw_html = html.unescape(raw_html)
    raw_html = raw_html.replace("\\/", "/")

    image_urls = re.findall(
        r"https?://[^\"'\s\)<>]+(?:\.jpg|\.jpeg|\.png|\.webp|\.avif)(?:\?[^\"'\s\)<>]*)?",
        raw_html,
        flags=re.IGNORECASE
    )

    # SWNN은 WordPress 업로드 이미지가 가장 안전하다.
    image_urls.sort(
        key=lambda url: 0 if "wp-content/uploads" in url.lower() else 1
    )

    for raw_url in image_urls:
        image_url = clean_image_url(raw_url, base_url)

        if is_probable_article_image(image_url):
            return image_url

    return ""


def extract_image_from_soup(soup, base_url=""):
    """
    기사 HTML에서 대표 이미지 후보를 여러 방식으로 추출한다.
    """
    meta_candidates = [
        ("meta", {"property": "og:image"}, "content"),
        ("meta", {"property": "og:image:url"}, "content"),
        ("meta", {"property": "og:image:secure_url"}, "content"),
        ("meta", {"name": "twitter:image"}, "content"),
        ("meta", {"name": "twitter:image:src"}, "content"),
        ("meta", {"name": "thumbnail"}, "content"),
        ("meta", {"itemprop": "image"}, "content"),
        ("link", {"rel": "image_src"}, "href"),
    ]

    for tag_name, attrs, value_attr in meta_candidates:
        tag = soup.find(tag_name, attrs=attrs)

        if tag and tag.get(value_attr):
            image_url = clean_image_url(tag.get(value_attr), base_url)

            if is_probable_article_image(image_url):
                return image_url

    # JSON-LD 확인
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            raw_text = script.string or script.get_text(strip=True)

            if not raw_text:
                continue

            data = json.loads(raw_text)
            image_url = extract_image_from_json_data(data, base_url)

            if image_url:
                return image_url

        except Exception:
            continue

    # article/main 내부 우선 확인
    containers = []

    article_tag = soup.find("article")
    if article_tag:
        containers.append(article_tag)

    main_tag = soup.find("main")
    if main_tag:
        containers.append(main_tag)

    containers.append(soup)

    for container in containers:
        for tag in container.find_all(True):
            image_url = extract_image_from_any_tag(tag, base_url)

            if image_url:
                return image_url

    # 최후 fallback: HTML 원문 정규식 탐색
    return extract_image_from_raw_html(str(soup), base_url)


def fetch_image_from_article_page(url):
    """
    RSS나 목록 페이지에 이미지가 없을 경우,
    기사 페이지에서 대표 이미지 URL을 최대한 찾아온다.
    """
    if not url:
        return ""

    try:
        response = requests.get(
            url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            }
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"대표 이미지 페이지 요청 실패: {url} / {e}")
        return ""

    soup = BeautifulSoup(response.text, "html.parser")

    image_url = extract_image_from_soup(soup, url)

    if not image_url:
        image_url = extract_image_from_raw_html(response.text, url)

    if not image_url:
        print(f"대표 이미지 없음: {url}")

    return image_url

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

        "underrated": "essay_column",
        "overlooked": "essay_column",
        "forgotten": "essay_column",
        "of the decade": "essay_column",
        "still holds up": "essay_column",
        "aged perfectly": "essay_column",
        "aged poorly": "essay_column",
        "rewatch": "essay_column",
        "perfect binge": "essay_column",
        "best weekend binge": "essay_column",
        "perfect thriller": "essay_column",
        "ranked from worst to best": "ranking_list",
        "from worst to best": "ranking_list",
        "every star wars": "list_article",
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

def is_collider_starwars_related(title, summary="", url=""):
    """
    Collider는 종합 엔터테인먼트 사이트이므로,
    Star Wars 명시 문구가 있는 기사만 통과시킨다.
    """
    return contains_explicit_star_wars_keyword(title, summary, url)

def is_screenrant_starwars_related(title, summary="", url=""):
    """
    ScreenRant는 종합 엔터테인먼트 사이트이므로,
    Star Wars 명시 문구가 있는 기사만 통과시킨다.
    """
    return contains_explicit_star_wars_keyword(title, summary, url)

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


def contains_explicit_star_wars_keyword(title, summary="", url=""):
    """
    Collider / ScreenRant처럼 종합 엔터테인먼트 사이트에서는
    Star Wars라는 명시 문구가 있는 기사만 통과시킨다.

    배우명, 캐릭터명, 감독명만으로 판단하면
    Ryan Reynolds의 Rey처럼 오탐이 발생할 수 있다.
    """
    text = f"{title} {summary} {url}".lower()

    explicit_keywords = [
        "star wars",
        "star-wars",
        "starwars",
    ]

    return any(keyword in text for keyword in explicit_keywords)


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
        "exclude_reason": reason,
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


def fetch_swnn_article_from_page(url, image_candidate=""):
    """
    SWNN 개별 기사 페이지는 현재 requests 접근 시 403이 발생하므로 사용하지 않는다.
    SWNN은 RSS 기반으로만 수집한다.
    """
    return None

def fetch_swnn_articles_from_pages(max_pages=3, limit=20):
    """
    SWNN 웹페이지 수집은 현재 403 차단이 발생하므로 비활성화한다.
    SWNN은 RSS feed 기반으로만 수집한다.
    """
    print("SWNN 웹페이지 수집은 403 차단으로 건너뜁니다.")
    return []


def fetch_swnn_articles(limit=20):
    if not SWNN_ENABLED:
        print("SWNN RSS 수집은 현재 비활성화되어 있습니다.")
        return []
    """
    Star Wars News Net RSS 기사 수집.
    SWNN은 기사 페이지와 WordPress API 접근 시 403이 발생하므로
    RSS feed 안에 포함된 정보만 사용한다.
    """
    feed = feedparser.parse(
        SWNN_FEED_URL,
        request_headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        }
    )

    articles = []

    for idx, entry in enumerate(feed.entries[:limit], start=1):
        title = entry.get("title", "").strip()
        url = normalize_url(entry.get("link", "").strip())

        if not title or not url:
            continue

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

        image_url = extract_image_url(entry)

        article = {
            "article_id": idx,
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
    SWNN은 웹페이지/개별 기사/WordPress API 접근 시 403이 발생하므로
    RSS feed에서 새 URL만 확인한다.
    """
    print("Star Wars News Net 빠른 갱신 시작")

    new_articles = []
    feed = feedparser.parse(
        SWNN_FEED_URL,
        request_headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/rss+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
        }
    )

    for entry in feed.entries[:rss_limit]:
        title = entry.get("title", "").strip()
        url = normalize_url(entry.get("link", "").strip())

        if not title or not url:
            continue

        if url in existing_urls:
            continue

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

        article = {
            "article_id": 0,
            "title": title,
            "title_ko": "",
            "source_name": "Star Wars News Net",
            "source_url": url,
            "url": url,
            "image_url": extract_image_url(entry),
            "published_at": format_date(entry),
            "summary": clean_summary(entry),
            "summary_ko": "",
            "category": guess_category(title),
            "franchise": "Star Wars",
            "label": guess_label(title, "Star Wars News Net")
        }

        new_articles.append(article)

        if len(new_articles) >= rss_limit:
            break

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

    if not metadata["image_url"]:
        metadata["image_url"] = extract_image_from_soup(soup, url)

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
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
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

    if not metadata["image_url"]:
        metadata["image_url"] = extract_image_from_soup(soup, url)

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
    Collider Star Wars 태그 페이지에서 기사 URL 후보를 수집한다.
    목록 페이지의 텍스트/이미지 alt는 신뢰하지 않고,
    실제 제목은 개별 기사 페이지의 og:title에서 다시 가져온다.
    """
    if page_number == 1:
        page_url = COLLIDER_STARWARS_URL
    else:
        page_url = COLLIDER_STARWARS_PAGE_URL.format(page_number=page_number)

    print(f"Collider 후보 페이지 수집 중: {page_url}")

    try:
        response = requests.get(
            page_url,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
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

        candidates.append({
            "url": href,
            "title_candidate": ""
        })

    print(f"Collider page/{page_number} 후보 URL 수: {len(candidates)}")

    return candidates


def fetch_collider_article_from_page(url, title_candidate=""):
    """
    Collider 개별 기사 페이지에서 기사 정보를 수집한다.
    """
    metadata = fetch_collider_article_metadata(url)

    title = metadata.get("title", "")

    if not title:
        print(f"Collider 제목 메타데이터 없음 제외: {url}")
        return None

    if not title:
        return None

    summary = metadata.get("summary", "")

    # Collider는 Lucasfilm 태그 기반이므로 Star Wars 관련성 필터를 반드시 적용
    if not is_collider_starwars_related(title, summary, url):
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


def fetch_collider_articles_incremental(existing_urls, limit=20, max_pages=1):
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


def fetch_collider_articles(limit=20, max_pages=1):
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

def parse_screenrant_date(date_text):
    """
    ScreenRant 날짜 문자열을 YYYY-MM-DD로 변환한다.
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


def clean_screenrant_title(title):
    """
    ScreenRant 제목에서 사이트명/불필요한 공백을 제거한다.
    """
    if not title:
        return ""

    title = re.sub(r"\s+", " ", title).strip()
    title = title.replace(" - ScreenRant", "").strip()
    title = title.replace(" | ScreenRant", "").strip()

    return title


def is_screenrant_article_url(url):
    """
    ScreenRant 실제 기사 URL인지 검사한다.
    tag/category/author/static 페이지는 제외한다.
    """
    if not url:
        return False

    if url.startswith("/"):
        url = "https://screenrant.com" + url

    if not url.startswith("https://screenrant.com/"):
        return False

    excluded_parts = [
        "/tag/",
        "/tags/",
        "/category/",
        "/author/",
        "/page/",
        "/search/",
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

    path = url.replace("https://screenrant.com/", "").strip("/")

    if not path:
        return False

    if "/" in path:
        return False

    if len(path) < 8:
        return False

    return True


def fetch_screenrant_article_metadata(url):
    """
    ScreenRant 개별 기사 페이지에서 제목/이미지/요약/날짜를 수집한다.
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
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            }
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"ScreenRant 기사 페이지 수집 실패: {url} / {e}")
        return metadata

    soup = BeautifulSoup(response.text, "html.parser")

    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        metadata["title"] = clean_screenrant_title(
            og_title.get("content").strip()
        )

    if not metadata["title"]:
        h1 = soup.find("h1")
        if h1:
            metadata["title"] = clean_screenrant_title(
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

    if not metadata["image_url"]:
        metadata["image_url"] = extract_image_from_soup(soup, url)

    published_meta = soup.find("meta", property="article:published_time")
    if published_meta and published_meta.get("content"):
        metadata["published_at"] = published_meta.get("content")[:10]

    if not metadata["published_at"]:
        time_tag = soup.find("time")
        if time_tag:
            if time_tag.get("datetime"):
                metadata["published_at"] = time_tag.get("datetime")[:10]
            else:
                metadata["published_at"] = parse_screenrant_date(
                    time_tag.get_text(" ", strip=True)
                )

    if not metadata["published_at"]:
        page_text = soup.get_text(" ", strip=True)

        date_match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
            page_text
        )

        if date_match:
            metadata["published_at"] = parse_screenrant_date(date_match.group(0))

    return metadata


def get_screenrant_candidates_from_google_news_sitemap(limit=40):
    """
    ScreenRant Google News sitemap에서 Star Wars 관련 최신 기사 후보를 수집한다.
    검색 페이지 HTML보다 최신 기사 후보를 안정적으로 잡기 위한 보조 수집 함수.
    """
    print(f"ScreenRant Google News sitemap 수집 중: {SCREENRANT_GOOGLE_NEWS_SITEMAP_URL}")

    candidates = []

    try:
        response = requests.get(
            SCREENRANT_GOOGLE_NEWS_SITEMAP_URL,
            timeout=10,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                "Accept": "application/xml,text/xml,application/rss+xml,text/html;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            }
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"ScreenRant Google News sitemap 수집 실패: {e}")
        return candidates

    try:
        root = ET.fromstring(response.content)
    except Exception as e:
        print(f"ScreenRant Google News sitemap 파싱 실패: {e}")
        return candidates

    namespaces = {
        "sitemap": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "news": "http://www.google.com/schemas/sitemap-news/0.9",
    }

    for url_node in root.findall("sitemap:url", namespaces):
        if len(candidates) >= limit:
            break

        loc_node = url_node.find("sitemap:loc", namespaces)
        title_node = url_node.find("news:news/news:title", namespaces)
        date_node = url_node.find("news:news/news:publication_date", namespaces)

        if loc_node is None or not loc_node.text:
            continue

        url = normalize_url(loc_node.text.strip())

        if not is_screenrant_article_url(url):
            continue

        title = ""
        if title_node is not None and title_node.text:
            title = clean_screenrant_title(title_node.text.strip())

        published_at = ""
        if date_node is not None and date_node.text:
            published_at = date_node.text[:10]

        # 제목이나 URL slug 기준으로 Star Wars 관련 기사만 후보에 넣는다.
        if not is_screenrant_starwars_related(title, "", url):
            continue

        candidates.append({
            "url": url,
            "title_candidate": title,
            "published_at_candidate": published_at,
        })

    print(f"ScreenRant Google News sitemap 후보 수: {len(candidates)}")

    return candidates


def get_screenrant_article_candidates_from_page(page_number=1):
    """
    ScreenRant Star Wars 후보 URL을 수집한다.
    우선순위:
    1. 직접 지정한 중요 URL
    2. Google News sitemap
    3. 검색 페이지
    4. 태그 페이지

    목록 페이지의 텍스트/이미지 alt는 신뢰하지 않고,
    실제 제목은 개별 기사 페이지에서 다시 가져온다.
    """
    candidates = []
    seen_urls = set()

    # 1. 직접 후보 URL을 맨 앞에 추가
    if page_number == 1:
        seed_added_count = 0

        for seed_url in SCREENRANT_SEED_URLS:
            normalized_seed_url = normalize_url(seed_url)

            if not normalized_seed_url:
                continue

            if normalized_seed_url in seen_urls:
                continue

            if not is_screenrant_article_url(normalized_seed_url):
                continue

            seen_urls.add(normalized_seed_url)

            candidates.append({
                "url": normalized_seed_url,
                "title_candidate": "",
                "source_hint": "seed",
            })

            seed_added_count += 1

        print(f"ScreenRant 직접 후보 URL 우선 추가 수: {seed_added_count}")

        # 2. Google News sitemap 후보 추가
        sitemap_candidates = get_screenrant_candidates_from_google_news_sitemap(limit=60)

        sitemap_added_count = 0

        for candidate in sitemap_candidates:
            url = normalize_url(candidate.get("url", ""))

            if not url:
                continue

            if url in seen_urls:
                continue

            seen_urls.add(url)

            candidates.append({
                "url": url,
                "title_candidate": candidate.get("title_candidate", ""),
                "published_at_candidate": candidate.get("published_at_candidate", ""),
                "source_hint": "google_news_sitemap",
            })

            sitemap_added_count += 1

        print(f"ScreenRant Google News sitemap 후보 추가 수: {sitemap_added_count}")

    # 3. 검색/태그 페이지 후보 추가
    if page_number == 1:
        page_urls = [
            SCREENRANT_SEARCH_URL,
            SCREENRANT_STARWARS_URL,
        ]
    else:
        page_urls = [
            SCREENRANT_STARWARS_PAGE_URL.format(page_number=page_number)
        ]

    for page_url in page_urls:
        print(f"ScreenRant 후보 페이지 수집 중: {page_url}")

        try:
            response = requests.get(
                page_url,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Connection": "keep-alive",
                }
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"ScreenRant 페이지 수집 실패: {page_url} / {e}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")

        page_candidate_count = 0

        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "").strip()

            if href.startswith("/"):
                href = "https://screenrant.com" + href

            href = normalize_url(href)

            if not is_screenrant_article_url(href):
                continue

            if href in seen_urls:
                continue

            seen_urls.add(href)

            candidates.append({
                "url": href,
                "title_candidate": "",
                "source_hint": "page",
            })

            page_candidate_count += 1

        print(f"ScreenRant 후보 URL 수: {page_candidate_count} / {page_url}")

    print(f"ScreenRant page/{page_number} 전체 후보 URL 수: {len(candidates)}")

    return candidates


def fetch_screenrant_article_from_page(url, title_candidate=""):
    """
    ScreenRant 개별 기사 페이지에서 기사 정보를 수집한다.
    """
    metadata = fetch_screenrant_article_metadata(url)

    title = metadata.get("title", "")

    if not title:
        title = clean_screenrant_title(title_candidate)

    if not title:
        print(f"ScreenRant 제목 메타데이터 없음 제외: {url}")
        return None

    summary = metadata.get("summary", "")

    if not is_screenrant_starwars_related(title, summary, url):
        print(f"ScreenRant Star Wars 관련성 부족 제외: {title}")

        add_auto_excluded_article(
            title=title,
            url=url,
            source_name="ScreenRant",
            published_at=metadata.get("published_at", ""),
            summary=summary,
            image_url=metadata.get("image_url", ""),
            category=guess_category(title),
            franchise="Star Wars"
        )

        return None

    if is_excluded_article(title, "ScreenRant") and not is_restored_auto_excluded_article(url):
        print(f"ScreenRant 제외됨: {title}")

        add_auto_excluded_article(
            title=title,
            url=url,
            source_name="ScreenRant",
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
        "source_name": "ScreenRant",
        "source_url": url,
        "url": url,
        "image_url": metadata.get("image_url", ""),
        "published_at": metadata.get("published_at", ""),
        "summary": summary,
        "summary_ko": "",
        "category": guess_category(title),
        "franchise": "Star Wars",
        "label": guess_label(title, "ScreenRant")
    }


def fetch_screenrant_articles_incremental(existing_urls, limit=20, max_pages=1):
    """
    ScreenRant 빠른 갱신.
    기존 URL은 건너뛰고, 새 후보만 상세 수집한다.
    """
    print("ScreenRant 빠른 갱신 시작")

    new_articles = []
    seen_candidate_urls = set()

    for page_number in range(1, max_pages + 1):
        candidates = get_screenrant_article_candidates_from_page(page_number)

        page_new_count = 0
        page_existing_count = 0

        for candidate in candidates:
            url = normalize_url(candidate.get("url", ""))

            if not url:
                continue

            if url in existing_urls:
                page_existing_count += 1
                continue

            if url in seen_candidate_urls:
                continue

            seen_candidate_urls.add(url)

            article = fetch_screenrant_article_from_page(url=url)

            if article:
                new_articles.append(article)
                page_new_count += 1

            if len(new_articles) >= limit:
                break

        print(
            f"ScreenRant page/{page_number} 신규 {page_new_count}개, "
            f"기존 {page_existing_count}개"
        )

        if len(new_articles) >= limit:
            break

        if page_new_count == 0 and page_existing_count >= FAST_UPDATE_EXISTING_STOP_COUNT:
            print("ScreenRant 기존 기사 중심으로 판단되어 이전 페이지 탐색 중단")
            break

    print(f"ScreenRant 빠른 갱신 신규 기사 수: {len(new_articles)}")

    return new_articles


def fetch_screenrant_articles(limit=20, max_pages=1):
    """
    ScreenRant 전체 수집.
    fetched_articles.json을 새로 만들 때 사용한다.
    """
    print("ScreenRant 기사 수집 시작")

    articles = []
    seen_urls = set()

    for page_number in range(1, max_pages + 1):
        candidates = get_screenrant_article_candidates_from_page(page_number)

        for candidate in candidates:
            if len(articles) >= limit:
                break

            url = normalize_url(candidate.get("url", ""))

            if not url or url in seen_urls:
                continue

            seen_urls.add(url)

            article = fetch_screenrant_article_from_page(url=url)

            if article:
                articles.append(article)

        if len(articles) >= limit:
            break

    print(f"ScreenRant 수집 기사 수: {len(articles)}")

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
        max_pages=1
    )

    # Collider에서 새로 추가된 URL도 ScreenRant 중복 판단에 반영
    for article in new_collider_articles:
        url = normalize_url(article.get("source_url") or article.get("url"))
        if url:
            existing_urls.add(url)

    new_screenrant_articles = fetch_screenrant_articles_incremental(
        existing_urls=existing_urls,
        limit=40,
        max_pages=1
    )

    all_articles = (
        existing_articles
        + new_swnn_articles
        + new_official_articles
        + new_thedirect_articles
        + new_collider_articles
        + new_screenrant_articles
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
    print(f"신규 ScreenRant 기사 수: {len(new_screenrant_articles)}")
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
    collider_articles = fetch_collider_articles(limit=20, max_pages=1)
    print(f"Collider 수집 기사 수: {len(collider_articles)}")

    print("ScreenRant 기사 수집 시작")
    screenrant_articles = fetch_screenrant_articles(limit=40, max_pages=1)
    print(f"ScreenRant 수집 기사 수: {len(screenrant_articles)}")

    for article in swnn_rss_articles + swnn_page_articles + official_articles + thedirect_articles + collider_articles + screenrant_articles:
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