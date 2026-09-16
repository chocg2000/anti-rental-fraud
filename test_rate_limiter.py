"""
rate_limiter 단위 테스트
"""

import time
import unittest

from rate_limiter import is_rate_limited, reset_for_testing


class TestIsRateLimited(unittest.TestCase):

    def setUp(self):
        reset_for_testing()

    def test_allows_up_to_max_requests(self):
        for _ in range(3):
            self.assertFalse(is_rate_limited("1.2.3.4", "test", max_requests=3))

    def test_blocks_after_max_requests(self):
        for _ in range(3):
            is_rate_limited("1.2.3.4", "test", max_requests=3)
        self.assertTrue(is_rate_limited("1.2.3.4", "test", max_requests=3))

    def test_different_ips_have_independent_limits(self):
        for _ in range(3):
            is_rate_limited("1.2.3.4", "test", max_requests=3)
        self.assertFalse(is_rate_limited("5.6.7.8", "test", max_requests=3))

    def test_different_buckets_have_independent_limits(self):
        # 한 IP가 "assessment" 한도를 다 써도 "registry_upload"에는 영향이 없어야 한다.
        for _ in range(3):
            is_rate_limited("1.2.3.4", "assessment", max_requests=3)
        self.assertFalse(is_rate_limited("1.2.3.4", "registry_upload", max_requests=3))

    def test_old_requests_expire_out_of_window(self):
        for _ in range(3):
            is_rate_limited("1.2.3.4", "test", max_requests=3, window_seconds=0.05)
        time.sleep(0.1)
        self.assertFalse(is_rate_limited("1.2.3.4", "test", max_requests=3, window_seconds=0.05))


if __name__ == "__main__":
    unittest.main(verbosity=2)
