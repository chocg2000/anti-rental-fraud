"""
PublicPriceAdapter — 브이월드(VWorld) 공동주택 공시가격 조회 (미검증 스텁)
--------------------------------------------------------------------------
market_price_estimator.estimate_market_price()의 public_price 인자로 넘길 값을
브이월드 API에서 가져온다. 실거래가/건축물대장 어댑터가 이미 쓰고 있는 것과 같은
반환 계약(status 기반)을 그대로 따른다 — property_aggregator.py가 이 함수 하나만
호출하면 되도록.

⚠️ 이 파일은 실제 vworld 응답을 단 한 번도 못 본 채로 작성됐다. 이 프로젝트를 만드는
동안 사용해온 방식(vworld.kr 자체가 싱가포르 IP에서 접속 제한돼서 API 문서조차 못 봤다.
그래서 다른 세 어댑터(주소/실거래가/건축물대장)와 다르게 "로직 먼저 → 실키로 검증" 순서를
못 지켰다 — 아래 요청 URL/파라미터/파싱 로직은 VWorld 데이터 API의 일반적인 패턴에
기반한 최선의 추정치일 뿐, 실제로 맞는지 전혀 확인되지 않았다.

키를 받으면 반드시 이 순서로 진행할 것 (다른 어댑터들도 전부 이렇게 만들었고, 실제로
추측한 태그명이 틀려서 버그가 났던 전적이 있다 — real_transaction_price_adapter.py,
building_register_adapter.py 상단 주석 참고):
  1. debug_vworld_call.py로 원본 응답을 먼저 눈으로 확인한다.
  2. 실제 필드명/구조를 보고 아래 _parse_response()를 다시 쓴다.
  3. property_aggregator.py의 통합 지점(아래 "연결 지점" 주석 참고)은 이미 붙여놨으니
     이 파일의 반환 계약만 유지하면 나머지 코드는 안 건드려도 된다.

키 발급/설정 관련 메모:
  - VWorld는 API 키 발급 시 "도메인"을 등록해야 하고, 실제 요청의 도메인이 등록값과
    다르면 유효한 키로도 거부당하는 경우가 흔하다 — 로컬 개발 중이면 "localhost"로
    등록했는지 확인할 것 (.env의 VWORLD_DOMAIN으로 오버라이드 가능).
  - 정확한 데이터셋 이름(공동주택가격 레이어 ID)은 vworld 데이터 카탈로그에서 확인해야
    하는데, 지금은 사이트 자체가 접속이 안 돼서 이름을 확정 못 했다. 아래 DATA_LAYER_ID는
    플레이스홀더 — 확인되는 대로 .env의 VWORLD_HOUSING_PRICE_LAYER_ID로 채워 넣거나
    이 파일의 기본값을 직접 고칠 것.

.env에 추가해야 할 것:
  VWORLD_API_KEY=<발급받은 키>
  VWORLD_DOMAIN=<키 발급 시 등록한 도메인, 로컬이면 보통 localhost>
  VWORLD_HOUSING_PRICE_LAYER_ID=<확인 후 채울 것 — 안 채우면 TODO_CONFIRM_LAYER_ID로 남아
    바로 invalid_request로 떨어짐. 코드가 안 죽는다는 뜻이지, 동작한다는 뜻이 아니다.>
"""

import os

import requests

VWORLD_API_KEY = os.environ.get("VWORLD_API_KEY")
VWORLD_DOMAIN = os.environ.get("VWORLD_DOMAIN", "localhost")
VWORLD_DATA_URL = "https://api.vworld.kr/req/data"

# TODO: vworld 데이터 카탈로그에서 "공동주택가격" 레이어의 정확한 data 파라미터 값을 확인할 것.
DATA_LAYER_ID = os.environ.get("VWORLD_HOUSING_PRICE_LAYER_ID", "TODO_CONFIRM_LAYER_ID")


class PublicPriceApiError(Exception):
    """API 자체가 에러를 반환했거나 응답 구조가 예상과 달라 파싱이 불가능할 때"""
    pass


def _parse_response(payload: dict) -> int | None:
    """
    ⚠️ 미검증 — 반드시 실제 응답을 보고 다시 작성할 것.

    지금은 VWorld 데이터 API(WFS 기반)의 일반적인 GeoJSON 스타일 Feature 응답을
    가정한 최선의 추측이다:
        {"response": {"status": "OK", "result": {"featureCollection": {"features": [
            {"properties": {...가격 관련 필드...}}
        ]}}}}
    실제로는 필드 위치나 이름이 다를 가능성이 높다 — debug_vworld_call.py로 확인 후 수정.
    """
    try:
        status = payload["response"]["status"]
    except (KeyError, TypeError):
        raise PublicPriceApiError(f"예상한 응답 구조가 아닙니다 — 원본을 직접 확인하세요: {payload}")

    if status != "OK":
        raise PublicPriceApiError(f"vworld API가 OK가 아닌 상태를 반환함: {status}")

    try:
        features = payload["response"]["result"]["featureCollection"]["features"]
    except (KeyError, TypeError):
        raise PublicPriceApiError(f"featureCollection을 찾을 수 없습니다 — 원본: {payload}")

    if not features:
        return None

    # TODO: 실제 속성명 확인 후 수정 (지금은 "price"/"govPrice"/"jiga" 등을 추측으로 시도)
    props = features[0].get("properties", {})
    for candidate_key in ("price", "govPrice", "jiga", "houseGovPrice"):
        if candidate_key in props and props[candidate_key]:
            return int(props[candidate_key])

    raise PublicPriceApiError(f"가격 필드를 찾지 못했습니다 — properties 원본: {props}")


def fetch_public_price(pnu: str) -> dict:
    """
    PNU(19자리)로 공동주택 공시가격을 조회한다.

    반환값은 이 프로젝트의 다른 어댑터들과 동일한 계약을 따른다:
      {"status": "ok", "data": {"publicPrice": int}}   # 만원 단위로 맞출 것 (검증 필요 —
                                                          vworld가 원 단위로 줄 수도 있음)
      {"status": "not_found"}
      {"status": "error", "reason": "invalid_request" | "api_down"}

    키/레이어ID가 아직 설정 안 됐으면(플레이스홀더 상태) 네트워크 호출 자체를 하지 않고
    바로 invalid_request를 반환한다 — 잘못된 요청을 vworld에 계속 날리지 않기 위함.
    """
    if not VWORLD_API_KEY or DATA_LAYER_ID == "TODO_CONFIRM_LAYER_ID":
        return {"status": "error", "reason": "invalid_request"}

    params = {
        "service": "data",
        "request": "GetFeature",
        "data": DATA_LAYER_ID,
        "key": VWORLD_API_KEY,
        "domain": VWORLD_DOMAIN,
        "format": "json",
        "attrFilter": f"pnu:=:{pnu}",  # TODO: 실제 필터 문법/속성명 확인 필요
    }

    try:
        res = requests.get(VWORLD_DATA_URL, params=params, timeout=5)
        res.raise_for_status()
    except requests.exceptions.Timeout:
        return {"status": "error", "reason": "api_down"}
    except requests.exceptions.RequestException:
        return {"status": "error", "reason": "api_down"}

    try:
        price = _parse_response(res.json())
    except (PublicPriceApiError, ValueError):
        return {"status": "error", "reason": "invalid_request"}

    if price is None:
        return {"status": "not_found"}

    return {"status": "ok", "data": {"publicPrice": price}}
