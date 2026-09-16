"""
등기부등본 PDF -> 요약 페이지 자동 탐지 -> OCR -> 파싱 (엔드투엔드)
--------------------------------------------------------------------
사전 준비:
  - Ubuntu/Debian: sudo apt-get install tesseract-ocr tesseract-ocr-kor poppler-utils
    (설치하면 tesseract/pdftoppm/pdfinfo가 PATH에 잡히므로 아래 환경변수는 안 넣어도 됨)
  - Windows: PATH에 안 잡히는 경우가 많아서, .env에 TESSERACT_CMD/PDFTOPPM_CMD/PDFINFO_CMD로
    각 실행파일의 전체 경로를 넣어주면 된다 (예: TESSERACT_CMD="C:/.../tesseract.exe").
    포터블 zip으로 설치했다면(관리자 권한 없이) 특히 필요 — PATH에 자동 등록이 안 되기 때문.

이 모듈은 pytesseract/pdf2image 같은 파이썬 래퍼를 쓰지 않는다 — tesseract/poppler
CLI 실행파일을 subprocess로 직접 호출한다. 그래서 "파이썬 라이브러리 설정"이 아니라
"실행파일 경로를 어떻게 찾을지"가 핵심이다.
"""

import glob
import os
import re
import subprocess
import tempfile

from registry_summary_parser import parse_summary_registry

SUMMARY_PAGE_MARKER = "주요 등기사항 요약"

# 기본값은 PATH에 있다고 가정하고 바로 실행 가능한 이름 그대로 둔다 (Ubuntu 배포 환경 기준).
# Windows처럼 PATH 등록이 안 된 환경에서는 .env에 전체 경로를 넣어 덮어쓴다.
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "tesseract")
PDFTOPPM_CMD = os.environ.get("PDFTOPPM_CMD", "pdftoppm")
PDFINFO_CMD = os.environ.get("PDFINFO_CMD", "pdfinfo")


def pdf_page_count(pdf_path: str) -> int:
    # encoding을 명시하지 않으면 subprocess는 플랫폼 기본 인코딩을 쓴다 — Windows에서는
    # 그게 cp949라 tesseract/pdfinfo의 UTF-8 출력을 디코딩하다 크래시한다(실제로 겪은 버그).
    # errors="replace"도 필요하다 — 포플러 Windows 빌드는 파일 경로 등 일부를 로컬
    # 코드페이지로 섞어 내보내기도 해서, 순수 UTF-8로 강제 디코딩하면 그 부분에서 다시
    # 깨진다(마찬가지로 실제로 겪음). 우리가 찾는 "Pages: N"은 항상 ASCII라 무관하다.
    result = subprocess.run(
        [PDFINFO_CMD, pdf_path], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    )
    m = re.search(r"Pages:\s*(\d+)", result.stdout)
    return int(m.group(1)) if m else 0


def render_pdf_page_to_png_bytes(pdf_path: str, page_num: int, dpi: int = 300) -> bytes:
    """
    PDF의 특정 페이지를 PNG 이미지로 렌더링해서 바이트로 반환한다. registry_gapgu_ocr.py가
    클로바 OCR에 보낼 페이지 이미지를 만들 때도 이 함수를 그대로 재사용한다(클로바는
    해상도 상한이 있어 dpi를 낮춰서 호출 — registry_gapgu_ocr.py 참고).
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        prefix = f"{tmpdir}/page"
        subprocess.run(
            [PDFTOPPM_CMD, "-png", "-r", str(dpi), "-f", str(page_num), "-l", str(page_num),
             pdf_path, prefix],
            check=True, capture_output=True,
        )
        png_files = glob.glob(f"{prefix}*.png")
        if not png_files:
            return b""
        with open(png_files[0], "rb") as f:
            return f.read()


def _ocr_page(pdf_path: str, page_num: int, dpi: int = 300) -> str:
    """PDF의 특정 페이지를 이미지로 뜨고 한글 OCR을 돌려 텍스트를 반환한다."""
    png_bytes = render_pdf_page_to_png_bytes(pdf_path, page_num, dpi=dpi)
    if not png_bytes:
        return ""

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp.write(png_bytes)
        tmp_path = tmp.name
    try:
        result = subprocess.run(
            [TESSERACT_CMD, tmp_path, "stdout", "-l", "kor", "--psm", "6"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=True,
        )
        return result.stdout
    finally:
        os.unlink(tmp_path)


def find_and_parse_summary_page(pdf_path: str, search_last_n_pages: int = 3) -> dict:
    """
    PDF 뒤에서부터 최대 search_last_n_pages장을 OCR로 훑어 '주요 등기사항 요약' 페이지를
    찾고, 찾으면 그 페이지를 파싱해서 반환한다.

    실제 검증 결과(2026-09-12): 본문(갑구/을구) 페이지는 배경무늬 때문에 OCR 품질이
    나쁘지만, 이 요약 페이지는 배경무늬가 거의 없어 정확도가 훨씬 높다 — 그래서 이
    페이지 하나만 정확히 찾아내는 전략이 전체 문서를 다 OCR하는 것보다 훨씬 효율적이다.
    """
    total_pages = pdf_page_count(pdf_path)
    if total_pages == 0:
        raise RuntimeError("PDF 페이지 수를 확인할 수 없습니다.")

    candidates = range(total_pages, max(total_pages - search_last_n_pages, 0), -1)

    for page_num in candidates:
        text = _ocr_page(pdf_path, page_num)
        if SUMMARY_PAGE_MARKER in text:
            result = parse_summary_registry(text)
            result["_sourcePage"] = page_num
            result["_rawOcrText"] = text
            return result

    raise RuntimeError(
        f"'{SUMMARY_PAGE_MARKER}' 페이지를 마지막 {search_last_n_pages}장 안에서 찾지 못했습니다. "
        "이 PDF는 '요약(참고용)' 페이지가 없는 발급 형식일 수 있습니다."
    )


if __name__ == "__main__":
    import sys

    pdf_path = sys.argv[1] if len(sys.argv) > 1 else "/mnt/user-data/uploads/등기부등본_내아파트.pdf"
    result = find_and_parse_summary_page(pdf_path)

    print(f"[요약 페이지: PDF {result['_sourcePage']}번째 페이지에서 발견]\n")
    print("=== 소유자 ===")
    for owner in result["owners"]:
        print(f"  {owner['ownerName']} ({owner['shareType']})")

    print("\n=== 현재 유효한 근저당권/전세권 ===")
    if not result["activeRights"]:
        print("  없음")
    for r in result["activeRights"]:
        print(f"  [{r['rank']}] {r['rightType']} - {r['amount']:,}원" if r["amount"]
              else f"  [{r['rank']}] {r['rightType']}")

    print(f"\n=== 선순위 채권 합계(근저당+전세권): {result['totalSeniorSecuredAmount']:,}원 ===")
