"""
PropertyAggregator (설계문서 7.4절)
------------------------------------
주소 하나를 받아서:
  1. AddressResolver로 정규화
  2. 실거래가(최근 N개월치를 모아서) + 건축물대장을 "병렬" 호출
  3. 결과를 합쳐서 PropertyInfo 형태로 반환

핵심 설계 원칙 (설계문서 7.4절 그대로):
- 실거래가/건축물대장은 서로 의존관계가 없으므로 병렬 호출한다.
- 하나가 실패해도 전체를 실패시키지 않는다 (부분 실패 허용).
- 없는 데이터는 억지로 채우지 않고 confidence/status로 정직하게 표시한다.
"""

import calendar
import concurrent.futures
from datetime import date

from address_resolver import resolve_address, AddressResolutionError
from real_transaction_price_adapter import fetch_apt_trades, fetch_villa_trades, fetch_officetel_trades
from building_register_adapter import fetch_building_register
from market_price_estimator import estimate_market_price
from public_price_adapter import fetch_public_price


class PropertyAggregationError(Exception):
    """주소 자체를 정규화할 수 없어 아무 데이터도 조회하지 못했을 때"""
    pass


def _trade_fetch_fn_for(property_type: str):
    """
    property_type -> 국토부 실거래 fetch 함수. "연립다세대" API 한 종류가 통계법상
    연립주택+다세대주택을 모두 커버하므로 "villa"/"multi_household" 둘 다 여기로 간다.
    ⚠️ villa/officetel 쪽은 real_transaction_price_adapter.py 모듈 docstring에 적어둔
    대로 태그명이 미검증 상태다.

    이 매핑을 모듈 최상단에 상수 dict로 미리 만들어두지 않고 매번 함수 호출 시점에
    만드는 이유: 상수로 만들면 import 시점의 fetch_apt_trades 등 함수 객체를 그대로
    캡처해버려서, 테스트가 @patch("property_aggregator.fetch_villa_trades")로 모듈
    전역을 바꿔치기해도 이 dict 안의 값은 옛날 그대로다(실제로 이 버그로 테스트가
    가짜 네트워크 호출을 실제로 내보내 66초가 걸린 적이 있다) — 매번 새로 만들면
    항상 그 시점의 모듈 전역(패치된 값 포함)을 참조한다.
    """
    return {
        "apartment": fetch_apt_trades,
        "villa": fetch_villa_trades,
        "multi_household": fetch_villa_trades,
        "officetel": fetch_officetel_trades,
    }.get(property_type)


def _recent_year_months(as_of: date, months: int) -> list[str]:
    """as_of 기준 최근 N개월의 'YYYYMM' 문자열 리스트 (최신순)."""
    result = []
    year, month = as_of.year, as_of.month
    for _ in range(months):
        result.append(f"{year}{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return result


def _fetch_recent_trades(fetch_fn, lawd_cd_5: str, as_of: date, months: int = 6) -> dict:
    """
    최근 months개월치 실거래를 각각 조회해서 하나의 리스트로 합친다.
    일부 달 조회가 실패해도(그 달만 거래가 없거나 일시 오류) 나머지 달 데이터로 계속 진행한다.

    fetch_fn: fetch_apt_trades / fetch_villa_trades / fetch_officetel_trades 중
        property_type에 맞는 것 — _trade_fetch_fn_for() 참고.
    """
    all_trades = []
    any_ok = False
    errors = []

    for ym in _recent_year_months(as_of, months):
        result = fetch_fn(lawd_cd_5, ym)
        if result["status"] == "ok":
            all_trades.extend(result["data"])
            any_ok = True
        elif result["status"] == "not_found":
            any_ok = True  # 정상 응답(거래가 없었을 뿐) — 실패로 치지 않는다
        else:
            errors.append({"dealYm": ym, **result})

    if not any_ok and errors:
        # 모든 달 호출이 전부 에러였던 경우만 완전 실패로 본다
        return {"status": "error", "errors": errors}

    return {"status": "ok", "data": all_trades, "partialErrors": errors}


def get_property_info(address_query: str, target_area: float, as_of: date | None = None,
                       months: int = 6, property_type: str = "apartment") -> dict:
    """
    주소와 대상 전용면적으로 PropertyInfo에 가까운 결과를 조립해 반환한다.

    반환 예시:
    {
        "normalizedAddress": {...},          # AddressResolver 결과
        "marketPrice": 246500,
        "marketPriceConfidence": "high",
        "marketPriceBasis": "...",
        "building": {...} | None,
        "registrySeparated": True | False | None,
        "violationStatusConfirmed": bool,
        "violationStatusRaw": str | None,
        "sourceStatuses": {                  # 디버깅/UX용 — 어떤 소스가 성공/실패했는지 투명하게 노출
            "transactionPrice": "ok" | "error" | "skipped" | ...,
            "buildingRegister": "ok" | "not_found" | "error" | ...,
            "publicPrice": "ok" | "not_found" | "error" | ...,  # vworld 키 없으면 항상 error
        }
    }

    Args:
        property_type: "apartment" | "villa" | "officetel" | "multi_household".
            _trade_fetch_fn_for() 매핑에 따라 국토부 실거래 엔드포인트를 골라 조회한다
            (아파트=AptTradeDev, 빌라/다세대=RHTrade, 오피스텔=OffiTrade —
            real_transaction_price_adapter.py 참고). ⚠️ RHTrade/OffiTrade는 아직
            실키로 응답 구조를 확인 못 한 미검증 엔드포인트다. 매핑에 없는 값이 오면
            (또는 향후 실거래 자체가 불가능한 유형이 생기면) 안전하게 조회를 건너뛴다
            — 실제로 54㎡ 다세대가 근처 아파트 실거래 기준 14.375억으로 잘못 나오고
            실제 시세는 9~10억이었던 버그(아파트 데이터를 모든 유형에 그대로 썼던 것)를
            겪고 나서, "모르면 아예 안 쓴다" 원칙을 여기 매핑으로 강제하게 됐다. 실거래
            비교가 없으면 공시가격 폴백(있으면 confidence="estimated_from_public_price")
            또는 marketPrice=None/confidence="unavailable"로 정직하게 떨어진다.
            기본값을 "apartment"로 둔 건 이 함수를 직접 호출하는 기존 코드(테스트 포함)의
            동작을 바꾸지 않기 위함 — 실제 서비스 흐름(full_assessment.py)은 유저가 고른
            property_type을 항상 명시적으로 전달한다.

    raises PropertyAggregationError: 주소 자체를 정규화하지 못한 경우 (이 경우는 부분 실패 허용 대상이 아님 —
        주소가 틀리면 뒤의 모든 조회가 무의미하므로 여기서만 예외를 던진다.)
    """
    if as_of is None:
        as_of = date.today()

    try:
        normalized = resolve_address(address_query)
    except AddressResolutionError as e:
        raise PropertyAggregationError(f"주소를 정규화하지 못해 조회를 진행할 수 없습니다: {e}")

    legal_dong_code = normalized["legalDongCode"]
    lawd_cd_5 = legal_dong_code[:5]
    bjdong_cd = legal_dong_code[5:]

    pnu = normalized.get("pnu")
    can_query_building = pnu is not None
    if can_query_building:
        # PNU 19자리 = 법정동코드(10) + 산여부(1) + 본번(4) + 부번(4)
        plat_gb_cd = pnu[10]
        bun = pnu[11:15]
        ji = pnu[15:19]

    # ---- 실거래가 + 건축물대장 + 공시가격을 병렬 호출 (서로 의존관계 없음) ----
    # 공시가격(public_price_adapter)은 아직 vworld 키가 없는 상태에서도 안전하게 붙여둔다 —
    # 키가 없으면 fetch_public_price()가 네트워크 호출 없이 바로 invalid_request를 반환하므로
    # (public_price_adapter.py 참고) 지금 당장의 동작은 이 통합 이전과 완전히 동일하다.
    # property_type에 맞는 실거래 fetch 함수를 고른다 — 매핑에 없으면(방어적) 조회
    # 자체를 건너뛴다(위 property_type 인자 설명 참고).
    trade_fetch_fn = _trade_fetch_fn_for(property_type)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        trade_future = (
            executor.submit(_fetch_recent_trades, trade_fetch_fn, lawd_cd_5, as_of, months)
            if trade_fetch_fn else None
        )
        if can_query_building:
            building_future = executor.submit(
                fetch_building_register, lawd_cd_5, bjdong_cd, plat_gb_cd, bun, ji
            )
        else:
            building_future = None
        public_price_future = executor.submit(fetch_public_price, pnu) if pnu else None

        trade_result = trade_future.result() if trade_future else {
            "status": "skipped",
            "reason": f"property_type='{property_type}'에 대응하는 국토부 실거래 엔드포인트가 없어 조회 대상 아님",
        }
        building_result = building_future.result() if building_future else {
            "status": "error", "reason": "invalid_request"  # PNU 없어서 애초에 조회 불가
        }
        public_price_result = public_price_future.result() if public_price_future else {
            "status": "error", "reason": "invalid_request"
        }

    public_price = (
        public_price_result["data"]["publicPrice"]
        if public_price_result["status"] == "ok" else None
    )

    # ---- 시세 추정 ----
    if trade_result["status"] == "ok":
        estimate = estimate_market_price(
            trade_result["data"], target_area=target_area, as_of=as_of, public_price=public_price,
        )
    elif trade_result["status"] == "skipped":
        # 아파트 실거래 비교 자체를 시도하지 않은 경우 — trades=[]로 넘기면
        # estimate_market_price()가 곧바로 공시가격 폴백(또는 unavailable)으로 넘어간다.
        estimate = estimate_market_price(
            [], target_area=target_area, as_of=as_of, public_price=public_price,
        )
    else:
        # TODO(vworld 연동 후): 이 분기(실거래가 API 호출 자체가 실패한 경우)는 아직
        # public_price로 폴백을 시도하지 않는다 — "조회를 안 해봄"과 "조회했는데 없음"을
        # 구분하는 현재의 명확한 basis 메시지를 유지하기 위해 일부러 남겨뒀다. vworld
        # 검증이 끝나면 이 분기에서도 public_price가 있으면 살려 쓸지 판단할 것.
        estimate = {"marketPrice": None, "confidence": "unavailable",
                     "usedTradeCount": 0, "basis": "실거래가 조회 자체가 실패함"}

    # ---- 건축물대장 결과 반영 ----
    building_info = None
    registry_separated = None
    violation_confirmed = False
    violation_raw = None
    non_residential_use_risk = False

    if building_result["status"] == "ok" and building_result["data"]:
        building_info = building_result["data"][0]  # 동일 지번에 여러 동이 있으면 첫 동만 우선 사용 (2단계에서 동 선택 UX 필요)
        kind = building_info.get("registerKind", "")
        if kind == "집합":
            registry_separated = True
        elif kind == "일반건축물":
            registry_separated = False
        violation_confirmed = building_info.get("violationStatusConfirmed", False)
        violation_raw = building_info.get("violationStatusRaw")
        non_residential_use_risk = building_info.get("isRegisteredAsNonResidential", False)

    return {
        "normalizedAddress": normalized,
        "marketPrice": estimate["marketPrice"],
        "marketPriceConfidence": estimate["confidence"],
        "marketPriceBasis": estimate["basis"],
        "building": building_info,
        "registrySeparated": registry_separated,
        "violationStatusConfirmed": violation_confirmed,
        "violationStatusRaw": violation_raw,
        "nonResidentialUseRisk": non_residential_use_risk,  # '근생빌라' 의심 플래그
        "sourceStatuses": {
            "transactionPrice": trade_result["status"],
            "buildingRegister": building_result["status"],
            "publicPrice": public_price_result["status"],  # vworld 키 없으면 항상 "error"
        },
    }
