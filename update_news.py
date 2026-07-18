import subprocess
import sys


def run_command(command):
    print(f"\n실행 중: {' '.join(command)}")

    result = subprocess.run(
        command,
        check=False,
        text=True
    )

    if result.returncode != 0:
        print(f"실패: {' '.join(command)}")
        sys.exit(result.returncode)


def main():
    print("뉴스 데이터 갱신 시작")

    run_command([sys.executable, "fetch_articles.py"])
    run_command([sys.executable, "group_topics.py"])

    print("\n뉴스 데이터 갱신 완료")
    print("data/fetched_articles.json 및 data/topics.json이 갱신되었습니다.")


if __name__ == "__main__":
    main()