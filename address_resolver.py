"""
AddressResolver 프로토타입
--------------------------------
유저가 입력한 자유 형식 주소(도로명/지번)를 받아서
- 도로명주소, 지번주소
- 법정동코드 (legalDongCode)
- PNU (고유번호, 19자리)
- 좌표(lat, lng)
로 정규화하는 모듈.

사전 준비:
1. https://developers.kakao.com 에서 애플리케이션 생성 → REST API 키 발급
2. pip install requests
3. 아래 KAKAO_REST_API_KEY 에 발급받은 키를 넣거나 환경변수 KAKAO_REST_API_KEY로 설정
"""

import os
import requests

KAKAO_REST_API_KEY = os.environ.get("KAKAO_REST_API_KEY")
KAKAO_ADDRESS_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/address.json"


class AddressResolutionError(Exception):
    """주소를 정규화할 수 없을 때 발생시키는 예외"""
    pass


def _build_pnu(b_code: str, mountain_yn: str, main_no: str, sub_no: str) -> str | None:
    """
    법정동코드 + 산여부 + 본번 + 부번 → PNU(19자리) 조합.
    본번이 비어 있으면(동/읍 단위 등 지번이 특정되지 않은 결과) PNU를 만들 수 없으므로 None 반환.
    """
    if not main_no:
        return None

    mountain_flag = "1" if mountain_yn == "Y" else "0"
    main_padded = main_no.zfill(4)
    sub_padded = (sub_no or "0").zfill(4)

    return f"{b_code}{mountain_flag}{main_padded}{sub_padded}"


def resolve_address(query: str) -> dict:
    """
    자유 형식 주소 문자열을 받아 NormalizedAddress 딕셔너리로 반환한다.

    반환 예시:
    {
        "roadAddress": "서울 강남구 테헤란로 427",
        "jibunAddress": "서울 강남구 삼성동 159",
        "legalDongCode": "1168010500",
        "pnu": "1168010500101590000",   # 본번/부번이 특정된 경우만
        "lat": 37.508845,
        "lng": 127.062554,
    }
    """
    if not query or not query.strip():
        raise AddressResolutionError("주소가 비어 있습니다.")

    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    params = {"query": query.strip()}

    try:
        res = requests.get(KAKAO_ADDRESS_SEARCH_URL, headers=headers, params=params, timeout=3)
        res.raise_for_status()
    except requests.exceptions.Timeout:
        raise AddressResolutionError("카카오 주소 API 응답 지연 (타임아웃)")
    except requests.exceptions.RequestException as e:
        raise AddressResolutionError(f"카카오 주소 API 호출 실패: {e}")

    data = res.json()
    documents = data.get("documents", [])

    if not documents:
        raise AddressResolutionError(f"주소를 찾을 수 없습니다: '{query}'")

    # TODO(2단계): 검색 결과가 여러 건이면 유저에게 선택지를 보여주는 UX가 필요.
    # 1단계 프로토타입에서는 가장 정확도 높은 첫 번째 결과만 사용한다.
    doc = documents[0]
    addr = doc.get("address")

    if addr is None:
        raise AddressResolutionError(f"지번 주소 정보를 찾을 수 없습니다: '{query}'")

    road_addr = doc.get("road_address")

    pnu = _build_pnu(
        b_code=addr["b_code"],
        mountain_yn=addr["mountain_yn"],
        main_no=addr["main_address_no"],
        sub_no=addr["sub_address_no"],
    )

    return {
        "roadAddress": road_addr["address_name"] if road_addr else None,
        "jibunAddress": addr["address_name"],
        "legalDongCode": addr["b_code"],
        "pnu": pnu,
        "lat": float(doc["y"]),
        "lng": float(doc["x"]),
    }


if __name__ == "__main__":
    # 간단한 동작 확인용. 실제 실행하려면 KAKAO_REST_API_KEY를 먼저 설정해야 합니다.
    test_queries = [
        "서울 강남구 테헤란로 427",
        "경기 성남시 분당구 정자동 178-1",
        "이런주소는없음asdf1234",
    ]

    for q in test_queries:
        print(f"\n입력: {q}")
        try:
            result = resolve_address(q)
            for k, v in result.items():
                print(f"  {k}: {v}")
        except AddressResolutionError as e:
            print(f"  [실패] {e}")
