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


class TestPropertyTypeForwardedToPropertyInfo(unittest.TestCase):
    """
    실제로 겪은 버그: property_type이 get_property_info까지 전달되지 않아서, 빌라를
    진단해도 국토부 아파트 실거래(더 비쌈)로 시세가 잡혔었다 — property_aggregator.py
    참고. 오케스트레이터가 이 값을 그대로 넘기는지만 여기서 확인한다(실제 분기 로직
    자체는 test_property_aggregator.py가 검증).
    """

    @patch("full_assessment.get_property_info")
    def test_property_type_is_forwarded(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000)

        run_full_assessment(
            address="서울 강남구 테헤란로 427",
            target_area=54.0,
            my_deposit=100_000_000,
            contract_landlord_name="홍길동",
            property_type="villa",
        )

        self.assertEqual(mock_get_info.call_args.kwargs["property_type"], "villa")


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


class TestPossessionGapAndFixedDateWiring(unittest.TestCase):
    """
    move_in_date/has_fixed_date가 tenancy_safety_rules의 새 두 룰까지 끊기지 않고
    전달되는지 검증. YATAP_REGISTRY_OCR_TEXT의 전세권 접수일은 2025-03-26으로 고정.
    """

    @patch("full_assessment.get_property_info")
    def test_move_in_same_day_as_registry_right_is_danger(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="경기 성남시 분당구 야탑동 335",
            target_area=39.6,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            property_type="multi_household",
            registry_summary_text=YATAP_REGISTRY_OCR_TEXT,
            move_in_date="2025-03-26",
        )

        gap_risk = result["tenancySafety"]["possessionPriorityGapRisk"]
        self.assertTrue(gap_risk["gapRiskDetected"])
        self.assertEqual(result["overallGrade"], "danger")

    @patch("full_assessment.get_property_info")
    def test_move_in_different_day_is_not_flagged(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="경기 성남시 분당구 야탑동 335",
            target_area=39.6,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            property_type="multi_household",
            registry_summary_text=YATAP_REGISTRY_OCR_TEXT,
            move_in_date="2025-04-01",
        )

        gap_risk = result["tenancySafety"]["possessionPriorityGapRisk"]
        self.assertFalse(gap_risk["gapRiskDetected"])
        self.assertEqual(result["overallGrade"], "safe")

    @patch("full_assessment.get_property_info")
    def test_move_in_date_omitted_gives_unknown_not_false_safety(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="경기 성남시 분당구 야탑동 335",
            target_area=39.6,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            property_type="multi_household",
            registry_summary_text=YATAP_REGISTRY_OCR_TEXT,
        )

        self.assertIsNone(result["tenancySafety"]["possessionPriorityGapRisk"]["gapRiskDetected"])

    @patch("full_assessment.get_property_info")
    def test_has_fixed_date_false_is_caution_not_warning(self, mock_get_info):
        # 계약 전이면 확정일자가 없는 게 정상이라 "warning"이 아니라 "caution"이어야
        # 한다(모든 사용자에게 매번 경고가 뜨면 안 됨) — tenancy_safety_rules.py 참고.
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="서울 강남구 테헤란로 427",
            target_area=84.99,
            my_deposit=100_000_000,
            contract_landlord_name="홍길동",
            has_fixed_date=False,
        )

        self.assertEqual(result["tenancySafety"]["fixedDateRisk"]["riskLevel"], "caution")
        self.assertIn(result["overallGrade"], ("caution", "warning", "danger"))

    @patch("full_assessment.get_property_info")
    def test_has_fixed_date_omitted_is_unknown_not_warning(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="서울 강남구 테헤란로 427",
            target_area=84.99,
            my_deposit=100_000_000,
            contract_landlord_name="홍길동",
        )

        self.assertEqual(result["tenancySafety"]["fixedDateRisk"]["riskLevel"], "unknown")
        self.assertEqual(result["overallGrade"], "safe")


class TestMinimumPriorityRepaymentWiring(unittest.TestCase):
    """
    priority_region_classifier.classify_priority_region()이 property_info의 주소로
    호출돼 tenancy_safety_rules.check_minimum_priority_repayment()까지 이어지는지 검증.
    """

    @patch("full_assessment.get_property_info")
    def test_seoul_address_computes_guaranteed_amount(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=1_000_000)  # 100억원 상당
        mock_get_info.return_value["normalizedAddress"] = {"roadAddress": "서울특별시 강남구 테헤란로 427"}

        result = run_full_assessment(
            address="서울특별시 강남구 테헤란로 427",
            target_area=84.99,
            my_deposit=100_000_000,
            contract_landlord_name="홍길동",
        )

        repayment = result["tenancySafety"]["minimumPriorityRepayment"]
        self.assertEqual(repayment["status"], "ok")
        self.assertEqual(repayment["guaranteedAmount"], 55_000_000)

    @patch("full_assessment.get_property_info")
    def test_ambiguous_region_address_is_unknown(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000)
        mock_get_info.return_value["normalizedAddress"] = {"roadAddress": "경기도 남양주시 호평동 1"}

        result = run_full_assessment(
            address="경기도 남양주시 호평동 1",
            target_area=84.99,
            my_deposit=100_000_000,
            contract_landlord_name="홍길동",
        )

        repayment = result["tenancySafety"]["minimumPriorityRepayment"]
        self.assertEqual(repayment["status"], "unknown")

    @patch("full_assessment.get_property_info")
    def test_uses_registry_active_rights_as_reference_date(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=1_000_000)
        mock_get_info.return_value["normalizedAddress"] = {"roadAddress": "서울특별시 강남구 1"}

        result = run_full_assessment(
            address="서울특별시 강남구 1",
            target_area=39.6,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            property_type="multi_household",
            registry_summary_text=YATAP_REGISTRY_OCR_TEXT,  # 전세권 접수일 2025-03-26
        )

        repayment = result["tenancySafety"]["minimumPriorityRepayment"]
        self.assertEqual(repayment["referenceDate"], "2025-03-26")


class TestEulguSecuredAmountCrossCheck(unittest.TestCase):
    """
    2026-09-16 을구 배선: 요약 페이지(근저당+전세권 합계)와 을구 본문 직접 파싱(근저당만)
    결과 중 더 큰 금액을 채택(Max Fallback)하는지 검증한다. 기준 시나리오는
    TestMarketPriceUnitConversion.test_manwon_to_won_conversion_matches_yatap_safe_scenario와
    동일(시세 6억, 요약 페이지 선순위 3억, 내 보증금 1억 -> 4억 <= 4.2억 안전).
    """

    @patch("full_assessment.get_property_info")
    def test_larger_eulgu_amount_escalates_previously_safe_case_to_risky(self, mock_get_info):
        # 을구 본문에서 요약 페이지가 놓친 근저당 2억을 추가로 찾았다고 가정 -> 5억으로
        # 올라가면 내 보증금 1억과 합쳐 6억 > 4.2억(임계값) -> 안전이었던 판정이 위험으로.
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="경기 성남시 분당구 야탑동 335",
            target_area=39.6,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            property_type="multi_household",
            registry_summary_text=YATAP_REGISTRY_OCR_TEXT,
            eulgu_valid_secured_amount=500_000_000,
        )

        self.assertTrue(result["tenancySafety"]["depositPriorityRisk"]["riskyDepositPriority"])
        self.assertEqual(result["overallGrade"], "warning")

    @patch("full_assessment.get_property_info")
    def test_smaller_eulgu_amount_does_not_reduce_risk_from_summary(self, mock_get_info):
        # 을구 쪽이 더 작게(또는 0으로) 나와도 요약 페이지의 더 큰 금액을 절대 깎지 않는다
        # (거짓 안심 방지 — Max Fallback은 한쪽 방향으로만 작동해야 한다).
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="경기 성남시 분당구 야탑동 335",
            target_area=39.6,
            my_deposit=250_000_000,  # 요약 3억 기준으로 이미 위험(danger 시나리오와 동일 입력)
            contract_landlord_name="조춘근",
            property_type="multi_household",
            registry_summary_text=YATAP_REGISTRY_OCR_TEXT,
            eulgu_valid_secured_amount=0,  # 을구 쪽은 전부 말소돼 0으로 나온 경우
        )

        self.assertTrue(result["tenancySafety"]["depositPriorityRisk"]["riskyDepositPriority"])

    @patch("full_assessment.get_property_info")
    def test_eulgu_amount_used_when_summary_text_absent(self, mock_get_info):
        # 요약 페이지 자체가 없어도(registry_summary_text=None) 을구 본문 값만으로
        # 깡통전세 위험을 계산해야 한다 — "확인 불가"로 방치하면 안 된다.
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="경기 성남시 분당구 야탑동 335",
            target_area=39.6,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            property_type="multi_household",
            eulgu_valid_secured_amount=500_000_000,
        )

        deposit_risk = result["tenancySafety"]["depositPriorityRisk"]
        self.assertIsNotNone(deposit_risk["riskyDepositPriority"])
        self.assertTrue(deposit_risk["riskyDepositPriority"])


class TestEulguUnparsedMortgageAmountWiring(unittest.TestCase):
    """
    2026-09-16 배선: 을구에 말소 안 된 근저당인데 금액 형식을 못 읽은 게 있으면(오래된
    등기의 한글 숫자 표기 등) caution으로 반영되는지 확인한다. 안전한 시나리오
    (TestMarketPriceUnitConversion 기준)에서도 이 신호가 안전 판정을 caution으로
    끌어올리는지가 핵심 — "안전"으로 보여도 참고용 경고는 남아야 한다.
    """

    @patch("full_assessment.get_property_info")
    def test_unparsed_amount_escalates_safe_case_to_caution(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="경기 성남시 분당구 야탑동 335",
            target_area=39.6,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            property_type="multi_household",
            registry_summary_text=YATAP_REGISTRY_OCR_TEXT,
            eulgu_has_unparsed_mortgage_amount=True,
        )

        self.assertFalse(result["tenancySafety"]["depositPriorityRisk"]["riskyDepositPriority"])
        self.assertEqual(result["overallGrade"], "caution")
        self.assertTrue(any("금액 형식을 인식하지 못한" in r for r in result["reasons"]))

    @patch("full_assessment.get_property_info")
    def test_flag_omitted_does_not_affect_grade(self, mock_get_info):
        mock_get_info.return_value = make_property_info(market_price=60_000)

        result = run_full_assessment(
            address="경기 성남시 분당구 야탑동 335",
            target_area=39.6,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            property_type="multi_household",
            registry_summary_text=YATAP_REGISTRY_OCR_TEXT,
        )

        self.assertEqual(result["overallGrade"], "safe")


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
