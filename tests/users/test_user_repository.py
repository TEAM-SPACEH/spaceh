"""M-02 user_repository 테스트. get_connection을 patch해 SQL 호출·반환을 확인한다."""

import unittest
from unittest import mock

from app.users.repositories import user_repository


def _fake_connection(fetchone=None, rowcount=0):
    """with get_connection() as conn, conn.cursor() as cur 를 흉내 내는 목."""
    cur = mock.MagicMock()
    cur.fetchone.return_value = fetchone
    cur.rowcount = rowcount
    cur.__enter__.return_value = cur
    conn = mock.MagicMock()
    conn.cursor.return_value = cur
    conn.__enter__.return_value = conn
    return conn, cur


class UserRepositoryTest(unittest.TestCase):
    @mock.patch("app.users.repositories.user_repository.get_connection")
    def test_find_profile_by_id(self, get_conn):
        conn, cur = _fake_connection(fetchone={"id": 1, "name": "이물류"})
        get_conn.return_value = conn

        result = user_repository.find_profile_by_id(1)

        self.assertEqual(result, {"id": 1, "name": "이물류"})
        sql, params = cur.execute.call_args.args
        self.assertIn("FROM users", sql)
        self.assertEqual(params, (1,))  # user_id가 %s 바인딩으로 전달

    @mock.patch("app.users.repositories.user_repository.get_connection")
    def test_find_password_hash_by_id(self, get_conn):
        conn, cur = _fake_connection(fetchone={"password_hash": "HASH"})
        get_conn.return_value = conn
        self.assertEqual(user_repository.find_password_hash_by_id(1), "HASH")

    @mock.patch("app.users.repositories.user_repository.get_connection")
    def test_find_password_hash_none(self, get_conn):
        conn, cur = _fake_connection(fetchone=None)
        get_conn.return_value = conn
        self.assertIsNone(user_repository.find_password_hash_by_id(999))

    @mock.patch("app.users.repositories.user_repository.get_connection")
    def test_update_password(self, get_conn):
        conn, cur = _fake_connection(rowcount=1)
        get_conn.return_value = conn

        self.assertEqual(user_repository.update_password(1, "NEWHASH"), 1)

        sql, params = cur.execute.call_args.args
        self.assertIn("UPDATE users", sql)
        self.assertEqual(params, ("NEWHASH", 1))


if __name__ == "__main__":
    unittest.main()
