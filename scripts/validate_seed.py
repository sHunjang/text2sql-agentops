"""
validate_seed.py
================
시드 파일(data/seed/seed.jsonl)을 자동으로 검사하는 스크립트입니다.

검사 항목:
  1. 각 줄이 올바른 JSON 형식인가?
  2. category / question / sql 세 가지 키가 모두 있는가?
  3. category 이름이 정해진 10개 중 하나인가?
  4. SQL이 "SELECT 한 문장"인가?
  5. SQL이 샘플 DB에서 실제로 실행되는가? (없는 컬럼 이름 등을 잡아냄)
  6. 결과가 비어 있거나 0 하나뿐이지는 않은가? (경고)
  7. 같은 질문이 중복되지는 않았는가?

실행 방법 (프로젝트 최상위 폴더에서):
  python scripts/validate_seed.py
"""

import json
import sqlite3
import sys
from collections import Counter

# 같은 scripts/ 폴더에 있는 dbutil.py 에서 필요한 것들을 가져옵니다.
from dbutil import PROJECT_ROOT, open_readonly, run_query

# 검사할 시드 파일의 위치
SEED_PATH = PROJECT_ROOT / "data" / "seed" / "seed.jsonl"

# 허용하는 카테고리 이름 10개 (오타 방지용)
ALLOWED_CATEGORIES = {
    "filter", "aggregate", "group_having", "top_n", "join2",
    "join3", "anti_join", "subquery", "date", "null",
}

# 카테고리당 목표 개수
TARGET_PER_CATEGORY = 3

# 필수로 있어야 하는 키
REQUIRED_KEYS = {"category", "question", "sql"}


def check_single_select(sql: str) -> str | None:
    """SQL이 'SELECT 한 문장'인지 간단히 검사합니다.

    문제가 있으면 이유를 글자로 돌려주고, 문제가 없으면 None을 돌려줍니다.
    (주의: 이것은 시드 검사용의 가벼운 검사입니다. 제품에 들어갈 본격적인
     안전장치는 7단계에서 따로 만듭니다.)
    """
    body = sql.strip()
    if body.endswith(";"):
        body = body[:-1]  # 맨 끝 세미콜론 하나는 정상이므로 떼어낸다

    if ";" in body:
        return "세미콜론으로 여러 문장이 이어져 있음"

    # 첫 단어를 소문자로 꺼낸다. (SELECT 또는 WITH 로 시작해야 함)
    first_word = body.split(None, 1)[0].lower() if body else ""
    if first_word not in ("select", "with"):
        return "SELECT 문이 아님"
    return None


def main() -> None:
    if not SEED_PATH.exists():
        print(f"시드 파일이 없습니다: {SEED_PATH}")
        sys.exit(1)

    errors: list[str] = []    # 반드시 고쳐야 하는 문제
    warnings: list[str] = []  # 확인이 필요한 의심 사항
    category_counts: Counter = Counter()  # 카테고리별 개수
    seen_questions: set[str] = set()      # 이미 나온 질문들 (중복 검사용)
    unique_sqls: set[str] = set()         # 서로 다른 SQL들

    conn = open_readonly()  # DB를 읽기 전용으로 연다
    try:
        with SEED_PATH.open(encoding="utf-8") as f:
            # enumerate(..., start=1): 줄 번호를 1부터 붙여 준다 (에러 위치 안내용)
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue  # 빈 줄은 건너뛴다

                # ---- 1) JSON 문법 검사 ----
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as e:
                    errors.append(f"{line_no}줄: JSON 문법 오류 - {e}")
                    continue

                # ---- 2) 필수 키 검사 ----
                if not isinstance(item, dict) or not REQUIRED_KEYS <= item.keys():
                    errors.append(
                        f"{line_no}줄: category/question/sql 세 키가 모두 필요함"
                    )
                    continue

                category = item["category"]
                question = item["question"]
                sql = item["sql"]

                # ---- 3) 카테고리 이름 검사 ----
                if category not in ALLOWED_CATEGORIES:
                    errors.append(f"{line_no}줄: 알 수 없는 category '{category}'")
                    continue
                category_counts[category] += 1

                # ---- 7) 질문 중복 검사 ----
                if question in seen_questions:
                    errors.append(f"{line_no}줄: 같은 질문이 중복됨 - {question}")
                seen_questions.add(question)

                # ---- 4) SELECT 한 문장인지 검사 ----
                reason = check_single_select(sql)
                if reason:
                    errors.append(f"{line_no}줄: {reason}")
                    continue

                # ---- 5) 실제로 실행해 보기 ----
                try:
                    rows = run_query(conn, sql)
                except sqlite3.Error as e:
                    errors.append(f"{line_no}줄: SQL 실행 에러 - {e}")
                    continue
                unique_sqls.add(sql.strip())

                # ---- 6) 빈 결과 / 0 하나뿐인 결과 경고 ----
                if not rows or rows == [(0,)]:
                    warnings.append(f"{line_no}줄: 결과가 비어 있거나 0 - {question}")

                # 눈으로 확인할 수 있게 한 줄씩 출력한다
                preview = str(rows[0])[:60] if rows else "(결과 없음)"
                print(f"{line_no:>3}줄 [{category:<12}] {question}")
                print(f"       -> {len(rows)}행, 첫 행: {preview}")
    finally:
        conn.close()  # 에러가 나도 DB 연결은 반드시 닫는다

    # ---------------- 요약 출력 ----------------
    print("\n" + "=" * 50)
    print("[카테고리별 개수] (목표 각 3개)")
    for category in sorted(ALLOWED_CATEGORIES):
        count = category_counts[category]
        mark = "OK" if count >= TARGET_PER_CATEGORY else "부족"
        print(f"  {category:<13} {count}개  {mark}")

    total = sum(category_counts.values())
    print(f"\n총 {total}개 / 서로 다른 정답 SQL {len(unique_sqls)}개")

    if warnings:
        print(f"\n[경고 {len(warnings)}건] (확인 필요)")
        for w in warnings:
            print("  -", w)
    if errors:
        print(f"\n[에러 {len(errors)}건] (반드시 수정)")
        for e in errors:
            print("  -", e)
        sys.exit(1)  # 0이 아닌 값으로 종료 = "실패했다"고 알림
    print("\n에러 없음")


# 이 파일을 직접 실행했을 때만 main()을 부릅니다.
if __name__ == "__main__":
    main()