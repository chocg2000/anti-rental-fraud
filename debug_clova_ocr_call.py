"""
디버그용: 네이버 클로바 OCR을 어댑터 없이 직접 호출해서 진짜 응답 구조를 확인한다.

⚠️ clova_ocr_adapter.py/gapgu_ocr_row_parser.py는 아직 실제 Secret Key로 한 번도
검증된 적이 없다 — 요청/응답 스펙은 네이버 공식 문서로만 확인했다(문서와 실제 응답이
다를 수 있다는 건 이 프로젝트가 MOLIT/VWorld 두 번 다 겪은 함정이다).

실제 Secret Key와 Invoke URL을 받으면(네이버클라우드플랫폼 콘솔 → AI·Application
Service → CLOVA OCR → General 템플릿 생성), 이 스크립트로 실제 등기부 갑구 페이지
이미지(스캔 PNG/JPG 한 장, 또는 PDF 한 페이지)를 넣어 돌려본 뒤:

  1. images[0].fields[]에 정말 inferText/boundingPoly.vertices가 있는지 확인.
  2. boundingPoly.vertices의 x/y가 문서 설명대로 좌상단 기준인지, 실제 값 범위가
     gapgu_ocr_row_parser.py의 y_threshold(기본 12) 가정과 맞는지 확인 — 이미지
     해상도에 따라 텍스트 높이가 다르면 이 값을 조정해야 할 수 있다.
  3. reconstruct_lines_from_clova_result()로 재조합한 줄들을 출력해서 실제 갑구
     레이아웃과 맞는지 눈으로 확인.
  4. split_line_into_row()가 뽑아낸 rank/purpose/receipt/cause/detail이 실제
     의미와 맞는지 확인 — 안 맞으면 이 함수부터 실제 레이아웃에 맞게 다시 짤 것.

실행: .env에 CLOVA_OCR_INVOKE_URL, CLOVA_OCR_SECRET을 설정한 뒤
  python debug_clova_ocr_call.py <이미지_또는_PDF_경로>
"""

import sys

from dotenv import load_dotenv

load_dotenv()

from clova_ocr_adapter import fetch_ocr_result
from gapgu_ocr_row_parser import reconstruct_lines_from_clova_result, extract_rows_from_clova_result


def main():
    if len(sys.argv) < 2:
        print("사용법: python debug_clova_ocr_call.py <등기부 갑구 페이지 이미지 또는 PDF 경로>")
        return

    path = sys.argv[1]
    ext = path.rsplit(".", 1)[-1].lower()
    image_format = ext if ext in ("pdf", "jpg", "jpeg", "png", "tif", "tiff") else "pdf"

    with open(path, "rb") as f:
        image_bytes = f.read()

    print(f"[호출] {path} ({len(image_bytes):,} bytes, format={image_format})")
    result = fetch_ocr_result(image_bytes, image_format=image_format, image_name="debug_gapgu")

    if result["status"] != "ok":
        print(f"[실패] status={result['status']} reason={result.get('reason')}")
        print("CLOVA_OCR_INVOKE_URL / CLOVA_OCR_SECRET이 .env에 설정돼 있는지 먼저 확인하세요.")
        return

    print("\n" + "=" * 60)
    print("원본 응답 (앞부분)")
    print("=" * 60)
    print(str(result["data"])[:2000])

    lines = reconstruct_lines_from_clova_result(result["data"])
    print("\n" + "=" * 60)
    print(f"재조합된 줄 ({len(lines)}개)")
    print("=" * 60)
    for line in lines:
        print(f"  {line}")

    rows = extract_rows_from_clova_result(result["data"])
    print("\n" + "=" * 60)
    print(f"컬럼 분리 결과 ({len(rows)}개 데이터 행으로 인식)")
    print("=" * 60)
    for row in rows:
        print(f"  {row}")


if __name__ == "__main__":
    main()
