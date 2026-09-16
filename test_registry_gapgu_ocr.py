"""
registry_gapgu_ocr 단위 테스트
--------------------------------
PDF 렌더링(render_pdf_page_to_png_bytes)과 클로바 호출(fetch_ocr_result)을 모킹해서,
"페이지를 몇 장 돌리고 어떻게 합치는가"라는 이 모듈만의 책임(오케스트레이션)만 검증한다.
줄 재조합/컬럼 분리(gapgu_ocr_row_parser.py)와 갑구 판별(registry_parser.py)은 각자
이미 별도 테스트로 커버되므로 여기서는 진짜 함수를 그대로 통합해서 쓴다(모킹 안 함).
"""

import unittest
from unittest.mock import patch

import registry_gapgu_ocr
from registry_gapgu_ocr import extract_ownership_history_from_pdf


def field(text, x, y):
    return {"inferText": text, "boundingPoly": {"vertices": [{"x": x, "y": y}]}}


def clova_ok(fields):
    return {"status": "ok", "data": {"images": [{"fields": fields}]}}


# "1 소유권보존 1990년1월1일 제1호 소유자 김철수" 형태의 실제 갑구 행 하나를 좌표로 구성
OWNERSHIP_PRESERVED_FIELDS = [
    field("1", 10, 100),
    field("소유권보존", 40, 100),
    field("1990년1월1일", 150, 100),
    field("제1호", 260, 100),
    field("소유자", 320, 100),
    field("김철수", 360, 100),
]

# "2 소유권이전 2020년5월5일 제200호 소유자 이영희" — 더 최근 소유권 이전
OWNERSHIP_TRANSFERRED_FIELDS = [
    field("2", 10, 100),
    field("소유권이전", 40, 100),
    field("2020년5월5일", 150, 100),
    field("제200호", 260, 100),
    field("소유자", 320, 100),
    field("이영희", 360, 100),
]

# 표제부처럼 갑구와 무관한 표(순위번호만 있고 등기목적이 비어있는 노이즈 행) — 실제 행(y=100)과는
# 다른 y좌표를 줘서 별도의 줄로 재조합되게 한다(같은 y면 두 행의 조각이 뒤섞여버림).
TITLE_SECTION_NOISE_FIELDS = [
    field("1", 10, 30),
    field("경기도 성남시", 40, 30),
]

# 을구 근저당권설정 행 — "1 근저당권설정 2020년1월1일 제1호 채권최고액 금100,000,000원"
MORTGAGE_FIELDS = [
    field("1", 10, 100), field("근저당권설정", 40, 100),
    field("2020년1월1일", 150, 100), field("제1호", 260, 100),
    field("채권최고액", 320, 100), field("금100,000,000원", 420, 100),
]

# 을구 임차권등기명령 행
LEASEHOLD_ORDER_FIELDS = [
    field("2", 10, 100), field("임차권등기명령", 40, 100),
    field("2021년2월2일", 150, 100), field("제2호", 260, 100),
    field("임차보증금", 320, 100), field("금50,000,000원", 420, 100),
]

# 을구 근저당권설정 행인데 금액이 한글 숫자 표기라 _AMOUNT_PATTERN이 못 읽는 경우
UNPARSEABLE_AMOUNT_MORTGAGE_FIELDS = [
    field("1", 10, 100), field("근저당권설정", 40, 100),
    field("1993년6월18일", 150, 100), field("제1호", 260, 100),
    field("채권최고액", 320, 100), field("금일천오백육십만원정", 420, 100),
]


class TestExtractOwnershipHistoryFromPdf(unittest.TestCase):

    def setUp(self):
        self._orig_url = registry_gapgu_ocr.CLOVA_OCR_INVOKE_URL
        self._orig_secret = registry_gapgu_ocr.CLOVA_OCR_SECRET
        registry_gapgu_ocr.CLOVA_OCR_INVOKE_URL = "https://fake.apigw.ntruss.com/custom/v1/1/fake/general"
        registry_gapgu_ocr.CLOVA_OCR_SECRET = "fake-secret"

    def tearDown(self):
        registry_gapgu_ocr.CLOVA_OCR_INVOKE_URL = self._orig_url
        registry_gapgu_ocr.CLOVA_OCR_SECRET = self._orig_secret

    def test_missing_credentials_returns_empty_without_any_page_work(self):
        registry_gapgu_ocr.CLOVA_OCR_INVOKE_URL = ""
        registry_gapgu_ocr.CLOVA_OCR_SECRET = ""

        with patch("registry_gapgu_ocr.pdf_page_count") as mock_page_count:
            result = extract_ownership_history_from_pdf("fake.pdf")

        mock_page_count.assert_not_called()
        self.assertEqual(result, {
            "ownershipHistory": [],
            "eulguCriticalKeywords": [],
            "eulguSeniorMortgageAmount": 0,
            "eulguHasUnparsedMortgageAmount": False,
            "pagesProcessed": 0,
            "pagesFailed": [],
        })

    @patch("registry_gapgu_ocr.fetch_ocr_result")
    @patch("registry_gapgu_ocr.render_pdf_page_to_png_bytes")
    @patch("registry_gapgu_ocr.pdf_page_count", return_value=2)
    def test_two_pages_merged_into_one_ownership_history(
        self, mock_page_count, mock_render, mock_fetch,
    ):
        mock_render.return_value = b"fake-png-bytes"
        mock_fetch.side_effect = [
            clova_ok(OWNERSHIP_PRESERVED_FIELDS),
            clova_ok(OWNERSHIP_TRANSFERRED_FIELDS),
        ]

        result = extract_ownership_history_from_pdf("fake.pdf")

        self.assertEqual(result["pagesProcessed"], 2)
        self.assertEqual(result["pagesFailed"], [])
        self.assertEqual(
            result["ownershipHistory"],
            [
                {"date": "1990-01-01", "ownerName": "김철수"},
                {"date": "2020-05-05", "ownerName": "이영희"},
            ],
        )

    @patch("registry_gapgu_ocr.fetch_ocr_result")
    @patch("registry_gapgu_ocr.render_pdf_page_to_png_bytes")
    @patch("registry_gapgu_ocr.pdf_page_count", return_value=3)
    def test_excluded_page_is_never_rendered_or_sent_to_clova(
        self, mock_page_count, mock_render, mock_fetch,
    ):
        mock_render.return_value = b"fake-png-bytes"
        mock_fetch.return_value = clova_ok(OWNERSHIP_PRESERVED_FIELDS)

        extract_ownership_history_from_pdf("fake.pdf", exclude_pages={2})

        rendered_pages = [call.args[1] for call in mock_render.call_args_list]
        self.assertEqual(rendered_pages, [1, 3])

    @patch("registry_gapgu_ocr.fetch_ocr_result")
    @patch("registry_gapgu_ocr.render_pdf_page_to_png_bytes")
    @patch("registry_gapgu_ocr.pdf_page_count", return_value=2)
    def test_page_render_failure_is_recorded_and_skipped(
        self, mock_page_count, mock_render, mock_fetch,
    ):
        mock_render.side_effect = [b"", b"fake-png-bytes"]
        mock_fetch.return_value = clova_ok(OWNERSHIP_TRANSFERRED_FIELDS)

        result = extract_ownership_history_from_pdf("fake.pdf")

        self.assertEqual(result["pagesFailed"], [1])
        self.assertEqual(result["pagesProcessed"], 1)
        self.assertEqual(result["ownershipHistory"], [{"date": "2020-05-05", "ownerName": "이영희"}])
        mock_fetch.assert_called_once()

    @patch("registry_gapgu_ocr.fetch_ocr_result")
    @patch("registry_gapgu_ocr.render_pdf_page_to_png_bytes")
    @patch("registry_gapgu_ocr.pdf_page_count", return_value=2)
    def test_clova_error_on_one_page_still_returns_partial_result(
        self, mock_page_count, mock_render, mock_fetch,
    ):
        mock_render.return_value = b"fake-png-bytes"
        mock_fetch.side_effect = [
            {"status": "error", "reason": "invalid_request"},
            clova_ok(OWNERSHIP_TRANSFERRED_FIELDS),
        ]

        result = extract_ownership_history_from_pdf("fake.pdf")

        self.assertEqual(result["pagesFailed"], [1])
        self.assertEqual(result["pagesProcessed"], 1)
        self.assertEqual(result["ownershipHistory"], [{"date": "2020-05-05", "ownerName": "이영희"}])

    @patch("registry_gapgu_ocr.fetch_ocr_result")
    @patch("registry_gapgu_ocr.render_pdf_page_to_png_bytes")
    @patch("registry_gapgu_ocr.pdf_page_count", return_value=1)
    def test_title_section_noise_row_does_not_pollute_ownership_history(
        self, mock_page_count, mock_render, mock_fetch,
    ):
        # 표제부가 갑구와 같은 페이지에 섞여도(순위번호는 있지만 "소유권보존"/"소유권이전"
        # 키워드가 없는 노이즈 행) parse_gapgu()가 그 키워드로만 골라내므로 결과에 영향이
        # 없어야 한다 (README "클로바 OCR 실키 검증" 섹션에서 실제로 확인된 부작용 케이스).
        mock_render.return_value = b"fake-png-bytes"
        mock_fetch.return_value = clova_ok(TITLE_SECTION_NOISE_FIELDS + OWNERSHIP_PRESERVED_FIELDS)

        result = extract_ownership_history_from_pdf("fake.pdf")

        self.assertEqual(result["ownershipHistory"], [{"date": "1990-01-01", "ownerName": "김철수"}])

    @patch("registry_gapgu_ocr.fetch_ocr_result")
    @patch("registry_gapgu_ocr.render_pdf_page_to_png_bytes")
    @patch("registry_gapgu_ocr.pdf_page_count", return_value=2)
    def test_eulgu_results_extracted_alongside_ownership_history(
        self, mock_page_count, mock_render, mock_fetch,
    ):
        # 갑구 페이지와 을구 페이지를 페이지별로 구분하지 않고 같은 파이프라인에 그대로
        # 태워도 parse_gapgu()/parse_eulgu()가 각자 알아서 걸러내 양쪽 결과가 모두
        # 정확히 나와야 한다 — 이게 이번 배선의 핵심 전제다.
        mock_render.return_value = b"fake-png-bytes"
        mock_fetch.side_effect = [
            clova_ok(OWNERSHIP_PRESERVED_FIELDS),  # 페이지 1: 갑구
            clova_ok(MORTGAGE_FIELDS),  # 페이지 2: 을구
        ]

        result = extract_ownership_history_from_pdf("fake.pdf")

        self.assertEqual(result["ownershipHistory"], [{"date": "1990-01-01", "ownerName": "김철수"}])
        self.assertEqual(result["eulguSeniorMortgageAmount"], 100_000_000)
        self.assertEqual(result["eulguCriticalKeywords"], [])

    @patch("registry_gapgu_ocr.fetch_ocr_result")
    @patch("registry_gapgu_ocr.render_pdf_page_to_png_bytes")
    @patch("registry_gapgu_ocr.pdf_page_count", return_value=1)
    def test_leasehold_registration_order_surfaced_as_critical_keyword(
        self, mock_page_count, mock_render, mock_fetch,
    ):
        mock_render.return_value = b"fake-png-bytes"
        mock_fetch.return_value = clova_ok(LEASEHOLD_ORDER_FIELDS)

        result = extract_ownership_history_from_pdf("fake.pdf")

        self.assertIn("임차권등기명령", result["eulguCriticalKeywords"])

    @patch("registry_gapgu_ocr.fetch_ocr_result")
    @patch("registry_gapgu_ocr.render_pdf_page_to_png_bytes")
    @patch("registry_gapgu_ocr.pdf_page_count", return_value=1)
    def test_korean_numeral_amount_flagged_as_unparsed_not_silently_dropped(
        self, mock_page_count, mock_render, mock_fetch,
    ):
        mock_render.return_value = b"fake-png-bytes"
        mock_fetch.return_value = clova_ok(UNPARSEABLE_AMOUNT_MORTGAGE_FIELDS)

        result = extract_ownership_history_from_pdf("fake.pdf")

        self.assertEqual(result["eulguSeniorMortgageAmount"], 0)
        self.assertTrue(result["eulguHasUnparsedMortgageAmount"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
