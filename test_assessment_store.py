"""
assessment_store 단위 테스트
------------------------------
매 테스트마다 독립된 인메모리 SQLite DB를 쓰도록 DB_PATH를 ":memory:"로 바꾸고
reset_for_testing()으로 캐싱된 커넥션을 강제로 새로 연결한다 — 실제 파일을
건드리지 않고, 테스트 간 데이터가 새어나가지 않는다.
"""

import unittest

import assessment_store
from assessment_store import save_assessment, get_assessment


class TestAssessmentStore(unittest.TestCase):

    def setUp(self):
        assessment_store.DB_PATH = ":memory:"
        assessment_store.reset_for_testing()

    def tearDown(self):
        assessment_store.reset_for_testing()

    def test_save_then_get_roundtrips(self):
        save_assessment("abc123", {"overallGrade": "safe", "reasons": ["이상 없음"]})

        result = get_assessment("abc123")

        self.assertEqual(result["overallGrade"], "safe")
        self.assertEqual(result["reasons"], ["이상 없음"])

    def test_unknown_id_returns_none(self):
        self.assertIsNone(get_assessment("존재하지않는id"))

    def test_overwrite_same_id_replaces_data(self):
        save_assessment("abc123", {"overallGrade": "safe"})
        save_assessment("abc123", {"overallGrade": "danger"})

        result = get_assessment("abc123")

        self.assertEqual(result["overallGrade"], "danger")

    def test_korean_text_roundtrips_correctly(self):
        # ensure_ascii=False로 저장하므로, 다시 읽었을 때 한글이 깨지거나
        # 유니코드 이스케이프 문자열로 남아있지 않아야 한다.
        save_assessment("abc123", {"reasons": ["임대인 불일치 — 위임장을 확인하세요"]})

        result = get_assessment("abc123")

        self.assertEqual(result["reasons"][0], "임대인 불일치 — 위임장을 확인하세요")

    def test_survives_connection_reset_when_backed_by_file(self):
        # ":memory:"가 아니라 실제 파일이었다면 커넥션을 새로 열어도(예: 프로세스 재시작을
        # 흉내) 데이터가 남아있어야 한다는 걸, 임시 파일로 검증한다.
        import tempfile
        import os as os_module

        fd, path = tempfile.mkstemp(suffix=".db")
        os_module.close(fd)
        try:
            assessment_store.DB_PATH = path
            assessment_store.reset_for_testing()
            save_assessment("abc123", {"overallGrade": "warning"})

            assessment_store.reset_for_testing()  # 새 커넥션 = 재시작 흉내
            result = get_assessment("abc123")

            self.assertEqual(result["overallGrade"], "warning")
        finally:
            assessment_store.reset_for_testing()
            os_module.unlink(path)

    def test_multiple_ids_independent(self):
        save_assessment("id1", {"overallGrade": "safe"})
        save_assessment("id2", {"overallGrade": "danger"})

        self.assertEqual(get_assessment("id1")["overallGrade"], "safe")
        self.assertEqual(get_assessment("id2")["overallGrade"], "danger")

    def test_cleanup_old_assessments_removes_records_older_than_30_days(self):
        with assessment_store._lock:
            conn = assessment_store._get_conn()
            conn.execute(
                "INSERT INTO assessments (id, data, created_at) VALUES (?, ?, ?)",
                ("old1", '{"overallGrade": "safe"}', '2020-01-01 00:00:00'),
            )
            conn.execute(
                "INSERT INTO assessments (id, data, created_at) VALUES (?, ?, ?)",
                ("new1", '{"overallGrade": "warning"}', '2030-01-01 00:00:00'),
            )
            conn.commit()

        removed = assessment_store.cleanup_old_assessments(days=30)

        self.assertEqual(removed, 1)
        self.assertIsNone(get_assessment("old1"))
        self.assertEqual(get_assessment("new1")["overallGrade"], "warning")


if __name__ == "__main__":
    unittest.main(verbosity=2)
