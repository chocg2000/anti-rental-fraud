"""
RealTransactionPriceAdapter 단위 테스트 (Mocking 기반)
--------------------------------------------------------
국토부 API 키 없이, 실제 API가 반환할 법한 XML을 fixture로 만들어
파싱 로직 + 에러 분기를 검증한다.

실행: python -m unittest test_real_transaction_price_adapter.py -v
"""

import unittest
from unittest.mock import patch, Mock

from real_transaction_price_adapter import (
    parse_apt_trade_xml,
    parse_villa_trade_xml,
    parse_officetel_trade_xml,
    fetch_apt_trades,
    fetch_villa_trades,
    fetch_officetel_trades,
    TransactionApiError,
)


# ---- 국토부 API 응답을 흉내낸 fixture들 ----
# 2026-09 실제 승인 키로 확인한 진짜 응답 형식(영문 태그, aptNm/dealAmount/excluUseAr 등)을 기준으로 작성.
# 값에 공백이 섞여있고 거래금액에 콤마가 들어있는 경우가 흔하다.

XML_NORMAL_MULTIPLE_ITEMS = """<response>
  <header>
    <resultCode>000</resultCode>
    <resultMsg>OK</resultMsg>
  </header>
  <body>
    <items>
      <item>
        <dealAmount>  85,000</dealAmount>
        <buildYear>2005</buildYear>
        <dealYear>2024</dealYear>
        <dealMonth>3</dealMonth>
        <dealDay>15</dealDay>
        <umdNm>  삼성동</umdNm>
        <aptNm>래미안</aptNm>
        <excluUseAr>84.99</excluUseAr>
        <jibun>159</jibun>
        <floor>10</floor>
        <cdealType></cdealType>
        <dealingGbn>중개거래</dealingGbn>
      </item>
      <item>
        <dealAmount>92,500</dealAmount>
        <buildYear>2005</buildYear>
        <dealYear>2024</dealYear>
        <dealMonth>4</dealMonth>
        <dealDay>2</dealDay>
        <umdNm>삼성동</umdNm>
        <aptNm>래미안</aptNm>
        <excluUseAr>84.99</excluUseAr>
        <jibun>159</jibun>
        <floor>5</floor>
        <cdealType></cdealType>
        <dealingGbn>직거래</dealingGbn>
      </item>
    </items>
    <numOfRows>10</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>2</totalCount>
  </body>
</response>"""

XML_WITH_CANCELLED_TRADE = """<response>
  <header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>
  <body>
    <items>
      <item>
        <dealAmount>150,000</dealAmount>
        <buildYear>2020</buildYear>
        <dealYear>2024</dealYear>
        <dealMonth>1</dealMonth>
        <dealDay>10</dealDay>
        <umdNm>역삼동</umdNm>
        <aptNm>테스트아파트</aptNm>
        <excluUseAr>59.5</excluUseAr>
        <jibun>700</jibun>
        <floor>3</floor>
        <cdealType>해제</cdealType>
        <cdealDay>20240201</cdealDay>
        <dealingGbn>중개거래</dealingGbn>
      </item>
      <item>
        <dealAmount>80,000</dealAmount>
        <buildYear>2020</buildYear>
        <dealYear>2024</dealYear>
        <dealMonth>1</dealMonth>
        <dealDay>20</dealDay>
        <umdNm>역삼동</umdNm>
        <aptNm>테스트아파트</aptNm>
        <excluUseAr>59.5</excluUseAr>
        <jibun>700</jibun>
        <floor>7</floor>
        <cdealType></cdealType>
        <dealingGbn>중개거래</dealingGbn>
      </item>
    </items>
    <numOfRows>10</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>2</totalCount>
  </body>
</response>"""

XML_SINGLE_ITEM_NOT_A_LIST = """<response>
  <header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>
  <body>
    <items>
      <item>
        <dealAmount>45,000</dealAmount>
        <buildYear>1998</buildYear>
        <dealYear>2024</dealYear>
        <dealMonth>6</dealMonth>
        <dealDay>1</dealDay>
        <umdNm>중화동</umdNm>
        <aptNm>단일단지</aptNm>
        <excluUseAr>39.6</excluUseAr>
        <jibun>10</jibun>
        <floor>2</floor>
        <cdealType></cdealType>
        <dealingGbn>중개거래</dealingGbn>
      </item>
    </items>
    <numOfRows>10</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>1</totalCount>
  </body>
</response>"""

XML_NO_TRANSACTIONS = """<response>
  <header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>
  <body>
    <items></items>
    <numOfRows>10</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>0</totalCount>
  </body>
</response>"""

XML_INVALID_SERVICE_KEY = """<response>
  <cmmMsgHeader>
    <errMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</errMsg>
  </cmmMsgHeader>
</response>"""

XML_AUTH_ERROR_STANDARD_FORMAT = """<response>
  <header>
    <resultCode>30</resultCode>
    <resultMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR: 등록되지 않은 서비스키 입니다.</resultMsg>
  </header>
  <body></body>
</response>"""

# 2024-XX 실제 국토부 API 테스트 중 확인된 실제 응답 형식 (403 + cmmMsgHeader).
# 위 XML_AUTH_ERROR_STANDARD_FORMAT과 태그 구조가 다르므로 별도 fixture로 고정해둔다.
XML_REAL_WORLD_403_CMM_HEADER = """<OpenAPI_ServiceResponse>
  <cmmMsgHeader>
    <errMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</errMsg>
    <returnAuthMsg>등록되지 않은 서비스키</returnAuthMsg>
    <returnReasonCode>30</returnReasonCode>
  </cmmMsgHeader>
</OpenAPI_ServiceResponse>"""

NOT_EVEN_XML = "<html><body>500 Internal Server Error</body></html"  # 일부러 태그 깨뜨림

# 2026-09-12 실제 승인 키로 LAWD_CD=11680, DEAL_YMD=202405 호출해 받은 진짜 응답 중 1건.
# 이게 바로 "한글 태그로 짰다가 전부 not_found로 떴던" 버그를 잡아낸 실제 데이터다.
XML_REAL_CAPTURED_APGUJEONG = """<response>
  <header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>
  <body>
    <items>
      <item>
        <aptNm>신현대11차</aptNm>
        <aptSeq>11680-425</aptSeq>
        <buildYear>1983</buildYear>
        <buyerGbn>개인</buyerGbn>
        <cdealDay></cdealDay>
        <cdealType></cdealType>
        <dealAmount> 690,000</dealAmount>
        <dealDay>17</dealDay>
        <dealMonth>5</dealMonth>
        <dealYear>2024</dealYear>
        <dealingGbn>중개거래</dealingGbn>
        <estateAgentSggNm>서울 강남구</estateAgentSggNm>
        <excluUseAr>183.41</excluUseAr>
        <floor>3</floor>
        <jibun>431</jibun>
        <landLeaseholdGbn>N</landLeaseholdGbn>
        <roadNm>압구정로</roadNm>
        <sggCd>11680</sggCd>
        <slerGbn>법인</slerGbn>
        <umdNm>압구정동</umdNm>
      </item>
    </items>
    <numOfRows>10</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>1</totalCount>
  </body>
</response>"""


class TestParseAptTradeXml(unittest.TestCase):
    """XML 파싱 로직만 순수하게 테스트 (네트워크 전혀 무관)"""

    def test_parses_multiple_items_and_strips_whitespace_comma(self):
        trades = parse_apt_trade_xml(XML_NORMAL_MULTIPLE_ITEMS)

        self.assertEqual(len(trades), 2)
        self.assertEqual(trades[0]["dealAmount"], 85000)  # 콤마+공백 제거 확인
        self.assertEqual(trades[0]["dong"], "삼성동")       # 앞 공백 제거 확인
        self.assertEqual(trades[1]["dealAmount"], 92500)

    def test_excludes_cancelled_trade(self):
        trades = parse_apt_trade_xml(XML_WITH_CANCELLED_TRADE)

        # 2건 중 해제(취소)된 1건은 제외되고 1건만 남아야 한다
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["dealAmount"], 80000)

    def test_parses_real_captured_response_correctly(self):
        # 실제 API가 영문 태그(aptNm, dealAmount, excluUseAr...)로 응답한다는 걸
        # 처음에 놓쳐서 전부 not_found로 떴던 버그의 회귀 테스트.
        trades = parse_apt_trade_xml(XML_REAL_CAPTURED_APGUJEONG)

        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade["dealAmount"], 690000)   # 콤마+공백 제거 확인
        self.assertEqual(trade["aptName"], "신현대11차")
        self.assertEqual(trade["dong"], "압구정동")
        self.assertEqual(trade["exclusiveArea"], 183.41)
        self.assertEqual(trade["dealYear"], "2024")
        self.assertEqual(trade["dealMonth"], "5")

    def test_single_item_not_wrapped_in_list_still_parsed(self):
        # ElementTree의 findall은 단일/복수 상관없이 항상 리스트를 반환하므로
        # 실제로는 이 케이스가 문제되지 않는다 — 그걸 확인하는 회귀 테스트.
        trades = parse_apt_trade_xml(XML_SINGLE_ITEM_NOT_A_LIST)
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["aptName"], "단일단지")

    def test_no_transactions_returns_empty_list(self):
        trades = parse_apt_trade_xml(XML_NO_TRANSACTIONS)
        self.assertEqual(trades, [])

    def test_auth_error_raises(self):
        with self.assertRaises(TransactionApiError):
            parse_apt_trade_xml(XML_AUTH_ERROR_STANDARD_FORMAT)

    def test_real_world_cmm_header_error_raises_with_useful_message(self):
        # David님이 실제로 받은 403 응답 형식 — errMsg에 SERVICE_KEY가 포함돼야
        # fetch_apt_trades가 이걸 invalid_request로 정확히 분류할 수 있다.
        with self.assertRaises(TransactionApiError) as ctx:
            parse_apt_trade_xml(XML_REAL_WORLD_403_CMM_HEADER)
        self.assertIn("SERVICE_KEY", str(ctx.exception).upper())

    def test_broken_xml_raises(self):
        with self.assertRaises(TransactionApiError):
            parse_apt_trade_xml(NOT_EVEN_XML)


XML_VILLA_WITH_MHOUSE_NAME = """<response>
  <header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>
  <body>
    <items>
      <item>
        <dealAmount>65,000</dealAmount>
        <buildYear>2019</buildYear>
        <dealYear>2025</dealYear>
        <dealMonth>3</dealMonth>
        <dealDay>26</dealDay>
        <umdNm>야탑동</umdNm>
        <mhouseNm>장미마을</mhouseNm>
        <excluUseAr>54.0</excluUseAr>
        <jibun>335</jibun>
        <floor>2</floor>
        <cdealType></cdealType>
        <dealingGbn>중개거래</dealingGbn>
      </item>
    </items>
    <numOfRows>10</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>1</totalCount>
  </body>
</response>"""

XML_OFFICETEL_WITH_OFFI_NAME = """<response>
  <header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>
  <body>
    <items>
      <item>
        <dealAmount>32,000</dealAmount>
        <buildYear>2015</buildYear>
        <dealYear>2025</dealYear>
        <dealMonth>6</dealMonth>
        <dealDay>1</dealDay>
        <umdNm>역삼동</umdNm>
        <offiNm>테스트오피스텔</offiNm>
        <excluUseAr>21.5</excluUseAr>
        <jibun>50</jibun>
        <floor>8</floor>
        <cdealType></cdealType>
        <dealingGbn>중개거래</dealingGbn>
      </item>
    </items>
    <numOfRows>10</numOfRows>
    <pageNo>1</pageNo>
    <totalCount>1</totalCount>
  </body>
</response>"""


class TestParseVillaAndOfficetelTradeXml(unittest.TestCase):
    """
    ⚠️ 아래 fixture의 mhouseNm/offiNm 태그명은 실제 응답으로 검증된 게 아니라
    real_transaction_price_adapter.py 모듈 docstring에 적어둔 추정치다. 여기서는
    "이름 태그가 파라미터화된 대로 정확히 반영되는지"라는 파싱 로직 자체만 검증하고,
    실제 국토부 응답과 태그명이 맞는지는 별개로 실키 검증이 필요하다.
    """

    def test_villa_xml_parsed_with_mhouse_name_tag(self):
        trades = parse_villa_trade_xml(XML_VILLA_WITH_MHOUSE_NAME)

        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade["dealAmount"], 65000)
        self.assertEqual(trade["aptName"], "장미마을")
        self.assertEqual(trade["dong"], "야탑동")
        self.assertEqual(trade["exclusiveArea"], 54.0)

    def test_officetel_xml_parsed_with_offi_name_tag(self):
        trades = parse_officetel_trade_xml(XML_OFFICETEL_WITH_OFFI_NAME)

        self.assertEqual(len(trades), 1)
        trade = trades[0]
        self.assertEqual(trade["dealAmount"], 32000)
        self.assertEqual(trade["aptName"], "테스트오피스텔")
        self.assertEqual(trade["exclusiveArea"], 21.5)

    def test_villa_xml_still_excludes_cancelled_trade(self):
        # 취소 판별(cdealType) 로직은 공유 코드이므로 아파트와 동일하게 동작해야 한다.
        trades = parse_villa_trade_xml(XML_WITH_CANCELLED_TRADE)
        self.assertEqual(len(trades), 1)

    def test_villa_xml_auth_error_raises(self):
        with self.assertRaises(TransactionApiError):
            parse_villa_trade_xml(XML_AUTH_ERROR_STANDARD_FORMAT)


class TestFetchVillaAndOfficetelTrades(unittest.TestCase):

    @patch("real_transaction_price_adapter.requests.get")
    def test_fetch_villa_trades_ok(self, mock_get):
        mock_get.return_value = Mock(text=XML_VILLA_WITH_MHOUSE_NAME)
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_villa_trades("41135", "202503")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"][0]["aptName"], "장미마을")

    @patch("real_transaction_price_adapter.requests.get")
    def test_fetch_villa_trades_calls_rh_endpoint(self, mock_get):
        mock_get.return_value = Mock(text=XML_NO_TRANSACTIONS)
        mock_get.return_value.raise_for_status.return_value = None

        fetch_villa_trades("41135", "202503")

        called_url = mock_get.call_args.args[0]
        self.assertIn("RTMSDataSvcRHTrade", called_url)

    @patch("real_transaction_price_adapter.requests.get")
    def test_fetch_officetel_trades_ok(self, mock_get):
        mock_get.return_value = Mock(text=XML_OFFICETEL_WITH_OFFI_NAME)
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_officetel_trades("11680", "202506")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"][0]["aptName"], "테스트오피스텔")

    @patch("real_transaction_price_adapter.requests.get")
    def test_fetch_officetel_trades_calls_offi_endpoint(self, mock_get):
        mock_get.return_value = Mock(text=XML_NO_TRANSACTIONS)
        mock_get.return_value.raise_for_status.return_value = None

        fetch_officetel_trades("11680", "202506")

        called_url = mock_get.call_args.args[0]
        self.assertIn("RTMSDataSvcOffiTrade", called_url)

    @patch("real_transaction_price_adapter.requests.get")
    def test_fetch_villa_trades_not_found(self, mock_get):
        mock_get.return_value = Mock(text=XML_NO_TRANSACTIONS)
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_villa_trades("41135", "202503")

        self.assertEqual(result["status"], "not_found")

    @patch("real_transaction_price_adapter.requests.get")
    def test_fetch_officetel_trades_invalid_key(self, mock_get):
        mock_get.return_value = Mock(text=XML_AUTH_ERROR_STANDARD_FORMAT)
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_officetel_trades("11680", "202506")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "invalid_request")


class TestFetchAptTrades(unittest.TestCase):
    """fetch_apt_trades()를 requests.get Mocking으로 검증 (AdapterResult 형태 확인)"""

    @patch("real_transaction_price_adapter.requests.get")
    def test_ok_status_with_confidence_high(self, mock_get):
        mock_get.return_value = Mock(text=XML_NORMAL_MULTIPLE_ITEMS)
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_apt_trades("11680", "202403")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["confidence"], "high")
        self.assertEqual(len(result["data"]), 2)

    @patch("real_transaction_price_adapter.requests.get")
    def test_not_found_when_no_transactions(self, mock_get):
        mock_get.return_value = Mock(text=XML_NO_TRANSACTIONS)
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_apt_trades("11680", "202403")

        self.assertEqual(result["status"], "not_found")

    @patch("real_transaction_price_adapter.requests.get")
    def test_invalid_service_key_maps_to_invalid_request(self, mock_get):
        mock_get.return_value = Mock(text=XML_AUTH_ERROR_STANDARD_FORMAT)
        mock_get.return_value.raise_for_status.return_value = None

        result = fetch_apt_trades("11680", "202403")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "invalid_request")

    @patch("real_transaction_price_adapter.requests.get")
    def test_http_403_with_real_world_body_still_parsed_as_invalid_request(self, mock_get):
        # 핵심 회귀 테스트: HTTP status_code가 403이어도(raise_for_status를 호출하지 않으므로)
        # 본문(cmmMsgHeader)을 읽어서 invalid_request로 정확히 분류해야 한다.
        # 이전 버그: raise_for_status()를 먼저 불러서 이 케이스가 전부 "api_down"으로 뭉개졌었음.
        fake_response = Mock(text=XML_REAL_WORLD_403_CMM_HEADER, status_code=403)
        mock_get.return_value = fake_response

        result = fetch_apt_trades("11680", "202403")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "invalid_request")

    @patch("real_transaction_price_adapter.requests.get")
    def test_network_timeout_maps_to_api_down(self, mock_get):
        import requests as real_requests
        mock_get.side_effect = real_requests.exceptions.Timeout()

        result = fetch_apt_trades("11680", "202403")

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["reason"], "api_down")


if __name__ == "__main__":
    unittest.main(verbosity=2)
