import time
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


CSV_PATH = "data/articles.csv"


def get_article_image(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[실패] 요청 오류: {url} / {e}")
        return ""

    soup = BeautifulSoup(response.text, "html.parser")

    # 1순위: Open Graph 대표 이미지
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        return og_image["content"].strip()

    # 2순위: Twitter 카드 이미지
    twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
    if twitter_image and twitter_image.get("content"):
        return twitter_image["content"].strip()

    # 3순위: 본문 첫 이미지
    first_img = soup.find("img")
    if first_img and first_img.get("src"):
        return urljoin(url, first_img["src"].strip())

    print(f"[실패] 이미지 없음: {url}")
    return ""


def main():
    df = pd.read_csv(CSV_PATH)

    if "image_url" not in df.columns:
        df.insert(4, "image_url", "")

    # image_url 컬럼을 문자열 타입으로 고정
    df["image_url"] = df["image_url"].fillna("").astype(str)

    for idx, row in df.iterrows():
        current_image = str(row.get("image_url", "")).strip()

        if current_image and current_image != "nan":
            print(f"[건너뜀] 이미 image_url 있음: {row['title']}")
            continue

        article_url = row["source_url"]
        print(f"[수집 중] {row['title']}")

        image_url = get_article_image(article_url)
        df.at[idx, "image_url"] = image_url

        if image_url:
            print(f"  → {image_url}")
        else:
            print("  → 이미지 수집 실패")

        time.sleep(1)

    df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")
    print("\n완료: data/articles.csv에 image_url 저장됨")


if __name__ == "__main__":
    main()