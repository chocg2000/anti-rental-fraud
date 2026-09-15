"""
RealTransactionPriceAdapter 프로토타입
--------------------------------------
국토교통부 "실거래가 상세 자료" API 3종(아파트/연립다세대/오피스텔)을 호출해서
실거래 리스트를 파싱한다. 시세 추정(중위값 계산 등)은 Aggregator의 몫이고,
이 모듈은 "API 응답 → 정제된 거래 리스트"까지만 책임진다.

실제 서비스 URL (공공데이터포털 승인 후 사용, MOLIT_SERVICE_KEY 하나로 3종 모두 사용 가능):
  아파트:      https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev
  연립다세대:  https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade
  오피스텔:    https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade

파라미터: serviceKey, LAWD_CD(법정동코드 앞 5자리), DEAL_YMD(계약년월 6자리, 예: 202401)

주의(실무에서 자주 걸리는 함정들):
1. "일반 자료"와 "상세 자료(Dev)"는 이름은 비슷해도 응답 태그명이 완전히 다르다. 일반
   자료는 한글 태그(거래금액, 아파트, 전용면적...)를 쓰지만, 이 모듈이 호출하는 상세
   자료(Dev)는 영문 태그(dealAmount, aptNm, excluUseAr...)를 쓴다. (아파트 API를 실제
   승인 키로 테스트하다가 이 차이 때문에 전부 not_found로 뜨는 버그를 잡은 적이 있다 —
   반드시 실제 응답을 한 번 찍어보고 태그명을 확인할 것.)
2. 응답이 XML이며, 태그 안 값에 앞뒤 공백이 섞여 있는 경우가 흔하다 (예: " 690,000").
3. 거래금액은 천단위 콤마가 포함된 문자열이다.
4. 결과가 1건이면 <item>이 리스트가 아니라 단일 엘리먼트로 온다 — 다만 ElementTree의
   findall()은 항상 리스트를 반환하므로 이 문제는 자동으로 해결된다.
5. 해제(취소)된 거래는 상세 자료(Dev) 기준으로 <cdealType> 태그에 값이 채워진다
   (일반 자료의 <해제여부>="O"에 대응). 값이 비어있지 않으면 취소 건으로 간주해 제외한다.

⚠️ 연립다세대(RHTrade)/오피스텔(OffiTrade) 태그명은 아직 우리 MOLIT_SERVICE_KEY로 직접
검증한 적은 없다 — 단, 이 코드를 짜면서 세션 중 관련 정보에 혼선이 있어(어떤 자료는
한글 태그 <연립다세대>/<단지>/<거래금액>이라고 주장, 어떤 자료는 영문 태그라고 주장)
GitHub의 독립적인 오픈소스 MOLIT API 클라이언트(tae0y/real-estate-mcp,
src/real_estate/mcp_server/parsers/trade.py)를 직접 찾아 대조했다. 그 구현체가 정확히
같은 엔드포인트(RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade, RTMSDataSvcOffiTrade/
getRTMSDataSvcOffiTrade — Dev 접미사 없음)와 같은 영문 태그(연립다세대=mhouseNm,
오피스텔=offiNm, 공통 dealAmount/dealYear/Month/Day/umdNm/excluUseAr/cdealType)를
쓰고 있어서, 아래 구현이 맞을 가능성이 높다고 판단해 그대로 뒀다. 하지만 이건 여전히
"우리가 실제로 검증"한 게 아니라 "남의 구현과 비교해 개연성이 높다"는 수준이다 —
public_price_adapter.py가 겪었던 함정과 근본적으로 같은 리스크이므로, 실제
MOLIT_SERVICE_KEY로 `debug_villa_officetel_call.py`를 반드시 한 번 돌려 진짜 응답을
찍어보고 이 경고를 지울 것. 다행히 "매물명" 태그는 market_price_estimator.py가 전혀
안 쓰는 참고용 필드라, 설령 이름이 틀려도 시세 계산 자체(dealAmount/excluUseAr/dealDate/
umdNm)는 안 깨진다 — 이 핵심 필드들이 세 API에서 공통 태그를 쓴다는 점은 위 독립
구현체에서도 일관되게 확인됐다.
"""

import os
import xml.etree.ElementTree as ET

import requests

SERVICE_KEY = os.environ.get("MOLIT_SERVICE_KEY", "여기에_공공데이터포털_인증키를_입력")
APT_API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
RH_API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade"
OFFI_API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade"

# 하위 호환 — 기존에 API_URL을 직접 참조하던 코드/테스트가 있을 수 있어 이름을 유지한다.
API_URL = APT_API_URL


class TransactionApiError(Exception):
    """API 자체가 에러를 반환했거나(인증키 오류 등) 응답 파싱이 불가능할 때"""
    pass


def _text(item: ET.Element, tag: str) -> str:
    """item 하위 tag의 텍스트를 안전하게 꺼내고 앞뒤 공백을 제거한다."""
    el = item.find(tag)
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _parse_amount(raw: str) -> int | None:
    """' 690,000' 같은 콤마/공백 포함 금액 문자열을 정수(만원 단위)로 변환한다."""
    cleaned = raw.replace(",", "").strip()
    if not cleaned:
        return None
    return int(cleaned)


def _parse_trade_xml(xml_text: str, name_tag: str) -> list[dict]:
    """
    국토부 실거래 '상세(Dev)' 계열 API의 XML 응답 문자열을 파싱해
    거래 리스트(dict의 list)로 변환한다. 아파트/연립다세대/오피스텔이 공유하는
    핵심 파싱 로직 — "매물명" 태그만 종류별로 다르다고 알려져 있어 name_tag로 뺐다
    (모듈 docstring의 "⚠️ 연립다세대/오피스텔 태그명은 미검증" 경고 참고).
    해제(취소)된 거래는 결과에서 제외한다.

    raises TransactionApiError: resultCode가 정상(000)이 아니거나 XML 파싱 자체가 실패한 경우
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise TransactionApiError(f"XML 파싱 실패 (응답이 XML이 아니거나 손상됨): {e}")

    # 공공데이터포털은 정상 응답과 다른 형식(cmmMsgHeader)으로 에러를 반환하는 경우가 있다.
    # 예: 등록되지 않은 서비스키, 잘못된 파라미터 등 — 이 경우 <header>가 아니라 <cmmMsgHeader>에 담겨 온다.
    cmm_header = root.find("cmmMsgHeader")
    if cmm_header is not None:
        err_msg = _text(cmm_header, "errMsg") or "알 수 없는 오류"
        raise TransactionApiError(f"국토부 API 오류 (cmmMsgHeader): {err_msg}")

    header = root.find("header")
    result_code = _text(header, "resultCode") if header is not None else None

    if result_code != "000":
        result_msg = _text(header, "resultMsg") if header is not None else "알 수 없는 오류"
        raise TransactionApiError(f"국토부 API 오류 (code={result_code}): {result_msg}")

    items_el = root.find("./body/items")
    if items_el is None:
        return []

    item_elements = items_el.findall("item")

    trades = []
    for item in item_elements:
        # 상세(Dev) API의 취소 표시는 cdealType — 값이 비어있지 않으면(보통 "해제") 취소 건
        is_cancelled = bool(_text(item, "cdealType"))
        if is_cancelled:
            continue

        deal_amount = _parse_amount(_text(item, "dealAmount"))
        if deal_amount is None:
            # 금액이 비어있는 비정상 레코드는 건너뛴다
            continue

        trades.append({
            "dealAmount": deal_amount,  # 만원 단위
            "buildYear": _text(item, "buildYear"),
            "dealYear": _text(item, "dealYear"),
            "dealMonth": _text(item, "dealMonth"),
            "dealDay": _text(item, "dealDay"),
            "dong": _text(item, "umdNm"),          # 읍면동명 (법정동)
            # 참고용 필드라 이름이 "aptName"으로 고정돼 있지만 연립다세대/오피스텔이면
            # 실제로는 그 매물명이 들어간다 — market_price_estimator.py는 이 필드를
            # 쓰지 않으므로 태그명이 틀려도 시세 계산에는 영향이 없다.
            "aptName": _text(item, name_tag),
            "exclusiveArea": float(_text(item, "excluUseAr") or 0),
            "jibun": _text(item, "jibun"),
            "floor": _text(item, "floor"),
            "dealType": _text(item, "dealingGbn"),  # 중개거래/직거래
        })

    return trades


def parse_apt_trade_xml(xml_text: str) -> list[dict]:
    """국토부 아파트매매 실거래 '상세(Dev)' API 응답 파싱 — 검증 완료(README 참고)."""
    return _parse_trade_xml(xml_text, name_tag="aptNm")


def parse_villa_trade_xml(xml_text: str) -> list[dict]:
    """
    국토부 연립다세대매매 실거래 '상세(Dev)' API 응답 파싱.
    ⚠️ 미검증 — 모듈 docstring 경고 참고. "매물명" 태그를 mhouseNm으로 추정했다.
    """
    return _parse_trade_xml(xml_text, name_tag="mhouseNm")


def parse_officetel_trade_xml(xml_text: str) -> list[dict]:
    """
    국토부 오피스텔매매 실거래 '상세(Dev)' API 응답 파싱.
    ⚠️ 미검증 — 모듈 docstring 경고 참고. "매물명" 태그를 offiNm으로 추정했다.
    """
    return _parse_trade_xml(xml_text, name_tag="offiNm")


def _fetch_trades(api_url: str, parse_fn, legal_dong_code_5: str, deal_ym: str) -> dict:
    """
    법정동코드 앞 5자리 + 계약년월(YYYYMM)로 국토부 API를 호출한다.
    아파트/연립다세대/오피스텔 fetch 함수가 공유하는 HTTP 호출 + 에러 분류 로직.

    반환값은 설계 문서 7.3절의 AdapterResult 형태를 그대로 따른다:
      {"status": "ok", "data": [...], "confidence": "high" | "low"}
      {"status": "not_found"}
      {"status": "error", "reason": "rate_limited" | "api_down" | "invalid_request"}
    """
    params = {
        "serviceKey": SERVICE_KEY,
        "LAWD_CD": legal_dong_code_5,
        "DEAL_YMD": deal_ym,
        "numOfRows": 100,
    }

    try:
        res = requests.get(api_url, params=params, timeout=5)
    except requests.exceptions.Timeout:
        return {"status": "error", "reason": "api_down"}
    except requests.exceptions.RequestException:
        return {"status": "error", "reason": "api_down"}

    # 주의: 공공데이터포털은 HTTP 상태코드가 200이 아니어도(403 등) 본문에
    # 정확한 에러 원인(XML)을 담아 보내는 경우가 많다. raise_for_status()로
    # 먼저 걸러버리면 이 원인을 못 보고 뭉뚱그려 "api_down"으로 처리하게 되므로,
    # 상태코드와 무관하게 먼저 본문 파싱을 시도한다.
    try:
        trades = parse_fn(res.text)
    except TransactionApiError as e:
        msg = str(e)
        if "SERVICE_KEY" in msg.upper() or "인증" in msg:
            return {"status": "error", "reason": "invalid_request"}
        return {"status": "error", "reason": "api_down"}

    if not trades:
        return {"status": "not_found"}

    return {"status": "ok", "data": trades, "confidence": "high"}


def fetch_apt_trades(legal_dong_code_5: str, deal_ym: str) -> dict:
    """아파트매매 실거래 조회 — 검증 완료(README 참고)."""
    return _fetch_trades(APT_API_URL, parse_apt_trade_xml, legal_dong_code_5, deal_ym)


def fetch_villa_trades(legal_dong_code_5: str, deal_ym: str) -> dict:
    """
    연립다세대매매 실거래 조회 (property_type "villa"/"multi_household" 대상).
    ⚠️ 미검증 — 모듈 docstring 경고 참고.
    """
    return _fetch_trades(RH_API_URL, parse_villa_trade_xml, legal_dong_code_5, deal_ym)


def fetch_officetel_trades(legal_dong_code_5: str, deal_ym: str) -> dict:
    """
    오피스텔매매 실거래 조회 (property_type "officetel" 대상).
    ⚠️ 미검증 — 모듈 docstring 경고 참고.
    """
    return _fetch_trades(OFFI_API_URL, parse_officetel_trade_xml, legal_dong_code_5, deal_ym)
