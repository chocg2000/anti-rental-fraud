"""
디버그용: 연립다세대(RHTrade)/오피스텔(OffiTrade) 국토부 API를 어댑터 없이
직접 호출해서 진짜 응답 태그명을 눈으로 확인한다.

real_transaction_price_adapter.py의 fetch_villa_trades/fetch_officetel_trades는
mhouseNm/offiNm 등 영문 태그를 가정하고 짰다(모듈 docstring 참고 — 독립 오픈소스
구현체와 대조는 했지만 우리 키로 직접 검증한 적은 없음). 이 스크립트로 실제 응답을
받아서, item 안에 mhouseNm/offiNm/dealAmount/excluUseAr/umdNm 태그가 실제로
있는지 확인하고, 다르면 real_transaction_price_adapter.py의 name_tag를 바로잡을 것.

실행: MOLIT_SERVICE_KEY 환경변수를 설정한 뒤 `python debug_villa_officetel_call.py`
"""

import os
import requests

SERVICE_KEY = os.environ.get("MOLIT_SERVICE_KEY", "")

if not SERVICE_KEY:
    print("⚠️  MOLIT_SERVICE_KEY 환경변수가 비어있습니다. 먼저 설정해주세요.")
    exit(1)

# 연립다세대/오피스텔 둘 다 아파트와 같은 인증키로 별도 활용신청만 하면 바로 쓸 수 있다
# (공공데이터포털 마이페이지에서 두 상품 모두 활용신청 승인 상태인지 먼저 확인할 것).
ENDPOINTS = {
    "연립다세대 (RHTrade)": "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade",
    "오피스텔 (OffiTrade)": "https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade",
}

# LAWD_CD=41135(경기 성남시 분당구, 이 프로젝트가 이미 실거래 검증에 써온 야탑동 지역)
# DEAL_YMD는 최근 달로 바꿔가며 여러 번 시도해볼 것 — 거래가 없는 달이면 totalCount=0만
# 나오고 태그 확인이 안 되니, 거래량이 있을 법한 서울/경기 인구밀집 지역 + 최근 6개월
# 범위에서 몇 달치를 돌려보는 게 좋다.
params = {
    "serviceKey": SERVICE_KEY,
    "LAWD_CD": "41135",
    "DEAL_YMD": "202503",
    "numOfRows": 10,
}

for label, url in ENDPOINTS.items():
    print(f"\n{'='*60}")
    print(f"시도: {label}")
    print(f"URL: {url}")
    print('='*60)
    try:
        res = requests.get(url, params=params, timeout=10)
        print(f"status_code: {res.status_code}")
        print(f"응답 전체:\n{res.text[:3000]}")
    except Exception as e:
        print(f"[예외 발생] {type(e).__name__}: {e}")

print(f"\n{'='*60}")
print("체크리스트 (real_transaction_price_adapter.py 수정 여부 판단용):")
print("  1. <item> 안에 mhouseNm(연립다세대)/offiNm(오피스텔) 태그가 실제로 있는가?")
print("     -> 다른 이름이면 parse_villa_trade_xml/parse_officetel_trade_xml의")
print("        name_tag 인자를 그 이름으로 바꿀 것.")
print("  2. dealAmount/excluUseAr/umdNm/dealYear/dealMonth/dealDay/cdealType 태그가")
print("     아파트(AptTradeDev)와 동일한 이름으로 오는가?")
print("     -> 다르면 _parse_trade_xml()을 공유하지 말고 이 두 API 전용 파서로 분리할 것.")
print("  3. totalCount=0이면 DEAL_YMD를 다른 달로, LAWD_CD를 다른 지역으로 바꿔서 재시도.")
print('='*60)
