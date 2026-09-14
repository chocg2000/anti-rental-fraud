"""
tenancy_safety_rules 단위 테스트
"""

import unittest

from tenancy_safety_rules import (
    check_deposit_priority_risk,
    check_fixed_date_risk,
    check_landlord_identity_match,
    check_possession_priority_gap_risk,
    evaluate_tenancy_safety,
)


def right(right_type="근저당권설정", amount=100_000_000, received_date=None):
    return {"rightType": right_type, "amount": amount, "receivedDate": received_date}


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


class TestPossessionPriorityGapRisk(unittest.TestCase):
    """
    룰 3 날짜 경계값 테스트 — 대항력은 전입신고 익일 0시부터, 등기부 권리는 접수 당일부터
    효력이 발생한다는 시간차를 정확히 경계에서 잡아내는지 집중적으로 검증한다.
    """

    def test_no_move_in_date_returns_unknown(self):
        result = check_possession_priority_gap_risk(None, [right(received_date="2026-09-01")])
        self.assertIsNone(result["gapRiskDetected"])

    def test_invalid_move_in_date_format_returns_unknown(self):
        result = check_possession_priority_gap_risk("2026/09/01", [])
        self.assertIsNone(result["gapRiskDetected"])

    def test_no_active_rights_is_not_risky(self):
        result = check_possession_priority_gap_risk("2026-09-01", [])
        self.assertFalse(result["gapRiskDetected"])

    def test_right_received_exact_same_day_is_danger(self):
        # 핵심 케이스: 잔금일 당일 접수 -> 등기 권리가 익일 0시보다 먼저 효력 발생 -> 위험
        result = check_possession_priority_gap_risk(
            "2026-09-01", [right(received_date="2026-09-01")]
        )
        self.assertTrue(result["gapRiskDetected"])
        self.assertEqual(len(result["suspiciousRights"]), 1)

    def test_right_received_one_day_before_is_not_flagged_by_this_rule(self):
        # 잔금일 하루 전 접수 -> 이미 존재하던 채권(룰 1의 LTV 합계가 이미 반영) ->
        # 이 룰이 잡으려는 "당일 타이밍 공백"은 아님
        result = check_possession_priority_gap_risk(
            "2026-09-01", [right(received_date="2026-08-31")]
        )
        self.assertFalse(result["gapRiskDetected"])

    def test_right_received_long_before_is_not_flagged(self):
        result = check_possession_priority_gap_risk(
            "2026-09-01", [right(received_date="2020-01-15")]
        )
        self.assertFalse(result["gapRiskDetected"])

    def test_right_received_one_day_after_is_not_flagged(self):
        # 대항력 발생(9/2 0시)이 그날 낮에 접수되는 어떤 등기보다도 빠르므로 세입자가 우선
        result = check_possession_priority_gap_risk(
            "2026-09-01", [right(received_date="2026-09-02")]
        )
        self.assertFalse(result["gapRiskDetected"])

    def test_right_received_long_after_is_not_flagged(self):
        result = check_possession_priority_gap_risk(
            "2026-09-01", [right(received_date="2027-01-01")]
        )
        self.assertFalse(result["gapRiskDetected"])

    def test_only_same_day_rights_included_among_mixed_dates(self):
        rights = [
            right(right_type="근저당권설정", received_date="2026-08-31"),  # 전날 — 제외
            right(right_type="전세권설정", received_date="2026-09-01"),     # 당일 — 포함
            right(right_type="근저당권설정", received_date="2026-09-02"),   # 다음날 — 제외
        ]
        result = check_possession_priority_gap_risk("2026-09-01", rights)
        self.assertTrue(result["gapRiskDetected"])
        self.assertEqual(len(result["suspiciousRights"]), 1)
        self.assertEqual(result["suspiciousRights"][0]["rightType"], "전세권설정")

    def test_right_missing_received_date_is_ignored_not_crash(self):
        result = check_possession_priority_gap_risk(
            "2026-09-01", [right(received_date=None)]
        )
        self.assertFalse(result["gapRiskDetected"])

    def test_reason_mentions_right_type_and_amount(self):
        result = check_possession_priority_gap_risk(
            "2026-09-01", [right(right_type="근저당권설정", amount=200_000_000, received_date="2026-09-01")]
        )
        self.assertIn("근저당권설정", result["reason"])
        self.assertIn("200,000,000", result["reason"])
        self.assertIn("2026-09-01", result["reason"])

    def test_move_in_date_echoed_back_for_frontend_timeline(self):
        # 프론트가 결과 화면만으로(폼 상태 없이) 타임라인을 그릴 수 있어야 하므로
        # 안전/위험 판정과 무관하게 moveInDate를 그대로 돌려줘야 한다.
        result = check_possession_priority_gap_risk("2026-09-01", [])
        self.assertEqual(result["moveInDate"], "2026-09-01")

    def test_rights_timeline_sorted_by_date_and_excludes_undated(self):
        rights = [
            right(right_type="근저당권설정", received_date="2026-09-02"),
            right(right_type="전세권설정", received_date="2026-08-31"),
            right(right_type="근저당권설정", received_date=None),
        ]
        result = check_possession_priority_gap_risk("2026-09-01", rights)
        dates = [r["receivedDate"] for r in result["rightsTimeline"]]
        self.assertEqual(dates, ["2026-08-31", "2026-09-02"])


class TestFixedDateRisk(unittest.TestCase):

    def test_none_is_unknown(self):
        result = check_fixed_date_risk(None)
        self.assertEqual(result["riskLevel"], "unknown")

    def test_true_is_safe(self):
        result = check_fixed_date_risk(True)
        self.assertEqual(result["riskLevel"], "safe")

    def test_false_is_caution_not_warning(self):
        # 이 앱은 "계약 전" 진단이 주 사용 시나리오다. 확정일자는 계약을 체결해야만
        # 받을 수 있으므로 False는 거의 모든 정상 사용자에게 해당하는 당연한 상태 —
        # "warning"(경고)으로 매번 뜨면 진짜 위험 신호의 신뢰도를 깎아먹는다.
        result = check_fixed_date_risk(False)
        self.assertEqual(result["riskLevel"], "caution")
        self.assertIn("우선변제권", result["reason"])
        self.assertIn("계약 전이라면 정상", result["reason"])


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

    def test_new_rules_default_to_unknown_when_omitted(self):
        # 기존 호출부(룰 3/4 도입 이전)가 새 파라미터를 안 넘겨도 깨지지 않고,
        # 자동으로 위험 판정을 내려버리지 않고 unknown으로 남아야 한다.
        result = evaluate_tenancy_safety(
            market_price=600_000_000,
            senior_secured_amount=300_000_000,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            registry_owners=[{"ownerName": "조춘근", "shareType": "단독소유"}],
            property_type="multi_household",
        )
        self.assertIsNone(result["possessionPriorityGapRisk"]["gapRiskDetected"])
        self.assertEqual(result["fixedDateRisk"]["riskLevel"], "unknown")

    def test_possession_gap_and_fixed_date_wired_through(self):
        result = evaluate_tenancy_safety(
            market_price=600_000_000,
            senior_secured_amount=300_000_000,
            my_deposit=100_000_000,
            contract_landlord_name="조춘근",
            registry_owners=[{"ownerName": "조춘근", "shareType": "단독소유"}],
            property_type="multi_household",
            move_in_date="2026-09-01",
            active_rights=[right(received_date="2026-09-01")],
            has_fixed_date=False,
        )
        self.assertTrue(result["possessionPriorityGapRisk"]["gapRiskDetected"])
        self.assertEqual(result["fixedDateRisk"]["riskLevel"], "caution")


if __name__ == "__main__":
    unittest.main(verbosity=2)
