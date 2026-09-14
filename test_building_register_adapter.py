"""
BuildingRegisterAdapter 단위 테스트 (Mocking 기반)
"""

import unittest
from unittest.mock import patch, Mock

from building_register_adapter import (
    parse_building_register_xml,
    fetch_building_register,
    BuildingRegisterApiError,
    is_registered_as_non_residential,
)


XML_NORMAL = """<response>
  <header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE</resultMsg></header>
  <body>
    <items>
      <item>
        <bldNm>래미안</bldNm>
        <mainPurpsCdNm>공동주택</mainPurpsCdNm>
        <etcPurps></etcPurps>
        <regstrKindCdNm>집합</regstrKindCdNm>
        <useAprDay>20050815</useAprDay>
        <hhldCnt>450</hhldCnt>
        <rserthqkDsgnApplyYn>1</rserthqkDsgnApplyYn>
        <totArea>85234.5</totArea>
      </item>
    </items>
    <numOfRows>20</numOfRows><pageNo>1</pageNo><totalCount>1</totalCount>
  </body>
</response>"""

# 위반건축물 후보 필드 중 하나가 실제로 채워져 있다고 가정한 케이스 (아직 실증 전 — 추측 기반 fixture)
XML_WITH_VIOLATION_CANDIDATE_FIELD = """<response>
  <header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE</resultMsg></header>
  <body>
    <items>
      <item>
        <bldNm>다가구주택</bldNm>
        <mainPurpsCdNm>단독주택</mainPurpsCdNm>
        <regstrKindCdNm>일반건축물</regstrKindCdNm>
        <useAprDay>19950101</useAprDay>
        <violationStatus>위반</violationStatus>
      </item>
    </items>
    <numOfRows>20</numOfRows><pageNo>1</pageNo><totalCount>1</totalCount>
  </body>
</response>"""

XML_NO_RESULTS = """<response>
  <header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE</resultMsg></header>
  <body><items></items><numOfRows>20</numOfRows><pageNo>1</pageNo><totalCount>0</totalCount></body>
</response>"""

XML_CMM_HEADER_ERROR = """<OpenAPI_ServiceResponse>
  <cmmMsgHeader>
    <errMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</errMsg>
  </cmmMsgHeader>
</OpenAPI_ServiceResponse>"""

# 2026-09-12 실제 승인 키로 확인한 진짜 응답 중 일부(코엑스, 강남구 삼성동 159번지).
# 이 API의 성공 코드가 "00"(두 자리)이라는 걸 놓쳐서 정상 응답을 에러로 오인했던 버그의 회귀 테스트.
XML_REAL_CAPTURED_COEX = """<response>
  <header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE</resultMsg></header>
  <body>
    <items>
      <item>
        <platPlc>서울특별시 강남구 삼성동 159번지</platPlc>
        <sigunguCd>11680</sigunguCd>
        <bjdongCd>10500</bjdongCd>
        <regstrGbCdNm>집합</regstrGbCdNm>
        <regstrKindCdNm>일반건축물</regstrKindCdNm>
        <newPlatPlc>서울특별시 강남구 영동대로 513 (삼성동) 한국종합무역센터단지</newPlatPlc>
        <bldNm></bldNm>
        <totArea>223985.02</totArea>
        <mainPurpsCd>05000</mainPurpsCd>
        <mainPurpsCdNm>문화및집회시설</mainPurpsCdNm>
        <etcPurps>문화및집회시설,업무시설,전시시설,판매시설,근린생활시설</etcPurps>
        <hhldCnt>0</hhldCnt>
        <useAprDay>20000203</useAprDay>
        <rserthqkDsgnApplyYn>1</rserthqkDsgnApplyYn>
      </item>
    </items>
    <numOfRows>1</numOfRows><pageNo>1</pageNo><totalCount>9</totalCount>
  </body>
</response>"""


class TestParseBuildingRegisterXml(unittest.TestCase):

    def test_parses_normal_building(self):
        buildings = parse_building_register_xml(XML_NORMAL)

        self.assertEqual(len(buildings), 1)
        b = buildings[0]
        self.assertEqual(b["bldName"], "래미안")
        self.assertEqual(b["registerKind"], "집합")
        self.assertEqual(b["householdCount"], "450")
        self.assertFalse(b["violationStatusConfirmed"])  # 이 fixture엔 후보 필드가 없음
        self.assertIsNone(b["violationStatusRaw"])
        self.assertFalse(b["isRegisteredAsNonResidential"])  # 주용도가 "공동주택"이라 정상

    def test_non_residential_use_detection(self):
        self.assertTrue(is_registered_as_non_residential("제2종근린생활시설"))
        self.assertTrue(is_registered_as_non_residential("업무시설"))
        self.assertFalse(is_registered_as_non_residential("공동주택"))
        self.assertFalse(is_registered_as_non_residential("단독주택"))

    def test_geunsaeng_villa_pattern_flagged(self):
        # '근생빌라' 패턴: 표제부 주용도가 근린생활시설인데 실제로는 원룸처럼 임대되는 케이스
        xml = XML_NORMAL.replace("<mainPurpsCdNm>공동주택</mainPurpsCdNm>",
                                  "<mainPurpsCdNm>제2종근린생활시설</mainPurpsCdNm>")
        buildings = parse_building_register_xml(xml)
        self.assertTrue(buildings[0]["isRegisteredAsNonResidential"])

    def test_parses_real_captured_response_with_two_digit_success_code(self):
        # resultCode="00"(두 자리)을 실거래가 API의 "000"과 혼동해 정상 응답을
        # 에러로 오인했던 실제 버그의 회귀 테스트.
        buildings = parse_building_register_xml(XML_REAL_CAPTURED_COEX)

        self.assertEqual(len(buildings), 1)
        b = buildings[0]
        self.assertEqual(b["mainPurpose"], "문화및집회시설")
        self.assertEqual(b["registerKind"], "일반건축물")
        self.assertEqual(b["totalFloorArea"], "223985.02")

    def test_violation_candidate_field_extracted_when_present(self):
        # 아직 실제로 검증되지 않은 필드명 추측이 맞다면 이렇게 잡힌다는 걸 보여주는 테스트.
        # 실제 키로 확인되면 이 fixture를 진짜 응답으로 교체할 것.
        buildings = parse_building_register_xml(XML_WITH_VIOLATION_CANDIDATE_FIELD)

        b = buildings[0]
        self.assertTrue(b["violationStatusConfirmed"])
        self.assertEqual(b["violationStatusRaw"], "위반")

    def test_empty_items_returns_empty_list(self):
        self.assertEqual(parse_building_register_xml(XML_NO_RESULTS), [])

    def test_cmm_header_error_raises(self):
        with self.assertRaises(BuildingRegisterApiError):
            parse_building_register_xml(XML_CMM_HEADER_ERROR)


class TestFetchBuildingRegister(unittest.TestCase):

    @patch("building_register_adapter.requests.get")
    def test_ok_status(self, mock_get):
        mock_get.return_value = Mock(text=XML_NORMAL)

        result = fetch_building_register("11680", "10500", "0", "159", "0000")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["data"]), 1)

    @patch("building_register_adapter.requests.get")
    def test_not_found(self, mock_get):
        mock_get.return_value = Mock(text=XML_NO_RESULTS)

        result = fetch_building_register("11680", "10500", "0", "999", "0000")

        self.assertEqual(result["status"], "not_found")

    @patch("building_register_adapter.requests.get")
    def test_invalid_key_maps_to_invalid_request(self, mock_get):
        mock_get.return_value = Mock(text=XML_CMM_HEADER_ERROR, status_code=403)

        result = fetch_building_register("11680", "10500", "0", "159", "0000")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "invalid_request")


if __name__ == "__main__":
    unittest.main(verbosity=2)
