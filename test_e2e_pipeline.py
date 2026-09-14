"""
E2E 회귀 테스트
------------------
목적: 어느 모듈 하나를 고쳤을 때 "주소 입력 → 최종 위험 등급"이라는
전체 흐름이 조용히 깨지지 않는지 잡아낸다.

원칙: 외부 API는 전부 Mocking하되, 그 안에 넣는 값은 e2e_fixtures.py에 고정해둔
'실제로 확인했던 진짜 데이터'를 쓴다. 그래서 이 테스트가 실패한다면 그건
"실거래가가 바뀌어서"가 아니라 "코드 로직이 바뀌어서"라고 확신할 수 있다.

실행: python -m unittest test_e2e_pipeline.py -v
"""

import unittest
from datetime import date
from unittest.mock import patch

from e2e_fixtures import (
    FAKE_KAKAO_RESPONSE_COEX,
    REAL_GANGNAM_84_TRADES,
    REAL_YATAP_BUILDING_INFO,
    REAL_YATAP_REGISTRY_OCR_TEXT,
)

from property_aggregator import get_property_info
from registry_summary_parser import parse_summary_registry
from tenancy_safety_rules import evaluate_tenancy_safety
from overall_safety_assessment import assess_overall_safety


class TestE2EGangnamApartmentPricing(unittest.TestCase):
    """시나리오 A: 주소 → AddressResolver → 실거래가 → 시세추정 (PropertyAggregator 전체 경로)"""

    @patch("property_aggregator.fetch_building_register")
    @patch("property_aggregator.fetch_apt_trades")
    @patch("property_aggregator.resolve_address")
    def test_end_to_end_market_price_matches_golden_snapshot(
        self, mock_resolve, mock_trades, mock_building
    ):
        mock_resolve.return_value = {
            "roadAddress": "서울 강남구 테헤란로 427",
            "jibunAddress": "서울 강남구 삼성동 159",
            "legalDongCode": "1168010500",
            "pnu": "1168010500001590000",
            "lat": 37.508845,
            "lng": 127.062554,
        }
        mock_trades.side_effect = lambda lawd, ym: (
            {"status": "ok", "data": REAL_GANGNAM_84_TRADES} if ym == "202405"
            else {"status": "not_found"}
        )
        mock_building.return_value = {"status": "not_found"}

        result = get_property_info(
            "서울 강남구 테헤란로 427", target_area=84.99, as_of=date(2024, 6, 15)
        )

        # 골든 스냅샷 — e2e_fixtures.py의 데이터가 바뀌지 않는 한 이 값들은 고정이다.
        self.assertEqual(result["marketPrice"], 250_500)
        self.assertEqual(result["marketPriceConfidence"], "high")
        self.assertEqual(result["sourceStatuses"]["transactionPrice"], "ok")


class TestE2EYatapVillaSafetyAssessment(unittest.TestCase):
    """시나리오 B: 등기부 요약(실제 OCR 원문) → 임대인검증+깡통전세 → 최종 등급"""

    def setUp(self):
        self.registry = parse_summary_registry(REAL_YATAP_REGISTRY_OCR_TEXT)

    def test_registry_parsing_matches_golden_snapshot(self):
        self.assertEqual(len(self.registry["owners"]), 1)
        self.assertEqual(self.registry["owners"][0]["ownerName"], "조춘근")
        self.assertEqual(self.registry["totalSeniorSecuredAmount"], 300_000_000)

    def test_safe_scenario_when_landlord_matches_and_deposit_is_low(self):
        tenancy = evaluate_tenancy_safety(
            market_price=600_000_000,
            senior_secured_amount=self.registry["totalSeniorSecuredAmount"],
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",  # 실제 소유자와 일치
            registry_owners=self.registry["owners"],
            property_type="multi_household",
        )
        overall = assess_overall_safety(
            tenancy, property_info=REAL_YATAP_BUILDING_INFO
        )

        # 300,000,000 + 100,000,000 = 400,000,000 <= 600,000,000*0.7=420,000,000 -> 안전
        self.assertFalse(tenancy["depositPriorityRisk"]["riskyDepositPriority"])
        self.assertEqual(tenancy["landlordIdentityCheck"]["riskLevel"], "safe")
        self.assertEqual(overall["overallGrade"], "safe")

    def test_danger_scenario_when_landlord_mismatches_and_deposit_is_high(self):
        tenancy = evaluate_tenancy_safety(
            market_price=600_000_000,
            senior_secured_amount=self.registry["totalSeniorSecuredAmount"],
            my_deposit=250_000_000,
            contract_landlord_name="김아무개",  # 실제 소유자(조춘근)와 불일치
            registry_owners=self.registry["owners"],
            property_type="multi_household",
        )
        overall = assess_overall_safety(tenancy, property_info=REAL_YATAP_BUILDING_INFO)

        self.assertTrue(tenancy["depositPriorityRisk"]["riskyDepositPriority"])
        self.assertEqual(tenancy["landlordIdentityCheck"]["riskLevel"], "danger")
        self.assertEqual(overall["overallGrade"], "danger")


if __name__ == "__main__":
    unittest.main(verbosity=2)
