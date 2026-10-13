"""
build_sample_db.py
==================
채점/검증용 "샘플 DB"를 만드는 스크립트입니다.

하는 일 (순서대로):
  1. schema.sql을 읽어서 빈 테이블 3개를 만든다.
  2. 가짜 에이전트 / 실행 기록 / 도구 호출 기록을 랜덤으로 채운다.
  3. 요약 정보를 출력해서 데이터가 제대로 들어갔는지 눈으로 확인한다.

중요한 점:
  - 랜덤 시드를 고정했기 때문에, 몇 번을 실행해도 "똑같은" DB가 만들어집니다.
    (그래야 평가 결과를 다른 사람도 재현할 수 있습니다.)
  - 테이블 구조는 이 파일에 직접 쓰지 않고 schema.sql에서 읽어옵니다.
    (스키마를 한 곳에서만 관리하기 위해서입니다.)

실행 방법 (프로젝트 최상위 폴더에서):
  python scripts/build_sample_db.py
"""

import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


# 1. 경로와 설정값

# __file__ 은 "지금 이 파이썬 파일의 위치"입니다.
# .parent 를 두 번 쓰면 scripts/ 의 한 단계 위, 즉 프로젝트 최상위 폴더가 됩니다.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 스키마 파일(테이블 구조)의 위치
SCHEMA_PATH = PROJECT_ROOT / "src" / "text2sql" / "schema.sql"

# 만들어질 DB 파일의 위치
DB_PATH = PROJECT_ROOT / "data" / "sample.db"

# 난수 생성기의 시작 번호. 이 숫자가 같으면 항상 같은 "랜덤" 결과가 나옵니다.
RANDOM_SEED = 42

# 가짜 로그가 존재하는 기간
DATA_START = datetime(2026, 1, 1, 0, 0, 0)
DATA_END = datetime(2026, 3, 31, 23, 59, 59)

# 만들 실행 기록(executions)의 개수
NUM_EXECUTIONS = 600

# 날짜를 문자열로 저장할 때 쓰는 형식. 예: '2026-03-15 09:30:00'
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 2. 가짜 데이터의 재료

# 에이전트 8명. 각 항목의 의미:
#   (이름, 역할, 사용 모델, 실행 비중, 실패 확률, 타임아웃 확률)
# - "실행 비중"이 클수록 일을 더 자주 하는 에이전트입니다.
# - 실패 확률을 에이전트마다 다르게 해서, "실패 많은 순" 순위가 뚜렷해지게 합니다.
AGENTS = [
    ("code-reviewer", "reviewer", "medium-model-v2", 14, 0.10, 0.03),
    ("code-writer", "coder", "large-model-v1", 18, 0.18, 0.05),
    ("web-researcher", "researcher", "medium-model-v2", 12, 0.25, 0.10),
    ("task-planner", "planner", "large-model-v1", 10, 0.05, 0.02),
    ("doc-summarizer", "researcher", "small-model-v1", 8, 0.08, 0.01),
    ("test-generator", "coder", "small-model-v1", 15, 0.30, 0.06),
    ("bug-triager", "reviewer", "small-model-v1", 9, 0.14, 0.04),
    ("data-analyst", "researcher", "large-model-v1", 11, 0.22, 0.08),
]

# 모델별 토큰 1개당 가격(달러). 큰 모델일수록 비쌉니다. (가상의 값)
MODEL_COST_PER_TOKEN = {
    "large-model-v1": 0.00003,
    "medium-model-v2": 0.000012,
    "small-model-v1": 0.000004,
}

# 도구 6종. 각 항목의 의미:
#   (도구 이름, 호출 비중, 최소 응답시간ms, 최대 응답시간ms, 실패 확률)
TOOLS = [
    ("web_search", 25, 600, 3000, 0.08),
    ("run_code", 20, 200, 5000, 0.15),
    ("read_file", 20, 20, 300, 0.03),
    ("write_file", 10, 30, 400, 0.04),
    ("sql_query", 15, 50, 1500, 0.10),
    ("http_request", 10, 300, 4000, 0.18),
]

# 실패한 실행에 붙일 에러 메시지 후보
ERROR_MESSAGES = [
    "Rate limit exceeded",
    "Tool call failed",
    "Invalid JSON in model output",
    "Context length exceeded",
    "Authentication error",
    "Upstream service unavailable",
]


# 3. 데이터를 만드는 함수들

def random_datetime(rng: random.Random, start: datetime, end: datetime) -> datetime:
    """start와 end 사이의 무작위 시각 하나를 돌려줍니다."""
    total_seconds = int((end - start).total_seconds())
    return start + timedelta(seconds=rng.randint(0, total_seconds))


def make_agents(rng: random.Random) -> list[tuple]:
    """agents 테이블에 넣을 행(row)들을 만듭니다."""
    rows = []
    # enumerate(..., start=1) 은 번호를 1부터 붙여 줍니다. 이 번호가 agent_id가 됩니다.
    for agent_id, agent in enumerate(AGENTS, start=1):
        name, role, model_name = agent[0], agent[1], agent[2]
        # 에이전트는 로그 기간 이전(2025년 12월)에 만들어진 것으로 합니다.
        created_at = random_datetime(
            rng, datetime(2025, 12, 1), datetime(2025, 12, 31, 23, 59, 59)
        )
        rows.append((agent_id, name, role, model_name, created_at.strftime(DATE_FORMAT)))
    return rows


def make_executions(rng: random.Random) -> list[tuple]:
    """executions 테이블에 넣을 행들을 만듭니다."""
    agent_ids = list(range(1, len(AGENTS) + 1))
    weights = [agent[3] for agent in AGENTS]  # 에이전트별 실행 비중

    drafts = []  # 아직 execution_id를 안 붙인 "초안" 목록
    for _ in range(NUM_EXECUTIONS):
        # 비중(weights)에 따라 에이전트를 하나 뽑습니다.
        agent_id = rng.choices(agent_ids, weights=weights, k=1)[0]
        agent = AGENTS[agent_id - 1]
        model_name, fail_prob, timeout_prob = agent[2], agent[4], agent[5]

        started_at = random_datetime(rng, DATA_START, DATA_END)

        # 0~1 사이 숫자를 하나 뽑아서 결과(성공/실패/타임아웃)를 정합니다.
        roll = rng.random()
        if roll < fail_prob:
            status = "failed"
            duration_ms = rng.randint(300, 15000)
            error_message = rng.choice(ERROR_MESSAGES)
        elif roll < fail_prob + timeout_prob:
            status = "timeout"
            duration_ms = rng.randint(30000, 60000)
            error_message = "Execution timed out"
        else:
            status = "success"
            duration_ms = rng.randint(800, 20000)
            error_message = None  # 성공이면 에러 메시지가 없으므로 NULL

        total_tokens = rng.randint(500, 12000)
        # 비용 = 토큰 수 x 모델별 단가 x 약간의 변동(0.8~1.2배)
        # 소수 6자리까지 남겨서, 서로 값이 같은(동점) 경우가 거의 없게 합니다.
        cost_usd = round(
            total_tokens * MODEL_COST_PER_TOKEN[model_name] * rng.uniform(0.8, 1.2), 6
        )

        drafts.append(
            (started_at, agent_id, status, duration_ms, total_tokens, cost_usd, error_message)
        )

    # 시간 순서대로 정렬한 뒤 번호를 붙입니다.
    # (그래야 execution_id가 클수록 나중에 일어난 실행이 되어 실제 로그와 비슷해집니다.)
    drafts.sort(key=lambda draft: draft[0])

    rows = []
    for execution_id, draft in enumerate(drafts, start=1):
        started_at, agent_id, status, duration_ms, total_tokens, cost_usd, error_message = draft
        rows.append(
            (
                execution_id,
                agent_id,
                status,
                started_at.strftime(DATE_FORMAT),
                duration_ms,
                total_tokens,
                cost_usd,
                error_message,
            )
        )
    return rows


def make_tool_calls(rng: random.Random, execution_rows: list[tuple]) -> list[tuple]:
    """tool_calls 테이블에 넣을 행들을 만듭니다. (실행 하나당 도구 호출 0~6개)"""
    tool_names = [tool[0] for tool in TOOLS]
    tool_weights = [tool[1] for tool in TOOLS]
    tool_info = {tool[0]: tool for tool in TOOLS}  # 이름으로 정보를 빨리 찾기 위한 사전

    rows = []
    tool_call_id = 1  # 도구 호출 번호 (1부터 하나씩 증가)

    for execution in execution_rows:
        # execution 한 줄은 (id, agent_id, status, started_at, duration_ms, ...) 순서입니다.
        execution_id, exec_status = execution[0], execution[2]
        started_at_text, duration_ms = execution[3], execution[4]

        # 약 12%의 실행은 도구를 한 번도 안 부릅니다. (LEFT JOIN 질문용)
        if rng.random() < 0.12:
            continue

        num_calls = rng.randint(1, 6)
        started_at = datetime.strptime(started_at_text, DATE_FORMAT)

        # 도구 호출 시점: 실행 시간 안의 임의 지점들을 오름차순으로 뽑습니다.
        fractions = sorted(rng.random() for _ in range(num_calls))

        for index, fraction in enumerate(fractions):
            tool_name = rng.choices(tool_names, weights=tool_weights, k=1)[0]
            _, _, latency_min, latency_max, tool_fail_prob = tool_info[tool_name]

            is_last_call = index == num_calls - 1
            if exec_status == "failed" and is_last_call:
                # 실패한 실행은 마지막 도구 호출도 실패한 것으로 해서 현실감을 줍니다.
                status = "failed"
            else:
                status = "failed" if rng.random() < tool_fail_prob else "success"

            called_at = started_at + timedelta(milliseconds=int(duration_ms * fraction))

            rows.append(
                (
                    tool_call_id,
                    execution_id,
                    tool_name,
                    status,
                    rng.randint(latency_min, latency_max),
                    called_at.strftime(DATE_FORMAT),
                )
            )
            tool_call_id += 1

    return rows


# 4. 만들어진 DB를 눈으로 확인하는 함수

def print_summary(conn: sqlite3.Connection) -> None:
    """데이터가 제대로 들어갔는지 요약 정보를 출력합니다."""
    print("\n[테이블별 행 개수]")
    # 아래 테이블 이름은 이 파일 안에 직접 적은 고정값이라 안전합니다.
    # (사용자 입력을 SQL 문자열에 끼워 넣는 것은 위험하므로 절대 하면 안 됩니다.)
    for table in ("agents", "executions", "tool_calls"):
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {table:<12} {count:>6}행")

    print("\n[에이전트별 실패(failed) 횟수 - 많은 순]")
    rows = conn.execute(
        """
        SELECT a.name, COUNT(*) AS failed_count
        FROM executions e
        JOIN agents a ON a.agent_id = e.agent_id
        WHERE e.status = 'failed'
        GROUP BY a.agent_id
        ORDER BY failed_count DESC
        """
    ).fetchall()
    for name, failed_count in rows:
        print(f"  {name:<16} {failed_count:>4}")

    no_tool = conn.execute(
        """
        SELECT COUNT(*) FROM executions e
        WHERE NOT EXISTS (
            SELECT 1 FROM tool_calls t WHERE t.execution_id = e.execution_id
        )
        """
    ).fetchone()[0]
    print(f"\n[도구 호출이 0건인 실행] {no_tool}건")

    # 외래키가 가리키는 대상이 실제로 존재하는지 검사합니다. 문제 없으면 0건이어야 합니다.
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    print(f"[외래키 위반] {len(violations)}건")


# 5. 전체 흐름

def main() -> None:
    # Random(시드)로 "이 스크립트 전용" 난수 생성기를 만듭니다.
    # 다른 곳의 랜덤과 섞이지 않아서 항상 같은 결과가 나옵니다.
    rng = random.Random(RANDOM_SEED)

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)  # data/ 폴더가 없으면 만든다
    if DB_PATH.exists():
        DB_PATH.unlink()  # 이전에 만든 DB가 있으면 지우고 처음부터 다시 만든다

    conn = sqlite3.connect(DB_PATH)
    try:
        # SQLite는 기본적으로 외래키 규칙을 "검사하지 않습니다".
        # 이 설정을 켜야 잘못된 연결(없는 agent_id 등)을 넣을 때 에러가 납니다.
        conn.execute("PRAGMA foreign_keys = ON")

        # 1) 스키마 파일을 읽어서 테이블 3개를 만든다.
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        # 2) 데이터를 만든다. (부모 테이블 -> 자식 테이블 순서)
        agent_rows = make_agents(rng)
        execution_rows = make_executions(rng)
        tool_call_rows = make_tool_calls(rng, execution_rows)

        # 3) DB에 넣는다. ? 는 값이 들어갈 자리 표시자입니다.
        conn.executemany(
            "INSERT INTO agents (agent_id, name, role, model_name, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            agent_rows,
        )
        conn.executemany(
            "INSERT INTO executions (execution_id, agent_id, status, started_at, "
            "duration_ms, total_tokens, cost_usd, error_message) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            execution_rows,
        )
        conn.executemany(
            "INSERT INTO tool_calls (tool_call_id, execution_id, tool_name, status, "
            "latency_ms, called_at) VALUES (?, ?, ?, ?, ?, ?)",
            tool_call_rows,
        )
        conn.commit()  # commit을 해야 변경 내용이 파일에 실제로 저장됩니다.

        print(f"샘플 DB 생성 완료: {DB_PATH}")
        print_summary(conn)
    finally:
        conn.close()  # 에러가 나도 DB 연결은 반드시 닫는다


# 이 파일을 직접 실행했을 때만 main()을 부릅니다.
# (다른 파일에서 import만 할 때는 실행되지 않게 하는 파이썬의 관례입니다.)
if __name__ == "__main__":
    main()