"""
BuildingRegisterAdapter 프로토타입
------------------------------------
국토교통부 건축HUB "건축물대장정보 서비스" 중 표제부(getBrTitleInfo)를 호출한다.

실제 서비스 URL (2024년 '건축HUB' 개편 반영 — 구버전 BldRgstService_v2는 폐기됨):
  http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo

파라미터:
  sigunguCd : 시군구코드 5자리 (법정동코드 10자리의 앞 5자리, AddressResolver의 legalDongCode[:5])
  bjdongCd  : 읍면동코드 5자리 (법정동코드 10자리의 뒤 5자리, legalDongCode[5:])
  platGbCd  : 대지구분코드 (0=대지, 1=산) — AddressResolver의 mountain_yn과 대응
  bun/ji    : 본번/부번 4자리씩 — AddressResolver의 main_address_no/sub_address_no와 대응
  ServiceKey, numOfRows

⚠️ 확인된 사실 (추측 아님 — 표제부/총괄표제부/기본개요/층별개요/전유부/소유자 등
  전체 대장 유형의 공식 필드 목록을 확인한 결과):
  건축물대장 API 응답에는 '위반건축물여부'에 해당하는 필드가 존재하지 않는다.
  국토부 분쟁조정 사례(2025-026)에서도 국토교통부가 "위반건축물 API"를 사업 목적으로는
  제공 거부한 전례가 있어, 이는 단순 누락이 아니라 의도적으로 비공개된 정보로 보인다.
  → 위반건축물 여부는 이 API로 자동화 불가능. 2.1절 데이터 모델의 isViolationBuilding은
    사용자가 등기부등본/건축물대장 PDF를 직접 확인하거나 세움터에서 열람해야 하는 항목으로
    재분류해야 한다 (2단계 이후 과제, 또는 유저 자기확인 체크리스트 항목으로 이동).
  아래 _VIOLATION_FIELD_CANDIDATES는 혹시 모를 필드 추가에 대비한 안전장치로만 남겨둔다
  (평소엔 항상 None으로 처리됨).
"""

import os
import xml.etree.ElementTree as ET

import requests

SERVICE_KEY = os.environ.get("MOLIT_SERVICE_KEY", "여기에_공공데이터포털_인증키를_입력")
API_URL = "http://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"

# 위반건축물 여부일 가능성이 있는 후보 태그명 — 실제 응답 확인 전까지는 추측이다.
_VIOLATION_FIELD_CANDIDATES = ["violationStatus", "violationInfo", "violationBldgYn"]

# '근생빌라' 탐지용 — 근린생활시설/판매/업무시설로 등재된 건물이 실제로는 주거용(원룸/투룸 등)으로
# 임대되는 경우, 위반건축물 딱지가 붙기 전이라도 구조적 불법 개조 가능성이 높다.
# (표제부 API의 mainPurpsCdNm 텍스트만으로 판별 — 별도 API 호출 불필요)
_NON_RESIDENTIAL_USE_KEYWORDS = ["근린생활시설", "판매시설", "업무시설", "숙박시설"]


def is_registered_as_non_residential(main_purpose: str) -> bool:
    """
    건축물대장상 주용도가 근린생활시설/판매/업무/숙박시설 등으로 등재돼 있는지 확인한다.
    유저가 이걸 '원룸 전세'로 계약하려는 매물이라면, 위반건축물 딱지 유무와 무관하게
    구조적으로 불법 개조된 '근생빌라'일 가능성이 높다는 경고 신호가 된다.
    """
    return any(keyword in main_purpose for keyword in _NON_RESIDENTIAL_USE_KEYWORDS)


class BuildingRegisterApiError(Exception):
    pass


def _text(item: ET.Element, tag: str) -> str:
    el = item.find(tag)
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def parse_building_register_xml(xml_text: str) -> list[dict]:
    """
    표제부 API XML 응답을 파싱한다. 한 주소에 여러 동(棟)이 있으면 item이 여러 개 온다
    (예: 아파트 단지 전체 동 목록이 아니라, 같은 지번 위 별동 건물들).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise BuildingRegisterApiError(f"XML 파싱 실패: {e}")

    cmm_header = root.find("cmmMsgHeader")
    if cmm_header is not None:
        err_msg = _text(cmm_header, "errMsg") or "알 수 없는 오류"
        raise BuildingRegisterApiError(f"국토부 API 오류 (cmmMsgHeader): {err_msg}")

    header = root.find("header")
    result_code = _text(header, "resultCode") if header is not None else None
    # 주의: 이 API의 성공 코드는 "00"(두 자리)이다. 실거래가 API의 "000"(세 자리)과 다르므로
    # 절대 재사용하지 말 것 — 실제로 이 차이 때문에 정상 응답을 에러로 오인한 버그가 있었다.
    if result_code != "00":
        result_msg = _text(header, "resultMsg") if header is not None else "알 수 없는 오류"
        raise BuildingRegisterApiError(f"국토부 API 오류 (code={result_code}): {result_msg}")

    items_el = root.find("./body/items")
    if items_el is None:
        return []

    buildings = []
    for item in items_el.findall("item"):
        violation_raw = None
        for candidate in _VIOLATION_FIELD_CANDIDATES:
            val = _text(item, candidate)
            if val:
                violation_raw = val
                break

        buildings.append({
            "bldName": _text(item, "bldNm"),
            "mainPurpose": _text(item, "mainPurpsCdNm"),
            "etcPurpose": _text(item, "etcPurps"),
            "registerKind": _text(item, "regstrKindCdNm"),  # "일반건축물" / "집합" 등
            "useApprovalDate": _text(item, "useAprDay"),     # 사용승인일 (YYYYMMDD)
            "householdCount": _text(item, "hhldCnt"),
            "seismicDesignApplied": _text(item, "rserthqkDsgnApplyYn"),
            "totalFloorArea": _text(item, "totArea"),
            "isRegisteredAsNonResidential": is_registered_as_non_residential(_text(item, "mainPurpsCdNm")),
            "violationStatusRaw": violation_raw,
            "violationStatusConfirmed": violation_raw is not None,  # False면 "unconfirmed"로 UX 처리
        })

    return buildings


def fetch_building_register(sigungu_cd: str, bjdong_cd: str, plat_gb_cd: str,
                             bun: str, ji: str) -> dict:
    """
    AdapterResult 형태로 반환 (설계 문서 7.3절과 동일한 형태):
      {"status": "ok", "data": [...], "confidence": "high"}
      {"status": "not_found"}
      {"status": "error", "reason": "rate_limited" | "api_down" | "invalid_request"}
    """
    params = {
        "serviceKey": SERVICE_KEY,
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "platGbCd": plat_gb_cd,
        "bun": bun,
        "ji": ji,
        "numOfRows": 20,
    }

    try:
        res = requests.get(API_URL, params=params, timeout=5)
    except requests.exceptions.Timeout:
        return {"status": "error", "reason": "api_down"}
    except requests.exceptions.RequestException:
        return {"status": "error", "reason": "api_down"}

    try:
        buildings = parse_building_register_xml(res.text)
    except BuildingRegisterApiError as e:
        msg = str(e)
        if "SERVICE_KEY" in msg.upper() or "인증" in msg:
            return {"status": "error", "reason": "invalid_request"}
        return {"status": "error", "reason": "api_down"}

    if not buildings:
        return {"status": "not_found"}

    return {"status": "ok", "data": buildings, "confidence": "high"}
