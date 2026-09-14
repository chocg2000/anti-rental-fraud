"""
전세사기 방지 핵심 룰 (설계문서 3.1절 LTV + 3.3절 임대인 리스크 연장)
------------------------------------------------------------------------
지금까지 만든 조각들을 실제 유저 판단에 쓰이는 두 가지 룰로 연결한다:

룰 1. 보증금보다 우선하는 선순위 채권액 계산 (을구 기반, 깡통전세 위험)
룰 2. 소유주 일치 여부 검증 (갑구 기반, 신탁/대리인/법인 사기 방지)
  + 추가: 공유자(공동소유) 케이스 — 계약서 이름이 일치해도 공유자 전원 동의가 없으면
    계약이 무효화될 수 있어 별도로 경고해야 한다.
"""

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

    return {
        "riskyDepositPriority": is_risky,
        "marketPrice": market_price,
        "safeRatio": safe_ratio,
        "safeThreshold": round(safe_threshold),
        "seniorSecuredAmount": senior_secured_amount,
        "myDeposit": my_deposit,
        "totalPriorityClaims": total_priority_claims,
        "reason": (
            f"선순위 채권({senior_secured_amount:,}원) + 내 보증금({my_deposit:,}원) = "
            f"{total_priority_claims:,}원이 시세의 {int(safe_ratio*100)}%인 "
            f"{round(safe_threshold):,}원을 {'초과' if is_risky else '초과하지 않음'}"
        ),
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


def evaluate_tenancy_safety(
    market_price: int | None,
    senior_secured_amount: int,
    my_deposit: int,
    contract_landlord_name: str,
    registry_owners: list[dict],
    property_type: str = "villa",
) -> dict:
    """룰 1 + 룰 2를 합쳐서 한 번에 결과를 낸다."""
    deposit_risk = check_deposit_priority_risk(market_price, senior_secured_amount, my_deposit, property_type)
    identity_check = check_landlord_identity_match(contract_landlord_name, registry_owners)

    return {
        "depositPriorityRisk": deposit_risk,
        "landlordIdentityCheck": identity_check,
    }
