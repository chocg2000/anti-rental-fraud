"""
1회성 디버그 스크립트 — Step3Result의 사기 패턴 UI(헤드라인 배너 + OwnershipTimeline +
3단계 행동 가이드)를 브라우저로 눈으로 확인하기 위해, 실제 신축 건물 등기부를 구하는 대신
fraud.triggered=true 조건을 만족하는 합성 결과를 assessment_store(SQLite)에 직접 심는다.

실제 파이프라인(run_full_assessment)을 거치지 않는 이유: 이 조건(사용승인 1년 이내 +
최근 소유권 변경)을 실제로 만족하는 신축 건물 등기부를 지금 당장 구하기 어렵고, 이건
UI 렌더링만 확인하면 되는 목적이라 화면에 필요한 형태의 데이터만 있으면 충분하다.

경고 색상(warning vs danger)을 둘 다 확인할 수 있도록 시나리오 2개를 심는다.

실행: python debug_seed_fraud_ui_demo.py
그 다음 브라우저에서 (uvicorn + vite 둘 다 떠있는 상태로):
  http://localhost:5173/result/demo-fraud-warning
  http://localhost:5173/result/demo-fraud-danger
"""

from assessment_store import save_assessment

FRAUD_RESULT = {
    "triggered": True,
    "reason": "신축(사용승인 20260201)이면서 2026-07-01에 소유권이 변경됨 — 신축빌라 명의이전 사기 패턴 의심",
    "isNewBuilding": True,
    "isRecentOwnershipChange": True,
    "ownershipHistory": [
        {"date": "2026-02-15", "ownerName": "한빛개발㈜"},
        {"date": "2026-07-01", "ownerName": "김바지"},
    ],
    "latestTransferDate": "2026-07-01",
}

BASE_TENANCY_SAFETY = {
    "depositPriorityRisk": {
        "riskyDepositPriority": False,
        "reason": "선순위채권 + 보증금이 시세의 안전 임계값 이내입니다.",
    },
    "landlordIdentityCheck": {
        "match": True,
        "riskLevel": "safe",
        "reason": "계약서 임대인과 등기부 소유자가 일치합니다.",
    },
    "possessionPriorityGapRisk": {
        "gapRiskDetected": False,
        "reason": "잔금(입주)일 당일 접수된 권리가 발견되지 않았습니다.",
        "moveInDate": "2026-08-15",
        "rightsTimeline": [],
    },
    "fixedDateRisk": {
        "riskLevel": "caution",
        "reason": "확정일자가 아직 없습니다 — 계약 체결 후 바로 받으세요.",
    },
    "minimumPriorityRepayment": {
        "status": "not_eligible",
        "reason": "내 보증금이 이 지역의 소액임차인 기준을 초과해 최우선변제 대상이 아닙니다.",
        "guaranteedAmount": None,
    },
}

BASE_PROPERTY_INFO = {
    "normalizedAddress": {"roadAddress": "경기 성남시 분당구 판교로 123"},
    "marketPrice": 25_000,  # 만원 단위 = 2억5천만원
    "marketPriceConfidence": "high",
    "marketPriceBasis": "인근 신축 빌라 실거래가 기준 추정",
    "building": {"useApprovalDate": "20260201"},
    "nonResidentialUseRisk": False,
    "violationStatusConfirmed": False,
    "violationStatusRaw": None,
    "sourceStatuses": {"transactionPrice": "ok", "buildingRegister": "ok"},
}


def make(overall_grade: str, violation: bool) -> dict:
    property_info = {**BASE_PROPERTY_INFO}
    reasons = [FRAUD_RESULT["reason"]]
    if violation:
        property_info = {
            **BASE_PROPERTY_INFO,
            "violationStatusConfirmed": True,
            "violationStatusRaw": "사용자 자가확인 — 위반건축물",
        }
        reasons = ["위반건축물로 확인됨 (사용자 자가확인 — 위반건축물)"] + reasons

    return {
        "overallGrade": overall_grade,
        "reasons": reasons,
        "propertyInfo": property_info,
        "tenancySafety": BASE_TENANCY_SAFETY,
        "fraudPatternResult": FRAUD_RESULT,
        "taxClearanceResult": None,
    }


def main():
    warning_id = "demo-fraud-warning"
    danger_id = "demo-fraud-danger"

    save_assessment(warning_id, {"id": warning_id, **make("warning", violation=False)})
    save_assessment(danger_id, {"id": danger_id, **make("danger", violation=True)})

    print("done")
    print(f"http://localhost:5173/result/{warning_id}")
    print(f"http://localhost:5173/result/{danger_id}")


if __name__ == "__main__":
    main()
