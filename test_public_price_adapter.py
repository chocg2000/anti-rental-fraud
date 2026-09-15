"""
public_price_adapter 단위 테스트
----------------------------------
2026-09-15: 성공 응답 구조는 지인이 vworld 공식 API 레퍼런스 페이지의 "API결과
미리보기" 버튼으로 받아온 실제 XML 원본(REAL_SUCCESS_XML)으로 검증됨 — 이 파일의
성공 케이스 테스트는 진짜 골든 테스트다.

⚠️ 에러 응답이 XML로도 같은 구조로 오는지는 아직 실제로 확인 못 했다 (2026-09-14에
확인한 에러 봉투는 다른 엔드포인트를 JSON으로 호출해서 받은 것). REAL_ERROR_XML은
그 JSON 구조를 XML 태그로 옮겨 적은 추정 픽스처다 — 실제 에러를 XML로 받아보면
다시 맞출 것.
"""

import unittest
from unittest.mock import Mock, patch

from public_price_adapter import (
    PublicPriceApiError,
    _parse_response,
    fetch_public_price,
)

# 실제 vworld 응답 원본 (2026-09-15, 공식 API 레퍼런스 페이지 "API결과 미리보기"로 확인).
# 서울 마포구 상암동 상암월드컵1단지 101동 201호 — 골든 픽스처, 함부로 고치지 말 것.
REAL_SUCCESS_XML = """<response>
  <numOfRows>10</numOfRows>
  <pageNo>1</pageNo>
  <totalCount>1</totalCount>
  <fields>
    <field>
      <pnu>1144012700116340000</pnu>
      <idCode>1144012700</idCode>
      <idCodeNm>서울특별시 마포구 상암동</idCodeNm>
      <regstrSeCode>1</regstrSeCode>
      <regstrSeCodeNm>일반</regstrSeCodeNm>
      <mnnmSlno>1634</mnnmSlno>
      <stdrYear>2012</stdrYear>
      <stdrMt>01</stdrMt>
      <aphusCode>20022499</aphusCode>
      <aphusSeCode>1</aphusSeCode>
      <aphusSeCodeNm>아파트</aphusSeCodeNm>
      <spclLandNm>상암택지개발사업지구2-1블럭</spclLandNm>
      <aphusNm>상암월드컵1단지</aphusNm>
      <dongNm>101</dongNm>
      <floorNm>2</floorNm>
      <hoNm>201</hoNm>
      <prvuseAr>39.66</prvuseAr>
      <pblntfPc>60000000</pblntfPc>
      <lastUpdtDt>2023-08-24</lastUpdtDt>
    </field>
  </fields>
</response>"""

REAL_NO_RESULT_XML = """<response>
  <numOfRows>10</numOfRows>
  <pageNo>1</pageNo>
  <totalCount>0</totalCount>
  <fields></fields>
</response>"""

# 2026-09-15, 배포 서버(국내 리전)에서 실제로 받은 "결과 없음" 응답 원본(다세대주택 PNU로
# 조회 — 이 API는 아파트 전용이라 애초에 대상이 아님). 위 REAL_NO_RESULT_XML은 <fields>가
# 빈 채로라도 존재한다고 가정했었는데, 실제로는 totalCount=0일 때 <fields> 태그 자체가
# 아예 빠진다 — 이전 가정이 틀렸었다는 걸 실제 응답으로 확인한 골든 픽스처.
REAL_NO_RESULT_XML_NO_FIELDS_TAG = """<response><numOfRows>100</numOfRows><pageNo>1</pageNo><totalCount>0</totalCount></response>"""

# 하나의 pnu(단지 전체)에 여러 동/호가 함께 돌아오는 경우를 가정한 픽스처
# (dongNm/hoNm을 생략하고 조회했을 때를 대비 — 실제로 이렇게 오는지는 미확인).
MULTIPLE_FIELDS_XML = """<response>
  <numOfRows>100</numOfRows>
  <pageNo>1</pageNo>
  <totalCount>3</totalCount>
  <fields>
    <field><dongNm>101</dongNm><hoNm>101</hoNm><pblntfPc>400000000</pblntfPc></field>
    <field><dongNm>101</dongNm><hoNm>201</hoNm><pblntfPc>450000000</pblntfPc></field>
    <field><dongNm>102</dongNm><hoNm>301</hoNm><pblntfPc>500000000</pblntfPc></field>
  </fields>
</response>"""

# ⚠️ 미검증 추정 픽스처 — 2026-09-14에 확인한 JSON 에러 봉투를 XML 태그로 옮겨 적은 것.
# 실제로 이 XML 구조로 오는지는 아직 확인 안 됨.
ASSUMED_ERROR_XML = """<response>
  <status>ERROR</status>
  <error>
    <level>1</level>
    <code>PARAM_REQUIRED</code>
    <text>필수 파라미터인 pnu가 없어서 요청을 처리할수 없습니다.</text>
  </error>
</response>"""

NOT_EVEN_XML = "<<< this is not xml at all"


class TestParseResponse(unittest.TestCase):

    def test_real_success_xml_converts_won_to_manwon(self):
        # 골든 픽스처 — pblntfPc=60,000,000원 -> 6,000만원
        self.assertEqual(_parse_response(REAL_SUCCESS_XML), 6000)

    def test_real_no_result_xml_returns_none(self):
        # 골든 픽스처 — totalCount=0, fields 비어있음
        self.assertIsNone(_parse_response(REAL_NO_RESULT_XML))

    def test_real_no_result_xml_without_fields_tag_returns_none(self):
        # 2026-09-15 배포 서버에서 실제로 받은 형태 — <fields> 태그 자체가 없음
        self.assertIsNone(_parse_response(REAL_NO_RESULT_XML_NO_FIELDS_TAG))

    def test_multiple_fields_uses_median(self):
        # 400,000,000 / 450,000,000 / 500,000,000원 -> 중위값 450,000,000원 -> 45,000만원
        self.assertEqual(_parse_response(MULTIPLE_FIELDS_XML), 45000)

    def test_assumed_error_xml_raises_with_code_and_text(self):
        with self.assertRaises(PublicPriceApiError) as ctx:
            _parse_response(ASSUMED_ERROR_XML)
        self.assertIn("PARAM_REQUIRED", str(ctx.exception))

    def test_broken_xml_raises(self):
        with self.assertRaises(PublicPriceApiError):
            _parse_response(NOT_EVEN_XML)

    def test_missing_fields_element_raises(self):
        with self.assertRaises(PublicPriceApiError):
            _parse_response("<response><numOfRows>10</numOfRows></response>")

    def test_missing_price_field_raises(self):
        xml = """<response><fields><field><dongNm>101</dongNm></field></fields></response>"""
        with self.assertRaises(PublicPriceApiError):
            _parse_response(xml)


class TestFetchPublicPrice(unittest.TestCase):

    @patch("public_price_adapter.VWORLD_API_KEY", None)
    @patch("public_price_adapter.requests.get")
    def test_no_api_key_returns_error_without_network_call(self, mock_get):
        result = fetch_public_price("1144012700116340000")

        self.assertEqual(result, {"status": "error", "reason": "invalid_request"})
        mock_get.assert_not_called()

    @patch("public_price_adapter.VWORLD_API_KEY", "fake-key")
    @patch("public_price_adapter.requests.get")
    def test_ok_with_real_response_shape(self, mock_get):
        mock_get.return_value = Mock(text=REAL_SUCCESS_XML)
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_public_price("1144012700116340000")

        self.assertEqual(result, {"status": "ok", "data": {"publicPrice": 6000}})

    @patch("public_price_adapter.VWORLD_API_KEY", "fake-key")
    @patch("public_price_adapter.requests.get")
    def test_not_found_when_no_fields(self, mock_get):
        mock_get.return_value = Mock(text=REAL_NO_RESULT_XML)
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_public_price("1168010500001590000")

        self.assertEqual(result, {"status": "not_found"})

    @patch("public_price_adapter.VWORLD_API_KEY", "fake-key")
    @patch("public_price_adapter.requests.get")
    def test_broken_response_maps_to_invalid_request(self, mock_get):
        mock_get.return_value = Mock(text=NOT_EVEN_XML)
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_public_price("1168010500001590000")

        self.assertEqual(result, {"status": "error", "reason": "invalid_request"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
