"""
gapgu_ocr_row_parser 단위 테스트
--------------------------------------
reconstruct_lines_from_clova_result()는 순수 기하학 계산이라 신뢰도가 높다 — 좌표
그룹핑/정렬 경계값을 집중적으로 검증한다. split_line_into_row()를 포함해 모듈
전체가 갑구/을구 실키 검증을 마쳤다(모듈 docstring 참고) — 아래 테스트 중 "2026-09-16"
날짜가 붙은 것들은 실제 클로바 OCR 응답에서 발견한 버그를 그대로 재현한 회귀 테스트다.
"""

import unittest

from gapgu_ocr_row_parser import (
    reconstruct_lines_from_clova_result,
    split_line_into_row,
    extract_rows_from_clova_result,
)
from registry_parser import parse_gapgu, parse_eulgu


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
                    field("2", 10, 190),  # 90px 차이 — 기본 임계값(30px) 초과
                ]
            }]
        }
        lines = reconstruct_lines_from_clova_result(clova_data)
        self.assertEqual(len(lines), 2)

    def test_rank_fragment_far_from_anchor_but_close_to_neighbor_joins_row(self):
        # 2026-09-16 을구 실키 검증(등기부등본_내아파트.pdf 7페이지)에서 발견한 실제
        # 좌표 그대로 재현. 같은 행 안에서도 컬럼마다 기준선이 어긋나 "상세란" 조각
        # (y=3125)이 정렬상 anchor가 되고, "순위번호"란 조각(y=3158)까지는 33px라
        # 예전(anchor 고정) 방식으로는 30px 임계값을 근소하게 넘겨 순위번호가 완전히
        # 다른 행으로 떨어져 나갔다. 연쇄 간격 클러스터링이면 직전 조각(y=3139)과는
        # 19px 차이라 자연스럽게 같은 행에 붙는다.
        clova_data = {
            "images": [{
                "fields": [
                    field("금138,000,000원", 3465, 3125),
                    field("채권최고액", 2943, 3127),
                    field("2007년11월7일", 1527, 3130),
                    field("근저당권설정", 642, 3139),
                    field("5", 363, 3158),  # anchor(3125)와는 33px, 직전 조각과는 19px
                ]
            }]
        }
        lines = reconstruct_lines_from_clova_result(clova_data)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("5 "))

    def test_empty_images_returns_empty_list(self):
        self.assertEqual(reconstruct_lines_from_clova_result({"images": []}), [])

    def test_missing_images_key_returns_empty_list(self):
        self.assertEqual(reconstruct_lines_from_clova_result({}), [])

    def test_rank_number_between_two_wrapped_subrows_joins_content_row(self):
        # 2026-09-15 실제 클로바 OCR 응답(등기부등본_내아파트.pdf 1페이지, 200 DPI)으로
        # 발견한 실제 간격을 그대로 재현한다: 그룹 anchor(행에서 가장 작은 y, 여기선
        # "1968년3월13일"의 3763)와 순위번호 "1"(3791)의 y차는 28px, 그 아래 "(전 1)"
        # 보조줄(3875)과는 84px 떨어져 있다 — 이전 임계값(12px)으로는 "1"이 어느 쪽에도
        # 못 붙고 혼자 떨어져 나와 소유권보존 행 전체가 파싱에서 누락됐었다.
        clova_data = {
            "images": [{
                "fields": [
                    field("1968년3월13일", 1537, 3763),  # 이 행의 anchor(가장 작은 y)
                    field("소유자", 2934, 3763),
                    field("소유권보존", 661, 3773),
                    field("1", 381, 3791),  # anchor와 28px, 아래 보조줄과는 84px 차이
                    field("(전", 270, 3875),
                    field("1)", 437, 3884),
                    field("제56호", 1537, 3875),
                ]
            }]
        }
        lines = reconstruct_lines_from_clova_result(clova_data)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("1 "))
        self.assertIn("소유권보존", lines[0])
        self.assertNotIn("소유권보존", lines[1])

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

    def test_cancellation_purpose_wrapped_across_three_lines_still_excludes_amount(self):
        # 2026-09-16 을구 실키 검증(debug_eulgu_ocr_call.py, 국토부 공식 샘플 등기부)으로
        # 발견한 실제 버그 그대로 재현. "1번근저당권설정, 2번근저당권설정등기말소"가 칸이
        # 좁아 물리적으로 세 줄("1번근저당권설정,"/"2번근저당권설정 제21825호 해지"/
        # "등기말소")로 찢어져 나온다 — y좌표 차이가 y_threshold(30)를 훌쩍 넘어 서로
        # 다른 "재조합 줄"로 잡히므로, 줄 단위 병합(_group_lines_into_row_blocks) 없이는
        # "등기말소" 키워드가 통째로 사라져 이미 말소된 근저당권이 여전히 유효한 것으로
        # 잘못 합산된다.
        clova_data = {
            "images": [{
                "fields": [
                    field("1", 10, 100), field("근저당권설정", 40, 100),
                    field("2020년1월1일", 200, 100),
                    field("채권최고액", 40, 140), field("금500,000,000원", 140, 140),
                    field("3", 10, 300), field("1번근저당권설정,", 40, 300),
                    field("2020년2월2일", 250, 300),
                    field("2번근저당권설정", 40, 340), field("제999호", 250, 340), field("해지", 320, 340),
                    field("등기말소", 40, 380),
                ]
            }]
        }

        rows = extract_rows_from_clova_result(clova_data)
        result = parse_eulgu(rows)

        self.assertEqual(result["seniorMortgageAmount"], 0)

    def test_footer_disclaimer_does_not_falsely_cancel_last_row(self):
        # 2026-09-16 을구 실키 검증으로 발견한 실제 위험 시나리오 재현: 대법원
        # 인터넷등기소가 모든 페이지 하단에 찍는 법적 고지문 "실선으로 그어진 부분은
        # 말소사항을 표시함"에 "말소"가 들어있고, 그 바로 앞줄 "11번 등기는 건물만에
        # 관한 것임"에는 "11번"이 들어있다. 이 두 줄이 마지막 데이터 행(11-1)에 그대로
        # 병합되면, 실제로는 유효한 11번 전세권(3억원)이 말소된 것으로 잘못 판정된다.
        clova_data = {
            "images": [{
                "fields": [
                    field("11", 10, 100), field("전세권설정", 40, 100),
                    field("2025년3월26일", 200, 100),
                    field("전세금", 40, 140), field("금300,000,000원", 140, 140),
                    field("11-1", 10, 300), field("11번", 40, 300),
                    field("등기는", 100, 300), field("건물만에", 180, 300),
                    field("관한", 260, 300), field("것임", 320, 300),
                    field("실선으로", 10, 500), field("그어진", 100, 500),
                    field("부분은", 180, 500), field("말소사항을", 260, 500),
                    field("표시함.", 400, 500),
                ]
            }]
        }

        rows = extract_rows_from_clova_result(clova_data)

        # 핵심 확인: 법적 고지문이 "11-1" 행(또는 그 어떤 행)에도 섞여 들어가면 안 된다.
        # 섞여 들어가면 registry_parser._find_canceled_ranks가 "11번...말소"를 찾아내
        # 실제로는 유효한 11번 전세권을 말소된 것으로 잘못 표시하게 된다.
        eleven_dash_one = next(r for r in rows if r["rank"] == "11-1")
        combined = eleven_dash_one["purpose"] + eleven_dash_one["detail"]
        self.assertNotIn("말소", combined)
        self.assertFalse(any("실선으로" in r["purpose"] + r["detail"] for r in rows))

        result = parse_eulgu(rows)
        self.assertEqual(result["seniorMortgageAmount"], 0)
        self.assertEqual(result["criticalKeywords"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
