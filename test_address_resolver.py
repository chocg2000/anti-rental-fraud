"""
AddressResolver 단위 테스트 (Mocking 기반)
--------------------------------------------
실제 카카오 API를 호출하지 않고, requests.get()을 가짜 응답으로 대체해서
- PNU 조합 로직
- 에러 분기 (주소 없음 / 타임아웃 / API 오류)
만 검증한다. 카카오 API가 점검 중이거나 인터넷이 안 되는 환경에서도 실행 가능.

실행: python -m unittest test_address_resolver.py -v
"""

import unittest
from unittest.mock import patch, Mock
import requests

from address_resolver import resolve_address, AddressResolutionError, _build_pnu


def make_fake_response(json_data, status_code=200, raise_for_status_error=None):
    """requests.Response를 흉내내는 Mock 객체 생성"""
    fake = Mock()
    fake.status_code = status_code
    fake.json.return_value = json_data
    if raise_for_status_error:
        fake.raise_for_status.side_effect = raise_for_status_error
    else:
        fake.raise_for_status.return_value = None
    return fake


# ---- 카카오 API 응답 형태를 흉내낸 고정 데이터(fixture) ----

FAKE_KAKAO_RESPONSE_NORMAL = {
    "documents": [
        {
            "address_name": "서울 강남구 삼성동 159",
            "address": {
                "address_name": "서울 강남구 삼성동 159",
                "region_1depth_name": "서울",
                "region_2depth_name": "강남구",
                "region_3depth_name": "삼성동",
                "b_code": "1168010500",
                "mountain_yn": "N",
                "main_address_no": "159",
                "sub_address_no": "",
                "zip_code": "06164",
                "x": "127.062554",
                "y": "37.508845",
            },
            "road_address": {
                "address_name": "서울 강남구 테헤란로 427",
            },
            "x": "127.062554",
            "y": "37.508845",
        }
    ]
}

FAKE_KAKAO_RESPONSE_MOUNTAIN = {
    "documents": [
        {
            "address_name": "경기 가평군 청평면 삼회리 산1-1",
            "address": {
                "address_name": "경기 가평군 청평면 삼회리 산1-1",
                "b_code": "4182034021",
                "mountain_yn": "Y",
                "main_address_no": "1",
                "sub_address_no": "1",
                "x": "127.4",
                "y": "37.7",
            },
            "road_address": None,
            "x": "127.4",
            "y": "37.7",
        }
    ]
}

FAKE_KAKAO_RESPONSE_NO_MAIN_NO = {
    "documents": [
        {
            "address_name": "서울 중랑구 중화동",
            "address": {
                "address_name": "서울 중랑구 중화동",
                "b_code": "1126010300",
                "mountain_yn": "N",
                "main_address_no": "",
                "sub_address_no": "",
                "x": "127.07",
                "y": "37.59",
            },
            "road_address": None,
            "x": "127.07",
            "y": "37.59",
        }
    ]
}

FAKE_KAKAO_RESPONSE_EMPTY = {"documents": []}


class TestBuildPnu(unittest.TestCase):
    """PNU 조합 로직 자체의 단위 테스트 (네트워크 전혀 무관)"""

    def test_normal_case(self):
        pnu = _build_pnu(b_code="1168010500", mountain_yn="N", main_no="159", sub_no="")
        self.assertEqual(pnu, "1168010500001590000")

    def test_mountain_flag(self):
        pnu = _build_pnu(b_code="4182034021", mountain_yn="Y", main_no="1", sub_no="1")
        # b_code(10) + 산여부'1'(1) + 본번 0001(4) + 부번 0001(4) = 19자리
        self.assertEqual(pnu, "4182034021100010001")

    def test_missing_main_no_returns_none(self):
        pnu = _build_pnu(b_code="1126010300", mountain_yn="N", main_no="", sub_no="")
        self.assertIsNone(pnu)


class TestResolveAddress(unittest.TestCase):
    """resolve_address()를 requests.get Mocking으로 검증"""

    @patch("address_resolver.requests.get")
    def test_success_with_road_address(self, mock_get):
        mock_get.return_value = make_fake_response(FAKE_KAKAO_RESPONSE_NORMAL)

        result = resolve_address("테헤란로 427")

        self.assertEqual(result["legalDongCode"], "1168010500")
        self.assertEqual(result["roadAddress"], "서울 강남구 테헤란로 427")
        self.assertEqual(result["jibunAddress"], "서울 강남구 삼성동 159")
        self.assertIsNotNone(result["pnu"])
        self.assertAlmostEqual(result["lat"], 37.508845)
        mock_get.assert_called_once()  # API가 정확히 1번만 호출됐는지도 확인

    @patch("address_resolver.requests.get")
    def test_success_mountain_address_no_road_address(self, mock_get):
        mock_get.return_value = make_fake_response(FAKE_KAKAO_RESPONSE_MOUNTAIN)

        result = resolve_address("삼회리 산1-1")

        self.assertIsNone(result["roadAddress"])  # 산지라 도로명주소가 없는 케이스
        self.assertTrue(result["pnu"].startswith("41820340211"))  # 산여부 플래그 '1' 확인

    @patch("address_resolver.requests.get")
    def test_pnu_none_when_main_address_no_missing(self, mock_get):
        mock_get.return_value = make_fake_response(FAKE_KAKAO_RESPONSE_NO_MAIN_NO)

        result = resolve_address("중화동")

        self.assertIsNone(result["pnu"])  # 동 단위 검색이라 지번 특정 안 됨 → PNU 없음

    @patch("address_resolver.requests.get")
    def test_no_documents_raises(self, mock_get):
        mock_get.return_value = make_fake_response(FAKE_KAKAO_RESPONSE_EMPTY)

        with self.assertRaises(AddressResolutionError):
            resolve_address("이런주소는없음asdf1234")

    @patch("address_resolver.requests.get")
    def test_timeout_raises_address_resolution_error(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout()

        with self.assertRaises(AddressResolutionError) as ctx:
            resolve_address("아무 주소")
        self.assertIn("타임아웃", str(ctx.exception))

    @patch("address_resolver.requests.get")
    def test_api_500_error_raises(self, mock_get):
        # API 서버 점검/장애 상황을 흉내낸다 (raise_for_status가 HTTPError를 던짐)
        mock_get.return_value = make_fake_response(
            {}, status_code=500,
            raise_for_status_error=requests.exceptions.HTTPError("500 Server Error")
        )

        with self.assertRaises(AddressResolutionError):
            resolve_address("아무 주소")

    def test_empty_query_raises_without_network_call(self):
        # 네트워크 호출 자체가 필요 없는 입력값 검증 — Mocking조차 필요 없는 케이스
        with self.assertRaises(AddressResolutionError):
            resolve_address("   ")


if __name__ == "__main__":
    unittest.main(verbosity=2)
