"""
ClovaOcrAdapter 단위 테스트 (Mocking 기반)
--------------------------------------------
실제 Secret Key 없이, 네이버 공식 문서 스펙을 흉내낸 응답으로 어댑터의 요청 구성과
에러 분기만 검증한다. 실제 응답 구조 자체는 미검증 — 모듈 docstring 참고.
"""

import unittest
from unittest.mock import patch, Mock

import clova_ocr_adapter
from clova_ocr_adapter import fetch_ocr_result


FAKE_SUCCESS_RESPONSE = {
    "version": "V2",
    "requestId": "test-request-id",
    "timestamp": 1710000000000,
    "images": [
        {
            "uid": "abc123",
            "name": "registry_page",
            "inferResult": "SUCCESS",
            "message": "SUCCESS",
            "fields": [
                {"inferText": "1", "boundingPoly": {"vertices": [{"x": 10, "y": 100}]}},
                {"inferText": "소유권이전", "boundingPoly": {"vertices": [{"x": 40, "y": 100}]}},
            ],
        }
    ],
}

FAKE_FAILURE_RESPONSE = {
    "version": "V2",
    "requestId": "test-request-id",
    "timestamp": 1710000000000,
    "images": [
        {"uid": "abc123", "name": "registry_page", "inferResult": "FAILURE", "message": "이미지 인식 실패"}
    ],
}


class TestFetchOcrResult(unittest.TestCase):

    def setUp(self):
        self._orig_url = clova_ocr_adapter.CLOVA_OCR_INVOKE_URL
        self._orig_secret = clova_ocr_adapter.CLOVA_OCR_SECRET
        clova_ocr_adapter.CLOVA_OCR_INVOKE_URL = "https://fake.apigw.ntruss.com/custom/v1/1/fake/general"
        clova_ocr_adapter.CLOVA_OCR_SECRET = "fake-secret"

    def tearDown(self):
        clova_ocr_adapter.CLOVA_OCR_INVOKE_URL = self._orig_url
        clova_ocr_adapter.CLOVA_OCR_SECRET = self._orig_secret

    def test_missing_credentials_returns_invalid_request_without_network_call(self):
        clova_ocr_adapter.CLOVA_OCR_INVOKE_URL = ""
        clova_ocr_adapter.CLOVA_OCR_SECRET = ""

        with patch("clova_ocr_adapter.requests.post") as mock_post:
            result = fetch_ocr_result(b"fake-pdf-bytes")

        mock_post.assert_not_called()
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "invalid_request")

    @patch("clova_ocr_adapter.requests.post")
    def test_success_response_returns_ok_with_data(self, mock_post):
        mock_post.return_value = Mock(status_code=200)
        mock_post.return_value.json.return_value = FAKE_SUCCESS_RESPONSE

        result = fetch_ocr_result(b"fake-pdf-bytes")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"], FAKE_SUCCESS_RESPONSE)

    @patch("clova_ocr_adapter.requests.post")
    def test_request_body_matches_documented_spec(self, mock_post):
        mock_post.return_value = Mock(status_code=200)
        mock_post.return_value.json.return_value = FAKE_SUCCESS_RESPONSE

        fetch_ocr_result(b"fake-pdf-bytes", image_format="pdf", image_name="gapgu")

        call_kwargs = mock_post.call_args.kwargs
        body = call_kwargs["json"]
        self.assertEqual(body["version"], "V2")
        self.assertIn("requestId", body)
        self.assertIn("timestamp", body)
        self.assertEqual(body["images"][0]["format"], "pdf")
        self.assertEqual(body["images"][0]["name"], "gapgu")
        self.assertIn("data", body["images"][0])  # base64 인코딩된 이미지
        self.assertEqual(call_kwargs["headers"]["X-OCR-SECRET"], "fake-secret")

    @patch("clova_ocr_adapter.requests.post")
    def test_infer_result_failure_is_treated_as_invalid_request(self, mock_post):
        mock_post.return_value = Mock(status_code=200)
        mock_post.return_value.json.return_value = FAKE_FAILURE_RESPONSE

        result = fetch_ocr_result(b"fake-pdf-bytes")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "invalid_request")

    @patch("clova_ocr_adapter.requests.post")
    def test_http_error_status_is_invalid_request(self, mock_post):
        mock_post.return_value = Mock(status_code=401)

        result = fetch_ocr_result(b"fake-pdf-bytes")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "invalid_request")

    @patch("clova_ocr_adapter.requests.post")
    def test_network_timeout_maps_to_api_down(self, mock_post):
        import requests as real_requests
        mock_post.side_effect = real_requests.exceptions.Timeout()

        result = fetch_ocr_result(b"fake-pdf-bytes")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "api_down")


if __name__ == "__main__":
    unittest.main(verbosity=2)
