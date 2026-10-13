"""
dbutil.py
=========
여러 스크립트가 함께 쓰는 "DB 관련 도우미 함수" 모음입니다.

왜 따로 파일로 뺐나요?
  시드 검증, 합성 데이터 검증, 평가(6단계)에서 모두 "DB를 읽기 전용으로 열고,
  'now'를 고정 시각으로 바꿔서 실행"하는 같은 작업을 합니다.
  이 로직을 파일마다 복사해 두면, 나중에 고칠 때 한 곳만 고치고 나머지는 빼먹는
  사고가 납니다. 한 곳에 모아 두고 가져다 쓰는 것이 안전합니다.
"""

import sqlite3
from pathlib import Path

# 프로젝트 최상위 폴더 (이 파일은 scripts/ 안에 있으니 한 단계 위)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 채점/검증에 쓰는 샘플 DB의 위치
DB_PATH = PROJECT_ROOT / "data" / "sample.db"

# "지금"을 이 시각으로 고정합니다 (time freeze).
# 샘플 데이터가 2026-01-01 ~ 2026-03-31 이므로, 그 다음 날 0시로 잡았습니다.
# 이렇게 하면 "최근 7일" 같은 질문의 정답이 언제 실행해도 항상 같습니다.
FROZEN_NOW = "2026-04-01 00:00:00"


def freeze_now(sql: str) -> str:
    """SQL 안의 'now' 를 고정 시각으로 바꿔서 돌려줍니다.

    예: datetime('now', '-7 days')
     -> datetime('2026-04-01 00:00:00', '-7 days')
    """
    return sql.replace("'now'", f"'{FROZEN_NOW}'")


def open_readonly(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """DB를 '읽기 전용'으로 엽니다.

    읽기 전용이면 검증하려는 SQL에 실수로 DELETE 같은 문장이 섞여 있어도
    데이터가 지워지지 않습니다. (이 프로젝트의 안전장치 중 하나입니다.)
    mode=ro 는 read-only(읽기 전용)의 약자입니다.
    """
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def run_query(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    """SQL을 (now 고정 후) 실행하고 결과 행 전체를 리스트로 돌려줍니다.

    SQL에 문제가 있으면 sqlite3.Error 계열의 에러가 그대로 발생합니다.
    에러를 어떻게 처리할지는 이 함수를 부르는 쪽이 정합니다.
    """
    return conn.execute(freeze_now(sql)).fetchall()