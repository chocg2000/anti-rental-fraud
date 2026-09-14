"""
종합 위험 등급 산출 (설계문서 3.6절 신호등 시스템)
------------------------------------------------------
지금까지 만든 조각들이 이미 낸 결과를 받아서 조합만 한다:
  - PropertyAggregator.get_property_info() -> 시세, 건축물대장 정보
  - RegistrySummaryParser.parse_summary_registry() -> 소유자, 선순위채권 합계
  - TenancySafetyRules.evaluate_tenancy_safety() -> 깡통전세 위험, 임대인 일치 여부
  - FraudPatternRules.detect_new_villa_recent_ownership_change() -> 신축빌라 패턴 (선택)

이 함수는 새로운 API를 호출하지 않는다 — 순수하게 "이미 나온 결과들을 어떻게
합쳐서 하나의 등급으로 만들지"만 책임진다. 그래서 각 조각을 재검증할 필요 없이
조합 로직만 테스트하면 된다.
"""

from typing import Literal

Grade = Literal["safe", "caution", "warning", "danger"]

_GRADE_RANK = {"safe": 0, "caution": 1, "warning": 2, "danger": 3}


def _max_grade(*grades: str) -> Grade:
    return max(grades, key=lambda g: _GRADE_RANK.get(g, 0))


def assess_overall_safety(
    tenancy_safety: dict,
    property_info: dict | None = None,
    fraud_pattern_result: dict | None = None,
    registry_critical_keywords: list[str] | None = None,
    tax_clearance_result: dict | None = None,
) -> dict:
    """
    각 조각의 결과를 3.6절 우선순위대로 합쳐 최종 등급(overallGrade)과 근거를 만든다.

    Args:
        tenancy_safety: tenancy_safety_rules.evaluate_tenancy_safety() 결과
        property_info: property_aggregator.get_property_info() 결과 (선택 —
                        nonResidentialUseRisk, violationStatus 등 활용)
        fraud_pattern_result: fraud_pattern_rules.detect_new_villa_recent_ownership_change()
                               결과 (선택 — 소유권 이전 이력을 아직 못 구했으면 생략 가능)
        registry_critical_keywords: registry_parser.parse_gapgu()/parse_eulgu()가 뽑은
                                     치명적 키워드 리스트 (선택 — 본문 갑구/을구 OCR을
                                     아직 못 구했으면 생략 가능. 하나라도 있으면 즉시 danger.)
        tax_clearance_result: tax_clearance_check.check_tax_clearance_certificate() 결과 (선택)
    """
    grade: Grade = "safe"
    reasons: list[str] = []

    # 3.6절 1순위: 등기부 치명적 키워드 — 있으면 즉시 danger, 다른 판단 무의미
    if registry_critical_keywords:
        return {
            "overallGrade": "danger",
            "reasons": [f"등기부에 치명적 키워드 검출: {', '.join(registry_critical_keywords)}"],
        }

    deposit_risk = tenancy_safety.get("depositPriorityRisk", {})
    if deposit_risk.get("riskyDepositPriority") is True:
        grade = _max_grade(grade, "warning")
        reasons.append(f"깡통전세 위험 — {deposit_risk.get('reason', '')}")
    elif deposit_risk.get("riskyDepositPriority") is None:
        reasons.append("시세 데이터 부족으로 깡통전세 위험 판단 불가 (참고용 미확인 표시 필요)")

    identity_check = tenancy_safety.get("landlordIdentityCheck", {})
    identity_risk_level = identity_check.get("riskLevel", "unknown")
    if identity_risk_level in ("caution", "warning", "danger"):
        grade = _max_grade(grade, identity_risk_level)
        reasons.append(f"임대인 확인 필요 — {identity_check.get('reason', '')}")

    if property_info:
        if property_info.get("nonResidentialUseRisk"):
            grade = _max_grade(grade, "warning")
            reasons.append("건축물대장상 주용도가 근린생활시설 등 비주거 — 근생빌라(불법 개조) 의심")

        if property_info.get("violationStatusConfirmed") and property_info.get("violationStatusRaw"):
            grade = _max_grade(grade, "danger")
            reasons.append(f"위반건축물로 확인됨 ({property_info['violationStatusRaw']})")

    if fraud_pattern_result and fraud_pattern_result.get("triggered"):
        grade = _max_grade(grade, "warning")
        reasons.append(fraud_pattern_result.get("reason", "신축빌라 명의변경 패턴 의심"))

    if tax_clearance_result:
        tax_risk_level = tax_clearance_result.get("riskLevel", "unknown")
        if tax_risk_level in ("caution", "warning", "danger"):
            grade = _max_grade(grade, tax_risk_level)
            reasons.append(f"완납증명서 확인 필요 — {tax_clearance_result.get('reason', '')}")

    if not reasons:
        reasons.append("특이 위험 신호가 발견되지 않았습니다.")

    return {"overallGrade": grade, "reasons": reasons}
