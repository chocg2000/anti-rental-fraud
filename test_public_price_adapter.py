"""
public_price_adapter 단위 테스트
----------------------------------
2026-09-15: 에러 응답 구조는 실제 vworld 응답(REAL_PARAM_REQUIRED_ERROR, 지인이 브라우저로
대신 호출해서 받아온 원본)으로 확인됨 — 이 부분 테스트는 진짜 검증이다.

⚠️ 성공("OK") 응답 쪽은 여전히 미검증이다 — 레이어 ID(`VWORLD_HOUSING_PRICE_LAYER_ID`)를
아직 못 찾아서 성공 응답을 한 번도 못 받아봤다. FAKE_OK_RESPONSE/FAKE_EMPTY_RESPONSE는
여전히 추측 픽스처이니, 실제 성공 응답을 받으면 반드시 다시 맞출 것.
"""

import unittest
from unittest.mock import Mock, patch

from public_price_adapter import (
    PublicPriceApiError,
    _parse_response,
    fetch_public_price,
)

# 실제 vworld 응답 원본 (2026-09-15, PARAM_REQUIRED 에러를 일부러 유도해서 받음).
# service/status/error 봉투 구조 자체가 검증된 골든 픽스처 — 함부로 고치지 말 것.
REAL_PARAM_REQUIRED_ERROR = {
    "response": {
        "service": {"name": "data", "version": "2.0", "operation": "GetFeature", "time": "6(ms)"},
        "status": "ERROR",
        "error": {
            "level": "1",
            "code": "PARAM_REQUIRED",
            "text": "필수 파라미터인 data가 없어서 요청을 처리할수 없습니다.",
        },
    }
}

# ⚠️ 아래부터는 여전히 미검증 추측 픽스처 (성공 응답 구조 미확인)
FAKE_OK_RESPONSE = {
    "response": {
        "status": "OK",
        "result": {
            "featureCollection": {
                "features": [
                    {"properties": {"price": "45000", "pnu": "1168010500001590000"}},
                ]
            }
        },
    }
}

FAKE_EMPTY_RESPONSE = {
    "response": {
        "status": "OK",
        "result": {"featureCollection": {"features": []}},
    }
}


class TestParseResponse(unittest.TestCase):

    def test_real_param_required_error_raises_with_code_and_text(self):
        # 골든 픽스처 — 실제 vworld 응답 그대로
        with self.assertRaises(PublicPriceApiError) as ctx:
            _parse_response(REAL_PARAM_REQUIRED_ERROR)
        self.assertIn("PARAM_REQUIRED", str(ctx.exception))
        self.assertIn("data가 없어서", str(ctx.exception))

    def test_extracts_price_from_known_shape(self):
        self.assertEqual(_parse_response(FAKE_OK_RESPONSE), 45000)

    def test_no_features_returns_none(self):
        self.assertIsNone(_parse_response(FAKE_EMPTY_RESPONSE))

    def test_unexpected_status_value_raises(self):
        with self.assertRaises(PublicPriceApiError):
            _parse_response({"response": {"status": "NOT_A_REAL_STATUS"}})

    def test_unexpected_shape_raises(self):
        with self.assertRaises(PublicPriceApiError):
            _parse_response({"totally": "unexpected"})

    def test_missing_price_field_raises(self):
        payload = {
            "response": {
                "status": "OK",
                "result": {"featureCollection": {"features": [{"properties": {"foo": "bar"}}]}},
            }
        }
        with self.assertRaises(PublicPriceApiError):
            _parse_response(payload)


class TestFetchPublicPrice(unittest.TestCase):

    @patch("public_price_adapter.VWORLD_API_KEY", None)
    @patch("public_price_adapter.requests.get")
    def test_no_api_key_returns_error_without_network_call(self, mock_get):
        result = fetch_public_price("1168010500001590000")

        self.assertEqual(result, {"status": "error", "reason": "invalid_request"})
        mock_get.assert_not_called()

    @patch("public_price_adapter.VWORLD_API_KEY", "fake-key")
    @patch("public_price_adapter.DATA_LAYER_ID", "TODO_CONFIRM_LAYER_ID")
    @patch("public_price_adapter.requests.get")
    def test_placeholder_layer_id_returns_error_without_network_call(self, mock_get):
        # 레이어 ID를 아직 확인 못 한 상태(기본 플레이스홀더)에서는 vworld에 잘못된
        # 요청을 계속 보내지 않도록 여기서 막아야 한다.
        result = fetch_public_price("1168010500001590000")

        self.assertEqual(result, {"status": "error", "reason": "invalid_request"})
        mock_get.assert_not_called()

    @patch("public_price_adapter.VWORLD_API_KEY", "fake-key")
    @patch("public_price_adapter.DATA_LAYER_ID", "some_confirmed_layer")
    @patch("public_price_adapter.requests.get")
    def test_ok_when_key_and_layer_configured(self, mock_get):
        mock_get.return_value = Mock(json=lambda: FAKE_OK_RESPONSE)
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_public_price("1168010500001590000")

        self.assertEqual(result, {"status": "ok", "data": {"publicPrice": 45000}})

    @patch("public_price_adapter.VWORLD_API_KEY", "fake-key")
    @patch("public_price_adapter.DATA_LAYER_ID", "some_confirmed_layer")
    @patch("public_price_adapter.requests.get")
    def test_not_found_when_no_features(self, mock_get):
        mock_get.return_value = Mock(json=lambda: FAKE_EMPTY_RESPONSE)
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_public_price("1168010500001590000")

        self.assertEqual(result, {"status": "not_found"})

    @patch("public_price_adapter.VWORLD_API_KEY", "fake-key")
    @patch("public_price_adapter.DATA_LAYER_ID", "some_confirmed_layer")
    @patch("public_price_adapter.requests.get")
    def test_unexpected_response_shape_maps_to_invalid_request(self, mock_get):
        mock_get.return_value = Mock(json=lambda: {"totally": "unexpected"})
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_public_price("1168010500001590000")

        self.assertEqual(result, {"status": "error", "reason": "invalid_request"})

    @patch("public_price_adapter.VWORLD_API_KEY", "fake-key")
    @patch("public_price_adapter.DATA_LAYER_ID", "some_confirmed_layer")
    @patch("public_price_adapter.requests.get")
    def test_real_vworld_error_response_maps_to_invalid_request(self, mock_get):
        # 골든 픽스처(실제 vworld 응답)를 fetch_public_price 전체 경로로 흘려보내는 테스트.
        mock_get.return_value = Mock(json=lambda: REAL_PARAM_REQUIRED_ERROR)
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_public_price("1168010500001590000")

        self.assertEqual(result, {"status": "error", "reason": "invalid_request"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
