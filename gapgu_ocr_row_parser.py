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
     5개 컬럼으로 나눈다.

✅ 갑구(2026-09-15~16)/을구(2026-09-16) 모두 실제 클로바 OCR 응답으로 검증 완료
(README "클로바 OCR 실키 검증"/"을구 실키 검증" 섹션 참고). 을구 검증 과정에서
실제 버그 3개(여러 줄에 걸친 말소 등기목적 병합 누락, 한 줄에 순위번호 2개를 말소하는
케이스, y좌표 anchor 고정 방식의 그룹핑 결함)와 위험한 시나리오 1개(페이지 하단 법적
고지문이 데이터 행에 섞여 들어가 유효한 권리를 말소된 것으로 오판할 뻔함)를 찾아
고쳤다 — 이 모듈이 원래 걱정했던 "컬럼을 잘못 나누면 최악의 경우 판별 불가로 떨어질
뿐"이라는 가정과 달리, 실제로는 "잘못된 확신"(거짓 안심 또는 거짓 위험)으로 이어질
수 있는 경로가 있었다는 뜻 — 새 실키 데이터로 검증할 때마다 이 가능성을 계속 의심할 것.
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

# 대법원 인터넷등기소가 모든 페이지 하단에 찍는 고정 법적 고지문/발급 정보 — 등기부
# 본문과 무관하지만 "말소", 순위번호(예: "11번 등기는 건물만에 관한 것임")를 그대로
# 포함하고 있어, 마지막 데이터 행에 그대로 병합되면 위험하다(2026-09-16 을구 실키
# 검증으로 발견: "실선으로 그어진 부분은 말소사항을 표시함"의 "말소"가 직전 순위번호
# "11번"과 합쳐져, 실제로는 유효한 11번 전세권이 말소된 것으로 잘못 판정될 뻔했다).
# _group_lines_into_rows()가 이 줄들을 아예 행에 편입시키지 않도록 미리 걸러낸다.
_FOOTER_NOISE_MARKERS = [
    "관할등기소", "이 증명서는", "발행번호", "발급확인번호", "수수료",
    "실선으로 그어진", "인터넷등기소", "전산운영책임관", "법원행정처",
    "기록사항 없는 갑구", "컬러 또는 흑백", "인터넷 발급",
    "서기 ", "이 하 여", "이하여백",
]
_PAGE_NUMBER_LINE_PATTERN = re.compile(r'^\s*\d+\s*/\s*\d+\s*$')


def _is_footer_noise_line(line: str) -> bool:
    if _PAGE_NUMBER_LINE_PATTERN.match(line):
        return True
    return any(marker in line for marker in _FOOTER_NOISE_MARKERS)


_RECEIPT_NO_PATTERN = re.compile(r'제\s*\d+\s*호')


def reconstruct_lines_from_clova_result(clova_response: dict, y_threshold: float = 30.0) -> list[str]:
    """
    클로바 General OCR(V2) 응답의 images[0].fields를 좌표 기준으로 재조합해서
    위→아래, 왼쪽→오른쪽 순서의 텍스트 줄 리스트로 만든다.

    같은 "행"으로 볼 조각들은 y 오름차순으로 훑을 때 직전 조각과의 y차가 y_threshold
    이내로 계속 이어지는 것들이다("연쇄 간격" 클러스터링 — 조각 A/B가 붙고 B/C가
    붙으면 A와 C의 y차가 threshold를 넘어도 한 행으로 묶인다). 행 안에서는 x좌표
    오름차순으로 정렬해 공백으로 이어붙인다.

    2026-09-16 을구 실키 검증(등기부등본_내아파트.pdf)에서 이전 방식(그 행에서 가장
    먼저 들어온 조각 "하나"를 고정 anchor로 삼아 나머지를 그것과만 비교)의 실제 결함을
    발견해 지금의 방식으로 바꿨다: 한 행 안에서도 컬럼마다(순위번호/등기목적/권리자
    등) 텍스트 기준선이 조금씩 어긋나다 보니, 정렬 순서상 anchor가 된 조각(가장 작은
    y)이 하필 그 행의 반대쪽 끝 컬럼이면 다른 쪽 끝 컬럼과의 거리가 실제 행 높이만큼
    벌어진다 — 이 문서에서 "채권최고액 금138,000,000원"(y=3125, 상세란)이 anchor가
    되고 순위번호 "5"(y=3158, 순위번호란)까지는 33px라 30px 임계값을 근소하게
    넘겨버려 "5"가 완전히 다른 행으로 떨어져 나갔다. 연쇄 간격 방식이면 "5"는 직전
    조각("근저당권설정", y=3139)과 19px 차이라 자연스럽게 같은 행에 붙는다.

    y_threshold=30.0(2026-09-15, "1"+"(전 1)"처럼 두 줄로 쪼개진 행 사례로 12.0→30.0
    조정 — 아래 테스트 참고): 실제 문서의 "행 내부 조각 간 간격"은 최대 84px 안쪽이고
    "서로 다른 행 사이 간격"은 최소 84px 이상이라, 30px로는 같은 행 내부는 다 이어
    붙이면서도 다른 행끼리 잘못 합쳐질 위험은 없다.
    ⚠️ 부작용: 표제부(토지의 표시)처럼 갑구/을구와 무관한 표가 같은 이미지에 같이
    찍혀 있으면, 그 표의 "표시번호"(1, 2, 3...) 칸도 순위번호처럼 보여 노이즈 행이
    같이 뽑힌다 — 다만 이 노이즈 행은 purpose가 항상 빈 문자열이라
    registry_parser.parse_gapgu()가 "소유권보존"/"소유권이전" 키워드 매칭에서 자동으로
    걸러내므로 결과에 영향은 없다(직접 확인함). 실사용 대상인 아파트 갑구는 보통
    표제부와 별도 페이지라 이 노이즈 자체가 거의 발생하지 않을 것으로 예상.

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

    # y 오름차순으로 정렬된 순서를 그대로 훑으면서, 직전 조각과의 y차가 y_threshold를
    # 넘을 때만 새 행을 연다("연쇄 간격" 클러스터링). 조각 하나짜리 행도 자연히 처리된다.
    rows: list[list[tuple]] = []
    prev_y: float | None = None
    for top_y, left_x, text in fragments:
        if prev_y is not None and (top_y - prev_y) <= y_threshold:
            rows[-1].append((top_y, left_x, text))
        else:
            rows.append([(top_y, left_x, text)])
        prev_y = top_y

    lines = []
    for row in rows:
        row.sort(key=lambda t: t[1])
        lines.append(" ".join(t[2] for t in row))
    return lines


def split_line_into_row(line: str) -> dict | None:
    """
    재조합된 한 줄을 rank/purpose/receipt/cause/detail로 나눈다(실키 검증 완료 —
    모듈 docstring 참고). 줄 맨 앞에 순위번호(숫자, 부기등기는 "3-1" 형태)가 없으면
    표의 데이터 행이 아니라고 보고 None을 반환한다(예: 섹션 제목, 페이지 머리말 등
    잡음 줄 제외).

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
                # 어휘 단어 앞에 "1번" 같은 순위번호 참조가 붙어있으면(예: 여러 줄에 걸친
                # 말소 기록의 첫 줄 "1번근저당권설정,") 그 접두어까지 purpose에 포함한다
                # — 어휘만 뽑아버리면 뒤 줄(detail로 이어붙는 "2번...등기말소")과 합쳐도
                # "1번" 자체는 영영 사라져 registry_parser의 다중 순위번호 말소 판별이
                # 그 번호를 놓친다(2026-09-16 을구 실키 검증으로 발견).
                purpose_end = idx + len(kw)
                purpose = rest[:purpose_end].strip()
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


def _group_lines_into_rows(lines: list[str]) -> list[dict]:
    """
    한 표 행이 등기목적/기타사항이 길어 물리적으로 여러 줄에 걸쳐 찍힌 경우를 처리한다.

    순위번호(_RANK_PATTERN)로 시작하는 줄만 split_line_into_row()로 분할해 그 행의
    rank/purpose/receipt/cause를 확정하고, 다음 순위번호 줄이 나오기 전까지 이어지는
    나머지 줄들은 전부 detail 뒤에 그대로 이어붙인다("첫 줄만 컬럼 분할, 나머지는
    detail로" 방식).

    2026-09-16 실키 검증(등기부등본_내아파트.pdf) 중 처음에는 "관련 줄을 전부 하나로
    합친 뒤 split_line_into_row()를 한 번만 호출"하는 방식을 썼었는데, 그러면 등기목적이
    여러 줄에 걸친 행에서 순위번호 뒤 "제N호" 접수번호가 실제보다 훨씬 뒤쪽에서 나타나
    receipt/cause/detail 경계가 밀리는 실제 버그가 있었다 — "소유자 OOO"나 "채권최고액
    금...원"이 detail이 아니라 receipt에 남거나, "전산이기" 같은 등기부 하단의 무관한
    날짜가 cause로 잘못 뽑혔다. 첫 줄만 분할하면 원래 컬럼 순서(첫 줄 안에서의 receipt→
    cause→detail 순서)를 그대로 신뢰할 수 있어 이 문제가 사라진다.

    대신 "1번근저당권설정, 2번근저당권설정등기말소"처럼 말소 기록이 여러 줄에 걸치는
    경우(을구 실키 검증으로 처음 발견한 문제 — 좁은 칸 때문에 "3 1번근저당권설정, ..." /
    "2번근저당권설정 제21825호 해지" / "등기말소" 세 줄로 찢어져 나온다)는, "말소"와
    나머지 순위번호가 이제 detail 쪽에 남게 되므로 registry_parser.py의 말소 판별
    로직(_find_canceled_ranks, is_cancellation_entry)이 purpose뿐 아니라 detail까지
    합쳐서 검사하도록 맞춰뒀다 — 그쪽에서 이 설계를 전제로 한다는 점에 주의.

    순위번호 줄이 나오기 전의 선두 줄(섹션 제목 등)과 순위번호를 인식 못 한 줄은
    애초에 데이터 행이 아니므로 버린다.
    """
    rows: list[dict] = []
    current: dict | None = None
    for line in lines:
        if _is_footer_noise_line(line):
            continue
        if _RANK_PATTERN.match(line):
            current = split_line_into_row(line)
            if current is not None:
                rows.append(current)
        elif current is not None:
            current["detail"] = f"{current['detail']} {line}".strip()
    return rows


def extract_rows_from_clova_result(clova_response: dict, y_threshold: float = 30.0) -> list[dict]:
    """
    reconstruct_lines_from_clova_result() + _group_lines_into_rows()를 이어붙인 편의
    함수. 데이터 행으로 인식되지 않은 줄(섹션 제목 등)은 조용히 걸러진다.
    """
    lines = reconstruct_lines_from_clova_result(clova_response, y_threshold=y_threshold)
    return _group_lines_into_rows(lines)
