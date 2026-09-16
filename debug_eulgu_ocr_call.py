"""
을구/갑구 실키 검증용 1회성 디버그 스크립트 — registry_gapgu_ocr.py를 실제 클로바 OCR
키로 돌려서 로직을 확인한다.

CLAUDE.md의 "개별 모듈 로직 먼저 → 실키로 검증" 원칙, run_real_*.py/debug_*.py 패턴을
그대로 따른다. `등기부등본_내아파트.pdf`는 국토부가 제공하는 공식 테스트 샘플로, 표제부/
갑구는 5페이지, 을구는 6~8페이지, 요약 페이지는 9페이지에 있다.

실행: python debug_eulgu_ocr_call.py
"""

from dotenv import load_dotenv

load_dotenv(".env")

from registry_gapgu_ocr import extract_ownership_history_from_pdf

PDF_PATH = "등기부등본_내아파트.pdf"
SUMMARY_PAGE = 9


def main():
    result = extract_ownership_history_from_pdf(PDF_PATH, exclude_pages={SUMMARY_PAGE})
    print("pagesProcessed:", result["pagesProcessed"])
    print("pagesFailed:", result["pagesFailed"])
    print("ownershipHistory:")
    for h in result["ownershipHistory"]:
        print(" -", h)
    print("eulguCriticalKeywords:", result["eulguCriticalKeywords"])
    print("eulguSeniorMortgageAmount:", result["eulguSeniorMortgageAmount"])


if __name__ == "__main__":
    main()
