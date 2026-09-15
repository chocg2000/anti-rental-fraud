"""
PublicPriceAdapter — 브이월드(VWorld) 공동주택가격 속성조회
--------------------------------------------------------------------------
market_price_estimator.estimate_market_price()의 public_price 인자로 넘길 값을
브이월드 API에서 가져온다. 실거래가/건축물대장 어댑터가 이미 쓰고 있는 것과 같은
반환 계약(status 기반)을 그대로 따른다 — property_aggregator.py가 이 함수 하나만
호출하면 되도록.

2026-09-15 확인 완료 (지인이 vworld 공식 API 레퍼런스 페이지의 "API결과 미리보기"
버튼으로 실제 데이터를 조회해서 응답 원본을 보내줌 — 이 머신은 vworld API 접속이
계속 불안정해서(연결 끊김/502) 직접 호출은 못 해봤지만, 실제 응답을 확보했으므로
파싱 로직은 검증된 것으로 본다):

  엔드포인트: GET https://api.vworld.kr/ned/data/getApartHousingPriceAttr
  요청 파라미터: pnu(필수, 고유번호), stdrYear/dongNm/hoNm/numOfRows/pageNo(선택),
                key(필수), domain(선택), format(선택, xml|json)

  **응답이 XML이다** — 처음엔 JSON일 거라 가정하고 GeoJSON 스타일로 짰었는데 완전히
  틀렸다. 실제 성공 응답은 이 프로젝트의 다른 국토부 API 어댑터들(real_transaction_
  price_adapter.py, building_register_adapter.py)과 같은 평범한 XML이다:

    <response>
      <numOfRows>10</numOfRows>
      <pageNo>1</pageNo>
      <totalCount>1</totalCount>
      <fields>
        <field>
          <pnu>1144012700116340000</pnu>
          <idCode>1144012700</idCode>
          <idCodeNm>서울특별시 마포구 상암동</idCodeNm>
          <aphusNm>상암월드컵1단지</aphusNm>
          <dongNm>101</dongNm>
          <floorNm>2</floorNm>
          <hoNm>201</hoNm>
          <prvuseAr>39.66</prvuseAr>
          <pblntfPc>60000000</pblntfPc>  <!-- 공시가격, 원 단위 -->
          <lastUpdtDt>2023-08-24</lastUpdtDt>
        </field>
        <!-- pnu만 주고 dongNm/hoNm을 생략하면 <field>가 여러 개 올 수 있음 -->
      </fields>
    </response>

  성공 응답에는 status/error 같은 봉투가 따로 없다 — `<fields><field>...`가 있으면
  성공, 아예 없으면 조회 결과 없음으로 본다. 에러 응답은 2026-09-14에 확인한 JSON
  기반 봉투(`{"response": {"status": "ERROR", "error": {...}}}`)였는데, 그건 다른
  엔드포인트(req/data GetFeature)를 JSON으로 호출해서 받은 것이라 이 XML 응답에도
  동일하게 적용되는지는 100% 확정은 아니다 — 다만 vworld 문서가 API 전체에 공통
  에러 코드 체계(PARAM_REQUIRED, INVALID_KEY 등)를 쓴다고 명시하고 있어, format=xml로
  요청하면 같은 필드명을 XML 태그로 감싼 형태로 올 것이라고 보고 아래처럼 처리한다.
  (실제 에러 케이스를 XML로 받아본 적은 없음 — 받으면 이 부분만 다시 확인할 것.)
"""

import os
import statistics
import xml.etree.ElementTree as ET

import requests

VWORLD_API_KEY = os.environ.get("VWORLD_API_KEY")
VWORLD_DOMAIN = os.environ.get("VWORLD_DOMAIN", "localhost")
VWORLD_DATA_URL = "https://api.vworld.kr/ned/data/getApartHousingPriceAttr"


class PublicPriceApiError(Exception):
    """API 자체가 에러를 반환했거나 응답 구조가 예상과 달라 파싱이 불가능할 때"""
    pass


def _parse_response(xml_text: str) -> int | None:
    """
    성공 시: 같은 pnu에 여러 동/호가 함께 돌아올 수 있어서(dongNm/hoNm 생략 시)
    pblntfPc(공시가격, 원 단위)들의 중위값을 만원 단위로 변환해 반환한다 — 이 프로젝트가
    실거래가에서도 평균 대신 중위값을 쓰는 것과 같은 이유(이상치에 덜 흔들리도록).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise PublicPriceApiError(f"XML 파싱 실패 (응답이 XML이 아니거나 손상됨): {e}")

    status_el = root.find("status")
    if status_el is not None and (status_el.text or "").upper() == "ERROR":
        error_el = root.find("error")
        code = error_el.findtext("code") if error_el is not None else None
        text = error_el.findtext("text") if error_el is not None else None
        raise PublicPriceApiError(f"vworld API 에러 (code={code}): {text}")

    fields_el = root.find("fields")
    if fields_el is None:
        # 2026-09-15 배포 서버(국내 리전)에서 실제로 확인: totalCount=0(조회 결과 없음)일
        # 때 vworld는 <fields></fields>를 빈 채로 보내는 게 아니라 태그 자체를 아예 뺀다
        # (다세대주택처럼 이 API(아파트 전용) 대상이 아닌 PNU로 조회하면 이 케이스가 뜬다).
        # totalCount가 "0"으로 명시돼 있으면 정상적인 "결과 없음"이지, 파싱 실패가 아니다 —
        # totalCount 자체가 없거나 0이 아니면 진짜 예상 밖 구조이므로 그대로 에러 처리한다.
        total_count_el = root.find("totalCount")
        if total_count_el is not None and (total_count_el.text or "").strip() == "0":
            return None
        raise PublicPriceApiError(f"예상한 응답 구조가 아닙니다 — 원본을 직접 확인하세요: {xml_text[:1000]}")

    field_els = fields_el.findall("field")
    if not field_els:
        return None

    prices_won = []
    for field_el in field_els:
        raw = field_el.findtext("pblntfPc")
        if raw and raw.strip():
            prices_won.append(int(raw.strip()))

    if not prices_won:
        raise PublicPriceApiError(f"pblntfPc(공시가격) 필드를 찾지 못했습니다 — 원본: {xml_text[:1000]}")

    median_won = statistics.median(prices_won)
    return round(median_won / 10_000)  # 원 -> 만원 (market_price_estimator 규약)


def fetch_public_price(pnu: str) -> dict:
    """
    PNU(19자리)로 공동주택 공시가격을 조회한다.

    반환값은 이 프로젝트의 다른 어댑터들과 동일한 계약을 따른다:
      {"status": "ok", "data": {"publicPrice": int}}   # 만원 단위
      {"status": "not_found"}
      {"status": "error", "reason": "invalid_request" | "api_down"}

    키가 아직 설정 안 됐으면 네트워크 호출 자체를 하지 않고 바로 invalid_request를
    반환한다 — 잘못된 요청을 vworld에 계속 날리지 않기 위함.
    """
    if not VWORLD_API_KEY:
        return {"status": "error", "reason": "invalid_request"}

    params = {
        "pnu": pnu,
        "key": VWORLD_API_KEY,
        "domain": VWORLD_DOMAIN,
        "format": "xml",
        "numOfRows": 100,
        "pageNo": 1,
    }

    try:
        res = requests.get(VWORLD_DATA_URL, params=params, timeout=5)
        res.raise_for_status()
    except requests.exceptions.Timeout:
        return {"status": "error", "reason": "api_down"}
    except requests.exceptions.RequestException:
        return {"status": "error", "reason": "api_down"}

    try:
        price = _parse_response(res.text)
    except PublicPriceApiError:
        return {"status": "error", "reason": "invalid_request"}

    if price is None:
        return {"status": "not_found"}

    return {"status": "ok", "data": {"publicPrice": price}}
