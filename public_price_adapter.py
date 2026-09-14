"""
PublicPriceAdapter — 브이월드(VWorld) 공동주택 공시가격 조회 (부분 검증됨)
--------------------------------------------------------------------------
market_price_estimator.estimate_market_price()의 public_price 인자로 넘길 값을
브이월드 API에서 가져온다. 실거래가/건축물대장 어댑터가 이미 쓰고 있는 것과 같은
반환 계약(status 기반)을 그대로 따른다 — property_aggregator.py가 이 함수 하나만
호출하면 되도록.

2026-09-15 확인된 것 (이 머신은 여전히 vworld API에 접속이 불안정해서 — Singapore IP
문제로 추정, 연결이 끊기거나 502가 나는 경우가 잦음 — 지인이 브라우저로 대신 호출해서
받아온 실제 응답으로 확인함):
  - **키/도메인은 유효하다** — domain="localhost"로 등록돼있고 인증도 정상 통과함.
  - **에러 응답 구조가 확인됨**:
      {"response": {"service": {...}, "status": "ERROR",
                     "error": {"level": "1", "code": "PARAM_REQUIRED",
                               "text": "필수 파라미터인 data가 없어서 요청을 처리할수 없습니다."}}}
    (필수 파라미터 data 없이 호출해서 일부러 받은 에러 — service/status/error 봉투
    구조 자체는 확정, 아래 _parse_response()에 반영함)

아직 미확인 (진짜 다음 과제):
  - **"공동주택가격" 데이터셋의 정확한 `data=` 값(레이어 ID)을 아직 모른다.** 이걸 모르면
    성공 응답 자체를 한 번도 못 받아봤다는 뜻이라, 성공 시 필드 구조(`_parse_response()`의
    `featureCollection.features[].properties.가격필드` 부분)는 여전히 추측이다.
    vworld 로그인 후 Open API 가이드/데이터 카탈로그에서 "공동주택가격"을 검색해서
    코드를 찾아 `.env`의 `VWORLD_HOUSING_PRICE_LAYER_ID`에 넣을 것.
  - 가격 단위가 만원인지 원인지도 실제 성공 응답을 봐야 확정 가능.

키를 받으면 반드시 이 순서로 진행할 것 (다른 어댑터들도 전부 이렇게 만들었고, 실제로
추측한 태그명이 틀려서 버그가 났던 전적이 있다 — real_transaction_price_adapter.py,
building_register_adapter.py 상단 주석 참고):
  1. debug_vworld_call.py로 원본 응답을 먼저 눈으로 확인한다 (이 머신에서 접속이 안 되면
     vworld_test_link.txt 같은 방식으로 브라우저에서 대신 열어볼 링크를 만들어 확인한다).
  2. 실제 필드명/구조를 보고 아래 _parse_response()의 성공 경로를 다시 쓴다.
  3. property_aggregator.py의 통합 지점은 이미 붙여놨으니 이 파일의 반환 계약만
     유지하면 나머지 코드는 안 건드려도 된다.

.env에 필요한 것:
  VWORLD_API_KEY=<발급받은 키> (확인 완료 — 유효함)
  VWORLD_DOMAIN=<키 발급 시 등록한 도메인, 기본값 localhost — 확인 완료>
  VWORLD_HOUSING_PRICE_LAYER_ID=<아직 미확인 — 안 채우면 TODO_CONFIRM_LAYER_ID로 남아
    네트워크 호출 자체를 안 하고 invalid_request로 떨어짐. 코드가 안 죽는다는 뜻이지
    동작한다는 뜻은 아직 아니다.>
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
    status/error 봉투 구조는 2026-09-15에 실제 응답으로 확인됨(위 모듈 docstring 참고).
    ⚠️ 성공("OK") 시의 result/featureCollection 구조는 여전히 추측이다 — 아직 성공
    응답을 한 번도 못 받아봤다(레이어 ID 미확인). debug_vworld_call.py로 성공 응답을
    확인하면 아래 "OK 분기"만 실제 구조에 맞게 고치면 된다 — 에러 분기는 이미 맞다.
    """
    try:
        status = payload["response"]["status"]
    except (KeyError, TypeError):
        raise PublicPriceApiError(f"예상한 응답 구조가 아닙니다 — 원본을 직접 확인하세요: {payload}")

    if status == "ERROR":
        error = payload["response"].get("error", {})
        raise PublicPriceApiError(
            f"vworld API 에러 (code={error.get('code')}): {error.get('text')}"
        )

    if status != "OK":
        raise PublicPriceApiError(f"예상 못 한 status 값: {status} — 원본: {payload}")

    # ⚠️ 아래부터는 미검증 — 실제 성공 응답을 받으면 다시 작성할 것.
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
