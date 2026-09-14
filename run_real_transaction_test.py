"""
국토부 실거래가 API 실제 호출 테스트
--------------------------------------
Mocking 없이 진짜 API를 호출한다. 이전에 만든 real_transaction_price_adapter.py와
같은 폴더에 두고 실행할 것.

실행 전 준비:
1. 터미널에서 환경변수 설정 (Decoding 버전 키를 넣을 것!)
   export MOLIT_SERVICE_KEY="발급받은_디코딩_인증키"
2. pip install requests
3. python run_real_transaction_test.py
"""

import os
from real_transaction_price_adapter import fetch_apt_trades

# 테스트용 지역/기간 — 필요하면 바꿔서 테스트해보세요.
# LAWD_CD 예시: 서울 강남구=11680, 서초구=11650, 송파구=11710, 마포구=11440
TEST_LAWD_CD = "11680"
TEST_DEAL_YMD = "202405"  # 실거래는 신고 후 반영되기까지 시차가 있으므로 최근 1~2개월 전을 추천


def main():
    if os.environ.get("MOLIT_SERVICE_KEY", "") in ("", "여기에_공공데이터포털_인증키를_입력"):
        print("⚠️  MOLIT_SERVICE_KEY 환경변수가 설정되지 않았습니다.")
        print('   터미널에서 먼저 실행하세요: export MOLIT_SERVICE_KEY="발급받은_디코딩_인증키"')
        return

    print(f"[요청] LAWD_CD={TEST_LAWD_CD}, DEAL_YMD={TEST_DEAL_YMD}")
    result = fetch_apt_trades(TEST_LAWD_CD, TEST_DEAL_YMD)

    print(f"\n[결과] status = {result['status']}")

    if result["status"] == "ok":
        print(f"거래 {len(result['data'])}건 조회됨 (confidence: {result['confidence']})\n")
        for t in result["data"][:5]:  # 앞 5건만 미리보기
            print(f"  {t['dealYear']}.{t['dealMonth']}.{t['dealDay']} "
                  f"/ {t['aptName']} {t['exclusiveArea']}㎡ / {t['dealAmount']}만원 / {t['floor']}층")
        if len(result["data"]) > 5:
            print(f"  ... 외 {len(result['data']) - 5}건")

    elif result["status"] == "not_found":
        print("해당 지역/기간에 거래 데이터가 없습니다. LAWD_CD나 DEAL_YMD를 바꿔서 다시 시도해보세요.")

    elif result["status"] == "error":
        print(f"에러 발생 — reason: {result['reason']}")
        print("  - invalid_request: 대부분 인증키 문제 (Decoding 버전인지, 활용신청 승인이 났는지 확인)")
        print("  - api_down: 네트워크/타임아웃 또는 국토부 서버 문제")


if __name__ == "__main__":
    main()
