"""
클로바 OCR 응답 → registry_parser.py가 이해하는 행(row) 형식으로 변환
--------------------------------------------------------------------------
registry_parser.py의 parse_gapgu()/parse_eulgu()는 이미 완성돼 있고 테스트도 12개
통과한 상태다(rank/purpose/receipt/cause/detail 딕셔너리 리스트를 받는다). 남은 문제는
"등기부 본문 스캔 이미지에서 그 딕셔너리를 어떻게 뽑아내는가"뿐이다.

이 모듈은 그 변환을 두 단계로 나눈다:
  1. reconstruct_lines_from_clova_result() — 클로바가 돌려주는 개별 텍스트 조각
     (inferText + 좌표)을 위→아래, 왼쪽→오른쪽 순서의 "줄" 문자열로 재조합한다.
     순수 기하학적 계산이라 실제 키 없이도 완전히 검증 가능하다(신뢰도 높음).
  2. split_line_into_row() — 재조합된 한 줄을 rank/purpose/receipt/cause/detail
     5개 컬럼으로 나눈다. 이건 ⚠️ 미검증이다 — 실제 클로바 OCR 결과를 한 번도 못 봤고,
     등기부 본문의 실제 줄바꿈/공백 패턴을 알지 못한 채 예상되는 형식(순위번호 →
     등기목적 → "YYYY년M월D일 제N호" 접수 → "YYYY년M월D일 원인설명" 등기원인 →
     나머지 권리자/기타사항)을 가정해 짰다. 실제 Secret Key가 생기면
     debug_clova_ocr_call.py로 진짜 응답을 받아 이 함수부터 다시 검증할 것.

    이 불확실성이 위험한 이유가 상대적으로 작은 이유: 컬럼을 잘못 나눠도 최악의 경우
    "소유권 이전 이력을 못 찾음"(판별 불가)으로 떨어질 뿐, fraud_pattern_rules.py가
    이미 그 경우를 "패턴 미해당"이 아니라 "판별 불가"로 명확히 구분해서 처리한다
    (거짓 안심이 아니라 거짓 음성 — 이 프로젝트가 절대 피하려는 "확인 안 된 걸 안전하다고
    말하기"보다는 훨씬 덜 위험하다).
"""

import re

# registry_parser.py의 _CANCEL_REF_PATTERN과 정확히 동일한 패턴 — 두 모듈이 어긋나면
# 안 되므로 값이 바뀌면 양쪽 다 같이 고칠 것.
_CANCEL_REF_PATTERN = re.compile(r'(\d+)\s*번[^말]*말소')

# 갑구/을구에서 실제로 등장하는 등기목적 어휘 — registry_parser.py의 키워드 상수와
# 겹치는 부분은 그대로 재사용해 일관성을 유지한다.
_PURPOSE_VOCABULARY = [
    "소유권보존", "소유권이전청구권가등기", "소유권이전", "근저당권설정", "전세권설정",
    "가압류", "압류", "가등기", "가처분", "경매개시결정", "임차권등기명령",
]

_RANK_PATTERN = re.compile(r'^\s*(\d+(?:-\d+)?)\s')
_DATE_PATTERN = re.compile(r'\d{4}년\s*\d{1,2}월\s*\d{1,2}일')
_RECEIPT_NO_PATTERN = re.compile(r'제\s*\d+\s*호')


def reconstruct_lines_from_clova_result(clova_response: dict, y_threshold: float = 12.0) -> list[str]:
    """
    클로바 General OCR(V2) 응답의 images[0].fields를 좌표 기준으로 재조합해서
    위→아래, 왼쪽→오른쪽 순서의 텍스트 줄 리스트로 만든다.

    같은 "행"으로 볼 조각들은 상단 y좌표 차이가 y_threshold 이내인 것들이다 — 스캔이
    약간 기울어져도 흡수하기 위한 여유값. 행 안에서는 x좌표 오름차순으로 정렬해
    공백으로 이어붙인다.

    Args:
        clova_response: fetch_ocr_result()가 돌려준 {"status": "ok", "data": ...}의
            "data" 값(클로바 원본 응답 dict) — 이 함수는 data를 그대로 받는다.
        y_threshold: 같은 행으로 묶을 y좌표 오차 허용 범위(픽셀 단위, 클로바 좌표계 기준)
    """
    images = clova_response.get("images") or []
    if not images:
        return []

    fields = images[0].get("fields") or []
    fragments = []
    for field in fields:
        text = (field.get("inferText") or "").strip()
        vertices = ((field.get("boundingPoly") or {}).get("vertices")) or []
        if not text or not vertices:
            continue
        top_y = min(v.get("y", 0) for v in vertices)
        left_x = min(v.get("x", 0) for v in vertices)
        fragments.append((top_y, left_x, text))

    if not fragments:
        return []

    fragments.sort(key=lambda t: (t[0], t[1]))

    rows: list[list[tuple]] = []
    for top_y, left_x, text in fragments:
        for row in rows:
            if abs(top_y - row[0][0]) <= y_threshold:
                row.append((top_y, left_x, text))
                break
        else:
            rows.append([(top_y, left_x, text)])

    rows.sort(key=lambda row: row[0][0])

    lines = []
    for row in rows:
        row.sort(key=lambda t: t[1])
        lines.append(" ".join(t[2] for t in row))
    return lines


def split_line_into_row(line: str) -> dict | None:
    """
    ⚠️ 미검증 — 모듈 docstring 참고. 재조합된 한 줄을 rank/purpose/receipt/cause/detail
    로 나눈다. 줄 맨 앞에 순위번호(숫자, 부기등기는 "3-1" 형태)가 없으면 표의 데이터
    행이 아니라고 보고 None을 반환한다(예: 섹션 제목, 페이지 머리말 등 잡음 줄 제외).

    Returns:
        {"rank": ..., "purpose": ..., "receipt": ..., "cause": ..., "detail": ...}
        registry_parser.parse_gapgu()/parse_eulgu()에 바로 넣을 수 있는 형식.
        데이터 행처럼 보이지 않으면 None.
    """
    rank_match = _RANK_PATTERN.match(line)
    if not rank_match:
        return None
    rank = rank_match.group(1)
    rest = line[rank_match.end():]

    purpose = None
    purpose_end = 0

    # 말소 기록("3번가압류등기말소")은 registry_parser._CANCEL_REF_PATTERN이 purpose
    # 필드 전체에서 "N번...말소" 패턴을 찾아 판별한다 — 어휘 매칭으로 "가압류"만 뽑아버리면
    # "말소"가 잘려나가 이 판별이 깨진다. 그래서 말소 패턴을 어휘 매칭보다 먼저 확인한다.
    cancel_match = _CANCEL_REF_PATTERN.search(rest)
    if cancel_match:
        purpose = rest[:cancel_match.end()].strip()
        purpose_end = cancel_match.end()

    if purpose is None:
        for kw in _PURPOSE_VOCABULARY:
            idx = rest.find(kw)
            if idx != -1:
                purpose = kw
                purpose_end = idx + len(kw)
                break

    if purpose is None:
        # 어휘에도, 말소 패턴에도 안 걸리는 등기목적 — 완전히 포기하지 않는다.
        # 접수번호나 날짜가 나오기 전까지를 통째로 purpose로 본다.
        receipt_no_match = _RECEIPT_NO_PATTERN.search(rest)
        date_match = _DATE_PATTERN.search(rest)
        boundary = min(
            (m.start() for m in (receipt_no_match, date_match) if m),
            default=len(rest),
        )
        purpose = rest[:boundary].strip()
        purpose_end = boundary

    after_purpose = rest[purpose_end:]

    dates = list(_DATE_PATTERN.finditer(after_purpose))
    receipt_no_match = _RECEIPT_NO_PATTERN.search(after_purpose)

    if dates and receipt_no_match and receipt_no_match.start() >= dates[0].start():
        receipt_end = receipt_no_match.end()
        receipt = after_purpose[:receipt_end].strip()
    elif dates:
        receipt_end = dates[0].end()
        receipt = after_purpose[:receipt_end].strip()
    else:
        receipt_end = 0
        receipt = ""

    remainder = after_purpose[receipt_end:]
    remaining_dates = list(_DATE_PATTERN.finditer(remainder))
    if remaining_dates:
        # 등기원인 칸은 "두 번째 날짜" 자체만 뽑는다(주변 설명 문구까지 정확히 어디서
        # 끝나는지는 실제 샘플 없이는 알 수 없다) — 대신 그 앞뒤 나머지 텍스트는 전부
        # detail로 넘긴다. detail에서 소유자 이름(_OWNER_PATTERN)을 찾아야 하므로,
        # 애매한 텍스트는 cause보다 detail 쪽에 남기는 게 더 안전하다.
        m = remaining_dates[0]
        cause = m.group()
        detail = (remainder[:m.start()] + " " + remainder[m.end():]).strip()
    else:
        cause = ""
        detail = remainder.strip()

    return {
        "rank": rank,
        "purpose": purpose,
        "receipt": receipt,
        "cause": cause,
        "detail": detail,
    }


def extract_rows_from_clova_result(clova_response: dict, y_threshold: float = 12.0) -> list[dict]:
    """
    reconstruct_lines_from_clova_result() + split_line_into_row()를 이어붙인 편의 함수.
    데이터 행으로 인식되지 않은 줄(섹션 제목 등)은 조용히 걸러진다.
    """
    lines = reconstruct_lines_from_clova_result(clova_response, y_threshold=y_threshold)
    rows = []
    for line in lines:
        row = split_line_into_row(line)
        if row is not None:
            rows.append(row)
    return rows
