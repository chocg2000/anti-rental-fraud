"""
디버그용: 연립다세대(RHTrade)/오피스텔(OffiTrade) 국토부 API를 어댑터 없이
직접 호출해서 진짜 응답 태그명을 눈으로 확인한다.

✅ 2026-09-15 실제 승인 키로 이미 한 번 돌려서 검증 완료 — real_transaction_price_adapter.py
의 mhouseNm/offiNm/dealAmount/excluUseAr/umdNm 등 태그 가정이 전부 실제 응답과 일치함을
확인했다(결과는 test_real_transaction_price_adapter.py의 XML_REAL_CAPTURED_VILLA/
OFFICETEL 회귀 테스트로 고정해뒀음). 이 스크립트는 나중에 국토부가 응답 스키마를 바꾸거나
다른 지역/API 상품을 추가로 확인해야 할 때 재사용하는 용도로 남겨둔다.

실행: .env에 MOLIT_SERVICE_KEY를 설정한 뒤 `python debug_villa_officetel_call.py`
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv()

SERVICE_KEY = os.environ.get("MOLIT_SERVICE_KEY", "")

if not SERVICE_KEY:
    print("[실패] MOLIT_SERVICE_KEY 환경변수가 비어있습니다. .env에 먼저 설정해주세요.")
    exit(1)

# 연립다세대/오피스텔 둘 다 아파트와 같은 인증키로 별도 활용신청만 하면 바로 쓸 수 있다
# (공공데이터포털 마이페이지에서 두 상품 모두 활용신청 승인 상태인지 먼저 확인할 것).
ENDPOINTS = {
    "연립다세대 (RHTrade)": "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade",
    "오피스텔 (OffiTrade)": "https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade",
}

# 여러 지역 x 여러 달을 시도해서 totalCount=0(거래 없음)으로 허탕 칠 확률을 낮춘다.
# 11680=서울 강남구(오피스텔 밀집), 41135=경기 성남시 분당구(이 프로젝트가 이미
# 실거래 검증에 써온 지역, 연립다세대도 있음).
REGIONS = ["11680", "41135"]
MONTHS = ["202508", "202507", "202506", "202503"]

for label, url in ENDPOINTS.items():
    print(f"\n{'='*60}")
    print(f"시도: {label}")
    print(f"URL: {url}")
    print('='*60)
    found_data = False
    for lawd_cd in REGIONS:
        for deal_ymd in MONTHS:
            params = {
                "serviceKey": SERVICE_KEY,
                "LAWD_CD": lawd_cd,
                "DEAL_YMD": deal_ymd,
                "numOfRows": 10,
            }
            try:
                res = requests.get(url, params=params, timeout=10)
            except Exception as e:
                print(f"[예외 발생] LAWD_CD={lawd_cd} DEAL_YMD={deal_ymd}: {type(e).__name__}: {e}")
                continue

            has_item = "<item>" in res.text
            print(f"LAWD_CD={lawd_cd} DEAL_YMD={deal_ymd} status_code={res.status_code} "
                  f"item_found={has_item}")

            if has_item:
                print(f"\n응답 전체:\n{res.text[:3000]}\n")
                found_data = True
                break
            elif res.status_code != 200 or "resultCode" not in res.text:
                # 인증/파라미터 에러는 즉시 원문을 보여준다 (반복해도 똑같이 실패할 것이므로)
                print(f"응답 전체:\n{res.text[:1500]}\n")
                found_data = True
                break
        if found_data:
            break
    if not found_data:
        print("모든 지역/기간 조합에서 거래 데이터를 못 찾았습니다 — REGIONS/MONTHS를 넓혀서 재시도할 것.")

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
