"""
api.py 테스트
----------------
목적: FastAPI 레이어가 request/response 계약을 제대로 지키는지만 검증한다
(Pydantic 유효성 검증, run_full_assessment로의 필드 매핑, 에러 핸들링).
비즈니스 로직 자체는 각 모듈 테스트 + test_full_assessment.py가 이미 커버한다.
"""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import assessment_store
from api import app
from property_aggregator import PropertyAggregationError

client = TestClient(app, raise_server_exceptions=False)


def setUpModule():
    # api.py가 이제 SQLite(assessment_store.py)로 결과를 저장한다 — 테스트 실행 중
    # 실제 data/assessments.db 파일이 생기지 않도록 인메모리 DB로 격리한다.
    assessment_store.DB_PATH = ":memory:"
    assessment_store.reset_for_testing()


def tearDownModule():
    assessment_store.reset_for_testing()

YATAP_REGISTRY_OCR_TEXT = """주요 등기사항 요약 (참고용)
고유번호 1356-1996-092460
1. 소유지분현황 ( 갑구 )
조춘근 (소유자) | 670209-1788617 | 단독소유    경기도 성남시 분당구 장미로 101, 822동
204호(야탑동, 장미마을)
2. 소유지분을 제외한 소유권에 관한 사항 ( 갑구 )
- 기록사항 없음
3. (근)저당권 및 전세권 등 ( 을구 )
11    전세권설정          2025년3월26일 | 전세금 _금300,000,000원                     조춘근
제1247861호  전세권자 주식회사지음이엔지
[참고사항]
"""

BASE_PROPERTY_INFO = {
    "normalizedAddress": {"roadAddress": "경기 성남시 분당구 장미로 101"},
    "marketPrice": 60_000,  # 만원 단위 = 6억원
    "marketPriceConfidence": "high",
    "marketPriceBasis": "test fixture",
    "building": None,
    "registrySeparated": True,
    "violationStatusConfirmed": False,
    "violationStatusRaw": None,
    "nonResidentialUseRisk": False,
    "sourceStatuses": {"transactionPrice": "ok", "buildingRegister": "not_found"},
}


def minimal_payload(**overrides):
    payload = {
        "address": "경기 성남시 분당구 야탑동 335",
        "target_area": 39.6,
        "my_deposit": 100_000_000,
        "contract_landlord_name": "조춘근",
    }
    payload.update(overrides)
    return payload


class TestHealthCheck(unittest.TestCase):

    def test_health_returns_ok(self):
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})


class TestRequestValidation(unittest.TestCase):

    def test_missing_required_field_is_422(self):
        payload = minimal_payload()
        del payload["address"]
        response = client.post("/assessment", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_invalid_property_type_is_422(self):
        response = client.post("/assessment", json=minimal_payload(property_type="원룸"))
        self.assertEqual(response.status_code, 422)

    def test_non_positive_deposit_is_422(self):
        response = client.post("/assessment", json=minimal_payload(my_deposit=0))
        self.assertEqual(response.status_code, 422)

    def test_unknown_field_is_rejected(self):
        # extra="forbid" — 계약에 없는 필드를 프론트가 실수로 보내면 조용히 무시되지 않고 바로 드러나야 함
        response = client.post("/assessment", json=minimal_payload(unexpected_field="x"))
        self.assertEqual(response.status_code, 422)


class TestAssessmentEndpoint(unittest.TestCase):

    @patch("full_assessment.get_property_info")
    def test_minimal_request_without_registry_returns_unknown_risk(self, mock_get_info):
        mock_get_info.return_value = BASE_PROPERTY_INFO

        response = client.post("/assessment", json=minimal_payload())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(body["overallGrade"], ("safe", "caution", "warning", "danger"))
        self.assertIsNone(body["tenancySafety"]["depositPriorityRisk"]["riskyDepositPriority"])
        self.assertEqual(body["tenancySafety"]["landlordIdentityCheck"]["riskLevel"], "unknown")

    @patch("full_assessment.get_property_info")
    def test_full_payload_with_registry_text_matches_safe_scenario(self, mock_get_info):
        mock_get_info.return_value = BASE_PROPERTY_INFO

        response = client.post("/assessment", json=minimal_payload(
            property_type="multi_household",
            registry_ocr_text=YATAP_REGISTRY_OCR_TEXT,
        ))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["overallGrade"], "safe")
        self.assertFalse(body["tenancySafety"]["depositPriorityRisk"]["riskyDepositPriority"])

    @patch("full_assessment.get_property_info")
    def test_landlord_mismatch_returns_danger(self, mock_get_info):
        mock_get_info.return_value = BASE_PROPERTY_INFO

        response = client.post("/assessment", json=minimal_payload(
            contract_landlord_name="김아무개",
            my_deposit=250_000_000,
            property_type="multi_household",
            registry_ocr_text=YATAP_REGISTRY_OCR_TEXT,
        ))

        body = response.json()
        self.assertEqual(body["overallGrade"], "danger")

    @patch("full_assessment.get_property_info")
    def test_move_in_date_same_day_as_registry_right_is_danger(self, mock_get_info):
        mock_get_info.return_value = BASE_PROPERTY_INFO

        response = client.post("/assessment", json=minimal_payload(
            property_type="multi_household",
            registry_ocr_text=YATAP_REGISTRY_OCR_TEXT,
            move_in_date="2025-03-26",
        ))

        body = response.json()
        self.assertTrue(body["tenancySafety"]["possessionPriorityGapRisk"]["gapRiskDetected"])
        self.assertEqual(body["overallGrade"], "danger")

    @patch("full_assessment.get_property_info")
    def test_has_fixed_date_false_is_caution_not_warning(self, mock_get_info):
        # 계약 전 진단이 주 사용 시나리오라 확정일자 미확보는 당연한 상태 — "caution"만
        # 이어야 한다("warning"이면 거의 모든 진단에 경고가 뜬다).
        mock_get_info.return_value = BASE_PROPERTY_INFO

        response = client.post("/assessment", json=minimal_payload(has_fixed_date=False))

        body = response.json()
        self.assertEqual(body["tenancySafety"]["fixedDateRisk"]["riskLevel"], "caution")
        self.assertIn(body["overallGrade"], ("caution", "warning", "danger"))

    @patch("full_assessment.get_property_info")
    def test_move_in_date_and_fixed_date_omitted_are_unknown(self, mock_get_info):
        mock_get_info.return_value = BASE_PROPERTY_INFO

        response = client.post("/assessment", json=minimal_payload())

        body = response.json()
        self.assertIsNone(body["tenancySafety"]["possessionPriorityGapRisk"]["gapRiskDetected"])
        self.assertEqual(body["tenancySafety"]["fixedDateRisk"]["riskLevel"], "unknown")

    @patch("full_assessment.get_property_info")
    def test_user_confirmed_violation_building_forces_danger(self, mock_get_info):
        mock_get_info.return_value = BASE_PROPERTY_INFO

        response = client.post("/assessment", json=minimal_payload(
            user_confirmed_violation_building=True,
        ))

        body = response.json()
        self.assertEqual(body["overallGrade"], "danger")
        self.assertIn("위반건축물", body["propertyInfo"]["violationStatusRaw"])

    @patch("full_assessment.get_property_info")
    def test_omitted_tax_clearance_field_is_skipped(self, mock_get_info):
        mock_get_info.return_value = BASE_PROPERTY_INFO

        response = client.post("/assessment", json=minimal_payload())

        body = response.json()
        self.assertIsNone(body["taxClearanceResult"])

    @patch("full_assessment.get_property_info")
    def test_explicit_tax_clearance_not_submitted_is_warning(self, mock_get_info):
        mock_get_info.return_value = BASE_PROPERTY_INFO

        response = client.post("/assessment", json=minimal_payload(
            tax_clearance={"submitted": False},
        ))

        body = response.json()
        self.assertEqual(body["taxClearanceResult"]["riskLevel"], "warning")

    @patch("full_assessment.get_property_info")
    def test_address_resolution_failure_returns_200_with_error_grade(self, mock_get_info):
        mock_get_info.side_effect = PropertyAggregationError("주소를 정규화하지 못해 조회를 진행할 수 없습니다: 테스트")

        response = client.post("/assessment", json=minimal_payload())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["overallGrade"], "error")
        self.assertIsNone(body["propertyInfo"])


class TestAssessmentResultRetrieval(unittest.TestCase):
    """
    POST /assessment가 저장한 결과를 GET /assessment/{id}로 다시 꺼내오는지 검증.
    프론트가 결과 화면을 /result/:id로 라우팅해서 새로고침/링크공유에도 버티게 하려는 목적.
    """

    @patch("full_assessment.get_property_info")
    def test_get_returns_the_same_result_that_post_created(self, mock_get_info):
        mock_get_info.return_value = BASE_PROPERTY_INFO

        post_response = client.post("/assessment", json=minimal_payload())
        assessment_id = post_response.json()["id"]

        get_response = client.get(f"/assessment/{assessment_id}")

        self.assertEqual(get_response.status_code, 200)
        body = get_response.json()
        self.assertEqual(body["id"], assessment_id)
        self.assertEqual(body["overallGrade"], post_response.json()["overallGrade"])

    def test_unknown_id_returns_404(self):
        response = client.get("/assessment/no-such-id")
        self.assertEqual(response.status_code, 404)


class TestRegistryUploadEndpoint(unittest.TestCase):
    """
    실제 tesseract/poppler 없이(이 개발 환경엔 설치돼있지 않음) find_and_parse_summary_page만
    모킹해서 API 배선(파일 검증, 임시파일 처리, RuntimeError->400 변환, 응답 매핑)만 검증한다.
    OCR/파싱 로직 자체는 registry_summary_ocr.py, registry_summary_parser.py가 이미 커버함.
    """

    @patch("api.find_and_parse_summary_page")
    def test_successful_upload_returns_parsed_preview(self, mock_find_and_parse):
        mock_find_and_parse.return_value = {
            "owners": [{"ownerName": "조춘근", "shareType": "단독소유"}],
            "activeRights": [{"rank": "11", "rightType": "전세권설정", "amount": 300_000_000, "rawLine": "..."}],
            "totalSeniorSecuredAmount": 300_000_000,
            "_sourcePage": 5,
            "_rawOcrText": "주요 등기사항 요약 (참고용) ...",
        }

        response = client.post(
            "/registry/upload",
            files={"file": ("등기부등본.pdf", b"%PDF-1.4 fake bytes", "application/pdf")},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["sourcePage"], 5)
        self.assertEqual(body["totalSeniorSecuredAmount"], 300_000_000)
        self.assertEqual(body["owners"][0]["ownerName"], "조춘근")
        self.assertIn("주요 등기사항 요약", body["registryOcrText"])

        # 업로드된 내용이 임시 파일 경로로 그대로 전달됐는지만 확인 (내용 자체는 모킹 대상 밖)
        mock_find_and_parse.assert_called_once()
        called_path = mock_find_and_parse.call_args[0][0]
        self.assertTrue(called_path.endswith(".pdf"))

    @patch("api.find_and_parse_summary_page")
    def test_summary_page_not_found_returns_400_not_500(self, mock_find_and_parse):
        mock_find_and_parse.side_effect = RuntimeError(
            "'주요 등기사항 요약' 페이지를 마지막 3장 안에서 찾지 못했습니다."
        )

        response = client.post(
            "/registry/upload",
            files={"file": ("등기부등본.pdf", b"%PDF-1.4 fake bytes", "application/pdf")},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("요약", response.json()["detail"])

    @patch("api.find_and_parse_summary_page")
    def test_non_pdf_upload_is_rejected_before_ocr_runs(self, mock_find_and_parse):
        response = client.post(
            "/registry/upload",
            files={"file": ("메모.txt", b"hello", "text/plain")},
        )

        self.assertEqual(response.status_code, 400)
        mock_find_and_parse.assert_not_called()

    @patch("api.find_and_parse_summary_page")
    def test_oversized_upload_is_rejected_before_ocr_runs(self, mock_find_and_parse):
        with patch("api.MAX_REGISTRY_UPLOAD_BYTES", 10):
            response = client.post(
                "/registry/upload",
                files={"file": ("등기부등본.pdf", b"x" * 100, "application/pdf")},
            )

        self.assertEqual(response.status_code, 400)
        mock_find_and_parse.assert_not_called()

    @patch("api.find_and_parse_summary_page")
    def test_empty_upload_is_rejected(self, mock_find_and_parse):
        response = client.post(
            "/registry/upload",
            files={"file": ("등기부등본.pdf", b"", "application/pdf")},
        )

        self.assertEqual(response.status_code, 400)
        mock_find_and_parse.assert_not_called()


class TestUnhandledExceptionHandling(unittest.TestCase):

    @patch("full_assessment.get_property_info")
    def test_unexpected_exception_returns_500_without_leaking_traceback(self, mock_get_info):
        mock_get_info.side_effect = RuntimeError("예상 못 한 내부 버그")

        response = client.post("/assessment", json=minimal_payload())

        self.assertEqual(response.status_code, 500)
        self.assertNotIn("RuntimeError", response.text)
        self.assertNotIn("Traceback", response.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
