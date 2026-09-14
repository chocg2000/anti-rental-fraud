"""
디버그용: 브이월드(VWorld) API를 어댑터 없이 직접 호출해서
진짜 응답 구조(성공/에러 형식, 필드명)를 그대로 확인한다.

★ vworld 키를 받으면 이 스크립트부터 돌려볼 것 — public_price_adapter.py의
  _parse_response()가 추측으로 짜여 있어서, 실제 응답을 보기 전까지는 신뢰할 수 없다.

실행 전 준비:
  1. .env에 VWORLD_API_KEY, (필요시) VWORLD_DOMAIN 설정
  2. 아래 TEST_PNU를 실제 확인해보고 싶은 매물의 PNU로 바꾼다
     (address_resolver.resolve_address() 결과의 "pnu" 필드에서 얻을 수 있음)
  3. python debug_vworld_call.py

이 스크립트가 출력하는 원본 응답을 보고:
  - 최상위 구조가 뭔지 (response/result/... 경로가 실제로 맞는지)
  - 가격 필드의 실제 이름이 뭔지
  를 확인한 뒤 public_price_adapter.py의 _parse_response()를 실제 구조에 맞게 고칠 것.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

VWORLD_API_KEY = os.environ.get("VWORLD_API_KEY", "")
VWORLD_DOMAIN = os.environ.get("VWORLD_DOMAIN", "localhost")

# 서울 강남구 삼성동 159 (이 프로젝트에서 계속 써온 테스트 주소) — 실제 매물 PNU로 바꿔도 됨
TEST_PNU = "1168010500001590000"


def main():
    if not VWORLD_API_KEY:
        print("[실패] VWORLD_API_KEY 환경변수가 비어있습니다. .env에 먼저 설정해주세요.")
        return

    print(f"[사용 도메인] {VWORLD_DOMAIN} (키 발급 시 등록한 도메인과 다르면 거부당할 수 있음)\n")

    # 데이터셋 이름(레이어 ID)을 아직 모르므로, 우선 vworld가 제공하는 데이터 목록 조회부터
    # 시도해본다 — 이게 되면 최소한 키/도메인은 유효하다는 뜻이고, 목록에서 공동주택가격
    # 관련 레이어 이름을 직접 찾을 수 있을 가능성이 있다.
    print("=" * 60)
    print("1단계: 데이터 API 기본 호출 (키/도메인 유효성 확인)")
    print("=" * 60)
    params = {
        "service": "data",
        "request": "GetFeature",
        "key": VWORLD_API_KEY,
        "domain": VWORLD_DOMAIN,
        "format": "json",
    }
    try:
        res = requests.get("https://api.vworld.kr/req/data", params=params, timeout=10)
        print(f"status_code: {res.status_code}")
        print(f"응답:\n{res.text[:2000]}")
    except Exception as e:
        print(f"[예외 발생] {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    print(f"2단계: PNU({TEST_PNU})로 공동주택가격 조회 시도 (레이어 ID는 추측값)")
    print("=" * 60)
    from public_price_adapter import DATA_LAYER_ID

    print(f"현재 설정된 DATA_LAYER_ID: {DATA_LAYER_ID}")
    if DATA_LAYER_ID == "TODO_CONFIRM_LAYER_ID":
        print("[안내] 아직 레이어 ID가 확정 안 돼서 이 단계는 건너뜁니다.")
        print("       1단계 응답이나 vworld 데이터 카탈로그에서 정확한 이름을 찾은 뒤")
        print("       .env의 VWORLD_HOUSING_PRICE_LAYER_ID에 넣고 다시 실행하세요.")
        return

    params = {
        "service": "data",
        "request": "GetFeature",
        "data": DATA_LAYER_ID,
        "key": VWORLD_API_KEY,
        "domain": VWORLD_DOMAIN,
        "format": "json",
        "attrFilter": f"pnu:=:{TEST_PNU}",
    }
    try:
        res = requests.get("https://api.vworld.kr/req/data", params=params, timeout=10)
        print(f"status_code: {res.status_code}")
        print(f"응답:\n{res.text[:2000]}")
    except Exception as e:
        print(f"[예외 발생] {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
