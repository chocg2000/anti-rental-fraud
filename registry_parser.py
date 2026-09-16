"""
등기부등본 파서 (Registry Parser)
------------------------------------
설계 문서 2.2절/3.2절 규칙을 코드로 구현한다.

핵심 설계 원칙: "PDF에서 표를 뽑아내는 것"과 "뽑아낸 표에서 위험 신호를 판별하는 것"을
분리한다. 후자(parse_registry_rows)는 순수 함수라 실제 PDF 없이도 완전히 테스트할 수 있고,
전자(extract_registry_rows_from_pdf)만 나중에 실제 PDF로 검증하면 된다.
지금까지 API 3개를 다 이 순서(로직 먼저 → 실제 데이터로 검증)로 만들어서 효과를 봤다.

행(row) 데이터 형식 — 갑구/을구 공통:
{
    "rank": "3" 또는 "3-1" (순위번호, 부기등기는 하이픈),
    "purpose": "가압류" 또는 "3번가압류등기말소" 등 (등기목적),
    "receipt": "2020년1월10일 제11111호" (접수),
    "cause": "2020년1월5일 서울중앙지방법원의 가압류결정(2020카단1234)" (등기원인),
    "detail": "청구금액 금50,000,000원 채권자 ..." (권리자 및 기타사항),
}
"""

import re
from datetime import date as date_cls

# ---- 3.2절: 갑구/을구 치명적 키워드 ----
CRITICAL_KEYWORDS_GAPGU = ["가압류", "압류", "가등기", "가처분", "경매개시결정"]
TRUST_KEYWORD = "신탁"
CRITICAL_KEYWORD_EULGU = "임차권등기명령"

# "3번가압류등기말소", "1번근저당권설정등기말소" 같은 표현에서 취소 대상 순위번호를 뽑는다.
_CANCEL_REF_PATTERN = re.compile(r'(\d+)\s*번[^말]*말소')
_RANK_REF_PATTERN = re.compile(r'(\d+)\s*번')
_MALSO_KEYWORD = "말소"
_AMOUNT_PATTERN = re.compile(r'채권최고액\s*금?\s*([\d,]+)\s*원')
_OWNER_PATTERN = re.compile(r'소유자\s+([가-힣A-Za-z0-9]+)')
_DATE_PATTERN = re.compile(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일')

_MORTGAGE_DEBT_RATIO = 1.2  # 등기부 을구 근저당권은 보통 실채무의 120%가 설정된다는 실무 관행


def _rank_base(rank: str) -> str:
    """'3-1' -> '3' (부기등기는 주등기 순위번호 기준으로 말소 여부를 판단)"""
    return str(rank).split("-")[0]


def _find_canceled_ranks(rows: list[dict]) -> set[str]:
    """
    이 섹션(갑구 또는 을구) 안에서 말소 대상으로 참조된 순위번호 집합을 찾는다.

    "1번근저당권설정, 2번근저당권설정등기말소"처럼 한 행이 여러 순위번호를 한꺼번에
    말소하는 실제 사례(2026-09-16 을구 실키 검증으로 발견 — 국토부 제공 공식 샘플
    등기부 자체에 이 패턴이 있었다)가 있다. `_CANCEL_REF_PATTERN.search()`는 첫 번째
    "N번"만 캡처하고 그 뒤 "[^말]*말소"가 이미 그 첫 매치 안에서 소비돼버려 두 번째
    이후 순위번호는 영영 못 찾는다 — 이러면 이미 말소된 근저당이 여전히 유효한 것으로
    잘못 합산돼 위험도를 실제보다 과대평가하게 된다. 그래서 "말소" 키워드 앞부분
    전체에서 "N번" 참조를 전부 훑는다.

    purpose뿐 아니라 detail까지 합쳐서 검사한다 — gapgu_ocr_row_parser._group_lines_
    into_rows()는 순위번호로 시작하는 첫 줄만 컬럼을 분할하고 그 다음에 이어지는
    줄(예: "2번근저당권설정 제999호 해지", "등기말소")은 전부 detail에 이어붙이는
    설계라, 말소 참조가 여러 줄에 걸친 경우 "말소"와 뒤쪽 순위번호가 purpose가 아니라
    detail 쪽에 남기 때문이다.
    """
    canceled = set()
    for row in rows:
        purpose = row.get("purpose", "") or ""
        detail = row.get("detail", "") or ""
        combined = f"{purpose} {detail}"
        idx = combined.find(_MALSO_KEYWORD)
        if idx == -1:
            continue
        canceled.update(_RANK_REF_PATTERN.findall(combined[:idx]))
    return canceled


def _parse_date(text: str) -> str | None:
    m = _DATE_PATTERN.search(text or "")
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    try:
        return date_cls(y, mo, d).isoformat()
    except ValueError:
        return None


def parse_gapgu(rows: list[dict]) -> dict:
    """
    갑구 행 리스트에서 치명적 키워드, 신탁 여부, 소유권 이전 이력을 뽑는다.
    말소된 항목은 키워드 검출 대상에서 제외한다 (해결된 사안까지 위험으로 잡으면 안 됨).
    """
    canceled_ranks = _find_canceled_ranks(rows)
    keywords_found: list[str] = []
    ownership_history: list[dict] = []
    trust_registered = False

    for row in rows:
        purpose = row.get("purpose", "") or ""
        receipt = row.get("receipt", "") or ""
        detail = row.get("detail", "") or ""
        combined = f"{purpose} {detail}"
        is_canceled = _rank_base(row.get("rank", "")) in canceled_ranks
        # "2번가압류등기말소"처럼 말소를 기록하는 행 자체의 텍스트에도 '가압류' 같은 단어가
        # 포함돼 있어 그 자체가 새 위험 신호로 오탐지될 수 있으므로, 말소 기록 행 자체는 제외한다.
        # purpose+detail 전체를 본다 — 여러 줄에 걸친 말소 참조는 detail에 남을 수 있다
        # (_find_canceled_ranks 주석 참고).
        is_cancellation_entry = bool(_CANCEL_REF_PATTERN.search(combined))

        if not is_canceled and not is_cancellation_entry:
            for kw in CRITICAL_KEYWORDS_GAPGU:
                if kw in combined and kw not in keywords_found:
                    keywords_found.append(kw)
            if TRUST_KEYWORD in combined:
                trust_registered = True

        # "공유자전원지분전부이전"(공유지분을 한 명이 전부 사들여 단독소유가 되는 경우)도
        # 소유권 이전 이력에 포함해야 한다 — 실제 클로바 OCR로 확인해보니(2026-09-16,
        # registry_gapgu_ocr.py 실키 검증) 등기목적 칸이 좁아 "...지분전부" / "이전"으로
        # 두 줄에 걸쳐 찍히는 문서가 있고, "이전"이 있는 둘째 줄은 순위번호가 없어
        # gapgu_ocr_row_parser가 노이즈로 걸러버려 purpose에 "지분전부"까지만 남는다.
        # "소유권이전" 문자열 매칭만으로는 이 케이스를 놓쳐서 최근 소유주 변경 자체가
        # 통째로 빠지는 실제 버그였다 — "지분전부"만으로도 매칭하도록 넓힘.
        if "소유권보존" in purpose or "소유권이전" in purpose or "지분전부" in purpose:
            # "소유자 OOO"가 항상 detail에만 있는 게 아니다 — 실키 검증(2026-09-16)으로
            # 확인: 등기목적이 물리적으로 여러 줄에 걸쳐 찍힌 행에서
            # gapgu_ocr_row_parser._group_lines_into_row_blocks()가 그 줄들을 합치면,
            # "접수번호(제N호)"가 원래보다 뒤에서 나타나면서 split_line_into_row()의
            # receipt/detail 경계가 밀려 "소유자 OOO"가 receipt 쪽에 남는 실제 사례가
            # 있다. 어느 칸에 있든 놓치지 않도록 둘 다 합쳐서 찾는다.
            owner_match = _OWNER_PATTERN.search(f"{receipt} {detail}")
            date_str = _parse_date(row.get("cause", "")) or _parse_date(receipt)
            if owner_match:
                ownership_history.append({"date": date_str, "ownerName": owner_match.group(1)})

    return {
        "criticalKeywords": keywords_found,
        "ownershipHistory": ownership_history,
        "trustRegistered": trust_registered,
    }


def parse_eulgu(rows: list[dict]) -> dict:
    """
    을구 행 리스트에서 임차권등기명령 이력, 근저당권 채권최고액 합계(말소 제외,
    공동담보 중복합산 방지)를 뽑는다.
    """
    canceled_ranks = _find_canceled_ranks(rows)
    keywords_found: list[str] = []
    amounts: list[int] = []
    joint_collateral_detected = False
    seen_joint_amounts: set[int] = set()

    for row in rows:
        purpose = row.get("purpose", "") or ""
        receipt = row.get("receipt", "") or ""
        detail = row.get("detail", "") or ""
        combined = f"{purpose} {detail}"
        # "채권최고액 금...원"이 항상 detail에만 있는 게 아니다 — parse_gapgu()의 소유자
        # 이름과 같은 이유(여러 줄에 걸친 등기목적이 병합되면서 receipt/detail 경계가
        # 밀리는 실키 케이스, 2026-09-16 검증)로 receipt 쪽에 남을 수 있다.
        receipt_and_detail = f"{receipt} {detail}"
        is_canceled = _rank_base(row.get("rank", "")) in canceled_ranks
        # purpose+detail 전체를 본다 — 여러 줄에 걸친 말소 참조는 detail에 남을 수 있다
        # (_find_canceled_ranks 주석 참고).
        is_cancellation_entry = bool(_CANCEL_REF_PATTERN.search(combined))

        # 임차권등기명령은 과거 이력 자체가 임대인 성향 감점 신호이므로 말소 여부와 무관하게 기록.
        # 단, 말소를 기록하는 행 자체("n번임차권등기명령 말소")의 텍스트는 제외한다.
        if not is_cancellation_entry and CRITICAL_KEYWORD_EULGU in combined \
                and CRITICAL_KEYWORD_EULGU not in keywords_found:
            keywords_found.append(CRITICAL_KEYWORD_EULGU)

        if "근저당권설정" in purpose and not is_canceled and not is_cancellation_entry:
            m = _AMOUNT_PATTERN.search(receipt_and_detail)
            if not m:
                continue
            amount = int(m.group(1).replace(",", ""))

            if "공동담보" in receipt_and_detail:
                joint_collateral_detected = True
                if amount in seen_joint_amounts:
                    continue  # 동일 채권이 건물+토지에 중복 설정된 경우 1건으로만 합산
                seen_joint_amounts.add(amount)

            amounts.append(amount)

    total = sum(amounts)
    return {
        "criticalKeywords": keywords_found,
        "seniorMortgageAmount": total,
        "estimatedActualDebt": round(total / _MORTGAGE_DEBT_RATIO) if total else 0,
        "jointCollateralDetected": joint_collateral_detected,
    }


def parse_registry_rows(gapgu_rows: list[dict], eulgu_rows: list[dict]) -> dict:
    """갑구+을구 결과를 합쳐 2.2절 RegistryInfo 형태로 반환한다."""
    gap = parse_gapgu(gapgu_rows)
    eul = parse_eulgu(eulgu_rows)

    ownership_history = gap["ownershipHistory"]

    return {
        "ownerName": ownership_history[-1]["ownerName"] if ownership_history else None,
        "ownershipHistory": ownership_history,
        "seniorMortgageAmount": eul["seniorMortgageAmount"],
        "estimatedActualDebt": eul["estimatedActualDebt"],
        "criticalKeywords": gap["criticalKeywords"] + eul["criticalKeywords"],
        "trustRegistered": gap["trustRegistered"],
        "jointCollateralDetected": eul["jointCollateralDetected"],
    }


def extract_registry_rows_from_pdf(pdf_path: str) -> tuple[list[dict], list[dict]]:
    """
    ⚠️ 아직 실제 등기부등본 PDF로 검증되지 않은 부분이다.
    등기부등본 PDF는 표 형태로 되어 있어 pdfplumber의 extract_tables()로 뽑을 수 있을
    것으로 예상하지만, 실제 문서마다 셀 병합/줄바꿈 방식이 달라 컬럼 개수가 다르게
    나올 가능성이 있다. 게다가 본문 페이지가 스캔 이미지(텍스트 레이어 없음)라면
    pdfplumber는 애초에 아무것도 못 뽑는다 — registry_summary_ocr.py가 요약 페이지에
    Tesseract를 써야 했던 것과 같은 이유. 실제 PDF를 구하면 반드시 아래 순서로 먼저
    확인할 것:
      1. pdf.pages[i].extract_tables() 결과를 그대로 print해서 컬럼 구조 확인(텍스트
         레이어가 아예 없으면 빈 결과가 나올 것 — 그러면 2번 경로로 갈아탈 것)
      2. 이 함수의 row_dict 매핑(rank/purpose/receipt/cause/detail)이 실제 컬럼 순서와
         맞는지 대조 후 수정
    핵심 판별 로직(parse_registry_rows)은 이 함수의 출력 형식만 맞으면 그대로 재사용 가능.

    대안 경로 (2026-09-15 추가): 본문이 배경무늬 있는 스캔 이미지라 Tesseract/pdfplumber
    둘 다 안 되면, gapgu_ocr_row_parser.extract_rows_from_clova_result()가 네이버
    클로바 OCR(clova_ocr_adapter.py)로 같은 rank/purpose/receipt/cause/detail 형식을
    만들어낸다 — 이쪽도 아직 실제 응답으로 검증 전이지만(각 모듈 docstring 참고),
    parse_gapgu()/parse_eulgu() 자체는 두 경로 모두에서 그대로 재사용된다.
    """
    import pdfplumber  # noqa: 지연 임포트 — 실제 PDF 파싱을 쓸 때만 필요

    gapgu_rows: list[dict] = []
    eulgu_rows: list[dict] = []
    current_section = None

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if "소유권에 관한 사항" in text:
                current_section = "gap"
            elif "소유권 이외의 권리에 관한 사항" in text:
                current_section = "eul"

            for table in page.extract_tables():
                for row in table:
                    if not row or len(row) < 3:
                        continue
                    row_dict = {
                        "rank": row[0] or "",
                        "purpose": row[1] or "",
                        "receipt": row[2] if len(row) > 4 else "",
                        "cause": row[3] if len(row) > 4 else "",
                        "detail": row[-1] or "",
                    }
                    if current_section == "gap":
                        gapgu_rows.append(row_dict)
                    elif current_section == "eul":
                        eulgu_rows.append(row_dict)

    return gapgu_rows, eulgu_rows
