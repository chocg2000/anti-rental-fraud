"""
tax_clearance_check 단위 테스트
"""

import unittest
from datetime import date

from tax_clearance_check import check_tax_clearance_certificate


class TestTaxClearanceCheck(unittest.TestCase):

    def test_not_submitted_is_warning(self):
        result = check_tax_clearance_certificate(submitted=False)
        self.assertFalse(result["submitted"])
        self.assertEqual(result["riskLevel"], "warning")

    def test_submitted_clean_case_is_safe(self):
        result = check_tax_clearance_certificate(
            submitted=True,
            document_landlord_name="조춘근",
            contract_landlord_name="조춘근",
            issue_date="2024-09-01",
            as_of=date(2024, 9, 5),
        )
        self.assertEqual(result["riskLevel"], "safe")

    def test_name_mismatch_is_danger(self):
        result = check_tax_clearance_certificate(
            submitted=True,
            document_landlord_name="김아무개",
            contract_landlord_name="조춘근",
        )
        self.assertEqual(result["riskLevel"], "danger")
        self.assertIn("다릅니다", result["reason"])

    def test_stale_issue_date_is_caution(self):
        result = check_tax_clearance_certificate(
            submitted=True,
            issue_date="2024-01-01",
            as_of=date(2024, 9, 1),  # 8개월 지남
        )
        self.assertEqual(result["riskLevel"], "caution")

    def test_recent_issue_date_within_threshold_is_safe(self):
        result = check_tax_clearance_certificate(
            submitted=True,
            issue_date="2024-08-20",
            as_of=date(2024, 9, 1),  # 12일 지남, 기본 임계값 30일 이내
        )
        self.assertEqual(result["riskLevel"], "safe")

    def test_name_mismatch_takes_priority_over_stale_date(self):
        # 이름 불일치(danger)와 오래된 발급일(caution)이 동시 발생하면 더 높은 danger가 최종
        result = check_tax_clearance_certificate(
            submitted=True,
            document_landlord_name="김아무개",
            contract_landlord_name="조춘근",
            issue_date="2024-01-01",
            as_of=date(2024, 9, 1),
        )
        self.assertEqual(result["riskLevel"], "danger")

    def test_no_optional_fields_still_works(self):
        # 이름/발급일 정보 없이 제출 여부만 아는 경우에도 에러 없이 동작해야 함
        result = check_tax_clearance_certificate(submitted=True)
        self.assertEqual(result["riskLevel"], "safe")

    def test_invalid_date_format_ignored_gracefully(self):
        result = check_tax_clearance_certificate(submitted=True, issue_date="not-a-date")
        self.assertEqual(result["riskLevel"], "safe")  # 파싱 실패해도 죽지 않고 무시


if __name__ == "__main__":
    unittest.main(verbosity=2)
