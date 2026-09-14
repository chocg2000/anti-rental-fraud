"""
public_price_adapter 단위 테스트
----------------------------------
⚠️ _parse_response()가 가정하는 응답 구조 자체가 미검증이라는 점을 기억할 것 —
이 테스트는 "우리가 짠 파싱 로직이 그 가정대로 동작하는지"만 검증하지, "vworld가
실제로 이 구조로 응답하는지"는 검증하지 못한다. 실제 응답을 확인하면 이 테스트의
FAKE_* 픽스처부터 다시 맞춰야 할 가능성이 높다.
"""

import unittest
from unittest.mock import Mock, patch

from public_price_adapter import (
    PublicPriceApiError,
    _parse_response,
    fetch_public_price,
)

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

FAKE_NOT_OK_RESPONSE = {"response": {"status": "NOT_FOUND"}}


class TestParseResponse(unittest.TestCase):

    def test_extracts_price_from_known_shape(self):
        self.assertEqual(_parse_response(FAKE_OK_RESPONSE), 45000)

    def test_no_features_returns_none(self):
        self.assertIsNone(_parse_response(FAKE_EMPTY_RESPONSE))

    def test_non_ok_status_raises(self):
        with self.assertRaises(PublicPriceApiError):
            _parse_response(FAKE_NOT_OK_RESPONSE)

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
