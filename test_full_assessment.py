"""
full_assessment 오케스트레이터 테스트
----------------------------------------
목적: 이 오케스트레이터가 새로 만든 로직(단위 변환, 등기부 부재 처리, 유저 자가확인
반영)만 검증한다. 각 조각(property_aggregator, tenancy_safety_rules 등) 자체의 로직은
각자의 test_*.py에서 이미 검증됐으므로 여기서는 get_property_info를 모킹해 배선만 본다.
"""

import unittest
from datetime import date
from unittest.mock import patch

from full_assessment import run_full_assessment
from property_aggregator import PropertyAggregationError

YATAP_REGISTRY_OCR_TEXT = """주요 등기사항 요약 (참고용)
고유번호 1356-1996-092460
1. 소유지분현황 ( 갑구 )
조춘근 (소유자) | 670209-1788617 | 단독소유    경기도 성남시 분당구 장미로 101, 822동
204호(야탑동, 장미마을)
2. 소유지분을 제외한 소유권에 관한 사항 ( 갑구 )
- 기록사항 없음
3. (근)저당권 및 전세권 등 ( 을구 )
11    전세권설정          2025년3월26일 | 전세금 _금300,000,000원                     조춘근
제1247861호  전세권자 주식회사지음이엔지
[참고사항]
"""


def make_property_info(market_price=60_000, building=None, violation_confirmed=False, violation_raw=None,
                        confidence=None):
    """market_price는 만원 단위 (property_aggregator/market_price_estimator 규약)."""
    if confidence is None:
        confidence = "high" if market_price is not None else "unavailable"
    return {
        "normalizedAddress": {"roadAddress": "경기 성남시 분당구 장미로 101"},
        "marketPrice": market_price,
        "marketPriceConfidence": confidence,
        "marketPriceBasis": "test fixture",
        "building": building,
        "registrySeparated": True,
        "violationStatusConfirmed": violation_confirmed,
        "violationStatusRaw": violation_raw,
        "nonResidentialUseRisk": False,
        "sourceStatuses": {"transactionPrice": "ok", "buildingRegister": "ok" if building else "not_found"},
    }


class TestAddressResolutionFailure(unittest.TestCase):

    @patch("full_assessment.get_property_info")
    def test_returns_error_grade_without_calling_downstream_rules(self, mock_get_info):
        mock_get_info.side_effect = PropertyAggregationError("주소를 정규화하지 못해 조회를 진행할 수 없습니다: 테스트")

        result = run_full_assessment(
            address="존재하지않는주소12345",
            target_area=84.99,
            my_deposit=100_000_000,
            contract_landlord_name="홍길동",
        )

        self.assertEqual(result["overallGrade"], "error")
        self.assertIsNone(result["propertyInfo"])
        self.assertIsNone(result["tenancySafety"])


class TestMissingRegistryData(unittest.TestCase):

    @patch("full_assessment.get_property_info")
    def test_no_registry_text_gives_unknown_deposit_risk_not_false_safety(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="서울 강남구 테헤란로 427",
            target_area=84.99,
            my_deposit=100_000_000,
            contract_landlord_name="홍길동",
        )

        deposit_risk = result["tenancySafety"]["depositPriorityRisk"]
        identity_check = result["tenancySafety"]["landlordIdentityCheck"]
        self.assertIsNone(deposit_risk["riskyDepositPriority"])
        self.assertEqual(identity_check["riskLevel"], "unknown")


class TestMarketPriceUnitConversion(unittest.TestCase):

    @patch("full_assessment.get_property_info")
    def test_manwon_to_won_conversion_matches_yatap_safe_scenario(self, mock_get_info):
        # market_price=60,000(만원) == 600,000,000원. 선순위 3억 + 내 보증금 1억 = 4억
        # <= 6억*0.7(multi_household)=4.2억 -> 안전. 변환이 안 되면(60,000을 원으로 오인하면)
        # 임계값이 42,000원이 되어 총액이 압도적으로 초과 -> 잘못된 위험 판정이 나온다.
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="경기 성남시 분당구 야탑동 335",
            target_area=39.6,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            property_type="multi_household",
            registry_summary_text=YATAP_REGISTRY_OCR_TEXT,
        )

        self.assertFalse(result["tenancySafety"]["depositPriorityRisk"]["riskyDepositPriority"])
        self.assertEqual(result["tenancySafety"]["landlordIdentityCheck"]["riskLevel"], "safe")
        self.assertEqual(result["overallGrade"], "safe")

    @patch("full_assessment.get_property_info")
    def test_landlord_mismatch_and_high_deposit_is_danger(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="경기 성남시 분당구 야탑동 335",
            target_area=39.6,
            my_deposit=250_000_000,
            contract_landlord_name="김아무개",  # 실제 소유자(조춘근)와 불일치
            property_type="multi_household",
            registry_summary_text=YATAP_REGISTRY_OCR_TEXT,
        )

        self.assertTrue(result["tenancySafety"]["depositPriorityRisk"]["riskyDepositPriority"])
        self.assertEqual(result["tenancySafety"]["landlordIdentityCheck"]["riskLevel"], "danger")
        self.assertEqual(result["overallGrade"], "danger")


class TestMarketPriceConfidenceWiring(unittest.TestCase):
    """
    property_info.marketPriceConfidence(예: vworld 공시가격 폴백을 썼다는 신호)가
    tenancy_safety_rules까지 끊기지 않고 전달되는지 검증 (오늘 vworld 연동을 실제로
    붙이면서 드러난 갭 — 시세 출처를 몰라도 위험 판정 자체는 항상 가능했지만, 그 판단이
    실거래가 기반인지 공시가격 추정치 기반인지는 유저에게 전혀 안 보여주고 있었음).
    """

    @patch("full_assessment.get_property_info")
    def test_estimated_from_public_price_confidence_flows_through_to_caution(self, mock_get_info):
        mock_get_info.return_value = make_property_info(
            market_price=60_000, confidence="estimated_from_public_price",
        )

        result = run_full_assessment(
            address="경기 성남시 분당구 야탑동 335",
            target_area=39.6,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            property_type="multi_household",
            registry_summary_text=YATAP_REGISTRY_OCR_TEXT,
        )

        deposit_risk = result["tenancySafety"]["depositPriorityRisk"]
        self.assertTrue(deposit_risk["priceIsEstimated"])
        # 이 시나리오 자체는 안전(위 유닛변환 테스트와 동일 수치)이지만, 추정치 기반이라
        # 최종 등급은 safe가 아니라 caution 이상이어야 한다.
        self.assertFalse(deposit_risk["riskyDepositPriority"])
        self.assertEqual(result["overallGrade"], "caution")
        self.assertTrue(any("공시가격 추정치" in r for r in result["reasons"]))

    @patch("full_assessment.get_property_info")
    def test_high_confidence_does_not_trigger_estimation_caution(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000, confidence="high")

        result = run_full_assessment(
            address="경기 성남시 분당구 야탑동 335",
            target_area=39.6,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            property_type="multi_household",
            registry_summary_text=YATAP_REGISTRY_OCR_TEXT,
        )

        self.assertFalse(result["tenancySafety"]["depositPriorityRisk"]["priceIsEstimated"])
        self.assertEqual(result["overallGrade"], "safe")


class TestUserConfirmedViolationBuilding(unittest.TestCase):

    @patch("full_assessment.get_property_info")
    def test_self_reported_violation_forces_danger_even_if_api_says_no(self, mock_get_info):
        mock_get_info.return_value = make_property_info(
            market_price=60_000, violation_confirmed=False, violation_raw=None,
        )

        result = run_full_assessment(
            address="서울 강남구 테헤란로 427",
            target_area=84.99,
            my_deposit=100_000_000,
            contract_landlord_name="홍길동",
            user_confirmed_violation_building=True,
        )

        self.assertEqual(result["overallGrade"], "danger")
        self.assertIn("위반건축물", result["propertyInfo"]["violationStatusRaw"])


class TestFraudPatternWiring(unittest.TestCase):

    @patch("full_assessment.get_property_info")
    def test_new_building_with_recent_ownership_change_is_flagged(self, mock_get_info):
        building = {
            "bldName": "테스트빌라", "mainPurpose": "공동주택", "useApprovalDate": "20240101",
            "isRegisteredAsNonResidential": False, "violationStatusRaw": None,
            "violationStatusConfirmed": False,
        }
        mock_get_info.return_value = make_property_info(market_price=60_000, building=building)

        result = run_full_assessment(
            address="서울 강남구 테헤란로 427",
            target_area=39.6,
            my_deposit=100_000_000,
            contract_landlord_name="홍길동",
            as_of=date(2024, 6, 15),
            ownership_history=[{"date": "2024-05-01", "ownerName": "홍길동"}],
        )

        self.assertTrue(result["fraudPatternResult"]["triggered"])
        self.assertIn(result["overallGrade"], ("warning", "danger"))

    @patch("full_assessment.get_property_info")
    def test_building_lookup_failed_skips_fraud_pattern_check(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000, building=None)

        result = run_full_assessment(
            address="서울 강남구 테헤란로 427",
            target_area=84.99,
            my_deposit=100_000_000,
            contract_landlord_name="홍길동",
        )

        self.assertIsNone(result["fraudPatternResult"])


class TestTaxClearanceWiring(unittest.TestCase):

    @patch("full_assessment.get_property_info")
    def test_omitted_tax_clearance_is_skipped_not_penalized(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="서울 강남구 테헤란로 427",
            target_area=84.99,
            my_deposit=100_000_000,
            contract_landlord_name="홍길동",
        )

        self.assertIsNone(result["taxClearanceResult"])

    @patch("full_assessment.get_property_info")
    def test_explicit_not_submitted_is_treated_as_warning(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="서울 강남구 테헤란로 427",
            target_area=84.99,
            my_deposit=100_000_000,
            contract_landlord_name="홍길동",
            tax_clearance={"submitted": False},
        )

        self.assertEqual(result["taxClearanceResult"]["riskLevel"], "warning")
        self.assertIn(result["overallGrade"], ("warning", "danger"))


class TestRegistryCriticalKeywordsWiring(unittest.TestCase):

    @patch("full_assessment.get_property_info")
    def test_critical_keyword_forces_immediate_danger(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="서울 강남구 테헤란로 427",
            target_area=84.99,
            my_deposit=100_000_000,
            contract_landlord_name="홍길동",
            registry_critical_keywords=["가압류"],
        )

        self.assertEqual(result["overallGrade"], "danger")
        self.assertTrue(any("가압류" in r for r in result["reasons"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
