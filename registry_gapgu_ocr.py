"""
등기부 본문(갑구+을구) OCR 파이프라인 — PDF 페이지 렌더링 → 클로바 OCR → 행 재구성 →
parse_gapgu() + parse_eulgu()
------------------------------------------------------------------------------------------
registry_summary_ocr.py가 "요약" 페이지를 tesseract로 찾아 처리하는 것과 짝을 이루는
모듈이다. 다만 요약 페이지와 달리 갑구/을구 본문은 위변조 방지 배경무늬 때문에 tesseract
정확도가 낮아서(clova_ocr_adapter.py/gapgu_ocr_row_parser.py 모듈 docstring 참고),
"요약 페이지 찾기"와 같은 방식(tesseract로 마커 텍스트를 찾아 페이지를 특정)을 여기서는
쓸 수 없다 — 실제로 이 방식을 시도해보니 배경무늬 때문에 "갑구"/"을구" 섹션 헤더 자체가
tesseract로 잘 안 잡히는 페이지가 있었다(요약 페이지만 예외적으로 배경무늬가 적어서
마커 검색이 가능했던 것).

그래서 이 모듈은 페이지를 사전에 특정하지 않는다 — 요약 페이지를 제외한 모든 페이지를
순서대로 클로바 OCR에 보내고, 어차피 parse_gapgu()가 "소유권보존"/"소유권이전" 키워드가
없는 행(표제부, 을구 등)은 자동으로 걸러내므로 결과에 영향이 없다(gapgu_ocr_row_parser.py의
"노이즈 행" 섹션 참고 — 실제로 표제부가 갑구와 같은 이미지에 섞여도 안전함을 확인한 바 있음).
등기부 PDF가 보통 5~15페이지인 걸 감안하면, 페이지 수만큼 클로바 호출이 늘어나는 비용은
새로운 판별 로직을 만드는 것보다 감당 가능한 트레이드오프라고 판단했다.
"""

from clova_ocr_adapter import CLOVA_OCR_INVOKE_URL, CLOVA_OCR_SECRET, fetch_ocr_result
from gapgu_ocr_row_parser import extract_rows_from_clova_result
from registry_parser import parse_gapgu, parse_eulgu
from registry_summary_ocr import pdf_page_count, render_pdf_page_to_png_bytes

# 클로바 OCR의 이미지 해상도 상한(8000px)에 걸리지 않도록 300 대신 200을 쓴다 — 실제로
# 300 DPI(이 PDF 기준 세로 약 10,700px)로 렌더링했다가 ERROR가 났고, 200 DPI(약 7,150px)로
# 낮춰서 해결한 실측 결과(README "클로바 OCR 실키 검증" 섹션 참고).
CLOVA_PAGE_RENDER_DPI = 200


def extract_ownership_history_from_pdf(pdf_path: str, exclude_pages: set[int] | None = None) -> dict:
    """
    exclude_pages(보통 요약 페이지 번호)를 제외한 PDF의 모든 페이지를 클로바 OCR에 돌려
    갑구 소유권 이전 이력 + 을구(근저당권/임차권등기명령) 결과를 함께 뽑는다.

    페이지를 갑구/을구로 미리 구분하지 않고 전부 같은 방식(렌더링→클로바→행 재구성)으로
    처리한 뒤, 같은 행 리스트를 parse_gapgu()와 parse_eulgu() 양쪽에 그대로 넘긴다 —
    각 함수가 자기 관심사(갑구는 "소유권보존/이전", 을구는 "근저당권설정"/"임차권등기명령")
    와 무관한 행은 이미 알아서 걸러내므로(각 모듈 실키 검증으로 확인됨) 별도 분리 로직이
    필요 없다.

    클로바 키가 없으면(로컬 개발 등) 다른 어댑터들과 같은 패턴으로 네트워크 호출 자체를
    하지 않고 바로 빈 결과를 반환한다. 특정 페이지의 클로바 호출이 실패해도(키 없음이
    아니라 개별 페이지 인식 실패 등) 그 페이지만 건너뛰고 나머지는 계속 처리한다 —
    "부분 실패 허용, 크래시 금지" 원칙.

    Returns:
        {
            "ownershipHistory": [{"date": "YYYY-MM-DD" | None, "ownerName": str}, ...],
            "eulguCriticalKeywords": [str, ...],  # 현재는 "임차권등기명령" 하나뿐
            "eulguSeniorMortgageAmount": int,  # 말소분 제외, 공동담보 중복제거된 근저당 총액(원)
            "pagesProcessed": int,   # 클로바 OCR 호출에 성공한 페이지 수
            "pagesFailed": [int, ...],  # 호출은 됐지만 실패했거나 렌더링 자체가 안 된 페이지 번호
        }
    """
    if not CLOVA_OCR_INVOKE_URL or not CLOVA_OCR_SECRET:
        return {
            "ownershipHistory": [],
            "eulguCriticalKeywords": [],
            "eulguSeniorMortgageAmount": 0,
            "pagesProcessed": 0,
            "pagesFailed": [],
        }

    exclude_pages = exclude_pages or set()
    total_pages = pdf_page_count(pdf_path)

    all_rows: list[dict] = []
    pages_processed = 0
    pages_failed: list[int] = []

    for page_num in range(1, total_pages + 1):
        if page_num in exclude_pages:
            continue

        png_bytes = render_pdf_page_to_png_bytes(pdf_path, page_num, dpi=CLOVA_PAGE_RENDER_DPI)
        if not png_bytes:
            pages_failed.append(page_num)
            continue

        ocr_result = fetch_ocr_result(png_bytes, image_format="png", image_name=f"gapgu_page_{page_num}")
        if ocr_result["status"] != "ok":
            pages_failed.append(page_num)
            continue

        all_rows.extend(extract_rows_from_clova_result(ocr_result["data"]))
        pages_processed += 1

    ownership_history = parse_gapgu(all_rows)["ownershipHistory"]
    eulgu_result = parse_eulgu(all_rows)

    return {
        "ownershipHistory": ownership_history,
        "eulguCriticalKeywords": eulgu_result["criticalKeywords"],
        "eulguSeniorMortgageAmount": eulgu_result["seniorMortgageAmount"],
        "pagesProcessed": pages_processed,
        "pagesFailed": pages_failed,
    }
