"""
IP 기반 요청 속도 제한 (인메모리, 슬라이딩 윈도우)
--------------------------------------------------
B2C 무료 버전은 회원가입/로그인이 없어서 유저를 구분할 유일한 단서가 클라이언트
IP뿐이다. `/assessment`(카카오/국토부/VWorld 쿼터를 소모)와 `/registry/upload`
(tesseract/poppler를 돌리는 CPU 집약적 엔드포인트)에 인증 없이 무제한 반복 호출이
가능하면, 봇이 두드릴 때 외부 API 일일 쿼터가 먼저 소진되거나 서버가 느려져서
정상 유저가 피해를 본다(OWASP API4:2023 Unrestricted Resource Consumption).

Redis 등 공유 저장소를 쓰지 않고 프로세스 메모리 dict로 직접 구현한다 — 이
프로젝트는 아직 단일 워커 프로토타입 전제라(assessment_store.py의 SQLite 선택과
같은 근거), 여러 워커/여러 서버로 스케일하기 전까지는 이 정도로 충분하다. 여러
워커로 스케일하면 워커마다 카운터가 따로 놀아 실제 허용량이 워커 수만큼 늘어나므로,
그때는 Redis 같은 공유 저장소로 옮겨야 한다.
"""

import threading
import time

_lock = threading.Lock()
_requests: dict[str, list[float]] = {}


def is_rate_limited(
    client_ip: str, bucket: str, max_requests: int, window_seconds: float = 60.0,
) -> bool:
    """
    (bucket, client_ip) 조합이 최근 window_seconds 동안 max_requests번을 이미
    썼으면 True(차단 대상)를 반환한다. 차단 대상이 아니면 이번 요청을 기록하고
    False를 반환한다 — 그래서 이 함수는 "확인"이 아니라 "확인하면서 소비"까지 한다.

    bucket은 엔드포인트별로 카운터를 분리하기 위한 키다(예: "assessment",
    "registry_upload") — 한 IP가 한쪽을 다 써도 다른 쪽엔 영향이 없어야 한다.
    """
    now = time.monotonic()
    cutoff = now - window_seconds
    key = f"{bucket}:{client_ip}"

    with _lock:
        timestamps = [t for t in _requests.get(key, []) if t >= cutoff]
        if len(timestamps) >= max_requests:
            _requests[key] = timestamps
            return True
        timestamps.append(now)
        _requests[key] = timestamps
        return False


def reset_for_testing() -> None:
    """테스트 전용 — 누적된 요청 기록을 전부 지운다."""
    with _lock:
        _requests.clear()
