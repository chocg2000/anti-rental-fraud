"""
registry_parser 단위 테스트
------------------------------
실제 PDF 없이, 갑구/을구 행 데이터를 직접 만들어서 핵심 판별 로직만 검증한다.
"""

import unittest

from registry_parser import parse_registry_rows, parse_gapgu, parse_eulgu


def gap_row(rank, purpose, cause="", detail="", receipt=""):
    return {"rank": rank, "purpose": purpose, "receipt": receipt, "cause": cause, "detail": detail}


def eul_row(rank, purpose, detail="", receipt=""):
    return {"rank": rank, "purpose": purpose, "receipt": receipt, "cause": "", "detail": detail}


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

    def test_owner_name_landing_in_receipt_field_is_still_found(self):
        # 2026-09-16 을구 배선 검증 중 실제 클로바 응답으로 발견한 회귀 버그 재현.
        # gapgu_ocr_row_parser._group_lines_into_row_blocks()가 여러 줄에 걸친 등기목적을
        # 병합하면서, 접수번호("제N호")가 원래보다 뒤에서 나타나는 실제 문서(등기부등본_
        # 내아파트.pdf 갑구 1번 행)에서는 split_line_into_row()의 receipt/detail 경계가
        # 밀려 "소유자 이윤재"가 detail이 아니라 receipt 쪽에 남는다. 이 경우에도
        # 소유권 이전 이력을 놓치면 안 된다.
        rows = [
            gap_row(
                "1", "소유권이전",
                cause="2001년 01월 09일",
                receipt="1999년3월19일 1999년2월10일 소유자 이윤재 581206-******* (전 3) 제33142호",
                detail="매매 경기 화성군 양감면 송산리 701-15",
            ),
        ]
        result = parse_gapgu(rows)
        self.assertEqual(result["ownershipHistory"], [{"date": "2001-01-09", "ownerName": "이윤재"}])


class TestParseEulgu(unittest.TestCase):

    def test_mortgage_amount_summed(self):
        rows = [
            eul_row("1", "근저당권설정", detail="채권최고액 금360,000,000원 채무자 홍길동"),
            eul_row("2", "근저당권설정", detail="채권최고액 금120,000,000원 채무자 홍길동"),
        ]
        result = parse_eulgu(rows)
        self.assertEqual(result["seniorMortgageAmount"], 480_000_000)
        self.assertEqual(result["estimatedActualDebt"], round(480_000_000 / 1.2))
        self.assertFalse(result["hasUnparsedMortgageAmount"])

    def test_active_mortgage_with_korean_numeral_amount_flagged_not_dropped(self):
        # 오래된 등기(1990년대)는 "금일천오백육십만원정"처럼 한글 숫자로 금액을 적어
        # _AMOUNT_PATTERN(아라비아 숫자만 인식)이 못 읽는다. 말소되지 않은 근저당인데
        # 조용히 무시하면 선순위채권 총액이 실제보다 적게 나오는 "거짓 안심"이 된다 —
        # 최소한 놓쳤다는 사실은 hasUnparsedMortgageAmount로 표시해야 한다.
        rows = [eul_row("1", "근저당권설정", detail="채권최고액 금일천오백육십만원정 채무자 소석두")]
        result = parse_eulgu(rows)
        self.assertEqual(result["seniorMortgageAmount"], 0)
        self.assertTrue(result["hasUnparsedMortgageAmount"])

    def test_cancelled_mortgage_with_korean_numeral_amount_not_flagged(self):
        # 말소된 근저당이면 애초에 합산 대상이 아니므로, 금액을 못 읽어도 놓친 게 없다 —
        # 불필요한 "확인 불가" 경고로 유저를 헷갈리게 하면 안 된다.
        rows = [
            eul_row("1", "근저당권설정", detail="채권최고액 금일천오백육십만원정"),
            eul_row("2", "1번근저당권설정등기말소"),
        ]
        result = parse_eulgu(rows)
        self.assertFalse(result["hasUnparsedMortgageAmount"])

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

    def test_single_line_cancelling_two_ranks_excludes_both(self):
        # 국토부 공식 샘플 등기부(등기부등본_내아파트.pdf, 집합건물 을구 3번 행)에서
        # 실제로 나온 표현 그대로 재현 — 한 줄이 "1번, 2번"을 한꺼번에 말소한다.
        # 예전 정규식은 첫 번째 순위번호만 잡아서 2번이 여전히 유효한 것으로
        # 잘못 합산되는 버그가 있었다 (2026-09-16 을구 실키 검증으로 발견).
        rows = [
            eul_row("1", "근저당권설정", detail="채권최고액 금360,000,000원"),
            eul_row("2", "근저당권설정", detail="채권최고액 금120,000,000원"),
            eul_row("3", "1번근저당권설정, 2번근저당권설정등기말소"),
        ]
        result = parse_eulgu(rows)
        self.assertEqual(result["seniorMortgageAmount"], 0)

    def test_amount_landing_in_receipt_field_is_still_summed(self):
        # 2026-09-16 을구 배선 검증 중 실제 클로바 응답으로 발견한 회귀 버그 재현
        # (test_owner_name_landing_in_receipt_field_is_still_found와 같은 원인 —
        # 등기부등본_내아파트.pdf 을구 4번 행에서 "채권최고액 금115,200,000원"이
        # split_line_into_row()에 의해 detail이 아니라 receipt 쪽에 남았다).
        rows = [
            eul_row(
                "4", "근저당권설정",
                receipt="2005년4월4일 2005년4월4일 채권최고액 금115,200,000원 제26863호",
                detail="설정계약 채무자 김하가",
            ),
        ]
        result = parse_eulgu(rows)
        self.assertEqual(result["seniorMortgageAmount"], 115_200_000)

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
