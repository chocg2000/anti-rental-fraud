"""
overall_safety_assessment 단위 테스트
"""

import unittest

from overall_safety_assessment import assess_overall_safety


def make_tenancy_safety(deposit_risky=False, identity_level="safe"):
    return {
        "depositPriorityRisk": {"riskyDepositPriority": deposit_risky, "reason": "테스트 사유"},
        "landlordIdentityCheck": {"riskLevel": identity_level, "reason": "테스트 사유"},
    }


class TestAssessOverallSafety(unittest.TestCase):

    def test_all_clean_is_safe(self):
        result = assess_overall_safety(make_tenancy_safety())
        self.assertEqual(result["overallGrade"], "safe")

    def test_critical_keyword_overrides_everything_to_danger(self):
        # 다른 건 다 안전해도 치명적 키워드 하나면 무조건 danger
        result = assess_overall_safety(
            make_tenancy_safety(deposit_risky=False, identity_level="safe"),
            registry_critical_keywords=["가압류"],
        )
        self.assertEqual(result["overallGrade"], "danger")

    def test_deposit_risk_alone_is_warning(self):
        result = assess_overall_safety(make_tenancy_safety(deposit_risky=True))
        self.assertEqual(result["overallGrade"], "warning")

    def test_landlord_mismatch_danger_propagates(self):
        result = assess_overall_safety(make_tenancy_safety(identity_level="danger"))
        self.assertEqual(result["overallGrade"], "danger")

    def test_co_owner_caution_alone_stays_caution(self):
        result = assess_overall_safety(make_tenancy_safety(identity_level="caution"))
        self.assertEqual(result["overallGrade"], "caution")

    def test_takes_highest_grade_among_multiple_signals(self):
        # caution급 임대인 이슈 + warning급 깡통전세 위험 -> 더 높은 warning이 최종
        result = assess_overall_safety(make_tenancy_safety(deposit_risky=True, identity_level="caution"))
        self.assertEqual(result["overallGrade"], "warning")

    def test_non_residential_use_risk_is_warning(self):
        result = assess_overall_safety(
            make_tenancy_safety(),
            property_info={"nonResidentialUseRisk": True},
        )
        self.assertEqual(result["overallGrade"], "warning")

    def test_violation_building_is_danger(self):
        result = assess_overall_safety(
            make_tenancy_safety(),
            property_info={"violationStatusConfirmed": True, "violationStatusRaw": "위반"},
        )
        self.assertEqual(result["overallGrade"], "danger")

    def test_fraud_pattern_triggered_is_warning(self):
        result = assess_overall_safety(
            make_tenancy_safety(),
            fraud_pattern_result={"triggered": True, "reason": "신축+소유주변경 패턴"},
        )
        self.assertEqual(result["overallGrade"], "warning")

    def test_tax_clearance_not_submitted_is_warning(self):
        result = assess_overall_safety(
            make_tenancy_safety(),
            tax_clearance_result={"submitted": False, "riskLevel": "warning", "reason": "미제출"},
        )
        self.assertEqual(result["overallGrade"], "warning")

    def test_tax_clearance_name_mismatch_is_danger(self):
        result = assess_overall_safety(
            make_tenancy_safety(),
            tax_clearance_result={"submitted": True, "riskLevel": "danger", "reason": "명의 불일치"},
        )
        self.assertEqual(result["overallGrade"], "danger")

    def test_tax_clearance_safe_does_not_affect_grade(self):
        result = assess_overall_safety(
            make_tenancy_safety(),
            tax_clearance_result={"submitted": True, "riskLevel": "safe", "reason": "이상 없음"},
        )
        self.assertEqual(result["overallGrade"], "safe")

    def test_real_document_scenario_combined(self):
        # 실제 검증 문서 기준: 임대인 불일치(danger) + 깡통전세 위험(warning) 동시 발생
        tenancy = {
            "depositPriorityRisk": {"riskyDepositPriority": True, "reason": "선순위+보증금이 시세 초과"},
            "landlordIdentityCheck": {"riskLevel": "danger", "reason": "임대인 불일치"},
        }
        result = assess_overall_safety(tenancy)
        self.assertEqual(result["overallGrade"], "danger")
        self.assertEqual(len(result["reasons"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
