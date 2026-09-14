"""
market_price_estimator 단위 테스트
------------------------------------
순수 함수라 Mocking 없이 입력 리스트만으로 검증 가능.
"""

import unittest
from datetime import date

from market_price_estimator import estimate_market_price


def make_trade(deal_amount, area, year, month, day=1, dong=None):
    return {
        "dealAmount": deal_amount,
        "exclusiveArea": area,
        "dealYear": str(year),
        "dealMonth": str(month),
        "dealDay": str(day),
        "dong": dong,
    }


class TestEstimateMarketPrice(unittest.TestCase):

    def test_empty_trades_returns_unavailable(self):
        result = estimate_market_price([], target_area=84.99)
        self.assertEqual(result["confidence"], "unavailable")
        self.assertIsNone(result["marketPrice"])

    def test_high_confidence_with_enough_recent_same_area_trades(self):
        as_of = date(2024, 6, 15)
        trades = [
            make_trade(80000, 84.99, 2024, 2),
            make_trade(85000, 84.99, 2024, 3),
            make_trade(90000, 84.99, 2024, 4),
        ]
        result = estimate_market_price(trades, target_area=84.99, as_of=as_of)

        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["usedTradeCount"], 3)
        self.assertEqual(result["marketPrice"], 85000)  # 중위값

    def test_excludes_trades_outside_recent_period(self):
        as_of = date(2024, 6, 15)
        trades = [
            make_trade(80000, 84.99, 2024, 3),   # 3개월 전 - 포함
            make_trade(50000, 84.99, 2022, 1),   # 너무 오래됨 - 12개월 기준으로도 제외
        ]
        result = estimate_market_price(trades, target_area=84.99, as_of=as_of)

        # 6개월/12개월 이내 매칭 1건뿐이라 high 기준(3건) 통과 못하고
        # 3단계(면적 넓힘, 기간은 12개월 유지)로 가도 오래된 거래는 여전히 컷오프 밖 → 1건만 반영
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["usedTradeCount"], 1)

    def test_widens_period_to_12_months_before_widening_area(self):
        as_of = date(2024, 6, 15)
        # 6개월 이내엔 2건뿐이라 1단계 실패, 12개월로 넓히면 3건 확보 → 2단계에서 high
        trades = [
            make_trade(80000, 84.99, 2024, 3),
            make_trade(85000, 84.99, 2024, 4),
            make_trade(75000, 84.99, 2023, 8),  # 10개월 전
        ]
        result = estimate_market_price(trades, target_area=84.99, as_of=as_of)

        self.assertEqual(result["confidence"], "high")
        self.assertEqual(result["usedTradeCount"], 3)
        self.assertIn("12개월", result["basis"])

    def test_falls_back_to_wider_area_with_low_confidence(self):
        as_of = date(2024, 6, 15)
        # 정확히 84.99㎡ 거래가 하나도 없고, 80.0㎡(오차 3 이내는 아니지만 5 이내인) 거래만 있음
        trades = [
            make_trade(70000, 80.0, 2024, 3),  # target과 4.99 차이 → ±3엔 안 걸리지만 ±5엔 걸림
        ]
        result = estimate_market_price(trades, target_area=84.99, as_of=as_of)

        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["usedTradeCount"], 1)
        self.assertEqual(result["marketPrice"], 70000)

    def test_no_comparable_trades_even_after_widening_returns_unavailable(self):
        as_of = date(2024, 6, 15)
        # 면적이 아예 동떨어진 원룸(20㎡)만 있는 경우 — 84.99㎡ 매물엔 비교 불가
        trades = [make_trade(30000, 20.0, 2024, 3)]
        result = estimate_market_price(trades, target_area=84.99, as_of=as_of)

        self.assertEqual(result["confidence"], "unavailable")
        self.assertIsNone(result["marketPrice"])

    def test_median_with_even_number_of_trades(self):
        as_of = date(2024, 6, 15)
        trades = [
            make_trade(80000, 84.99, 2024, 3),
            make_trade(90000, 84.99, 2024, 4),
            make_trade(100000, 84.99, 2024, 5),
            make_trade(110000, 84.99, 2024, 5),
        ]
        result = estimate_market_price(trades, target_area=84.99, as_of=as_of)

        # 4건 중위값 = (90000+100000)/2 = 95000
        self.assertEqual(result["marketPrice"], 95000)
        self.assertEqual(result["confidence"], "high")

    def test_public_price_fallback_when_no_trades_at_all(self):
        # 실거래가 아예 없는 나홀로 아파트 — 공시가격 30,000만원이 주어지면 ×1.4 적용
        result = estimate_market_price([], target_area=59.9, public_price=30000)

        self.assertEqual(result["marketPrice"], 42000)  # 30000 * 1.4
        self.assertEqual(result["confidence"], "estimated_from_public_price")

    def test_public_price_fallback_when_area_never_matches(self):
        # 거래는 있지만 면적이 완전히 동떨어져 3단계까지 다 실패하는 경우도 공시가격으로 폴백
        as_of = date(2024, 6, 15)
        trades = [make_trade(30000, 20.0, 2024, 3)]  # target 84.99와 너무 다른 원룸
        result = estimate_market_price(trades, target_area=84.99, as_of=as_of, public_price=50000)

        self.assertEqual(result["marketPrice"], 70000)  # 50000 * 1.4
        self.assertEqual(result["confidence"], "estimated_from_public_price")

    def test_no_public_price_and_no_trades_is_truly_unavailable(self):
        result = estimate_market_price([], target_area=59.9, public_price=None)

        self.assertIsNone(result["marketPrice"])
        self.assertEqual(result["confidence"], "unavailable")

    def test_real_trade_data_never_falls_back_even_if_public_price_given(self):
        # 실거래 비교가 가능하면 공시가격은 아예 참조되지 않아야 한다 (우선순위 확인)
        as_of = date(2024, 6, 15)
        trades = [
            make_trade(85000, 84.99, 2024, 3),
            make_trade(90000, 84.99, 2024, 4),
            make_trade(88000, 84.99, 2024, 5),
        ]
        result = estimate_market_price(trades, target_area=84.99, as_of=as_of, public_price=999999)

        self.assertEqual(result["confidence"], "high")
        self.assertNotEqual(result["marketPrice"], round(999999 * 1.4))

    def test_same_dong_preferred_over_whole_district(self):
        as_of = date(2024, 6, 15)
        trades = [
            # 같은 동(삼성동) 3건 — 이걸로 충분히 high 판정 가능
            make_trade(85000, 84.99, 2024, 3, dong="삼성동"),
            make_trade(90000, 84.99, 2024, 4, dong="삼성동"),
            make_trade(88000, 84.99, 2024, 5, dong="삼성동"),
            # 다른 동(역삼동)의 훨씬 비싼 거래 — 같은 동 우선이면 이 값에 안 흔들려야 함
            make_trade(500000, 84.99, 2024, 5, dong="역삼동"),
            make_trade(510000, 84.99, 2024, 5, dong="역삼동"),
        ]
        result = estimate_market_price(trades, target_area=84.99, as_of=as_of, target_dong="삼성동")

        self.assertEqual(result["marketPrice"], 88000)  # 삼성동 3건의 중위값
        self.assertEqual(result["usedTradeCount"], 3)
        self.assertIn("삼성동", result["basis"])

    def test_falls_back_to_whole_district_when_same_dong_insufficient(self):
        as_of = date(2024, 6, 15)
        trades = [
            make_trade(85000, 84.99, 2024, 3, dong="삼성동"),  # 삼성동엔 1건뿐 -> 부족
            make_trade(90000, 84.99, 2024, 4, dong="역삼동"),
            make_trade(88000, 84.99, 2024, 5, dong="청담동"),
        ]
        result = estimate_market_price(trades, target_area=84.99, as_of=as_of, target_dong="삼성동")

        # 삼성동만으론 3건이 안 되니 자치구 전체(3건)로 확대돼야 한다
        self.assertEqual(result["usedTradeCount"], 3)
        self.assertIn("확대", result["basis"])

    def test_no_target_dong_behaves_like_before(self):
        # target_dong을 안 주면 기존처럼 곧바로 자치구 전체 기준으로 판단 (하위 호환)
        as_of = date(2024, 6, 15)
        trades = [
            make_trade(85000, 84.99, 2024, 3, dong="삼성동"),
            make_trade(90000, 84.99, 2024, 4, dong="역삼동"),
            make_trade(88000, 84.99, 2024, 5, dong="청담동"),
        ]
        result = estimate_market_price(trades, target_area=84.99, as_of=as_of)

        self.assertEqual(result["usedTradeCount"], 3)
        self.assertEqual(result["confidence"], "high")


if __name__ == "__main__":
    unittest.main(verbosity=2)
