"""
파이프라인 통합 데모
---------------------
주소 입력 → 정규화 → 실거래가 조회 → 시세 추정 까지
지금까지 만든 3개 모듈을 실제로 이어붙여서 실행해본다.
카카오/국토부 API는 네트워크 없이 Mocking으로 대체한다.
"""

from datetime import date
from unittest.mock import patch, Mock

from address_resolver import resolve_address
from real_transaction_price_adapter import fetch_apt_trades
from market_price_estimator import estimate_market_price


FAKE_KAKAO_RESPONSE = {
    "documents": [
        {
            "address_name": "서울 강남구 삼성동 159",
            "address": {
                "address_name": "서울 강남구 삼성동 159",
                "b_code": "1168010500",
                "mountain_yn": "N",
                "main_address_no": "159",
                "sub_address_no": "",
                "x": "127.062554",
                "y": "37.508845",
            },
            "road_address": {"address_name": "서울 강남구 테헤란로 427"},
            "x": "127.062554",
            "y": "37.508845",
        }
    ]
}

FAKE_MOLIT_XML = """<response>
  <header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header>
  <body>
    <items>
      <item>
        <거래금액>  85,000</거래금액>
        <건축년도>2005</건축년도>
        <년>2024</년><월>3</월><일>10</일>
        <법정동>삼성동</법정동><아파트>래미안</아파트>
        <전용면적>84.99</전용면적><지번>159</지번><층>10</층>
        <해제여부></해제여부><거래유형>중개거래</거래유형>
      </item>
      <item>
        <거래금액>92,500</거래금액>
        <건축년도>2005</건축년도>
        <년>2024</년><월>4</월><일>2</일>
        <법정동>삼성동</법정동><아파트>래미안</아파트>
        <전용면적>84.99</전용면적><지번>159</지번><층>5</층>
        <해제여부></해제여부><거래유형>직거래</거래유형>
      </item>
    </items>
    <numOfRows>10</numOfRows><pageNo>1</pageNo><totalCount>2</totalCount>
  </body>
</response>"""


def run_pipeline(user_input_address: str, target_area: float):
    print(f"[입력] 유저 주소: {user_input_address}, 대상 전용면적: {target_area}㎡\n")

    # ---- 1단계: AddressResolver ----
    print("=== 1단계: 주소 정규화 (AddressResolver) ===")
    with patch("address_resolver.requests.get") as mock_get:
        mock_get.return_value = Mock()
        mock_get.return_value.raise_for_status.return_value = None
        mock_get.return_value.json.return_value = FAKE_KAKAO_RESPONSE
        normalized = resolve_address(user_input_address)

    for k, v in normalized.items():
        print(f"  {k}: {v}")

    # ---- 2단계: RealTransactionPriceAdapter ----
    print("\n=== 2단계: 실거래가 조회 (RealTransactionPriceAdapter) ===")
    lawd_cd_5 = normalized["legalDongCode"][:5]
    with patch("real_transaction_price_adapter.requests.get") as mock_get:
        mock_get.return_value = Mock(text=FAKE_MOLIT_XML)
        mock_get.return_value.raise_for_status.return_value = None
        trade_result = fetch_apt_trades(lawd_cd_5, "202403")

    print(f"  status: {trade_result['status']}")
    if trade_result["status"] == "ok":
        for t in trade_result["data"]:
            print(f"    - {t['dealYear']}.{t['dealMonth']} / {t['dealAmount']}만원 / {t['exclusiveArea']}㎡")

    # ---- 3단계: MarketPriceEstimator ----
    print("\n=== 3단계: 시세 추정 (MarketPriceEstimator) ===")
    if trade_result["status"] != "ok":
        print("  실거래 데이터가 없어 시세 추정 불가")
        return

    estimate = estimate_market_price(
        trade_result["data"], target_area=target_area, as_of=date(2024, 6, 15)
    )
    for k, v in estimate.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    run_pipeline("서울 강남구 테헤란로 427", target_area=84.99)
