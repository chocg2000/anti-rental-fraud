"""
디버그용: 브이월드(VWorld) 공동주택가격속성조회 API를 어댑터 없이 직접 호출해서
진짜 응답 구조(성공/에러 형식, 필드명)를 그대로 확인한다.

엔드포인트/파라미터는 vworld 공식 API 레퍼런스 페이지로 확인됨(2026-09-15):
  GET https://api.vworld.kr/ned/data/getApartHousingPriceAttr

★ vworld 키를 받으면 이 스크립트부터 돌려볼 것 — public_price_adapter.py의
  _parse_response()가 성공("OK") 응답의 봉투 구조를 여전히 추측으로 짜놨어서,
  실제 응답을 보기 전까지는 신뢰할 수 없다.

실행 전 준비:
  .env에 VWORLD_API_KEY, (필요시) VWORLD_DOMAIN 설정

이 머신이 vworld API 접속 자체가 불안정하면(연결 끊김/502) 이 스크립트가 실패할 수
있다 — 그럴 땐 아래 TEST_PNU로 만든 URL을 브라우저에서 대신 열어볼 링크로 만들어
한국 IP를 쓰는 사람에게 부탁하는 방식을 쓸 것 (vworld_test_link.txt와 같은 패턴).

이 스크립트가 출력하는 원본 응답을 보고 public_price_adapter.py의 _parse_response()를
실제 구조에 맞게 고칠 것 (에러 분기는 이미 실제 응답으로 검증돼 있어 안 건드려도 됨).
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

VWORLD_API_KEY = os.environ.get("VWORLD_API_KEY", "")
VWORLD_DOMAIN = os.environ.get("VWORLD_DOMAIN", "localhost")
VWORLD_URL = "https://api.vworld.kr/ned/data/getApartHousingPriceAttr"

# vworld 공식 API 레퍼런스 페이지의 샘플데이터 그대로 (경기도 성남시 분당구 상암동
# 언저리가 아니라 실제로는 서울 마포구 상암동 상암월드컵1단지 101동 201호로 보임)
TEST_PNU = "1144012700116340000"
TEST_DONG_NM = "101"
TEST_HO_NM = "201"


def main():
    if not VWORLD_API_KEY:
        print("[실패] VWORLD_API_KEY 환경변수가 비어있습니다. .env에 먼저 설정해주세요.")
        return

    print(f"[사용 도메인] {VWORLD_DOMAIN} (키 발급 시 등록한 도메인과 다르면 거부당할 수 있음)\n")

    print("=" * 60)
    print(f"1단계: 공식 샘플데이터로 조회 (pnu={TEST_PNU}, dongNm={TEST_DONG_NM}, hoNm={TEST_HO_NM})")
    print("=" * 60)
    params = {
        "pnu": TEST_PNU,
        "dongNm": TEST_DONG_NM,
        "hoNm": TEST_HO_NM,
        "key": VWORLD_API_KEY,
        "domain": VWORLD_DOMAIN,
        "format": "xml",
        "numOfRows": 10,
        "pageNo": 1,
    }
    try:
        res = requests.get(VWORLD_URL, params=params, timeout=10)
        print(f"status_code: {res.status_code}")
        print(f"응답:\n{res.text[:3000]}")
    except Exception as e:
        print(f"[예외 발생] {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    print(f"2단계: dongNm/hoNm 없이 pnu만으로 조회 (여러 동/호가 함께 오는지 확인)")
    print("=" * 60)
    params = {
        "pnu": TEST_PNU,
        "key": VWORLD_API_KEY,
        "domain": VWORLD_DOMAIN,
        "format": "xml",
        "numOfRows": 100,
        "pageNo": 1,
    }
    try:
        res = requests.get(VWORLD_URL, params=params, timeout=10)
        print(f"status_code: {res.status_code}")
        print(f"응답:\n{res.text[:3000]}")
    except Exception as e:
        print(f"[예외 발생] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
