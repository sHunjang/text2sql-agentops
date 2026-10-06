-- ============================================================
-- AgentOps 에이전트 실행 로그 스키마 (SQLite)
-- 이 파일이 프로젝트 전체의 "단일 진실 공급원(SSOT)"입니다.
-- 학습 데이터 / 평가 DB / 시스템 프롬프트는 모두 이 파일을 기준으로 합니다.
-- ============================================================

-- [1] agents: AI 에이전트 목록 (예: 코드 리뷰 에이전트, 검색 에이전트)
CREATE TABLE agents (
    agent_id    INTEGER PRIMARY KEY,   -- 에이전트 고유 번호
    name        TEXT NOT NULL UNIQUE,  -- 에이전트 이름 (예: 'code-reviewer')
    role        TEXT NOT NULL,         -- 역할: 'planner', 'coder', 'reviewer', 'researcher'
    model_name  TEXT NOT NULL,         -- 에이전트가 사용하는 LLM 이름
    created_at  TEXT NOT NULL          -- 생성 시각 (예: '2026-01-10 09:00:00')
);

-- [2] executions: 에이전트가 한 번 일을 수행한 기록 (1 에이전트 : N 실행)
CREATE TABLE executions (
    execution_id  INTEGER PRIMARY KEY,                -- 실행 고유 번호
    agent_id      INTEGER NOT NULL
                  REFERENCES agents(agent_id),        -- 어느 에이전트의 실행인지 (외래키)
    status        TEXT NOT NULL
                  CHECK (status IN ('success', 'failed', 'timeout')),  -- 실행 결과
    started_at    TEXT NOT NULL,                      -- 실행 시작 시각
    duration_ms   INTEGER NOT NULL,                   -- 걸린 시간 (밀리초)
    total_tokens  INTEGER NOT NULL,                   -- 사용한 토큰 수
    cost_usd      REAL NOT NULL,                      -- 비용 (미국 달러)
    error_message TEXT                                -- 실패 사유 (성공이면 NULL)
);

-- [3] tool_calls: 실행 중에 에이전트가 호출한 도구 기록 (1 실행 : N 도구 호출)
CREATE TABLE tool_calls (
    tool_call_id  INTEGER PRIMARY KEY,                -- 도구 호출 고유 번호
    execution_id  INTEGER NOT NULL
                  REFERENCES executions(execution_id), -- 어느 실행에서 호출했는지 (외래키)
    tool_name     TEXT NOT NULL,                      -- 도구 이름 (예: 'web_search', 'run_code')
    status        TEXT NOT NULL
                  CHECK (status IN ('success', 'failed')),  -- 호출 결과
    latency_ms    INTEGER NOT NULL,                   -- 응답 시간 (밀리초)
    called_at     TEXT NOT NULL                       -- 호출 시각
);