"""
국세·지방세 완납증명서 체크 룰
----------------------------------
당초 아이디어는 "완납증명서를 파싱해서 체납액을 선순위 채권에 합산"하는 것이었지만,
완납증명서는 애초에 "완납했다/안 했다"만 증명하는 서류라 체납액 숫자 자체가 안 담겨있다
(체납이 있으면 애초에 이 서류가 발급되지 않는다). 그래서 체납액 합산 로직은 원본 서류에
없는 데이터를 만들어내는 셈이라 구현 불가능하고, 대신 세 가지만 확인하는 게 현실적이다:

  1. 제출 여부 (True/False) — 실무상 계약 당일 중개사가 임대인을 데리고 발급받으러 가므로,
     제출 안 됐다는 것 자체가 이례적인 위험 신호다.
  2. 서류상 명의와 계약서 임대인 이름 일치 여부
  3. 발급일이 계약 시점 기준으로 충분히 최신인지 (완납증명서는 발급 시점 스냅샷이라
     오래된 서류는 그 사이 체납이 생겼어도 알 수 없다)
"""

from datetime import date

_GRADE_RANK = {"safe": 0, "caution": 1, "warning": 2, "danger": 3}


def _max_grade(a: str, b: str) -> str:
    return a if _GRADE_RANK[a] >= _GRADE_RANK[b] else b


def check_tax_clearance_certificate(
    submitted: bool,
    document_landlord_name: str | None = None,
    contract_landlord_name: str | None = None,
    issue_date: str | None = None,
    as_of: date | None = None,
    max_valid_days: int = 30,
) -> dict:
    """
    Args:
        submitted: 국세완납증명서 + 지방세완납증명서가 (둘 다) 제출됐는지
        document_landlord_name: 증명서에 적힌 명의자 이름
        contract_landlord_name: 임대차 계약서상 임대인 이름
        issue_date: 증명서 발급일 ("YYYY-MM-DD")
        as_of: 계약(판단) 기준일 — 기본값 오늘
        max_valid_days: 발급일로부터 이 기간(일)이 지나면 "최신 아님"으로 간주 (기본 30일)
    """
    if not submitted:
        return {
            "submitted": False,
            "riskLevel": "warning",
            "reason": (
                "국세·지방세 완납증명서가 제출되지 않았습니다. "
                "계약 전 임대인에게 반드시 요청하세요 (통상 계약 당일 중개사가 임대인과 "
                "함께 발급받는 서류입니다 — 없다는 것 자체가 이례적인 신호일 수 있습니다)."
            ),
        }

    risk = "safe"
    reasons = []

    if document_landlord_name and contract_landlord_name:
        if document_landlord_name.strip() != contract_landlord_name.strip():
            risk = _max_grade(risk, "danger")
            reasons.append(
                f"완납증명서 명의('{document_landlord_name}')가 "
                f"계약서 임대인('{contract_landlord_name}')과 다릅니다."
            )

    if issue_date:
        try:
            issued = date.fromisoformat(issue_date)
        except ValueError:
            issued = None

        if issued is not None:
            reference = as_of or date.today()
            age_days = (reference - issued).days
            if age_days > max_valid_days:
                risk = _max_grade(risk, "caution")
                reasons.append(
                    f"완납증명서 발급일({issue_date})로부터 {age_days}일이 지나 "
                    "최신 상태가 아닐 수 있습니다 — 재발급을 요청하세요."
                )

    if not reasons:
        reasons.append("완납증명서가 제출됐고 명의·발급일에 특이사항이 없습니다.")

    return {"submitted": True, "riskLevel": risk, "reason": " ".join(reasons)}
