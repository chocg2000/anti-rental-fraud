"""
gapgu_ocr_row_parser 단위 테스트
--------------------------------------
reconstruct_lines_from_clova_result()는 순수 기하학 계산이라 신뢰도가 높다 — 좌표
그룹핑/정렬 경계값을 집중적으로 검증한다.
split_line_into_row()는 ⚠️ 미검증 로직(모듈 docstring 참고)이므로, 여기서는 "내가
설계한 규칙대로 정확히 동작하는가"만 검증한다 — 실제 클로바 OCR 결과와 일치한다는
보장은 아니다.
"""

import unittest

from gapgu_ocr_row_parser import (
    reconstruct_lines_from_clova_result,
    split_line_into_row,
    extract_rows_from_clova_result,
)
from registry_parser import parse_gapgu


def field(text, x, y):
    return {"inferText": text, "boundingPoly": {"vertices": [{"x": x, "y": y}]}}


class TestReconstructLines(unittest.TestCase):

    def test_single_row_fragments_joined_in_x_order(self):
        clova_data = {
            "images": [{
                "fields": [
                    field("이전", 60, 100),
                    field("1", 10, 100),
                    field("소유권", 30, 100),
                ]
            }]
        }
        lines = reconstruct_lines_from_clova_result(clova_data)
        self.assertEqual(lines, ["1 소유권 이전"])

    def test_two_rows_sorted_top_to_bottom(self):
        clova_data = {
            "images": [{
                "fields": [
                    field("2", 10, 200),
                    field("1", 10, 100),
                ]
            }]
        }
        lines = reconstruct_lines_from_clova_result(clova_data)
        self.assertEqual(lines, ["1", "2"])

    def test_slightly_tilted_scan_within_threshold_same_row(self):
        # 스캔이 살짝 기울어져 같은 행인데 y좌표가 몇 픽셀 다른 경우
        clova_data = {
            "images": [{
                "fields": [
                    field("1", 10, 100),
                    field("소유권이전", 40, 105),  # y가 5px 다름 — 기본 임계값(12px) 이내
                ]
            }]
        }
        lines = reconstruct_lines_from_clova_result(clova_data)
        self.assertEqual(len(lines), 1)

    def test_y_difference_beyond_threshold_is_separate_row(self):
        clova_data = {
            "images": [{
                "fields": [
                    field("1", 10, 100),
                    field("2", 10, 130),  # 30px 차이 — 기본 임계값(12px) 초과
                ]
            }]
        }
        lines = reconstruct_lines_from_clova_result(clova_data)
        self.assertEqual(len(lines), 2)

    def test_empty_images_returns_empty_list(self):
        self.assertEqual(reconstruct_lines_from_clova_result({"images": []}), [])

    def test_missing_images_key_returns_empty_list(self):
        self.assertEqual(reconstruct_lines_from_clova_result({}), [])

    def test_field_without_text_or_coords_ignored(self):
        clova_data = {
            "images": [{
                "fields": [
                    field("1", 10, 100),
                    {"inferText": "", "boundingPoly": {"vertices": [{"x": 5, "y": 100}]}},
                    {"inferText": "무시됨", "boundingPoly": {"vertices": []}},
                ]
            }]
        }
        lines = reconstruct_lines_from_clova_result(clova_data)
        self.assertEqual(lines, ["1"])


class TestSplitLineIntoRow(unittest.TestCase):

    def test_ownership_transfer_line_extracts_columns(self):
        line = "2 소유권이전 2021년3월10일 제5678호 2021년3월5일 매매 소유자 홍길동 서울시 강남구"
        row = split_line_into_row(line)

        self.assertEqual(row["rank"], "2")
        self.assertEqual(row["purpose"], "소유권이전")
        self.assertIn("2021년3월10일", row["receipt"])
        self.assertIn("제5678호", row["receipt"])
        self.assertIn("2021년3월5일", row["cause"])
        self.assertIn("홍길동", row["detail"])

    def test_ownership_preservation_line_without_cause_date(self):
        # 소유권보존은 "등기원인" 자체가 없는 게 보통이다 — 날짜가 하나(접수일)뿐인 경우
        line = "1 소유권보존 2020년1월2일 제1234호 소유자 조춘근 경기도 성남시"
        row = split_line_into_row(line)

        self.assertEqual(row["purpose"], "소유권보존")
        self.assertEqual(row["cause"], "")
        self.assertIn("조춘근", row["detail"])

    def test_supplementary_registration_rank_with_hyphen(self):
        line = "3-1 근저당권변경 2022년5월1일 제9999호 채권최고액 변경"
        row = split_line_into_row(line)
        self.assertEqual(row["rank"], "3-1")

    def test_line_without_leading_rank_returns_none(self):
        # 섹션 제목이나 표 머리말처럼 순위번호로 시작하지 않는 줄은 데이터 행이 아니다
        self.assertIsNone(split_line_into_row("소유권에 관한 사항 (갑구)"))

    def test_cancellation_entry_without_vocabulary_match_still_gets_purpose(self):
        line = "2 3번가압류등기말소 2022년6월1일 제1111호"
        row = split_line_into_row(line)
        self.assertEqual(row["rank"], "2")
        self.assertIn("말소", row["purpose"])


class TestExtractRowsIntegration(unittest.TestCase):
    """OCR 재조합 -> 컬럼 분리 -> parse_gapgu()까지 전체 파이프라인이 이어지는지 확인."""

    def test_end_to_end_ownership_history_reaches_parse_gapgu(self):
        clova_data = {
            "images": [{
                "fields": [
                    field("1", 10, 100), field("소유권보존", 40, 100),
                    field("2020년1월2일", 120, 100), field("제1234호", 200, 100),
                    field("소유자", 260, 100), field("조춘근", 300, 100),
                    field("2", 10, 140), field("소유권이전", 40, 140),
                    field("2021년3월10일", 120, 140), field("제5678호", 200, 140),
                    field("2021년3월5일", 260, 140), field("매매", 340, 140),
                    field("소유자", 380, 140), field("홍길동", 420, 140),
                ]
            }]
        }

        rows = extract_rows_from_clova_result(clova_data)
        result = parse_gapgu(rows)

        names = [h["ownerName"] for h in result["ownershipHistory"]]
        self.assertIn("조춘근", names)
        self.assertIn("홍길동", names)

    def test_end_to_end_cancelled_seizure_not_flagged(self):
        # 회귀 테스트: purpose를 어휘 매칭으로 "가압류"만 뽑아버리면 "말소" 텍스트가
        # 잘려나가 registry_parser의 취소 판별(_CANCEL_REF_PATTERN)이 깨진다.
        clova_data = {
            "images": [{
                "fields": [
                    field("1", 10, 100), field("가압류", 40, 100),
                    field("2020년1월1일", 120, 100), field("제1000호", 200, 100),
                    field("2", 10, 140), field("1번가압류등기말소", 40, 140),
                    field("2020년6월1일", 200, 140), field("제2000호", 280, 140),
                ]
            }]
        }

        rows = extract_rows_from_clova_result(clova_data)
        result = parse_gapgu(rows)

        self.assertNotIn("가압류", result["criticalKeywords"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
