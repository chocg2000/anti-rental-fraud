"""
등기부등본 '주요 등기사항 요약 (참고용)' 페이지 파서
--------------------------------------------------------
실제 OCR 테스트로 확인된 사실: 본문(갑구/을구 전체) 페이지는 위변조 방지 배경무늬 때문에
Tesseract OCR 정확도가 심각하게 떨어지지만, 인터넷등기소가 마지막 페이지에 제공하는
"주요 등기사항 요약" 페이지는 배경무늬가 거의 없어 OCR 품질이 훨씬 좋다.

트레이드오프: 이 요약 페이지는 "현재 유효한(말소되지 않은)" 권리만 보여주고
소유권 이전 이력은 안 보여준다. 그래서:
  - LTV 계산에 필요한 "근저당권+전세권 잔존 채무 합계"는 이 페이지만으로 충분하고,
    오히려 말소 판별 로직을 우리가 직접 짤 필요가 없어진다 (법원 시스템이 이미 걸러줌).
  - 3.3절 "신축빌라+소유주 변경" 같은 이력 기반 룰은 이 페이지로는 판별 불가 —
    본문 갑구가 필요한 별도 과제로 분리한다.

실제 검증된 원본 OCR 텍스트 예시 (2026-09-12, 경기 성남시 분당구 야탑동 335 장미마을 822동 204호):

    1. 소유지분현황 ( 갑구 )
    조춘근 (소유자) | 670209-1788617 | 단독소유    경기도 성남시 분당구 장미로 101, 822동            5
    204호(야탑동, 장미마을)
    2. 소유지분을 제외한 소유권에 관한 사항 ( 갑구 )
    - 기록사항 없음
    3. (근)저당권 및 전세권 등 ( 을구 )
    11    전세권설정          2025년3월26일 | 전세금 _금300,000,000원                     조춘근
    제1247861호  전세권자 주식회사지음이엔지
"""

import re
from datetime import date as date_cls

_AMOUNT_PATTERN = re.compile(r'금?\s*([\d,]+)\s*원')
_OWNER_LINE_PATTERN = re.compile(
    r'([가-힣]{2,10})\s*\((?:소유자|공유자)\)\s*\|?\s*([\d\-]{6,14})\s*\|?\s*(단독소유|공유)'
)
_RANK_PATTERN = re.compile(r'^\s*(\d+(?:-\d+)?)\s')
_RIGHT_TYPE_PATTERN = re.compile(r'(근저당권설정|전세권설정)')
_NO_RECORD_PATTERN = re.compile(r'기록사항\s*없음')
_DATE_PATTERN = re.compile(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일')


def _parse_date(text: str) -> str | None:
    m = _DATE_PATTERN.search(text or "")
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return date_cls(y, mo, d).isoformat()
    except ValueError:
        return None


def parse_summary_ownership(section_text: str) -> list[dict]:
    """'1. 소유지분현황 (갑구)' 섹션에서 소유자 목록을 뽑는다."""
    if _NO_RECORD_PATTERN.search(section_text):
        return []

    owners = []
    for match in _OWNER_LINE_PATTERN.finditer(section_text):
        name, _reg_no, share_type = match.groups()
        # 주민등록번호(_reg_no)는 개인정보라 결과에 포함하지 않는다.
        owners.append({"ownerName": name, "shareType": share_type})
    return owners


def parse_summary_rights(section_text: str) -> list[dict]:
    """
    '3. (근)저당권 및 전세권 등 (을구)' 섹션에서 현재 유효한 근저당권/전세권을 뽑는다.
    이미 말소된 권리는 법원 시스템이 요약에서 제외해주므로, 여기 나온 건 전부 '유효'하다고
    간주해도 된다 (본문 페이지처럼 말소 판별 로직이 필요 없다).

    receivedDate(접수일)는 tenancy_safety_rules.check_possession_priority_gap_risk()가
    "대항력 발생 시점보다 먼저(또는 같은 날) 접수된 권리가 있는지" 판단할 때 쓴다.
    """
    if _NO_RECORD_PATTERN.search(section_text):
        return []

    rights = []
    lines = [l for l in section_text.splitlines() if l.strip()]

    for line in lines:
        type_match = _RIGHT_TYPE_PATTERN.search(line)
        if not type_match:
            continue

        rank_match = _RANK_PATTERN.search(line)
        amount_match = _AMOUNT_PATTERN.search(line)

        rights.append({
            "rank": rank_match.group(1) if rank_match else None,
            "rightType": type_match.group(1),
            "amount": int(amount_match.group(1).replace(",", "")) if amount_match else None,
            "receivedDate": _parse_date(line),
            "rawLine": line.strip(),
        })

    return rights


def parse_summary_registry(full_text: str) -> dict:
    """
    요약 페이지 전체 텍스트를 받아 섹션 1/2/3으로 나눈 뒤 각각 파싱하고 합친다.
    반환값은 데이터 모델 확장판(전세권 포함) — RiskAssessmentResult 계산에 바로 쓸 수 있다.
    """
    section1 = _extract_section(full_text, "1. 소유지분현황", "2. 소유지분을")
    section3 = _extract_section(full_text, "3. (근)저당권", "[참고사항]")

    owners = parse_summary_ownership(section1)
    rights = parse_summary_rights(section3)

    total_secured = sum(r["amount"] for r in rights if r["amount"] is not None)

    return {
        "owners": owners,
        "activeRights": rights,  # 근저당권 + 전세권 통합 리스트
        "totalSeniorSecuredAmount": total_secured,  # LTV 분자에 들어갈 값 (근저당+전세권 합계)
    }


def _extract_section(text: str, start_marker: str, end_marker: str) -> str:
    """start_marker가 등장하는 지점부터 end_marker 직전까지의 텍스트를 잘라낸다."""
    start_idx = text.find(start_marker)
    if start_idx == -1:
        return ""
    end_idx = text.find(end_marker, start_idx + len(start_marker))
    return text[start_idx: end_idx if end_idx != -1 else None]
