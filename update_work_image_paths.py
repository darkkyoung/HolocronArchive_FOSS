import os
import pandas as pd

CSV_PATH = "data/works.csv"

# 실제 이미지 폴더 위치
IMAGE_DIR = "static/images"

# 브라우저에서 접근하는 경로
STATIC_PREFIX = "/static/images"

IMAGE_MAP = {
    "Star Wars: A New Hope (Episode IV)": "a-new-hope.png",
    "Star Wars: The Empire Strikes Back (Episode V)": "the-empire-strikes-back.png",
    "Star Wars: Return of the Jedi (Episode VI)": "return-of-the-jedi.png",
    "Star Wars: The Phantom Menace (Episode I)": "the-phantom-menace.png",
    "Star Wars: Attack of the Clones (Episode II)": "attack-of-the-clones.png",
    "Star Wars: Revenge of the Sith (Episode III)": "revenge-of-the-sith.png",
    "Star Wars: The Force Awakens (Episode VII)": "the-force-awakens.png",
    "Star Wars: The Last Jedi (Episode VIII)": "the-last-jedi.png",
    "Star Wars: The Rise of Skywalker (Episode IX)": "the-rise-of-skywalker.png",

    "Star Wars: The Clone Wars": "the-clone-wars-movie.png",
    "Star Wars: The Clone Wars Series": "the-clone-wars-series.png",
    "Star Wars Rebels": "rebels.png",
    "Rogue One: A Star Wars Story": "rogue-one.png",
    "Solo: A Star Wars Story": "solo.png",
    "Star Wars Resistance": "resistance.png",
    "The Mandalorian": "the-mandalorian.png",
    "Star Wars: The Bad Batch": "the-bad-batch.png",
    "The Book of Boba Fett": "the-book-of-boba-fett.png",
    "Obi-Wan Kenobi": "obi-wan-kenobi.png",
    "Andor": "andor.png",
    "Star Wars: Tales of the Jedi": "tales-of-the-jedi.png",
    "Ahsoka": "ahsoka.png",
    "Star Wars: Tales of the Empire": "tales-of-the-empire.png",
    "The Acolyte": "the-acolyte.png",
    "Skeleton Crew": "skeleton-crew.png",
    "Star Wars: Tales of the Underworld": "tales-of-the-underworld.png",
    "Star Wars: Maul - Shadow Lord": "maul-shadow-lord.png",

    # 네 실제 파일명 기준
    "Star Wars: The Mandalorian and Grogu": "mandalorian-grogu.png",

    "Star Wars: Starfighter": "starfighter.png",
}

df = pd.read_csv(CSV_PATH)

if "image_url" not in df.columns:
    df["image_url"] = ""

missing_titles = []
missing_files = []

for idx, row in df.iterrows():
    title = str(row["title"]).strip()

    if title not in IMAGE_MAP:
        missing_titles.append(title)
        continue

    filename = IMAGE_MAP[title]
    file_path = os.path.join(IMAGE_DIR, filename)

    if not os.path.exists(file_path):
        missing_files.append((title, filename))
        continue

    df.at[idx, "image_url"] = f"{STATIC_PREFIX}/{filename}"

df.to_csv(CSV_PATH, index=False, encoding="utf-8-sig")

print("완료: data/works.csv의 image_url을 실제 이미지 경로로 수정했습니다.")

if missing_titles:
    print("\n매칭되지 않은 작품명:")
    for title in missing_titles:
        print("-", title)

if missing_files:
    print("\n파일을 찾지 못한 항목:")
    for title, filename in missing_files:
        print(f"- {title} -> {filename}")