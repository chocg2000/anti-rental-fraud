"""
priority_region_classifier 단위 테스트
------------------------------------------
지역 등급 판정 자체가 최우선변제금 계산의 입력값이라, 여기서 틀리면 뒤의 모든 계산이
틀어진다. 특히 "일부 동만 걸치는 예외 지역은 unknown을 반환해야 한다"는 게 이 모듈의
핵심 안전장치이므로 그 경계를 집중적으로 검증한다.
"""

import unittest

from priority_region_classifier import classify_priority_region


class TestClassifyPriorityRegion(unittest.TestCase):

    def test_seoul_road_address(self):
        self.assertEqual(classify_priority_region("서울특별시 강남구 테헤란로 427"), "seoul")

    def test_seoul_short_form(self):
        self.assertEqual(classify_priority_region("서울 강남구 테헤란로 427"), "seoul")

    def test_overcrowded_gyeonggi_city(self):
        self.assertEqual(classify_priority_region("경기도 성남시 분당구 야탑동 335"), "overcrowded")

    def test_overcrowded_incheon_full_gu(self):
        self.assertEqual(classify_priority_region("인천광역시 연수구 송도동 123"), "overcrowded")

    def test_overcrowded_sejong(self):
        self.assertEqual(classify_priority_region("세종특별자치시 어진동 1"), "overcrowded")

    def test_overcrowded_yongin(self):
        self.assertEqual(classify_priority_region("경기도 용인시 수지구 1"), "overcrowded")

    def test_metropolitan_busan(self):
        self.assertEqual(classify_priority_region("부산광역시 해운대구 1"), "metropolitan")

    def test_metropolitan_gyeonggi_ansan(self):
        self.assertEqual(classify_priority_region("경기도 안산시 단원구 1"), "metropolitan")

    def test_metropolitan_gyeonggi_gwangju(self):
        # 경기도 광주시(3호)와 광주광역시(3호)는 둘 다 같은 등급이라 혼동해도 결과는 같다
        self.assertEqual(classify_priority_region("경기도 광주시 1"), "metropolitan")

    def test_other_gangwon(self):
        self.assertEqual(classify_priority_region("강원특별자치도 춘천시 1"), "other")

    def test_other_jeju(self):
        self.assertEqual(classify_priority_region("제주특별자치도 제주시 1"), "other")

    def test_clearly_other_incheon_ganghwa(self):
        # 인천이지만 강화군은 과밀억제권역에서 명시적으로 제외됨 — "그 밖의 지역" 확정
        self.assertEqual(classify_priority_region("인천광역시 강화군 1"), "other")

    def test_ambiguous_namyangju_returns_unknown(self):
        # 남양주시는 특정 동(호평동 등)만 과밀억제권역 — 주소만으론 정밀 판정 불가
        self.assertIsNone(classify_priority_region("경기도 남양주시 호평동 1"))

    def test_ambiguous_siheung_returns_unknown(self):
        self.assertIsNone(classify_priority_region("경기도 시흥시 정왕동 1"))

    def test_ambiguous_incheon_seogu_returns_unknown(self):
        self.assertIsNone(classify_priority_region("인천광역시 서구 청라동 1"))

    def test_empty_address_returns_unknown(self):
        self.assertIsNone(classify_priority_region(""))

    def test_none_address_returns_unknown(self):
        self.assertIsNone(classify_priority_region(None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
