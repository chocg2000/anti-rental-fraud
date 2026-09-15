"""
전세사기 방지 핵심 룰 (설계문서 3.1절 LTV + 3.3절 임대인 리스크 연장 + 대항력/우선변제권)
------------------------------------------------------------------------
지금까지 만든 조각들을 실제 유저 판단에 쓰이는 다섯 가지 룰로 연결한다:

룰 1. 보증금보다 우선하는 선순위 채권액 계산 (을구 기반, 깡통전세 위험)
룰 2. 소유주 일치 여부 검증 (갑구 기반, 신탁/대리인/법인 사기 방지)
  + 추가: 공유자(공동소유) 케이스 — 계약서 이름이 일치해도 공유자 전원 동의가 없으면
    계약이 무효화될 수 있어 별도로 경고해야 한다.
룰 3. 대항력 발생의 시간적 공백(Gap) 위험 (주택임대차보호법 제3조)
  전입신고+인도(대항력)는 신고 익일 0시부터 효력이 발생하지만, 등기부상 권리(근저당권 등)는
  접수 당일 즉시 효력이 발생한다. 임대인이 잔금일 당일에 근저당권을 설정하면 그 권리가
  세입자의 대항력보다 먼저 효력을 갖게 되어 보증금이 후순위로 밀린다 — 실제 전세사기에서
  자주 쓰이는 수법이라 별도 룰로 분리해 날카롭게 잡아낸다 (룰 1의 LTV 합계 계산에도 이
  채권이 포함되긴 하지만, "왜 위험한지"에 대한 설명은 안 해준다).
룰 4. 확정일자 미부여 위험 (주택임대차보호법 제3조의2)
  대항력이 있어도 확정일자가 없으면 경매 시 우선변제권(배당요구권) 자체가 발생하지 않는다.
룰 5. 최우선변제금(소액임차인 보호, 주택임대차보호법 제8조) — 2026-09-15 확보한 검증된
  현행(2023-02-21 시행) 테이블 범위로 한정해 구현. 기준일이 그 이전이거나 지역 판정이
  불가능한 경우는 의도적으로 "unknown"을 반환한다 — 자세한 범위 제한 사유는
  check_minimum_priority_repayment() docstring 참고.
"""

from datetime import date as date_cls
from typing import Literal

RiskLevel = Literal["safe", "caution", "warning", "danger", "unknown"]

# 아파트/빌라 안전 임계치가 다르다는 건 스코어링 룰 3.1절에 이미 정의돼 있음 — 그대로 재사용.
_SAFE_RATIO_BY_TYPE = {"apartment": 0.8, "villa": 0.7, "officetel": 0.7, "multi_household": 0.7}

_CORPORATE_KEYWORDS = ["주식회사", "(주)", "유한회사", "합자회사", "재단법인", "사단법인"]
_TRUST_KEYWORDS = ["신탁"]


def check_deposit_priority_risk(
    market_price: int | None,
    senior_secured_amount: int,
    my_deposit: int,
    property_type: str = "villa",
    market_price_confidence: str = "high",
) -> dict:
    """
    룰 1: [시세 × 안전비율]보다 [선순위 채권 총액 + 내 보증금]이 크면 깡통전세 위험.

    Args:
        market_price: MarketPriceEstimator가 추정한 시세 (만원 단위, 없으면 None)
        senior_secured_amount: RegistrySummaryParser의 totalSeniorSecuredAmount
                                (근저당권+전세권 합계, 원 단위)
        my_deposit: 내가 들어갈 보증금 (원 단위)
        property_type: "apartment" | "villa" | "officetel" | "multi_household"
                       유형별로 안전 임계 비율이 다르다 (아파트 80%, 그 외 70%).
        market_price_confidence: market_price_estimator.estimate_market_price()의
            confidence 값("high"|"low"|"estimated_from_public_price"|"unavailable")을
            그대로 전달받는다. "estimated_from_public_price"(실거래가 없이 공시가격×1.4로
            추정한 값)인 경우, 이 계산 자체는 그대로 수행하되 그 판단 근거가 실거래가만큼
            믿을 만하지 않다는 걸 결과에 명시적으로 남긴다 — 공시가격 연동 전에는
            이 값을 안 넘기면 기본값 "high"로 동작해 기존 호출부와 100% 호환된다.
    """
    if market_price is None:
        return {
            "riskyDepositPriority": None,
            "reason": "시세 데이터가 없어 판단할 수 없습니다 (실거래가 부족 지역일 수 있음)",
        }

    safe_ratio = _SAFE_RATIO_BY_TYPE.get(property_type, 0.7)
    safe_threshold = market_price * safe_ratio
    total_priority_claims = senior_secured_amount + my_deposit
    is_risky = total_priority_claims > safe_threshold

    reason = (
        f"선순위 채권({senior_secured_amount:,}원) + 내 보증금({my_deposit:,}원) = "
        f"{total_priority_claims:,}원이 시세의 {int(safe_ratio*100)}%인 "
        f"{round(safe_threshold):,}원을 {'초과' if is_risky else '초과하지 않음'}"
    )

    price_is_estimated = market_price_confidence == "estimated_from_public_price"
    if price_is_estimated:
        reason += (
            " (참고: 이 시세는 실거래가가 아니라 공시가격 추정치를 기반으로 계산되었습니다 "
            "— 실제 매매가와 차이가 있을 수 있어 신뢰도가 제한적입니다.)"
        )

    return {
        "riskyDepositPriority": is_risky,
        "marketPrice": market_price,
        "marketPriceConfidence": market_price_confidence,
        "priceIsEstimated": price_is_estimated,
        "safeRatio": safe_ratio,
        "safeThreshold": round(safe_threshold),
        "seniorSecuredAmount": senior_secured_amount,
        "myDeposit": my_deposit,
        "totalPriorityClaims": total_priority_claims,
        "reason": reason,
    }


def check_landlord_identity_match(contract_landlord_name: str, registry_owners: list[dict]) -> dict:
    """
    룰 2: 계약서상 임대인 이름과 등기부(갑구) 소유자를 대조한다.

    Args:
        contract_landlord_name: 임대차 계약서에 적힌 임대인 이름
        registry_owners: RegistrySummaryParser의 owners 리스트
                          [{"ownerName": str, "shareType": "단독소유"|"공유"}, ...]
    """
    if not registry_owners:
        return {
            "match": None,
            "riskLevel": "unknown",
            "reason": "등기부에서 소유자 정보를 확인하지 못했습니다.",
        }

    owner_names = [o["ownerName"] for o in registry_owners]
    name_matches = contract_landlord_name.strip() in owner_names
    is_corporate = any(any(kw in name for kw in _CORPORATE_KEYWORDS) for name in owner_names)
    is_trust = any(any(kw in name for kw in _TRUST_KEYWORDS) for name in owner_names)
    is_co_owned = len(registry_owners) > 1

    if is_trust:
        return {
            "match": name_matches,
            "riskLevel": "danger",
            "reason": (
                f"등기부상 소유자가 신탁({', '.join(owner_names)})입니다 — "
                "신탁 부동산은 수탁자 동의 없는 임대차 계약이 원천 무효가 될 수 있습니다. "
                "반드시 수탁자(신탁회사) 명의의 동의서를 확인하세요."
            ),
        }

    if is_corporate:
        return {
            "match": name_matches,
            "riskLevel": "warning" if name_matches else "danger",
            "reason": (
                f"등기부상 소유자가 법인({', '.join(owner_names)})입니다 — "
                "대표자 본인이 아니라면 법인 인감이 날인된 위임장을 반드시 확인하세요."
            ),
        }

    if not name_matches:
        return {
            "match": False,
            "riskLevel": "danger",
            "reason": (
                f"계약서 임대인('{contract_landlord_name}')이 등기부 소유자"
                f"({', '.join(owner_names)})와 다릅니다 — "
                "위임장과 인감증명서로 대리 권한을 반드시 확인하세요."
            ),
        }

    if is_co_owned:
        return {
            "match": True,
            "riskLevel": "caution",
            "reason": (
                f"소유자가 {len(registry_owners)}명(공유)입니다 — "
                "계약서에 이름이 있는 분 외에 공유자 전원의 동의(서명)가 없으면 "
                "계약이 무효화될 위험이 있습니다."
            ),
        }

    return {"match": True, "riskLevel": "safe", "reason": "계약서 임대인과 등기부 소유자가 일치합니다."}


def check_possession_priority_gap_risk(
    move_in_date: str | None,
    active_rights: list[dict],
) -> dict:
    """
    룰 3: 대항력 발생의 시간적 공백 위험.

    전입신고(대항력)는 신고한 날의 "익일 0시"부터 효력이 발생하지만, 등기부상 권리는
    접수된 "당일" 즉시 효력이 발생한다. 그래서 잔금 지급/입주(전입신고)일과 같은 날
    접수된 근저당권 등이 있으면, 세입자의 대항력이 채 발생하기도 전에 그 권리가 먼저
    선순위를 차지해버린다 — 계약 당일 임대인이 대출을 실행하는 전형적인 사기 수법.

    하루라도 먼저(과거에) 접수된 권리는 이미 룰 1(선순위채권 합계)에 정직하게 반영돼
    있으므로 여기서 다시 위험으로 잡지 않는다 — 이 룰이 잡아내는 건 "타이밍이 수상한"
    바로 그 당일 접수 건만이다.

    Args:
        move_in_date: 계약서상 잔금 지급/입주(전입신고 예정)일 ("YYYY-MM-DD"). 아직 안
            정했거나 입력 안 받았으면 None — 이 경우 판단 자체를 건너뛴다(unknown).
        active_rights: RegistrySummaryParser의 activeRights (각 항목에 receivedDate 필요).
    """
    if not move_in_date:
        return {
            "gapRiskDetected": None,
            "reason": "잔금(입주) 예정일 정보가 없어 대항력 공백 위험을 판단할 수 없습니다.",
        }

    try:
        date_cls.fromisoformat(move_in_date)
    except (ValueError, TypeError):
        return {
            "gapRiskDetected": None,
            "reason": f"잔금(입주) 예정일 형식이 올바르지 않아 판단할 수 없습니다: {move_in_date!r}",
        }

    same_day_rights = [
        r for r in active_rights if r.get("receivedDate") == move_in_date
    ]
    # 프론트가 잔금일 대비 등기부 접수일들을 시각적 타임라인으로 그릴 수 있도록, 날짜를
    # 확인할 수 있는 권리만(추측 없이) 접수일 순으로 정리해 함께 내려준다.
    dated_rights = sorted(
        (r for r in active_rights if r.get("receivedDate")),
        key=lambda r: r["receivedDate"],
    )

    if not same_day_rights:
        return {
            "gapRiskDetected": False,
            "moveInDate": move_in_date,
            "rightsTimeline": dated_rights,
            "reason": "잔금(입주)일 당일에 새로 접수된 권리가 발견되지 않았습니다.",
        }

    names = ", ".join(f"{r.get('rightType', '권리')}({r.get('amount', 0):,}원)" for r in same_day_rights)
    return {
        "gapRiskDetected": True,
        "moveInDate": move_in_date,
        "rightsTimeline": dated_rights,
        "suspiciousRights": same_day_rights,
        "reason": (
            f"잔금(입주) 예정일({move_in_date}) 당일에 접수된 권리가 있습니다: {names}. "
            "대항력은 전입신고 다음 날 0시부터 발생하지만 등기부상 권리는 접수 당일 즉시 "
            "효력이 발생하므로, 해당 채권이 선순위가 되어 보증금이 보호받지 못할 위험이 "
            "매우 높습니다 — 전입신고를 며칠 앞당기거나 계약을 재검토하세요."
        ),
    }


def check_fixed_date_risk(has_fixed_date: bool | None) -> dict:
    """
    룰 4: 확정일자 미부여 위험.

    대항력(전입신고+인도)이 있어도 확정일자를 안 받으면, 매물이 경매로 넘어갔을 때
    법적으로 보증금을 우선 돌려받을 수 있는 "우선변제권" 자체가 발생하지 않는다.

    Args:
        has_fixed_date: 확정일자를 받았는지 여부.
            None = 아직 안 물어봤음(유저 입력 자체가 없음) -> "unknown"으로 판단 보류.
            False = 유저가 명시적으로 "아직 안 받았다"고 답함 -> "caution".
            True = 받았다고 확인됨 -> "safe".
            (완납증명서 체크의 None=건너뜀 vs False=명시적 미제출 구분과 같은 패턴.
            None을 곧바로 경고로 처리하면 이 필드를 아직 안 물어보는 모든 기존 호출부가
            갑자기 매번 경고를 받게 되므로 반드시 구분해야 한다.)

            ⚠️ False를 "warning"이 아니라 "caution"으로 두는 이유: 이 앱은 "계약 전"
            진단이 주 사용 시나리오인데, 확정일자는 계약을 체결해야만 받을 수 있다 —
            전입신고도 마찬가지로 계약서 없이는 불가능하다. 즉 대부분의 정상적인
            사용자에게 False는 항상 참인 당연한 상태이지 이 매물의 위험 신호가 아니다.
            "warning"으로 두면 거의 모든 진단에서 매번 경고가 떠서 실제 위험 신호의
            신뢰도만 깎아먹는다 — "caution" 수준의 할일 리마인더로만 다룬다.
    """
    if has_fixed_date is None:
        return {
            "riskLevel": "unknown",
            "reason": "확정일자 여부를 확인하지 못했습니다.",
        }

    if has_fixed_date:
        return {
            "riskLevel": "safe",
            "reason": "확정일자가 부여되어 우선변제권 요건을 갖췄습니다.",
        }

    return {
        "riskLevel": "caution",
        "reason": (
            "확정일자가 아직 없습니다 — 확정일자는 계약을 체결해야만 받을 수 있으므로 "
            "계약 전이라면 정상입니다. 다만 확정일자가 없으면 매물이 경매로 넘어가도 "
            "법적으로 보증금을 우선 돌려받을 수 있는 우선변제권이 발생하지 않으니, "
            "계약 체결 당일 바로 주민센터나 인터넷등기소에서 확정일자를 받으세요."
        ),
    }


# 2026-09-15 세 개 독립 출처(국가법령정보센터 시행령, 법제처 찾기쉬운 생활법령정보,
# 부동산케이스노트 개정연혁 정리)로 교차 확인한 현행(2023-02-21 시행) 최우선변제금 테이블.
# 이 시행령은 여러 차례(1984, 1987, 1990, 1995, 2001, 2008, 2010, 2014, 2016, 2018,
# 2021, 2023) 개정됐는데, 이 중 지금 확보/검증한 건 가장 최근 구간 하나뿐이다 — 그
# 이전 기준일은 check_minimum_priority_repayment()가 의도적으로 "unknown"을 반환한다.
_PRIORITY_TABLE_EFFECTIVE_DATE = date_cls(2023, 2, 21)
_PRIORITY_REPAYMENT_TABLE = {
    "seoul": {"maxDeposit": 165_000_000, "claimAmount": 55_000_000},
    "overcrowded": {"maxDeposit": 145_000_000, "claimAmount": 48_000_000},
    "metropolitan": {"maxDeposit": 85_000_000, "claimAmount": 28_000_000},
    "other": {"maxDeposit": 75_000_000, "claimAmount": 25_000_000},
}


def _earliest_secured_right_date(active_rights: list[dict]) -> date_cls | None:
    """active_rights 중 receivedDate가 유효한 것들만 골라 가장 오래된 날짜를 찾는다."""
    dates = []
    for r in active_rights:
        raw = r.get("receivedDate")
        if not raw:
            continue
        try:
            dates.append(date_cls.fromisoformat(raw))
        except (ValueError, TypeError):
            continue
    return min(dates) if dates else None


def check_minimum_priority_repayment(
    my_deposit: int,
    market_price: int | None,
    active_rights: list[dict],
    region: str | None,
    as_of: date_cls | None = None,
) -> dict:
    """
    룰 5: 최우선변제금(소액임차인 보호, 주택임대차보호법 제8조).

    다른 룰들과 성격이 다르다 — 이건 "위험 신호"가 아니라 "안전망 안내"다. 그래서
    overall_safety_assessment.py의 등급 산정에는 관여하지 않는다(safe/eligible이어도
    등급을 낮추지 않고, not_eligible/unknown이어도 등급을 올리지 않는다) — 단지
    "이 정도는 최우선으로 보장받는다"는 참고 정보를 결과 화면에 보여주기 위한 룰이다.

    기준일(基準日)은 계약일이나 진단일이 아니라 "등기부상 가장 오래된 선순위 담보물권의
    접수일"이다 — 선순위 권리자가 사후 법 개정으로 불이익을 받지 않도록 하기 위한 법리다.
    담보물권이 하나도 없으면 진단 시점(as_of)을 기준일로 쓴다(보호할 기존 담보권이
    없으므로 현재 시행 중인 법을 적용하는 게 타당하다).

    ⚠️ 의도적으로 좁힌 범위 (모듈 docstring의 "여기 포함 안 된 것" 참고했던 기존 보류를
    부분적으로만 해제):
      1. 기준일이 2023-02-21보다 이르면 status="unknown" — 그 이전 개정 이력(최소
         7차례)의 정확한 금액 테이블을 아직 확보/검증하지 못했다. 확인 안 된 옛날
         금액을 채워넣느니 "모른다"가 낫다.
      2. region이 None(priority_region_classifier.classify_priority_region()이
         판정 불가라고 한 경우 — 시/군 일부 동만 걸치는 지역)이면 status="unknown".
      3. market_price가 없으면 "최우선변제금은 주택가액의 2분의 1을 넘을 수 없다"는
         법정 상한을 적용할 수 없어 status="unknown".

    Args:
        my_deposit: 내 보증금 (원 단위)
        market_price: 시세 (원 단위 — 다른 룰들과 동일하게 이미 만원→원 변환된 값)
        active_rights: RegistrySummaryParser의 activeRights (receivedDate 필요)
        region: priority_region_classifier.classify_priority_region()의 반환값
        as_of: 진단 기준일 (기본값: 오늘)
    """
    if as_of is None:
        as_of = date_cls.today()

    reference_date = _earliest_secured_right_date(active_rights) or as_of

    if reference_date < _PRIORITY_TABLE_EFFECTIVE_DATE:
        return {
            "status": "unknown",
            "reason": (
                f"선순위 담보물권 설정일({reference_date.isoformat()})이 현재 확보한 "
                "최우선변제금 기준표(2023-02-21 시행)보다 오래돼 정확한 금액을 계산할 "
                "수 없습니다 — 확인 안 된 과거 금액을 추정하지 않습니다."
            ),
        }

    if region is None:
        return {
            "status": "unknown",
            "reason": (
                "매물 소재지가 시/군 일부 동에 따라 최우선변제금 지역 등급이 갈리는 "
                "지역이라 주소만으로는 정확히 판정할 수 없습니다."
            ),
        }

    if market_price is None:
        return {
            "status": "unknown",
            "reason": (
                "시세 데이터가 없어 '최우선변제금은 주택가액의 2분의 1을 넘을 수 없다'는 "
                "법정 상한을 적용할 수 없습니다."
            ),
        }

    table = _PRIORITY_REPAYMENT_TABLE[region]

    if my_deposit > table["maxDeposit"]:
        return {
            "status": "not_eligible",
            "eligible": False,
            "regionTier": region,
            "maxDeposit": table["maxDeposit"],
            "referenceDate": reference_date.isoformat(),
            "reason": (
                f"내 보증금({my_deposit:,}원)이 이 지역의 소액임차인 기준"
                f"({table['maxDeposit']:,}원)을 초과해 최우선변제 대상이 아닙니다."
            ),
        }

    guaranteed = min(table["claimAmount"], market_price // 2)
    capped_by_half = guaranteed < table["claimAmount"]

    reason = (
        f"소액임차인에 해당해(보증금 {my_deposit:,}원 ≤ 기준 {table['maxDeposit']:,}원), "
        f"매물이 경매로 넘어가도 최우선으로 {guaranteed:,}원을 돌려받을 수 있습니다"
    )
    if capped_by_half:
        reason += f" (법정 한도는 {table['claimAmount']:,}원이지만 주택가액의 2분의 1인 {guaranteed:,}원으로 제한됨)"
    reason += "."

    return {
        "status": "ok",
        "eligible": True,
        "regionTier": region,
        "maxDeposit": table["maxDeposit"],
        "guaranteedAmount": guaranteed,
        "cappedByHalfOfPropertyValue": capped_by_half,
        "referenceDate": reference_date.isoformat(),
        "reason": reason,
    }


def evaluate_tenancy_safety(
    market_price: int | None,
    senior_secured_amount: int,
    my_deposit: int,
    contract_landlord_name: str,
    registry_owners: list[dict],
    property_type: str = "villa",
    market_price_confidence: str = "high",
    move_in_date: str | None = None,
    active_rights: list[dict] | None = None,
    has_fixed_date: bool | None = None,
    region: str | None = None,
    as_of: date_cls | None = None,
) -> dict:
    """룰 1~5를 합쳐서 한 번에 결과를 낸다."""
    deposit_risk = check_deposit_priority_risk(
        market_price, senior_secured_amount, my_deposit, property_type, market_price_confidence
    )
    identity_check = check_landlord_identity_match(contract_landlord_name, registry_owners)
    possession_gap_risk = check_possession_priority_gap_risk(move_in_date, active_rights or [])
    fixed_date_risk = check_fixed_date_risk(has_fixed_date)
    priority_repayment = check_minimum_priority_repayment(
        my_deposit, market_price, active_rights or [], region, as_of=as_of
    )

    return {
        "depositPriorityRisk": deposit_risk,
        "landlordIdentityCheck": identity_check,
        "possessionPriorityGapRisk": possession_gap_risk,
        "fixedDateRisk": fixed_date_risk,
        "minimumPriorityRepayment": priority_repayment,
    }
