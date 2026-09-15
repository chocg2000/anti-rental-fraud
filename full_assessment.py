"""
전체 파이프라인 오케스트레이터 (README "다음 단계" 3번)
--------------------------------------------------------
개별 모듈 9개를 실제 서비스 흐름 순서대로 호출해서
"주소 입력 → 최종 신호등 등급"을 함수 하나로 완결시킨다.

인터페이스 계약:
  필수: address, target_area, my_deposit, contract_landlord_name
  선택: registry_summary_text, tax_clearance, ownership_history,
        registry_critical_keywords, property_type
  유저 자가확인 필수(건축물대장 API로 자동화 불가 — building_register_adapter.py 참고):
        user_confirmed_violation_building

이 함수는 새 비즈니스 로직을 추가하지 않는다 — 각 모듈이 이미 내는 status/confidence를
그대로 상위로 전파한다 (예: 공시가격 API 미연결 상태면 marketPriceConfidence
"unavailable"이 그대로 올라간다). 예외적으로 이 오케스트레이터가 직접 책임지는 것은 두 가지뿐이다:

  1. 단위 변환 — market_price_estimator/property_aggregator의 marketPrice는 "만원" 단위인데
     tenancy_safety_rules는 "원" 단위를 기대한다(test_tenancy_safety_rules.py 실사용 기준).
     여기서 변환하지 않으면 시세가 1만 배 작게 들어가 깡통전세 위험 판정이 완전히 틀어진다.
  2. 등기부 데이터 부재 처리 — senior_secured_amount를 확보 못했을 때 0으로 채우면
     "선순위채권 없음"이라는 거짓 안전 신호가 되므로, 이 경우 check_deposit_priority_risk를
     호출하지 않고 riskyDepositPriority=None(unknown)인 결과를 직접 구성한다.
"""

from datetime import date

from property_aggregator import get_property_info, PropertyAggregationError
from registry_summary_parser import parse_summary_registry
from tenancy_safety_rules import (
    check_deposit_priority_risk,
    check_landlord_identity_match,
    check_possession_priority_gap_risk,
    check_fixed_date_risk,
    check_minimum_priority_repayment,
)
from priority_region_classifier import classify_priority_region
from fraud_pattern_rules import detect_new_villa_recent_ownership_change
from tax_clearance_check import check_tax_clearance_certificate
from overall_safety_assessment import assess_overall_safety

USER_SELF_CHECK_VIOLATION_LABEL = "사용자 자가확인 — 위반건축물"

_WON_PER_MANWON = 10_000


def run_full_assessment(
    address: str,
    target_area: float,
    my_deposit: int,
    contract_landlord_name: str,
    property_type: str = "villa",
    as_of: date | None = None,
    registry_summary_text: str | None = None,
    tax_clearance: dict | None = None,
    ownership_history: list[dict] | None = None,
    registry_critical_keywords: list[str] | None = None,
    user_confirmed_violation_building: bool = False,
    move_in_date: str | None = None,
    has_fixed_date: bool | None = None,
) -> dict:
    """
    Args:
        address: 유저가 입력한 주소 (도로명/지번, 자유형식)
        target_area: 대상 전용면적 (㎡)
        my_deposit: 내가 들어갈 보증금 (원 단위)
        contract_landlord_name: 임대차 계약서상 임대인 이름
        property_type: "apartment" | "villa" | "officetel" | "multi_household".
            LTV 안전비율뿐 아니라 시세 산출 방식도 이 값에 좌우된다 — "apartment"가
            아니면 property_aggregator가 국토부 아파트 실거래 비교를 건너뛴다(연립다세대/
            오피스텔 실거래 API는 아직 미연동이라, 안 그러면 같은 동네 아파트 가격을
            빌라/다세대 시세인 것처럼 잘못 보여주게 된다 — property_aggregator.py 참고).
        as_of: 판단 기준일 (기본값: 오늘)
        registry_summary_text: 등기부등본 '주요 등기사항 요약' 페이지 OCR 원문 (선택 —
            없으면 깡통전세 위험은 unknown, 임대인 일치 확인도 unknown으로 나간다)
        tax_clearance: {"submitted": bool, "document_landlord_name": str | None,
            "issue_date": "YYYY-MM-DD" | None} (선택 — 아예 안 주면 체크 자체를 건너뛴다.
            submitted=False를 명시적으로 주면 "미제출" 자체가 warning으로 반영된다.)
        ownership_history: registry_parser.parse_gapgu() 출력 형식의 소유권 이전 이력
            (선택 — 본문 갑구 OCR 데이터 확보 경로가 아직 없어 대부분 비어있을 것으로 예상)
        registry_critical_keywords: 등기부 본문 갑구/을구 치명적 키워드
            (가압류/압류/가등기/가처분/경매개시결정/임차권등기명령) — 있으면 즉시 danger
        user_confirmed_violation_building: 유저가 직접 확인한 위반건축물 여부.
            건축물대장 API는 이 정보를 제공하지 않으므로 반드시 유저 자가확인
            체크리스트에서 받아와야 한다. True면 최종 등급이 danger로 강제된다.
        move_in_date: 잔금(입주)/전입신고 예정일 "YYYY-MM-DD" (선택 — 없으면 대항력
            공백 위험은 unknown으로 나간다)
        has_fixed_date: 확정일자를 받았는지 여부 (선택 — None이면 unknown으로 나간다.
            아직 안 받았다면 False를 명시적으로 줘야 "미확보" warning이 반영된다)

    Returns:
        {
            "overallGrade": "safe" | "caution" | "warning" | "danger" | "error",
            "reasons": [...],
            "propertyInfo": get_property_info() 결과 그대로 | None,
            "tenancySafety": {"depositPriorityRisk": ..., "landlordIdentityCheck": ...,
                              "possessionPriorityGapRisk": ..., "fixedDateRisk": ...,
                              "minimumPriorityRepayment": ...} | None,
            "fraudPatternResult": ... | None,
            "taxClearanceResult": ... | None,
        }
        주소 정규화 자체가 실패하면 overallGrade="error"로 나머지 조회 없이 즉시 반환한다
        (주소가 틀리면 뒤의 모든 조회가 무의미하므로 — property_aggregator.py와 같은 원칙).
    """
    if as_of is None:
        as_of = date.today()

    try:
        property_info = get_property_info(address, target_area, as_of=as_of, property_type=property_type)
    except PropertyAggregationError as e:
        return {
            "overallGrade": "error",
            "reasons": [str(e)],
            "propertyInfo": None,
            "tenancySafety": None,
            "fraudPatternResult": None,
            "taxClearanceResult": None,
        }

    if user_confirmed_violation_building:
        property_info["violationStatusConfirmed"] = True
        property_info["violationStatusRaw"] = USER_SELF_CHECK_VIOLATION_LABEL

    if registry_summary_text:
        registry = parse_summary_registry(registry_summary_text)
        registry_owners = registry["owners"]
        senior_secured_amount = registry["totalSeniorSecuredAmount"]
        active_rights = registry["activeRights"]
    else:
        registry_owners = []
        senior_secured_amount = None
        active_rights = []

    market_price_won = (
        property_info["marketPrice"] * _WON_PER_MANWON
        if property_info["marketPrice"] is not None else None
    )

    if senior_secured_amount is None:
        deposit_risk = {
            "riskyDepositPriority": None,
            "reason": "등기부등본 정보가 없어 선순위채권을 확인할 수 없습니다 — 등기부 요약 페이지를 제출해주세요.",
        }
    else:
        deposit_risk = check_deposit_priority_risk(
            market_price_won, senior_secured_amount, my_deposit, property_type,
            market_price_confidence=property_info["marketPriceConfidence"],
        )

    identity_check = check_landlord_identity_match(contract_landlord_name, registry_owners)
    possession_gap_risk = check_possession_priority_gap_risk(move_in_date, active_rights)
    fixed_date_risk = check_fixed_date_risk(has_fixed_date)

    normalized_address = property_info.get("normalizedAddress") or {}
    priority_region = classify_priority_region(
        normalized_address.get("roadAddress") or normalized_address.get("jibunAddress")
    )
    priority_repayment = check_minimum_priority_repayment(
        my_deposit, market_price_won, active_rights, priority_region, as_of=as_of
    )

    tenancy_safety = {
        "depositPriorityRisk": deposit_risk,
        "landlordIdentityCheck": identity_check,
        "possessionPriorityGapRisk": possession_gap_risk,
        "fixedDateRisk": fixed_date_risk,
        "minimumPriorityRepayment": priority_repayment,
    }

    fraud_pattern_result = None
    building_info = property_info.get("building")
    if building_info and building_info.get("useApprovalDate"):
        fraud_pattern_result = detect_new_villa_recent_ownership_change(
            building_info["useApprovalDate"], ownership_history or [], as_of=as_of
        )

    tax_clearance_result = None
    if tax_clearance is not None:
        tax_clearance_result = check_tax_clearance_certificate(
            submitted=tax_clearance.get("submitted", False),
            document_landlord_name=tax_clearance.get("document_landlord_name"),
            contract_landlord_name=contract_landlord_name,
            issue_date=tax_clearance.get("issue_date"),
            as_of=as_of,
        )

    overall = assess_overall_safety(
        tenancy_safety,
        property_info=property_info,
        fraud_pattern_result=fraud_pattern_result,
        registry_critical_keywords=registry_critical_keywords,
        tax_clearance_result=tax_clearance_result,
    )

    return {
        "overallGrade": overall["overallGrade"],
        "reasons": overall["reasons"],
        "propertyInfo": property_info,
        "tenancySafety": tenancy_safety,
        "fraudPatternResult": fraud_pattern_result,
        "taxClearanceResult": tax_clearance_result,
    }
