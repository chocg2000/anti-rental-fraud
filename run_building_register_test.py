"""
건축물대장 API 실제 호출 테스트
--------------------------------
Mocking 없이 진짜 API를 호출한다. building_register_adapter.py와 같은 폴더에 둘 것.

실행 전 준비:
1. export MOLIT_SERVICE_KEY="발급받은_디코딩_인증키"  (실거래가 때와 동일한 키)
2. python run_building_register_test.py

기본값은 서울 강남구 삼성동 159번지로 맞춰뒀습니다.
다른 주소로 테스트하려면 아래 SIGUNGU_CD 등을 바꾸면 됩니다.
- sigunguCd/bjdongCd 찾는 법: 카카오맵/네이버지도에서 주소 검색 후 법정동코드 확인,
  또는 법정동코드 앞 5자리=sigunguCd, 뒤 5자리=bjdongCd
- bun(본번)/ji(부번): 지번의 앞/뒤 숫자, 4자리로 맞춰 0으로 채움 (예: 159번지 → bun=0159, ji=0000)
"""

import os
import requests
from building_register_adapter import fetch_building_register, API_URL

SERVICE_KEY = os.environ.get("MOLIT_SERVICE_KEY", "")

# 테스트용 주소: 서울 강남구 삼성동 159 (원하는 주소로 바꿔서 테스트 가능)
SIGUNGU_CD = "11680"
BJDONG_CD = "10500"
PLAT_GB_CD = "0"   # 0=대지, 1=산
BUN = "0159"
JI = "0000"


def main():
    if not SERVICE_KEY:
        print("⚠️  MOLIT_SERVICE_KEY 환경변수가 설정되지 않았습니다.")
        return

    print(f"[요청] sigunguCd={SIGUNGU_CD}, bjdongCd={BJDONG_CD}, "
          f"platGbCd={PLAT_GB_CD}, bun={BUN}, ji={JI}\n")

    # 1) 어댑터를 통한 정식 호출
    result = fetch_building_register(SIGUNGU_CD, BJDONG_CD, PLAT_GB_CD, BUN, JI)
    print(f"[어댑터 결과] status = {result['status']}")

    if result["status"] == "ok":
        for b in result["data"]:
            print(f"\n  건물명: {b['bldName']}")
            print(f"  주용도: {b['mainPurpose']}")
            print(f"  대장구분: {b['registerKind']}")
            print(f"  사용승인일: {b['useApprovalDate']}")
            print(f"  세대수: {b['householdCount']}")
            print(f"  내진설계여부: {b['seismicDesignApplied']}")
            print(f"  위반건축물 확인여부: {b['violationStatusConfirmed']} (원본값: {b['violationStatusRaw']})")
    else:
        print(f"  상세: {result}")

    # 2) 원본 XML도 그대로 출력 — 위반건축물 관련 필드가 실제로 뭐라고 오는지
    #    눈으로 직접 찾아보기 위함 (우리가 추측한 필드명이 틀렸을 수 있음)
    print("\n" + "=" * 60)
    print("원본 XML 응답 (위반건축물 관련 필드를 직접 눈으로 찾아보세요)")
    print("=" * 60)
    params = {
        "serviceKey": SERVICE_KEY, "sigunguCd": SIGUNGU_CD, "bjdongCd": BJDONG_CD,
        "platGbCd": PLAT_GB_CD, "bun": BUN, "ji": JI, "numOfRows": 20,
    }
    try:
        res = requests.get(API_URL, params=params, timeout=10)
        print(res.text)
    except Exception as e:
        print(f"[예외] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
