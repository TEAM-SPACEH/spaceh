"""access_repository 테스트. MySQL 은 가짜 연결로, Chroma 는 임시 폴더의 진짜 Chroma 로 확인한다.

실행: python -m unittest tests.admin.test_access_repository
확인 대상: UPDATE 바인딩, Chroma 청크 메타데이터 갱신(다른 값 보존), Chroma 실패 시 MySQL 롤백, LIKE 이스케이프.
"""

import tempfile
import unittest
from datetime import datetime
from unittest.mock import patch

import chromadb

from app.admin.repositories import access_repository
from core import config


class FakeCursor:
    """실행된 SQL·바인딩 값을 기록하고 미리 정한 결과를 돌려준다."""

    def __init__(self, one=None):
        self.executed: list[tuple[str, object]] = []
        self._one = list(one or [])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return []


class FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


class _Connection:
    """get_connection 대용. 블록이 예외로 끝나면 rolled_back 이 True 가 된다 (실제 get_connection 과 같은 규칙)."""

    def __init__(self, cursor):
        self.conn = FakeConn(cursor)
        self.rolled_back = False
        self.committed = False

    def __call__(self):
        return self

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.rolled_back = True
        else:
            self.committed = True
        return False


class UpdateGroupShareTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        patcher = patch.object(config, "CHROMA_DIR", tmp.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.shared_at = datetime(2026, 10, 28, 9, 0, 0)

    def _seed_chroma(self):
        client = chromadb.PersistentClient(path=config.CHROMA_DIR)
        collection = client.get_or_create_collection(config.CHROMA_COLLECTION)
        collection.add(
            ids=["doc-1#0001", "doc-1#0002", "doc-2#0001"],
            embeddings=[[0.1, 0.2], [0.2, 0.3], [0.3, 0.4]],
            metadatas=[
                {"doc_id": "doc-1", "company_id": "MVX", "is_group_shared": False},
                {"doc_id": "doc-1", "company_id": "MVX", "is_group_shared": False},
                {"doc_id": "doc-2", "company_id": "ELV", "is_group_shared": False},
            ],
        )
        client.close()

    def _read_chroma(self):
        client = chromadb.PersistentClient(path=config.CHROMA_DIR)
        try:
            return client.get_collection(config.CHROMA_COLLECTION).get(include=["metadatas"])
        finally:
            client.close()

    def test_updates_mysql_and_only_that_documents_chunks(self):
        """MySQL 은 %s 바인딩으로 바뀌고, Chroma 는 그 문서의 청크 값만 바뀌며 다른 메타데이터는 그대로다."""
        self._seed_chroma()
        cursor = FakeCursor()
        connection = _Connection(cursor)

        with patch.object(access_repository, "get_connection", connection):
            access_repository.update_group_share("doc-1", True, 7, self.shared_at)

        sql, params = cursor.executed[0]
        self.assertIn("UPDATE documents SET is_group_shared = %s", sql)
        self.assertEqual(params, (1, 7, self.shared_at, "doc-1"))
        self.assertTrue(connection.committed)

        stored = dict(zip(*[self._read_chroma()[k] for k in ("ids", "metadatas")]))
        self.assertIs(stored["doc-1#0001"]["is_group_shared"], True)
        self.assertIs(stored["doc-1#0002"]["is_group_shared"], True)
        self.assertEqual(stored["doc-1#0001"]["company_id"], "MVX")
        self.assertIs(stored["doc-2#0001"]["is_group_shared"], False)

    def test_chroma_failure_rolls_back_mysql(self):
        """Chroma 갱신이 실패하면 예외가 올라가 MySQL 이 롤백된다."""
        connection = _Connection(FakeCursor())

        with patch.object(access_repository, "get_connection", connection), patch.object(
            access_repository, "_sync_chroma", side_effect=RuntimeError("chroma down")
        ):
            with self.assertRaises(RuntimeError):
                access_repository.update_group_share("doc-1", True, 7, self.shared_at)

        self.assertTrue(connection.rolled_back)

    def test_missing_collection_is_skipped(self):
        """색인 전이라 컬렉션이 없으면 MySQL 만 바꾸고 오류 없이 끝난다."""
        connection = _Connection(FakeCursor())

        with patch.object(access_repository, "get_connection", connection), self.assertLogs(
            access_repository.logger, level="WARNING"
        ):
            access_repository.update_group_share("doc-1", True, 7, self.shared_at)

        self.assertTrue(connection.committed)


class ListDocumentsTest(unittest.TestCase):
    def test_builds_parameterized_query_with_escaped_like(self):
        """값은 모두 바인딩으로 넘기고, 검색어의 % _ 는 글자 그대로 찾는다."""
        cursor = FakeCursor(one=[{"total": 0}])

        with patch.object(access_repository, "get_connection", _Connection(cursor)):
            access_repository.list_documents(("internal", "confidential"), "MVX", "100%_a", False, 20, 40)

        count_sql, count_params = cursor.executed[0]
        self.assertIn("access_level IN (%s, %s)", count_sql)
        self.assertIn("company_id = %s", count_sql)
        self.assertIn("(title LIKE %s OR file_name LIKE %s)", count_sql)
        self.assertNotIn("100", count_sql)  # 검색어는 SQL 문자열에 들어가지 않는다
        # 제목·파일명 두 곳에서 같은 패턴을 찾으므로 검색어 값이 두 번 들어간다.
        self.assertEqual(count_params, ["internal", "confidential", "MVX", "%100\\%\\_a%", "%100\\%\\_a%", 0])
        _, list_params = cursor.executed[1]
        self.assertEqual(list_params[-2:], [20, 40])


class CountShareStatusTest(unittest.TestCase):
    def test_counts_are_bound_and_scoped_by_company(self):
        """회사 코드는 바인딩으로 넘기고, 세 값을 정수로 돌려준다."""
        cursor = FakeCursor(one=[{"shared": 3, "unshared": 5, "confidential": 2}])
        with patch.object(access_repository, "get_connection", _Connection(cursor)):
            got = access_repository.count_share_status("MVX")

        self.assertEqual(got, {"shared": 3, "unshared": 5, "confidential": 2})
        sql, params = cursor.executed[0]
        self.assertIn("WHERE company_id = %s", sql)
        self.assertEqual(params, ["MVX"])

    def test_all_companies_has_no_where(self):
        """회사를 정하지 않으면(최종 어드민 전체) WHERE 가 없다."""
        cursor = FakeCursor(one=[{"shared": 0, "unshared": 0, "confidential": 0}])
        with patch.object(access_repository, "get_connection", _Connection(cursor)):
            access_repository.count_share_status(None)
        self.assertNotIn("WHERE", cursor.executed[0][0])
        self.assertEqual(cursor.executed[0][1], [])


class GetCompanyNameTest(unittest.TestCase):
    def test_returns_name_or_none(self):
        """회사 코드는 바인딩으로 넘기고, 없는 코드는 None 이다."""
        cursor = FakeCursor(one=[{"name": "현대무벡스"}, None])
        with patch.object(access_repository, "get_connection", _Connection(cursor)):
            self.assertEqual(access_repository.get_company_name("MVX"), "현대무벡스")
            self.assertIsNone(access_repository.get_company_name("XXX"))
        self.assertEqual(cursor.executed[0][1], ("MVX",))


if __name__ == "__main__":
    unittest.main()
