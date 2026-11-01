"""audit_repository 테스트. 실제 MySQL 없이 가짜 커서로 실행된 SQL·바인딩 값만 확인한다."""

import json
import unittest
from contextlib import contextmanager
from datetime import datetime
from unittest.mock import patch

from app.admin.repositories import audit_repository


class FakeCursor:
    """실행된 SQL·바인딩 값을 기록하고, 미리 정해 둔 결과를 돌려준다 (MySQL 없이 검증)."""

    def __init__(self, one=None, many=None):
        self.executed: list[tuple[str, list | tuple]] = []
        self.lastrowid = 42
        self._one = list(one or [])
        self._many = list(many or [])

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return self._many.pop(0) if self._many else []


class FakeConn:
    """get_connection 이 돌려주는 연결 대신 쓰는 가짜. cursor() 로 FakeCursor 를 내준다."""

    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor


def _patch_connection(cursor, opened=None):
    """get_connection 을 가짜로 바꾼다. opened 리스트에 연결을 열 때마다 1을 쌓는다."""

    @contextmanager
    def fake_get_connection():
        if opened is not None:
            opened.append(1)
        yield FakeConn(cursor)

    return patch.object(audit_repository, "get_connection", fake_get_connection)


def _insert(**overrides):
    """insert_log 를 기본값으로 호출한다. 바꿀 인자만 overrides 로 넘긴다."""
    args = {
        "user_id": 1,
        "employee_no": None,
        "action": "login",
        "target_type": None,
        "target_id": None,
        "query": None,
        "filters": None,
        "doc_ids": None,
        "doc_companies": None,
        "result_count": None,
        "is_blocked": False,
        "block_reason": None,
        "context_detail": None,
        "created_at": datetime(2026, 10, 27, 9, 0, 0),
    }
    args.update(overrides)
    return audit_repository.insert_log(**args)


# users 테이블에서 조회된 것으로 가정하는 사용자 행 (현대무벡스 일반 직원).
MVX_USER = {"id": 1, "employee_no": "MVX-0001", "role": "employee", "company_id": "MVX"}


class AuditRepositoryTest(unittest.TestCase):
    """SQL 인젝션 방지(%s 바인딩), 계열사 범위 제한, JSON 변환, 사용자 스냅샷 복사를 검증한다."""

    def assert_bound(self, sql, params):
        """SQL 의 %s 개수와 바인딩 값 개수가 같은지 본다."""
        """SQL 의 %s 개수와 바인딩 값 개수가 같은지 본다."""
        self.assertEqual(sql.count("%s"), len(params), sql)

    def test_search_binds_every_filter_and_never_inlines_values(self):
        """모든 검색 조건이 %s 로 바인딩되고 값이 SQL 문자열에 섞이지 않는다 (SQL 인젝션 방지)."""
        # 건수 조회(one) 1번 + 목록 조회(many) 1번 순서로 결과를 준비한다.
        cursor = FakeCursor(one=[{"cnt": 3}], many=[[{"id": 1}]])
        injection = "x'; DROP TABLE audit_logs; --"
        start, end = datetime(2026, 10, 1), datetime(2026, 11, 1)

        with _patch_connection(cursor):
            rows, total = audit_repository.search_logs(
                "MVX", injection, "login", start, end, True, 20, 40
            )

        self.assertEqual((rows, total), ([{"id": 1}], 3))
        count_sql, count_params = cursor.executed[0]
        list_sql, list_params = cursor.executed[1]
        for sql, params in cursor.executed:
            self.assert_bound(sql, params)
            self.assertNotIn("DROP TABLE", sql)
        # 악성 문자열도 SQL 이 아니라 바인딩 값으로만 전달되어야 한다.
        # 계열사 조건은 바인딩 값이 1개다: 행동한 사람의 소속 코드.
        self.assertEqual(count_params, ["MVX", injection, "login", start, end])
        # 목록 쿼리는 조건 값 뒤에 limit, offset 이 붙는다.
        self.assertEqual(
            list_params, ["MVX", injection, "login", start, end, 20, 40]
        )
        self.assertIn("company_code = %s", count_sql)
        self.assertNotIn("doc_companies", count_sql)
        self.assertIn("employee_no = %s", count_sql)
        self.assertIn("action = %s", count_sql)
        self.assertIn("is_blocked = 1", count_sql)
        self.assertIn("ORDER BY created_at DESC", list_sql)

    def test_super_admin_scope_has_no_company_condition(self):
        """계열사 제한이 없는 전체 조회(super_admin)는 WHERE 절이 아예 없다."""
        cursor = FakeCursor(one=[{"cnt": 0}])
        with _patch_connection(cursor):
            audit_repository.search_logs(None, None, None, None, None, False, 20, 0)
        self.assertNotIn("WHERE", cursor.executed[0][0])

    def test_get_log_scopes_company_and_id(self):
        """상세 조회는 계열사와 id 를 모두 조건으로 건다 (다른 계열사 로그 id 로는 못 본다)."""
        cursor = FakeCursor(one=[{"id": 5}])
        with _patch_connection(cursor):
            row = audit_repository.get_log(5, "MVX")
        sql, params = cursor.executed[0]
        self.assert_bound(sql, params)
        self.assertEqual(params, ["MVX", 5])
        self.assertEqual(row, {"id": 5})

    def test_get_log_without_company_filters_only_by_id(self):
        """계열사 제한이 없으면 id 조건만 건다."""
        cursor = FakeCursor()
        with _patch_connection(cursor):
            audit_repository.get_log(5, None)
        sql, params = cursor.executed[0]
        self.assert_bound(sql, params)
        self.assertEqual(params, [5])

    def test_json_columns_are_parsed_when_read(self):
        """읽을 때 JSON 문자열 컬럼이 dict/list 로 바뀌고, NULL 은 None 으로 남는다."""
        row = {
            "id": 5,
            "filters": '{"year": 2025}',
            "doc_ids": '["d1", "d2"]',
            "doc_companies": None,
            "context_detail": '{"메모": "한글"}',
        }
        cursor = FakeCursor(one=[row])
        with _patch_connection(cursor):
            got = audit_repository.get_log(5, None)
        self.assertEqual(got["filters"], {"year": 2025})
        self.assertEqual(got["doc_ids"], ["d1", "d2"])
        self.assertIsNone(got["doc_companies"])
        self.assertEqual(got["context_detail"], {"메모": "한글"})

    def test_insert_copies_user_snapshot_in_one_connection(self):
        """저장 시 users 의 사원번호·역할·소속을 복사하며, 조회와 INSERT 가 한 연결에서 이뤄진다."""
        cursor = FakeCursor(one=[MVX_USER])
        opened: list[int] = []

        with _patch_connection(cursor, opened):
            log_id = _insert(user_id=1)

        self.assertEqual(len(opened), 1)
        self.assertEqual(log_id, 42)
        lookup_sql, lookup_params = cursor.executed[0]
        insert_sql, insert_params = cursor.executed[1]
        self.assertIn("FROM users", lookup_sql)
        self.assertEqual(lookup_params, (1,))
        self.assert_bound(lookup_sql, lookup_params)
        self.assert_bound(insert_sql, insert_params)
        # created_at, user_id, employee_no, role, company_code 순서
        self.assertEqual(
            insert_params[:5],
            (datetime(2026, 10, 27, 9, 0, 0), 1, "MVX-0001", "employee", "MVX"),
        )
        self.assertNotIn("ip_address", insert_sql)

    def test_insert_finds_user_by_employee_no_when_id_is_unknown(self):
        """user_id 가 없으면 사원번호로 사용자를 찾아 스냅샷을 채운다 (예: 로그인 차단 기록)."""
        cursor = FakeCursor(one=[MVX_USER])
        with _patch_connection(cursor):
            _insert(user_id=None, employee_no="MVX-0001", is_blocked=True)
        lookup_sql, lookup_params = cursor.executed[0]
        self.assertIn("employee_no = %s", lookup_sql)
        self.assertEqual(lookup_params, ("MVX-0001",))
        self.assertEqual(cursor.executed[1][1][1:5], (1, "MVX-0001", "employee", "MVX"))

    def test_insert_unknown_login_keeps_only_typed_employee_no(self):
        """존재하지 않는 로그인 ID 는 입력된 사원번호만 남기고 나머지는 NULL 로 둔다."""
        cursor = FakeCursor()
        with _patch_connection(cursor):
            _insert(user_id=None, employee_no="NOPE-1", is_blocked=True)
        # user_id·role·company_code 는 NULL, 입력된 사원번호만 남는다.
        self.assertEqual(cursor.executed[1][1][1:5], (None, "NOPE-1", None, None))

    def test_insert_nonexistent_user_id_is_stored_as_null_not_fk_error(self):
        """없는 users.id 는 NULL 로 저장해 외래키 오류로 로그가 유실되지 않게 한다."""
        cursor = FakeCursor()
        with _patch_connection(cursor):
            _insert(user_id=999)
        self.assertIsNone(cursor.executed[1][1][1])

    def test_insert_without_any_user_skips_lookup(self):
        """user_id·사원번호가 모두 없으면 사용자 조회 없이 INSERT 만 실행한다."""
        cursor = FakeCursor()
        with _patch_connection(cursor):
            _insert(user_id=None, employee_no=None)
        self.assertEqual(len(cursor.executed), 1)
        self.assertIn("INSERT INTO audit_logs", cursor.executed[0][0])

    def test_insert_serializes_json_columns(self):
        """filters·doc_ids·doc_companies·context_detail 이 JSON 문자열로 저장된다."""
        cursor = FakeCursor(one=[MVX_USER])
        with _patch_connection(cursor):
            _insert(
                filters={"회사": "MVX"},
                doc_ids=["d1"],
                doc_companies=["MVX", "ELV"],
                context_detail={"page": 1},
            )
        params = cursor.executed[1][1]
        # filters, doc_ids, doc_companies 는 INSERT 값 10~12번째, context_detail 은 마지막.
        self.assertEqual(json.loads(params[9]), {"회사": "MVX"})
        self.assertEqual(json.loads(params[10]), ["d1"])
        self.assertEqual(json.loads(params[11]), ["MVX", "ELV"])
        self.assertEqual(json.loads(params[-1]), {"page": 1})
        self.assertIn("회사", params[9])  # 한글을 \u 이스케이프로 저장하지 않는다.

    def test_insert_leaves_unset_json_as_null(self):
        """값이 없는 JSON 컬럼은 'null' 문자열이 아니라 진짜 NULL(None)로 저장된다."""
        cursor = FakeCursor(one=[MVX_USER])
        with _patch_connection(cursor):
            _insert()
        params = cursor.executed[1][1]
        self.assertEqual((params[9], params[10], params[11], params[-1]), (None,) * 4)

    def test_filter_option_queries_are_scoped_and_bound(self):
        """필터 선택지(사원번호·행위 코드) 조회도 계열사 범위와 바인딩을 지킨다."""
        cursor = FakeCursor(many=[[{"employee_no": "MVX-0001"}], [{"action": "login"}]])
        with _patch_connection(cursor):
            nos = audit_repository.list_employee_nos("MVX")
            actions = audit_repository.list_actions("MVX")
        self.assertEqual((nos, actions), (["MVX-0001"], ["login"]))
        for sql, params in cursor.executed:
            self.assert_bound(sql, params)
            self.assertEqual(params, ["MVX"])
        self.assertIn("employee_no IS NOT NULL", cursor.executed[0][0])


    def test_company_scope_is_only_logs_of_own_employees(self):
        """계열사 범위는 행동한 사람의 소속이 자사인 로그뿐이다. 자사 문서를 건드린 타사 직원의 로그는 조건에 없다."""
        cursor = FakeCursor(one=[{"id": 5}])
        with _patch_connection(cursor):
            audit_repository.get_log(5, "MVX")
        sql, params = cursor.executed[0]
        self.assertIn("WHERE company_code = %s AND id = %s", sql)
        # SELECT 컬럼에는 doc_companies 가 있으므로 WHERE 절만 본다.
        self.assertNotIn("doc_companies", sql.split("WHERE", 1)[1])
        self.assertNotIn("JSON_CONTAINS", sql)
        self.assertEqual(params, ["MVX", 5])


class AuditRepositoryExtraTest(unittest.TestCase):
    """이름·문서 제목 조회와 요약 집계."""

    def test_lookup_user_names_binds_ids_and_skips_db_when_empty(self):
        """id 는 바인딩으로 넘기고, 목록이 비면 DB 를 읽지 않는다."""
        cursor = FakeCursor()
        cursor.fetchall = lambda: [{"id": 1, "name": "홍길동"}]
        with _patch_connection(cursor):
            self.assertEqual(audit_repository.lookup_user_names([1, 2]), {1: "홍길동"})
            self.assertEqual(audit_repository.lookup_user_names([]), {})
        self.assertEqual(len(cursor.executed), 1)
        sql, params = cursor.executed[0]
        self.assertIn("id IN (%s, %s)", sql)
        self.assertEqual(params, [1, 2])

    def test_lookup_documents_returns_title_and_company(self):
        """문서는 제목과 소유 회사를 함께 돌려준다 (회사로 제목 공개 여부를 판단하기 위해)."""
        cursor = FakeCursor()
        cursor.fetchall = lambda: [{"doc_id": "d1", "title": "사양서", "company_id": "MVX"}]
        with _patch_connection(cursor):
            got = audit_repository.lookup_documents(["d1"])
        self.assertEqual(got, {"d1": {"title": "사양서", "company_id": "MVX"}})
        self.assertEqual(audit_repository.lookup_documents([]), {})

    def test_summarize_scopes_every_query_and_binds_values(self):
        """집계 6개 쿼리 모두 같은 범위(소속·기간) 조건을 쓰고 값은 바인딩으로만 넘긴다."""
        cursor = FakeCursor(
            one=[{"cnt": 10}, {"cnt": 3}, {"cnt": 4}, {"cnt": 1}],
            many=[[{"reason": "기밀", "cnt": 2}], [{"hr": 9, "cnt": 5}]],
        )
        start, end = datetime(2026, 10, 28), datetime(2026, 10, 29)
        with _patch_connection(cursor):
            got = audit_repository.summarize("MVX", start, end)

        self.assertEqual(got["total"], 10)
        self.assertEqual(got["blocked"], 3)
        self.assertEqual(got["blocked_reasons"], [("기밀", 2)])
        self.assertEqual((got["downloads"], got["blocked_downloads"]), (4, 1))
        self.assertEqual(got["hourly"], {9: 5})
        self.assertEqual(len(cursor.executed), 6)
        for sql, params in cursor.executed:
            self.assertIn("company_code = %s", sql)
            self.assertIn("created_at >= %s", sql)
            self.assertEqual(params[:3], ["MVX", start, end])
            self.assertNotIn("MVX", sql)
            self.assertNotIn("JSON_CONTAINS", sql)

    def test_summarize_for_super_admin_has_no_company_condition(self):
        """최종 어드민(범위 없음)은 소속 조건 없이 기간만 건다."""
        cursor = FakeCursor(one=[{"cnt": 0}] * 4)
        with _patch_connection(cursor):
            audit_repository.summarize(None, datetime(2026, 10, 28), datetime(2026, 10, 29))
        for sql, _ in cursor.executed:
            self.assertNotIn("company_code", sql.split("WHERE", 1)[1])


if __name__ == "__main__":
    unittest.main()
