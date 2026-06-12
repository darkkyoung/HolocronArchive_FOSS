import csv
import json
import os


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")


def csv_to_json(csv_filename, json_filename):
    csv_path = os.path.join(DATA_DIR, csv_filename)
    json_path = os.path.join(DATA_DIR, json_filename)

    rows = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for idx, row in enumerate(reader, start=1):
            clean_row = {}

            for key, value in row.items():
                if value is None:
                    clean_row[key] = ""
                else:
                    clean_row[key] = value.strip()

            # 기존 DB의 article_id, work_id 역할을 JSON에서 직접 만들어줌
            if csv_filename == "works.csv":
                clean_row["work_id"] = idx
                clean_row.setdefault("franchise", "Star Wars")

                # works.csv에 franchise 컬럼이 없으면 기본값 추가
                if not clean_row.get("franchise"):
                    clean_row["franchise"] = "Star Wars"

            if csv_filename == "articles.csv":
                clean_row["article_id"] = idx

                if not clean_row.get("franchise"):
                    clean_row["franchise"] = "Star Wars"

            rows.append(clean_row)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)

    print(f"{csv_filename} -> {json_filename} 변환 완료")


def main():
    csv_to_json("works.csv", "works.json")
    csv_to_json("articles.csv", "articles.json")


if __name__ == "__main__":
    main()