"""
진단 결과 저장소 (SQLite)
--------------------------
POST /assessment가 계산한 결과를 프로세스 재시작에도 살아남게 저장한다.

이전엔 api.py의 인메모리 dict(_ASSESSMENT_STORE)에만 있어서 서버가 재시작하면
결과가 전부 사라지고, 유저가 공유한 /result/:id 링크가 배포할 때마다 깨졌다.
SQLite를 고른 이유: 이 앱은 아직 단일 프로세스/단일 워커로 돌아가는 프로토타입
단계라 별도 서비스(Redis 등)를 운영 부담 없이 붙일 이유가 없다 — 파일 하나로
동작하고, Docker에서는 볼륨 하나만 마운트하면 컨테이너 재배포에도 살아남는다.
여러 워커/여러 서버로 스케일하게 되면 그때는 Redis 같은 공유 스토어로 옮겨야
한다(SQLite 파일은 워커마다 따로 열리면 잠금 경합이 심해진다).

연결을 지연 생성해서 모듈 전역에 하나만 캐싱하고, 매 호출을 락(threading.Lock)으로
직렬화한다 — FastAPI의 동기 엔드포인트는 스레드풀에서 실행되므로 여러 스레드가
동시에 호출할 수 있는데, sqlite3 커넥션 하나를 스레드마다 새로 만들었다 버리는
대신(그러면 :memory: 테스트가 매번 빈 DB를 보게 된다) 커넥션을 재사용하고 락으로
보호하는 쪽이 이 트래픽 규모에서는 더 단순하고 테스트하기도 쉽다.
"""

import json
import os
import sqlite3
import threading
from pathlib import Path

DB_PATH = os.environ.get("ASSESSMENT_DB_PATH", "data/assessments.db")

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        if DB_PATH != ":memory:":
            Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.execute(
            "CREATE TABLE IF NOT EXISTS assessments ("
            "id TEXT PRIMARY KEY, "
            "data TEXT NOT NULL, "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        _conn.commit()
    return _conn


def save_assessment(assessment_id: str, data: dict) -> None:
    with _lock:
        conn = _get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO assessments (id, data) VALUES (?, ?)",
            (assessment_id, json.dumps(data, ensure_ascii=False)),
        )
        conn.commit()


def cleanup_old_assessments(days: int = 30) -> int:
    """
    30일 이상 지난 진단 결과를 삭제한다.

    이 함수는 README/개인정보처리방침에서 약속한 보관기간과 실제 동작을 맞추기 위한
    최소 구현이다. API startup 시점에서 한 번 호출되고, 추가 운영 환경에서는 주기적
    백그라운드 스케줄러로 재호출하면 된다.
    """
    if days < 0:
        raise ValueError("days must be >= 0")

    with _lock:
        conn = _get_conn()
        deleted = conn.execute(
            "DELETE FROM assessments WHERE created_at < datetime('now', '-' || ? || ' days')",
            (str(days),),
        )
        conn.commit()
        return deleted.rowcount


def get_assessment(assessment_id: str) -> dict | None:
    with _lock:
        conn = _get_conn()
        row = conn.execute(
            "SELECT data FROM assessments WHERE id = ?", (assessment_id,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def reset_for_testing() -> None:
    """
    테스트 전용 — 모듈이 캐싱한 커넥션을 닫고 비운다. DB_PATH를 ":memory:"로 바꾼 뒤
    이 함수를 불러야 다음 _get_conn() 호출이 새 인메모리 DB로 다시 연결된다(안 그러면
    이전 테스트의 커넥션을 계속 재사용해서 데이터가 테스트 간에 새어나간다).
    """
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
        _conn = None
