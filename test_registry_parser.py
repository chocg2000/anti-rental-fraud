"""
registry_parser 단위 테스트
------------------------------
실제 PDF 없이, 갑구/을구 행 데이터를 직접 만들어서 핵심 판별 로직만 검증한다.
"""

import unittest

from registry_parser import parse_registry_rows, parse_gapgu, parse_eulgu


def gap_row(rank, purpose, cause="", detail=""):
    return {"rank": rank, "purpose": purpose, "receipt": "", "cause": cause, "detail": detail}


def eul_row(rank, purpose, detail=""):
    return {"rank": rank, "purpose": purpose, "receipt": "", "cause": "", "detail": detail}


class TestParseGapgu(unittest.TestCase):

    def test_clean_registry_no_keywords(self):
        rows = [
            gap_row("1", "소유권보존", cause="2005년3월15일", detail="소유자 홍길동"),
        ]
        result = parse_gapgu(rows)
        self.assertEqual(result["criticalKeywords"], [])
        self.assertFalse(result["trustRegistered"])
        self.assertEqual(len(result["ownershipHistory"]), 1)
        self.assertEqual(result["ownershipHistory"][0]["ownerName"], "홍길동")

    def test_active_seizure_detected(self):
        rows = [
            gap_row("1", "소유권보존", cause="2005년3월15일", detail="소유자 홍길동"),
            gap_row("2", "가압류", cause="2020년1월5일 가압류결정", detail="청구금액 금50,000,000원"),
        ]
        result = parse_gapgu(rows)
        self.assertIn("가압류", result["criticalKeywords"])

    def test_cancelled_seizure_not_flagged(self):
        rows = [
            gap_row("1", "소유권보존", cause="2005년3월15일", detail="소유자 홍길동"),
            gap_row("2", "가압류", detail="청구금액 금50,000,000원"),
            gap_row("3", "2번가압류등기말소", cause="2021년1월1일 해제"),
        ]
        result = parse_gapgu(rows)
        # 말소됐으므로 danger 트리거 대상에서 제외돼야 한다
        self.assertNotIn("가압류", result["criticalKeywords"])

    def test_trust_detected(self):
        rows = [
            gap_row("1", "소유권보존", detail="소유자 홍길동"),
            gap_row("2", "소유권이전", cause="2022년1월1일 신탁", detail="수탁자 OO신탁 신탁"),
        ]
        result = parse_gapgu(rows)
        self.assertTrue(result["trustRegistered"])

    def test_ownership_history_multiple_transfers(self):
        rows = [
            gap_row("1", "소유권보존", cause="2005년3월15일", detail="소유자 홍길동"),
            gap_row("2", "소유권이전", cause="2015년6월1일 매매", detail="소유자 김철수"),
            gap_row("3", "소유권이전", cause="2024년1월10일 매매", detail="소유자 박영희"),
        ]
        result = parse_gapgu(rows)
        self.assertEqual(len(result["ownershipHistory"]), 3)
        self.assertEqual(result["ownershipHistory"][-1]["ownerName"], "박영희")
        self.assertEqual(result["ownershipHistory"][-1]["date"], "2024-01-10")

    def test_joint_owners_buyout_wrapped_across_two_lines_is_detected(self):
        # 2026-09-16 실키 검증(registry_gapgu_ocr.py)으로 실제 발견한 케이스 그대로 재현.
        # "공유자전원지분전부이전"이 등기목적 칸에서 "공유자전원지분전부"/"이전" 두 줄로
        # 잘려 찍혔고, "이전"만 있는 둘째 줄은 순위번호가 없어 행 재조합 단계에서
        # 노이즈로 걸러진다 — purpose에는 "지분전부"까지만 남는다.
        rows = [
            gap_row("1", "소유권이전", cause="1999년2월10일 매매", detail="소유자 이윤재"),
            gap_row("5", "공유자전원지분전부", cause="2015년7월17일 매매", detail="소유자 조춘근"),
        ]
        result = parse_gapgu(rows)
        self.assertEqual(
            result["ownershipHistory"],
            [
                {"date": "1999-02-10", "ownerName": "이윤재"},
                {"date": "2015-07-17", "ownerName": "조춘근"},
            ],
        )


class TestParseEulgu(unittest.TestCase):

    def test_mortgage_amount_summed(self):
        rows = [
            eul_row("1", "근저당권설정", detail="채권최고액 금360,000,000원 채무자 홍길동"),
            eul_row("2", "근저당권설정", detail="채권최고액 금120,000,000원 채무자 홍길동"),
        ]
        result = parse_eulgu(rows)
        self.assertEqual(result["seniorMortgageAmount"], 480_000_000)
        self.assertEqual(result["estimatedActualDebt"], round(480_000_000 / 1.2))

    def test_cancelled_mortgage_excluded_from_sum(self):
        rows = [
            eul_row("1", "근저당권설정", detail="채권최고액 금360,000,000원"),
            eul_row("2", "1번근저당권설정등기말소"),
        ]
        result = parse_eulgu(rows)
        self.assertEqual(result["seniorMortgageAmount"], 0)  # 말소됐으므로 합산에서 제외

    def test_active_and_cancelled_mixed(self):
        rows = [
            eul_row("1", "근저당권설정", detail="채권최고액 금360,000,000원"),
            eul_row("2", "1번근저당권설정등기말소"),
            eul_row("3", "근저당권설정", detail="채권최고액 금100,000,000원"),
        ]
        result = parse_eulgu(rows)
        # 1번은 말소, 3번만 유효 -> 100,000,000만 합산돼야 함
        self.assertEqual(result["seniorMortgageAmount"], 100_000_000)

    def test_joint_collateral_not_double_counted(self):
        # 건물 + 토지에 동일 채권최고액으로 공동담보 설정된 경우 1건으로만 합산
        rows = [
            eul_row("1", "근저당권설정", detail="채권최고액 금500,000,000원 공동담보 건물"),
            eul_row("2", "근저당권설정", detail="채권최고액 금500,000,000원 공동담보 토지"),
        ]
        result = parse_eulgu(rows)
        self.assertEqual(result["seniorMortgageAmount"], 500_000_000)  # 1,000,000,000이 아니라 500,000,000
        self.assertTrue(result["jointCollateralDetected"])

    def test_leasehold_registration_order_detected(self):
        rows = [
            eul_row("1", "임차권등기명령", detail="임차보증금 금80,000,000원 임차인 이순신"),
        ]
        result = parse_eulgu(rows)
        self.assertIn("임차권등기명령", result["criticalKeywords"])


class TestParseRegistryRowsIntegration(unittest.TestCase):

    def test_full_flow_combines_gapgu_and_eulgu(self):
        gapgu = [
            gap_row("1", "소유권보존", cause="2005년3월15일", detail="소유자 홍길동"),
            gap_row("2", "가압류", detail="청구금액 금50,000,000원"),
        ]
        eulgu = [
            eul_row("1", "근저당권설정", detail="채권최고액 금360,000,000원"),
        ]
        result = parse_registry_rows(gapgu, eulgu)

        self.assertEqual(result["ownerName"], "홍길동")
        self.assertIn("가압류", result["criticalKeywords"])
        self.assertEqual(result["seniorMortgageAmount"], 360_000_000)
        self.assertFalse(result["trustRegistered"])

    def test_completely_clean_registry(self):
        gapgu = [gap_row("1", "소유권보존", cause="2010년1월1일", detail="소유자 이몽룡")]
        eulgu = []
        result = parse_registry_rows(gapgu, eulgu)

        self.assertEqual(result["criticalKeywords"], [])
        self.assertEqual(result["seniorMortgageAmount"], 0)
        self.assertFalse(result["trustRegistered"])
        self.assertFalse(result["jointCollateralDetected"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
