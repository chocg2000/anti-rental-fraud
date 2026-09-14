"""
등기부등본 OCR 실환경 테스트 (Tesseract/Poppler 실제 바이너리)
------------------------------------------------------------------
Mocking 없이 진짜 tesseract/pdftoppm/pdfinfo 실행파일을 호출한다.
registry_summary_ocr.py와 같은 폴더에 둘 것.

실행 전 준비:
  - .env에 TESSERACT_CMD / PDFTOPPM_CMD / PDFINFO_CMD로 각 실행파일 전체 경로를 넣어둘 것
    (PATH에 이미 잡혀있는 환경이면 안 넣어도 기본값 "tesseract" 등으로 동작)
  - 프로젝트 루트에 실제 등기부등본 PDF가 있어야 함 (기본값: 등기부등본_내아파트.pdf,
    .gitignore로 제외된 개인 파일 — 다른 PDF로 테스트하려면 인자로 경로를 넘기면 됨)

실행: python run_real_registry_ocr_test.py [pdf_경로]
"""

import sys

from dotenv import load_dotenv

# registry_summary_ocr.py가 모듈 로드 시점에 TESSERACT_CMD 등을 읽으므로 import보다 먼저 실행.
load_dotenv()

from registry_summary_ocr import find_and_parse_summary_page

DEFAULT_PDF_PATH = "등기부등본_내아파트.pdf"


def main():
    pdf_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PDF_PATH

    print(f"[입력 PDF] {pdf_path}\n")

    try:
        result = find_and_parse_summary_page(pdf_path)
    except FileNotFoundError:
        print(f"[실패] PDF 파일을 찾을 수 없습니다: {pdf_path}")
        return
    except RuntimeError as e:
        print(f"[실패] {e}")
        return

    print(f"[성공] PDF {result['_sourcePage']}번째 페이지에서 요약 페이지 발견\n")

    print("=== OCR 원문 ===")
    print(result["_rawOcrText"])

    print("=== 소유자 ===")
    if not result["owners"]:
        print("  (인식 실패 또는 기록 없음)")
    for owner in result["owners"]:
        print(f"  {owner['ownerName']} ({owner['shareType']})")

    print("\n=== 현재 유효한 근저당권/전세권 ===")
    if not result["activeRights"]:
        print("  없음")
    for r in result["activeRights"]:
        print(f"  [{r['rank']}] {r['rightType']} - {r['amount']:,}원" if r["amount"]
              else f"  [{r['rank']}] {r['rightType']}")

    print(f"\n=== 선순위 채권 합계(근저당+전세권): {result['totalSeniorSecuredAmount']:,}원 ===")


if __name__ == "__main__":
    main()
