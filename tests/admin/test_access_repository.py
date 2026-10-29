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


class _EventCursor(FakeCursor):
    """실행 순서를 공용 events 목록에 남기고, 지정한 번째 execute 에서 오류를 낸다 (순서·되돌리기 검증용)."""

    def __init__(self, events, fail_on=()):
        super().__init__()
        self.events = events
        self.fail_on = set(fail_on)

    def execute(self, sql, params=()):
        super().execute(sql, params)
        self.events.append(("mysql", params))
        if len(self.executed) in self.fail_on:
            raise RuntimeError("mysql down")


PREVIOUS = {"is_group_shared": 0, "shared_by": 5, "shared_at": datetime(2026, 10, 1, 9, 0, 0)}


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

    def _run(self, share_enabled, events, *, mysql_fail_on=(), chroma_fail_on=(), previous=PREVIOUS):
        """저장소 호출을 순서 기록과 함께 실행한다. Chroma 는 호출마다 events 에 ("chroma", 값)을 남기는 가짜로 바꾼다."""
        cursor = _EventCursor(events, mysql_fail_on)
        calls = []

        def fake_sync(doc_id, enabled):
            calls.append(enabled)
            events.append(("chroma", enabled))
            if len(calls) in chroma_fail_on:
                raise RuntimeError("chroma down")

        with patch.object(access_repository, "get_connection", _Connection(cursor)), patch.object(
            access_repository, "_sync_chroma", side_effect=fake_sync
        ):
            access_repository.update_group_share("doc-1", share_enabled, 7, self.shared_at, previous)
        return cursor

    def test_updates_mysql_and_only_that_documents_chunks(self):
        """MySQL 은 %s 바인딩으로 바뀌고, Chroma 는 그 문서의 청크 값만 바뀌며 다른 메타데이터는 그대로다."""
        self._seed_chroma()
        cursor = FakeCursor()
        connection = _Connection(cursor)

        with patch.object(access_repository, "get_connection", connection):
            access_repository.update_group_share("doc-1", True, 7, self.shared_at, PREVIOUS)

        sql, params = cursor.executed[0]
        self.assertIn("UPDATE documents SET is_group_shared = %s", sql)
        self.assertEqual(params, (1, 7, self.shared_at, "doc-1"))
        self.assertTrue(connection.committed)

        stored = dict(zip(*[self._read_chroma()[k] for k in ("ids", "metadatas")]))
        self.assertIs(stored["doc-1#0001"]["is_group_shared"], True)
        self.assertIs(stored["doc-1#0002"]["is_group_shared"], True)
        self.assertEqual(stored["doc-1#0001"]["company_id"], "MVX")
        self.assertIs(stored["doc-2#0001"]["is_group_shared"], False)

    def test_turning_on_commits_mysql_first_then_turns_chroma_on(self):
        """켤 때는 MySQL 을 먼저 확정하고 그다음에 Chroma 를 켠다 (Chroma 가 먼저 열리는 순간이 없다)."""
        events = []
        self._run(True, events)
        self.assertEqual([e[0] for e in events], ["mysql", "chroma"])
        self.assertIs(events[1][1], True)

    def test_turning_off_turns_chroma_off_first_then_commits_mysql(self):
        """끌 때는 Chroma 를 먼저 끄고 MySQL 을 확정한다 (MySQL 이 실패해도 Chroma 는 이미 닫혀 있다)."""
        events = []
        self._run(False, events, previous={**PREVIOUS, "is_group_shared": 1})
        self.assertEqual([e[0] for e in events], ["chroma", "mysql"])
        self.assertIs(events[0][1], False)

    def test_turning_on_restores_mysql_when_chroma_fails(self):
        """켜는 중 Chroma 가 실패하면 MySQL 을 이전 값(공유 여부·변경자·시각)으로 되돌리고 원래 오류를 올린다."""
        events = []
        with self.assertRaisesRegex(RuntimeError, "chroma down"):
            self._run(True, events, chroma_fail_on=(1,))

        self.assertEqual([e[0] for e in events], ["mysql", "chroma", "mysql"])
        self.assertEqual(events[0][1][0], 1)  # 먼저 켰다가
        self.assertEqual(events[2][1], (0, 5, PREVIOUS["shared_at"], "doc-1"))  # 이전 값으로 복원

    def test_turning_off_restores_chroma_when_mysql_fails(self):
        """끄는 중 MySQL 이 실패하면 Chroma 를 이전 값(켜짐)으로 되돌리고 원래 오류를 올린다."""
        events = []
        with self.assertRaisesRegex(RuntimeError, "mysql down"):
            self._run(False, events, mysql_fail_on=(1,), previous={**PREVIOUS, "is_group_shared": 1})

        self.assertEqual(events[0], ("chroma", False))
        self.assertEqual(events[-1], ("chroma", True))

    def test_mysql_failure_before_anything_changed_leaves_chroma_alone_when_turning_on(self):
        """켤 때 MySQL 자체가 실패하면 Chroma 는 건드리지 않는다 (둘 다 이전 상태)."""
        events = []
        with self.assertRaisesRegex(RuntimeError, "mysql down"):
            self._run(True, events, mysql_fail_on=(1,))
        self.assertEqual([e[0] for e in events], ["mysql"])

    def test_failed_restore_is_logged_and_original_error_is_kept(self):
        """되돌리기까지 실패해도 원래 오류가 올라가고, 수동 확인이 필요하다는 로그가 남는다 (Chroma 는 닫힌 쪽)."""
        events = []
        # 켜는 중: MySQL 쓰기(1번) 성공, Chroma 실패, 복원용 MySQL 쓰기(2번) 실패
        with self.assertLogs(access_repository.logger, level="ERROR") as logs, self.assertRaisesRegex(
            RuntimeError, "chroma down"
        ):
            self._run(True, events, chroma_fail_on=(1,), mysql_fail_on=(2,))
        self.assertTrue(any("수동 확인 필요" in line for line in logs.output))

    def test_missing_collection_is_skipped(self):
        """색인 전이라 컬렉션이 없으면 MySQL 만 바꾸고 오류 없이 끝난다."""
        connection = _Connection(FakeCursor())

        with patch.object(access_repository, "get_connection", connection), self.assertLogs(
            access_repository.logger, level="WARNING"
        ):
            access_repository.update_group_share("doc-1", True, 7, self.shared_at, PREVIOUS)

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
