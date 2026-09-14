"""
사기 패턴 탐지 룰 - 신축빌라 + 최근 소유주 변경 (설계문서 3.3절)
--------------------------------------------------------------------
건축주가 빌라를 짓고 세입자를 들인 직후 명의를 무자력자('바지사장')에게
넘기는 사기 패턴을 탐지한다. LTV가 낮아도(근저당이 적어도) 이 패턴이
맞물리면 위험 등급을 강제로 올려야 한다는 게 원래 스코어링 룰의 취지다.

이 모듈은 "룰 자체"만 구현한다. 필요한 입력값(사용승인일, 소유권 이전 이력)을
실제로 어떻게 얻을지는 별개 문제다:
  - useApprovalDate: BuildingRegisterAdapter가 이미 제공 (실사용 검증 완료)
  - ownershipHistory: registry_parser.parse_gapgu()가 본문 갑구 전체를 받으면
    이미 뽑아낼 수 있음 (다만 본문 OCR 품질이 아직 검증 전이라 데이터 확보
    경로만 미해결 — 룰 로직 자체는 지금 확정해서 테스트까지 끝내둔다).

나중에 실제 이력 데이터를 확보하면 이 함수를 그대로 호출하기만 하면 된다.
"""

from datetime import date

NEW_BUILDING_THRESHOLD_DAYS = 365  # 사용승인 후 이 기간 이내면 '신축'으로 간주
RECENT_OWNERSHIP_CHANGE_DAYS = 180  # 소유권 이전 후 이 기간 이내면 '최근 변경'으로 간주


def _parse_yyyymmdd(text: str) -> date | None:
    """건축물대장의 '20090211' 같은 8자리 날짜 문자열을 date로 변환."""
    if not text or len(text) != 8 or not text.isdigit():
        return None
    try:
        return date(int(text[0:4]), int(text[4:6]), int(text[6:8]))
    except ValueError:
        return None


def detect_new_villa_recent_ownership_change(
    use_approval_date: str,
    ownership_history: list[dict],
    as_of: date | None = None,
) -> dict:
    """
    설계문서 3.3절 룰: '신축빌라 + 6개월 내 소유주 변경' 패턴을 판별한다.

    Args:
        use_approval_date: 건축물대장의 사용승인일 ("YYYYMMDD", BuildingRegisterAdapter 출력)
        ownership_history: [{"date": "YYYY-MM-DD", "ownerName": str}, ...]
                            (registry_parser.parse_gapgu() 출력, 오래된 순으로 정렬 가정)
        as_of: 판단 기준일 (기본값: 오늘)

    Returns:
        {"triggered": bool, "reason": str, "isNewBuilding": bool, "isRecentOwnershipChange": bool}
        스코어링 룰 3.6절 순서에 따라 triggered=True면 최종 등급을 최소 warning으로 강제해야 한다.
    """
    if as_of is None:
        as_of = date.today()

    approval_date = _parse_yyyymmdd(use_approval_date)
    is_new_building = (
        approval_date is not None and (as_of - approval_date).days <= NEW_BUILDING_THRESHOLD_DAYS
    )

    is_recent_change = False
    latest_transfer_date = None
    if ownership_history:
        dated_entries = [h for h in ownership_history if h.get("date")]
        if dated_entries:
            latest = max(dated_entries, key=lambda h: h["date"])
            latest_transfer_date = date.fromisoformat(latest["date"])
            is_recent_change = (as_of - latest_transfer_date).days <= RECENT_OWNERSHIP_CHANGE_DAYS

    triggered = is_new_building and is_recent_change

    if triggered:
        reason = (
            f"신축(사용승인 {use_approval_date})이면서 "
            f"{latest_transfer_date.isoformat()}에 소유권이 변경됨 — "
            "신축빌라 명의이전 사기 패턴 의심"
        )
    elif is_new_building and not ownership_history:
        reason = "신축 건물이나 소유권 이전 이력 데이터가 없어 판별 불가"
    else:
        reason = "패턴 미해당"

    return {
        "triggered": triggered,
        "reason": reason,
        "isNewBuilding": is_new_building,
        "isRecentOwnershipChange": is_recent_change,
    }
