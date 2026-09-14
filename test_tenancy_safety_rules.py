"""
tenancy_safety_rules 단위 테스트
"""

import unittest

from tenancy_safety_rules import (
    check_deposit_priority_risk,
    check_landlord_identity_match,
    evaluate_tenancy_safety,
)


class TestDepositPriorityRisk(unittest.TestCase):

    def test_safe_when_below_threshold(self):
        result = check_deposit_priority_risk(
            market_price=500_000_000, senior_secured_amount=0,
            my_deposit=300_000_000, property_type="villa",
        )
        # 300,000,000 <= 500,000,000*0.7=350,000,000 -> 안전
        self.assertFalse(result["riskyDepositPriority"])

    def test_risky_when_exceeds_threshold(self):
        result = check_deposit_priority_risk(
            market_price=500_000_000, senior_secured_amount=100_000_000,
            my_deposit=300_000_000, property_type="villa",
        )
        # 100,000,000 + 300,000,000 = 400,000,000 > 350,000,000 -> 위험
        self.assertTrue(result["riskyDepositPriority"])

    def test_apartment_uses_higher_threshold_than_villa(self):
        common_kwargs = dict(market_price=500_000_000, senior_secured_amount=0, my_deposit=380_000_000)
        villa_result = check_deposit_priority_risk(**common_kwargs, property_type="villa")
        apt_result = check_deposit_priority_risk(**common_kwargs, property_type="apartment")

        # 380,000,000은 빌라 임계치(350,000,000) 초과라 위험, 아파트 임계치(400,000,000)는 이내라 안전
        self.assertTrue(villa_result["riskyDepositPriority"])
        self.assertFalse(apt_result["riskyDepositPriority"])

    def test_no_market_price_returns_unknown(self):
        result = check_deposit_priority_risk(
            market_price=None, senior_secured_amount=0, my_deposit=300_000_000,
        )
        self.assertIsNone(result["riskyDepositPriority"])

    def test_real_document_case_jeonse_right_as_senior_claim(self):
        # 실제 검증 문서(성남 야탑동) 사례: 선순위 전세권 3억이 이미 있는 집에
        # 내가 2억 보증금으로 들어가려는 경우 -> 총 5억이 시세를 넘으면 위험
        result = check_deposit_priority_risk(
            market_price=600_000_000, senior_secured_amount=300_000_000,
            my_deposit=200_000_000, property_type="apartment",
        )
        # 5억 <= 6억*0.8=4.8억? -> 5억 > 4.8억 이므로 위험
        self.assertTrue(result["riskyDepositPriority"])

    def test_default_confidence_is_high_and_not_flagged_as_estimated(self):
        # market_price_confidence를 안 넘기면 기존 호출부(vworld 연동 전)와 100% 호환돼야 함
        result = check_deposit_priority_risk(
            market_price=500_000_000, senior_secured_amount=0, my_deposit=300_000_000,
        )
        self.assertEqual(result["marketPriceConfidence"], "high")
        self.assertFalse(result["priceIsEstimated"])
        self.assertNotIn("공시가격 추정치", result["reason"])

    def test_estimated_from_public_price_flags_and_appends_caution(self):
        result = check_deposit_priority_risk(
            market_price=500_000_000, senior_secured_amount=0, my_deposit=300_000_000,
            property_type="villa", market_price_confidence="estimated_from_public_price",
        )
        self.assertTrue(result["priceIsEstimated"])
        self.assertEqual(result["marketPriceConfidence"], "estimated_from_public_price")
        self.assertIn("공시가격 추정치", result["reason"])

    def test_estimated_from_public_price_still_computes_risk_correctly(self):
        # 신뢰도 캡션이 붙어도 위험/안전 판정 자체(숫자 비교)는 그대로 정확해야 함
        result = check_deposit_priority_risk(
            market_price=500_000_000, senior_secured_amount=100_000_000, my_deposit=300_000_000,
            property_type="villa", market_price_confidence="estimated_from_public_price",
        )
        # 100,000,000 + 300,000,000 = 400,000,000 > 350,000,000 -> 위험 (test_risky_when_exceeds_threshold와 동일 수치)
        self.assertTrue(result["riskyDepositPriority"])

    def test_low_confidence_is_not_flagged_as_estimated(self):
        # "low"(실거래가 기반, 면적/기간만 넓힌 것)는 공시가격 추정과는 다르므로 캡션 대상 아님
        result = check_deposit_priority_risk(
            market_price=500_000_000, senior_secured_amount=0, my_deposit=300_000_000,
            market_price_confidence="low",
        )
        self.assertFalse(result["priceIsEstimated"])


class TestLandlordIdentityMatch(unittest.TestCase):

    def test_match_single_owner(self):
        result = check_landlord_identity_match("홍길동", [{"ownerName": "홍길동", "shareType": "단독소유"}])
        self.assertEqual(result["riskLevel"], "safe")
        self.assertTrue(result["match"])

    def test_mismatch_individual_owner_is_danger(self):
        result = check_landlord_identity_match("김철수", [{"ownerName": "홍길동", "shareType": "단독소유"}])
        self.assertEqual(result["riskLevel"], "danger")
        self.assertFalse(result["match"])

    def test_corporate_owner_name_matches_is_warning_not_danger(self):
        result = check_landlord_identity_match(
            "주식회사지음이엔지", [{"ownerName": "주식회사지음이엔지", "shareType": "단독소유"}]
        )
        self.assertEqual(result["riskLevel"], "warning")  # 법인 자체 리스크는 여전히 존재

    def test_corporate_owner_name_mismatch_is_danger(self):
        result = check_landlord_identity_match(
            "박영희", [{"ownerName": "주식회사지음이엔지", "shareType": "단독소유"}]
        )
        self.assertEqual(result["riskLevel"], "danger")
        self.assertFalse(result["match"])

    def test_trust_owner_always_danger_even_if_name_matches(self):
        result = check_landlord_identity_match(
            "한국자산신탁", [{"ownerName": "한국자산신탁", "shareType": "단독소유"}]
        )
        self.assertEqual(result["riskLevel"], "danger")

    def test_co_owner_case_flags_caution(self):
        result = check_landlord_identity_match(
            "김형진",
            [
                {"ownerName": "김형진", "shareType": "공유"},
                {"ownerName": "장형순", "shareType": "공유"},
            ],
        )
        self.assertTrue(result["match"])
        self.assertEqual(result["riskLevel"], "caution")
        self.assertIn("전원", result["reason"])

    def test_no_owner_data_returns_unknown(self):
        result = check_landlord_identity_match("홍길동", [])
        self.assertIsNone(result["match"])
        self.assertEqual(result["riskLevel"], "unknown")


class TestEvaluateTenancySafetyIntegration(unittest.TestCase):

    def test_real_document_scenario(self):
        # 실제 검증 문서(성남 야탑동, 조춘근 단독소유, 전세권 3억)를 기준으로
        # 다른 사람이 임대인이라고 주장하는 시나리오
        result = evaluate_tenancy_safety(
            market_price=600_000_000,
            senior_secured_amount=300_000_000,
            my_deposit=250_000_000,
            contract_landlord_name="주식회사지음이엔지",  # 실제 소유자는 '조춘근'
            registry_owners=[{"ownerName": "조춘근", "shareType": "단독소유"}],
            property_type="apartment",
        )
        self.assertTrue(result["depositPriorityRisk"]["riskyDepositPriority"])
        self.assertEqual(result["landlordIdentityCheck"]["riskLevel"], "danger")

    def test_market_price_confidence_forwarded_to_deposit_risk(self):
        result = evaluate_tenancy_safety(
            market_price=600_000_000,
            senior_secured_amount=300_000_000,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            registry_owners=[{"ownerName": "조춘근", "shareType": "단독소유"}],
            property_type="multi_household",
            market_price_confidence="estimated_from_public_price",
        )
        self.assertTrue(result["depositPriorityRisk"]["priceIsEstimated"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
