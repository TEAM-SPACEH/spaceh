"""company_repository 테스트. 실제 MySQL 없이 가짜 커서로 실행된 SQL·바인딩 값을 확인한다.

실행: python -m unittest tests.admin.test_company_repository
"""

import unittest
from decimal import Decimal
from unittest.mock import patch

import pymysql

from app.admin.repositories import company_repository
from app.admin.repositories.company_repository import DuplicateCompanyError


class FakeCursor:
    """실행된 SQL·바인딩 값을 기록하고 미리 정한 결과를 돌려준다."""

    def __init__(self, one=None, many=None, error=None):
        self.executed: list[tuple[str, object]] = []
        self._one = list(one or [])
        self._many = list(many or [])
        self._error = error

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if self._error:
            raise self._error

    def fetchone(self):
        return self._one.pop(0) if self._one else None

    def fetchall(self):
        return self._many.pop(0) if self._many else []


class _Connection:
    """get_connection 대용."""

    def __init__(self, cursor):
        self._cursor = cursor

    def __call__(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self._cursor


def _patched(cursor):
    return patch.object(company_repository, "get_connection", _Connection(cursor))


def _duplicate(key):
    """MySQL 이 중복 키에서 내는 오류 모양 (8.0.19 이후는 'companies.' 접두어가 붙는다)."""
    return pymysql.err.IntegrityError(1062, f"Duplicate entry 'X' for key '{key}'")


class ListCompaniesTest(unittest.TestCase):
    def test_counts_are_converted_to_int_and_query_has_no_user_input(self):
        """SUM 의 Decimal 이 정수로 바뀌고, 사용 중인 사용자만 센다."""
        row = {
            "company_id": "MVX",
            "name": "현대무벡스",
            "dart_code": None,
            "is_active": 1,
            "default_share_enabled": 0,
            "doc_total": Decimal("10"),
            "doc_public": Decimal("1"),
            "doc_internal": Decimal("6"),
            "doc_confidential": Decimal("3"),
            "user_count": 2,
        }
        cursor = FakeCursor(many=[[row]])
        with _patched(cursor):
            got = company_repository.list_companies()

        self.assertEqual(got[0]["doc_internal"], 6)
        self.assertIsInstance(got[0]["doc_total"], int)
        sql, params = cursor.executed[0]
        self.assertIn("LEFT JOIN", sql)
        self.assertIn("is_active = 1", sql)
        self.assertIn("ORDER BY c.created_at, c.company_id", sql)

    def test_active_options_shape(self):
        """필터 선택지는 {"id", "name"} 모양이다."""
        cursor = FakeCursor(many=[[{"company_id": "ELV", "name": "현대엘리베이터"}]])
        with _patched(cursor):
            self.assertEqual(company_repository.list_active_company_options(), [{"id": "ELV", "name": "현대엘리베이터"}])
        self.assertIn("is_active = 1", cursor.executed[0][0])


class WriteTest(unittest.TestCase):
    def test_insert_binds_values(self):
        """등록 값은 모두 %s 바인딩이고 공유 기본값은 1/0 이다."""
        cursor = FakeCursor()
        with _patched(cursor):
            company_repository.insert_company("HIP", "현대투자파트너스", "00126380", True)
        sql, params = cursor.executed[0]
        self.assertIn("INSERT INTO companies", sql)
        self.assertNotIn("HIP", sql)
        self.assertEqual(params, ("HIP", "현대투자파트너스", "00126380", 1))

    def test_duplicate_keys_become_duplicate_company_error(self):
        """겹친 키 이름에 따라 어느 값이 겹쳤는지(kind)를 알려 준다."""
        for key, kind in (
            ("companies.uq_companies_name", "name"),
            ("uq_companies_name", "name"),
            ("companies.uq_companies_dart_code", "dart_code"),
            ("companies.PRIMARY", "company_id"),
            ("PRIMARY", "company_id"),
        ):
            with self.subTest(key=key):
                with _patched(FakeCursor(error=_duplicate(key))), self.assertRaises(DuplicateCompanyError) as ctx:
                    company_repository.insert_company("HIP", "회사", None, False)
                self.assertEqual(ctx.exception.kind, kind)

    def test_other_integrity_errors_are_not_hidden(self):
        """중복이 아닌 무결성 오류(외래키 등)는 그대로 올라간다."""
        error = pymysql.err.IntegrityError(1452, "Cannot add or update a child row")
        with _patched(FakeCursor(error=error)), self.assertRaises(pymysql.err.IntegrityError):
            company_repository.insert_company("HIP", "회사", None, False)

    def test_update_dart_code_binds_and_maps_duplicate(self):
        """DART 고유번호 수정은 바인딩으로 넘기고, 겹치면 DuplicateCompanyError 다. None 은 NULL 로 비운다."""
        cursor = FakeCursor()
        with _patched(cursor):
            company_repository.update_dart_code("MVX", None)
        self.assertEqual(cursor.executed[0][1], (None, "MVX"))

        with _patched(FakeCursor(error=_duplicate("companies.uq_companies_dart_code"))), self.assertRaises(
            DuplicateCompanyError
        ) as ctx:
            company_repository.update_dart_code("MVX", "00126380")
        self.assertEqual(ctx.exception.kind, "dart_code")

    def test_get_company_returns_row_or_none(self):
        """회사 코드는 바인딩으로 넘기고, 없으면 None 이다."""
        cursor = FakeCursor(one=[{"company_id": "MVX"}, None])
        with _patched(cursor):
            self.assertEqual(company_repository.get_company("MVX"), {"company_id": "MVX"})
            self.assertIsNone(company_repository.get_company("NOPE"))
        self.assertEqual(cursor.executed[0][1], ("MVX",))


if __name__ == "__main__":
    unittest.main()
