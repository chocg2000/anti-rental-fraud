"""
fraud_pattern_rules 단위 테스트
"""

import unittest
from datetime import date

from fraud_pattern_rules import detect_new_villa_recent_ownership_change


class TestNewVillaRecentOwnershipChange(unittest.TestCase):

    def test_triggered_new_building_and_recent_transfer(self):
        history = [
            {"date": "2024-03-15", "ownerName": "건축주"},
            {"date": "2024-08-01", "ownerName": "무자력자"},  # 승인 후 5개월, 이전 후 얼마 안 됨
        ]
        result = detect_new_villa_recent_ownership_change(
            use_approval_date="20240301",
            ownership_history=history,
            as_of=date(2024, 9, 1),
        )
        self.assertTrue(result["triggered"])
        self.assertTrue(result["isNewBuilding"])
        self.assertTrue(result["isRecentOwnershipChange"])
        # 프론트(Step3Result)가 소유권 변동 타임라인을 그리는 데 쓰는 필드 — 입력을
        # 그대로/가공해 돌려주는 것뿐이라 판정 로직과 별개로 계약을 고정해둔다.
        self.assertEqual(result["ownershipHistory"], history)
        self.assertEqual(result["latestTransferDate"], "2024-08-01")

    def test_not_triggered_has_no_latest_transfer_date_without_history(self):
        result = detect_new_villa_recent_ownership_change(
            use_approval_date="20240301",
            ownership_history=[],
            as_of=date(2024, 9, 1),
        )
        self.assertIsNone(result["latestTransferDate"])
        self.assertEqual(result["ownershipHistory"], [])

    def test_not_triggered_old_building(self):
        result = detect_new_villa_recent_ownership_change(
            use_approval_date="20050815",  # 20년 다 된 건물
            ownership_history=[{"date": "2024-08-01", "ownerName": "새주인"}],
            as_of=date(2024, 9, 1),
        )
        self.assertFalse(result["triggered"])
        self.assertFalse(result["isNewBuilding"])

    def test_not_triggered_new_building_but_old_ownership(self):
        result = detect_new_villa_recent_ownership_change(
            use_approval_date="20240301",
            ownership_history=[{"date": "2020-01-01", "ownerName": "원소유자"}],  # 소유권 변경이 오래전
            as_of=date(2024, 9, 1),
        )
        self.assertFalse(result["triggered"])
        self.assertTrue(result["isNewBuilding"])
        self.assertFalse(result["isRecentOwnershipChange"])

    def test_no_ownership_history_not_triggered_but_flagged_undecidable(self):
        result = detect_new_villa_recent_ownership_change(
            use_approval_date="20240301",
            ownership_history=[],
            as_of=date(2024, 9, 1),
        )
        self.assertFalse(result["triggered"])
        self.assertIn("판별 불가", result["reason"])

    def test_invalid_date_format_treated_as_not_new(self):
        result = detect_new_villa_recent_ownership_change(
            use_approval_date="",
            ownership_history=[{"date": "2024-08-01", "ownerName": "새주인"}],
        )
        self.assertFalse(result["triggered"])
        self.assertFalse(result["isNewBuilding"])

    def test_boundary_exactly_at_threshold(self):
        # 정확히 365일째 - 경계값 포함 여부 확인
        result = detect_new_villa_recent_ownership_change(
            use_approval_date="20230901",
            ownership_history=[{"date": "2024-08-01", "ownerName": "새주인"}],
            as_of=date(2024, 9, 1),  # 사용승인일로부터 정확히 366일 (2024는 윤년)
        )
        # 365일 임계값을 하루 넘겼으므로 신축 아님으로 판정돼야 함
        self.assertFalse(result["isNewBuilding"])

    def test_multiple_transfers_uses_latest_only(self):
        result = detect_new_villa_recent_ownership_change(
            use_approval_date="20240301",
            ownership_history=[
                {"date": "2024-03-15", "ownerName": "건축주"},
                {"date": "2024-04-01", "ownerName": "중간소유자"},
                {"date": "2024-08-20", "ownerName": "최종소유자"},  # 가장 최근
            ],
            as_of=date(2024, 9, 1),
        )
        self.assertTrue(result["isRecentOwnershipChange"])
        self.assertIn("2024-08-20", result["reason"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
