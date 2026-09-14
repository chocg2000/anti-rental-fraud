"""
registry_summary_parser 단위 테스트
--------------------------------------
REAL_OCR_TEXT는 Mocking이 아니라 2026-09-12 실제 등기부등본 PDF를
Tesseract(kor)로 OCR 돌려서 나온 원문 그대로다 (경기 성남시 분당구 야탑동
335 장미마을 822동 204호, 요약 페이지).
"""

import unittest

from registry_summary_parser import (
    parse_summary_ownership,
    parse_summary_rights,
    parse_summary_registry,
)

REAL_OCR_TEXT = """즈     ,              ^     =
주요 등기사항 요약 (참고용)
[주의사항]
본 주요 둥기사항 요약은 중명서상에 말소되지 않은 사항을 간략히 요약한 것으로 증명서로서의 기능을 제공하지 않습니다.
실제 권리사항 파악을 위해서는 발급된 중명서를 필히 확인하시기 바랍니다.
고유번호 1356-1996-092460
[집합건물] 경기도 성남시 분당구 야탑동 335 장미마을 제822동 제2충 제204호
1. 소유지분현황 ( 갑구 )
조춘근 (소유자) | 670209-1788617 | 단독소유    경기도 성남시 분당구 장미로 101, 822동            5
204호(야탑동, 장미마을)
2. 소유지분을 제외한 소유권에 관한 사항 ( 갑구 )
- 기록자항 없음
3. (근)저당권 및 전세권 등 ( 을구 )
11    전세권설정          2025년3월26일 | 전세금 _금300,000,000원                     조춘근
제1247861호  전세권자 주식회사지음이엔지
[참고사항]
가. 등기기록에서 유효한 지분을 가진 소유자 혹은 공유자 현황을 가나다 순으로 표시합니다.                      ,
"""


class TestParseSummaryOwnership(unittest.TestCase):

    def test_real_ocr_owner_extracted(self):
        section1 = REAL_OCR_TEXT.split("1. 소유지분현황")[1].split("2. 소유지분")[0]
        owners = parse_summary_ownership(section1)

        self.assertEqual(len(owners), 1)
        self.assertEqual(owners[0]["ownerName"], "조춘근")
        self.assertEqual(owners[0]["shareType"], "단독소유")

    def test_no_registration_number_leaked(self):
        # 개인정보(주민등록번호)가 결과 dict 어디에도 남아있으면 안 된다
        section1 = REAL_OCR_TEXT.split("1. 소유지분현황")[1].split("2. 소유지분")[0]
        owners = parse_summary_ownership(section1)

        self.assertNotIn("670209", str(owners))

    def test_no_record_returns_empty(self):
        owners = parse_summary_ownership("- 기록사항 없음")
        self.assertEqual(owners, [])

    def test_co_owners_both_extracted(self):
        text = (
            "김형진 (공유자) | 740820-1234567 | 공유    경기도 성남시            4\n"
            "장형순 (공유자) | 750928-7654321 | 공유    경기도 성남시            4\n"
        )
        owners = parse_summary_ownership(text)
        names = [o["ownerName"] for o in owners]
        self.assertIn("김형진", names)
        self.assertIn("장형순", names)


class TestParseSummaryRights(unittest.TestCase):

    def test_real_ocr_jeonse_right_extracted(self):
        section3 = REAL_OCR_TEXT.split("3. (근)저당권")[1].split("[참고사항]")[0]
        rights = parse_summary_rights(section3)

        self.assertEqual(len(rights), 1)
        self.assertEqual(rights[0]["rightType"], "전세권설정")
        self.assertEqual(rights[0]["amount"], 300_000_000)
        self.assertEqual(rights[0]["receivedDate"], "2025-03-26")

    def test_missing_date_returns_none_not_crash(self):
        text = "4    근저당권설정          채권최고액 금115,200,000원          김하기\n"
        rights = parse_summary_rights(text)
        self.assertIsNone(rights[0]["receivedDate"])

    def test_no_record_returns_empty(self):
        rights = parse_summary_rights("- 기록사항 없음")
        self.assertEqual(rights, [])

    def test_multiple_rights_summed_correctly(self):
        text = (
            "4    근저당권설정          2005년4월4일 | 채권최고액 금115,200,000원          김하기\n"
            "11   전세권설정          2025년3월26일 | 전세금 금300,000,000원              조춘근\n"
        )
        rights = parse_summary_rights(text)
        self.assertEqual(len(rights), 2)
        total = sum(r["amount"] for r in rights)
        self.assertEqual(total, 415_200_000)


class TestParseSummaryRegistryIntegration(unittest.TestCase):

    def test_full_real_document_end_to_end(self):
        result = parse_summary_registry(REAL_OCR_TEXT)

        self.assertEqual(len(result["owners"]), 1)
        self.assertEqual(result["owners"][0]["ownerName"], "조춘근")
        self.assertEqual(len(result["activeRights"]), 1)
        self.assertEqual(result["totalSeniorSecuredAmount"], 300_000_000)

    def test_section_markers_robust_to_stray_numbers(self):
        # 짧은 '1.'/'2.'/'3.' 마커를 썼다면, 본문 중간에 우연히 등장하는 숫자+마침표
        # (예: 주소의 "204호" 앞 순위번호 "5", 또는 다른 문장의 "2." 표기)에 의해
        # 섹션이 잘못 잘릴 위험이 있다. 전체 문구 마커로 바꿔서 이를 방지했는지 확인.
        noisy_text = (
            "1. 소유지분현황 ( 갑구 )\n"
            "조춘근 (소유자) | 670209-1788617 | 단독소유    참고: 2. 3층 계약 관련 별첨 문서 있음     5\n"
            "2. 소유지분을 제외한 소유권에 관한 사항 ( 갑구 )\n"
            "- 기록사항 없음\n"
            "3. (근)저당권 및 전세권 등 ( 을구 )\n"
            "11    전세권설정          2025년3월26일 | 전세금 금300,000,000원              조춘근\n"
            "[참고사항]\n"
        )
        result = parse_summary_registry(noisy_text)

        # 본문 중간의 가짜 "2."에 낚여서 섹션1이 잘못 잘리면 소유자를 못 찾는다.
        self.assertEqual(len(result["owners"]), 1)
        self.assertEqual(result["owners"][0]["ownerName"], "조춘근")
        self.assertEqual(result["totalSeniorSecuredAmount"], 300_000_000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
