"""
전체 테스트 스위트 한 번에 실행
----------------------------------
이 폴더의 test_*.py를 전부 찾아서 한 번에 돌린다.
파일이 하나라도 빠져있으면 ModuleNotFoundError로 바로 드러나고,
어느 모듈을 고쳤을 때 다른 모듈이 조용히 깨지는지도 이걸로 잡아낸다.

실행: python run_all_tests.py
"""

import unittest

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=".", pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    print(f"총 {result.testsRun}개 테스트 실행 — "
          f"성공 {result.testsRun - len(result.failures) - len(result.errors)}, "
          f"실패 {len(result.failures)}, 에러 {len(result.errors)}")
    print("=" * 60)

    if not result.wasSuccessful():
        raise SystemExit(1)
