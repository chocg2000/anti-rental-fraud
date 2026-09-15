"""
PropertyAggregator 단위 테스트 (Mocking 기반)
------------------------------------------------
하위 어댑터 3개를 전부 Mocking해서, 오케스트레이션 로직(병렬 호출·부분 실패 허용·
여러 달 데이터 병합)만 순수하게 검증한다.
"""

import unittest
from datetime import date
from unittest.mock import patch

from property_aggregator import get_property_info, PropertyAggregationError
from address_resolver import AddressResolutionError


FAKE_NORMALIZED = {
    "roadAddress": "서울 강남구 테헤란로 427",
    "jibunAddress": "서울 강남구 삼성동 159",
    "legalDongCode": "1168010500",
    "pnu": "1168010500001590000",
    "lat": 37.508845,
    "lng": 127.062554,
}

FAKE_NORMALIZED_NO_PNU = {**FAKE_NORMALIZED, "pnu": None}


def make_trade(amount, area, year, month):
    return {"dealAmount": amount, "exclusiveArea": area, "dealYear": str(year),
            "dealMonth": str(month), "dealDay": "1"}


class TestGetPropertyInfo(unittest.TestCase):

    @patch("property_aggregator.fetch_building_register")
    @patch("property_aggregator.fetch_apt_trades")
    @patch("property_aggregator.resolve_address")
    def test_full_success_combines_both_sources(self, mock_resolve, mock_trades, mock_building):
        mock_resolve.return_value = FAKE_NORMALIZED
        # 6개월치 호출 중 최근 3건에만 데이터가 있고 나머지는 not_found라고 가정
        mock_trades.side_effect = lambda lawd, ym: (
            {"status": "ok", "data": [make_trade(85000, 84.99, 2024, 3),
                                       make_trade(90000, 84.99, 2024, 3),
                                       make_trade(88000, 84.99, 2024, 3)]}
            if ym == "202403" else {"status": "not_found"}
        )
        mock_building.return_value = {
            "status": "ok",
            "data": [{"bldName": "래미안", "registerKind": "집합",
                      "violationStatusConfirmed": False, "violationStatusRaw": None}],
        }

        result = get_property_info("서울 강남구 테헤란로 427", target_area=84.99,
                                    as_of=date(2024, 4, 1))

        self.assertEqual(result["marketPrice"], 88000)
        self.assertEqual(result["marketPriceConfidence"], "high")
        self.assertEqual(result["registrySeparated"], True)
        self.assertEqual(result["sourceStatuses"]["transactionPrice"], "ok")
        self.assertEqual(result["sourceStatuses"]["buildingRegister"], "ok")

    @patch("property_aggregator.fetch_building_register")
    @patch("property_aggregator.fetch_apt_trades")
    @patch("property_aggregator.resolve_address")
    def test_partial_failure_building_error_does_not_block_market_price(
        self, mock_resolve, mock_trades, mock_building
    ):
        mock_resolve.return_value = FAKE_NORMALIZED
        mock_trades.side_effect = lambda lawd, ym: (
            {"status": "ok", "data": [make_trade(85000, 84.99, 2024, 3)] * 3}
            if ym == "202403" else {"status": "not_found"}
        )
        mock_building.return_value = {"status": "error", "reason": "api_down"}

        result = get_property_info("아무 주소", target_area=84.99, as_of=date(2024, 4, 1))

        # 건축물대장은 실패했지만 시세는 정상적으로 계산돼야 한다 (부분 실패 허용)
        self.assertEqual(result["marketPrice"], 85000)
        self.assertIsNone(result["building"])
        self.assertIsNone(result["registrySeparated"])
        self.assertEqual(result["sourceStatuses"]["buildingRegister"], "error")

    @patch("property_aggregator.fetch_building_register")
    @patch("property_aggregator.fetch_apt_trades")
    @patch("property_aggregator.resolve_address")
    def test_partial_failure_all_trades_not_found_still_returns_building_info(
        self, mock_resolve, mock_trades, mock_building
    ):
        mock_resolve.return_value = FAKE_NORMALIZED
        mock_trades.return_value = {"status": "not_found"}  # 6개월 내내 거래 없음
        mock_building.return_value = {
            "status": "ok",
            "data": [{"bldName": "테스트빌라", "registerKind": "일반건축물",
                      "violationStatusConfirmed": True, "violationStatusRaw": "위반"}],
        }

        result = get_property_info("아무 주소", target_area=59.5, as_of=date(2024, 4, 1))

        self.assertIsNone(result["marketPrice"])
        self.assertEqual(result["marketPriceConfidence"], "unavailable")
        self.assertEqual(result["registrySeparated"], False)
        self.assertTrue(result["violationStatusConfirmed"])
        self.assertEqual(result["violationStatusRaw"], "위반")

    @patch("property_aggregator.fetch_building_register")
    @patch("property_aggregator.fetch_villa_trades")
    @patch("property_aggregator.fetch_apt_trades")
    @patch("property_aggregator.resolve_address")
    def test_villa_property_type_queries_rh_endpoint_not_apartment(
        self, mock_resolve, mock_apt_trades, mock_villa_trades, mock_building
    ):
        # 실제로 겪은 버그: 예전엔 국토부 아파트매매 API만 있어서 빌라/다세대에도 그대로
        # 적용돼 근처 아파트 가격(더 비쌈)이 빌라 시세인 것처럼 나왔다. 연립다세대 전용
        # 엔드포인트(RHTrade)가 생겼으니, villa는 이제 그쪽으로만 조회해야 하고
        # 아파트 엔드포인트는 절대 호출하면 안 된다.
        mock_resolve.return_value = FAKE_NORMALIZED
        mock_villa_trades.side_effect = lambda lawd, ym: (
            {"status": "ok", "data": [make_trade(65000, 54.0, 2024, 3)] * 3}
            if ym == "202403" else {"status": "not_found"}
        )
        mock_building.return_value = {"status": "not_found"}

        result = get_property_info(
            "서울 강남구 테헤란로 427", target_area=54.0, as_of=date(2024, 4, 1), property_type="villa",
        )

        mock_apt_trades.assert_not_called()
        mock_villa_trades.assert_called()
        self.assertEqual(result["sourceStatuses"]["transactionPrice"], "ok")
        self.assertEqual(result["marketPrice"], 65000)

    @patch("property_aggregator.fetch_public_price")
    @patch("property_aggregator.fetch_building_register")
    @patch("property_aggregator.fetch_villa_trades")
    @patch("property_aggregator.resolve_address")
    def test_multi_household_also_routes_to_villa_endpoint(
        self, mock_resolve, mock_villa_trades, mock_building, mock_public_price
    ):
        # "연립다세대" API 한 종류가 연립주택+다세대주택을 모두 커버하므로
        # property_type="multi_household"도 villa와 같은 엔드포인트로 가야 한다.
        mock_resolve.return_value = FAKE_NORMALIZED
        mock_villa_trades.return_value = {"status": "not_found"}
        mock_building.return_value = {"status": "not_found"}
        mock_public_price.return_value = {"status": "error", "reason": "invalid_request"}

        get_property_info(
            "서울 강남구 테헤란로 427", target_area=39.6, as_of=date(2024, 4, 1), property_type="multi_household",
        )

        mock_villa_trades.assert_called()

    @patch("property_aggregator.fetch_public_price")
    @patch("property_aggregator.fetch_building_register")
    @patch("property_aggregator.fetch_villa_trades")
    @patch("property_aggregator.resolve_address")
    def test_villa_property_type_still_falls_back_to_public_price_when_no_trades(
        self, mock_resolve, mock_villa_trades, mock_building, mock_public_price
    ):
        mock_resolve.return_value = FAKE_NORMALIZED
        mock_villa_trades.return_value = {"status": "not_found"}
        mock_building.return_value = {"status": "not_found"}
        mock_public_price.return_value = {"status": "ok", "data": {"publicPrice": 50_000}}

        result = get_property_info(
            "서울 강남구 테헤란로 427", target_area=54.0, as_of=date(2024, 4, 1), property_type="villa",
        )

        self.assertEqual(result["marketPriceConfidence"], "estimated_from_public_price")
        self.assertEqual(result["marketPrice"], round(50_000 * 1.4))

    @patch("property_aggregator.fetch_building_register")
    @patch("property_aggregator.fetch_officetel_trades")
    @patch("property_aggregator.resolve_address")
    def test_officetel_property_type_queries_offi_endpoint(
        self, mock_resolve, mock_offi_trades, mock_building
    ):
        mock_resolve.return_value = FAKE_NORMALIZED
        mock_offi_trades.side_effect = lambda lawd, ym: (
            {"status": "ok", "data": [make_trade(32000, 21.5, 2024, 3)] * 3}
            if ym == "202403" else {"status": "not_found"}
        )
        mock_building.return_value = {"status": "not_found"}

        result = get_property_info(
            "서울 강남구 테헤란로 427", target_area=21.5, as_of=date(2024, 4, 1), property_type="officetel",
        )

        mock_offi_trades.assert_called()
        self.assertEqual(result["marketPrice"], 32000)

    @patch("property_aggregator.fetch_public_price")
    @patch("property_aggregator.fetch_building_register")
    @patch("property_aggregator.fetch_apt_trades")
    @patch("property_aggregator.fetch_villa_trades")
    @patch("property_aggregator.fetch_officetel_trades")
    @patch("property_aggregator.resolve_address")
    def test_unknown_property_type_skips_all_trade_fetches_defensively(
        self, mock_resolve, mock_offi, mock_villa, mock_apt, mock_building, mock_public_price
    ):
        # 매핑에 없는 property_type이 어쩌다 들어와도(방어적) 어떤 실거래 엔드포인트도
        # 잘못 호출하지 않고 안전하게 건너뛰어야 한다.
        mock_resolve.return_value = FAKE_NORMALIZED
        mock_building.return_value = {"status": "not_found"}
        mock_public_price.return_value = {"status": "error", "reason": "invalid_request"}

        result = get_property_info(
            "서울 강남구 테헤란로 427", target_area=54.0, as_of=date(2024, 4, 1), property_type="단독주택",
        )

        mock_apt.assert_not_called()
        mock_villa.assert_not_called()
        mock_offi.assert_not_called()
        self.assertEqual(result["sourceStatuses"]["transactionPrice"], "skipped")

    @patch("property_aggregator.fetch_building_register")
    @patch("property_aggregator.fetch_apt_trades")
    @patch("property_aggregator.resolve_address")
    def test_apartment_property_type_still_uses_trade_data(
        self, mock_resolve, mock_trades, mock_building
    ):
        # 기본값(생략 시 "apartment")과 명시적으로 "apartment"를 넘긴 경우 모두
        # 기존 동작(아파트 실거래 비교)이 그대로 유지돼야 한다.
        mock_resolve.return_value = FAKE_NORMALIZED
        mock_trades.side_effect = lambda lawd, ym: (
            {"status": "ok", "data": [make_trade(85000, 84.99, 2024, 3)] * 3}
            if ym == "202403" else {"status": "not_found"}
        )
        mock_building.return_value = {"status": "not_found"}

        result = get_property_info(
            "서울 강남구 테헤란로 427", target_area=84.99, as_of=date(2024, 4, 1), property_type="apartment",
        )

        mock_trades.assert_called()
        self.assertEqual(result["sourceStatuses"]["transactionPrice"], "ok")
        self.assertEqual(result["marketPrice"], 85000)

    @patch("property_aggregator.resolve_address")
    def test_address_resolution_failure_raises(self, mock_resolve):
        mock_resolve.side_effect = AddressResolutionError("주소를 찾을 수 없습니다")

        with self.assertRaises(PropertyAggregationError):
            get_property_info("이상한주소", target_area=84.99)

    @patch("property_aggregator.fetch_building_register")
    @patch("property_aggregator.fetch_apt_trades")
    @patch("property_aggregator.resolve_address")
    def test_missing_pnu_skips_building_call_without_crashing(
        self, mock_resolve, mock_trades, mock_building
    ):
        # 동 단위로만 검색돼 PNU를 못 만든 경우 (예: 다가구 지번 특정 실패)
        mock_resolve.return_value = FAKE_NORMALIZED_NO_PNU
        mock_trades.return_value = {"status": "not_found"}

        result = get_property_info("동 단위 주소", target_area=59.5, as_of=date(2024, 4, 1))

        mock_building.assert_not_called()  # PNU 없으면 애초에 호출 시도조차 안 해야 함
        self.assertEqual(result["sourceStatuses"]["buildingRegister"], "error")
        self.assertIsNone(result["building"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
