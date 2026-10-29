
import unittest
from unittest.mock import patch

from app.search.services.search_access_service import (
    get_fresh_search_user,
    inspect_search_access,
)


class TestSearchAccess(unittest.TestCase):

    def setUp(self):
        self.user = {
            "id": 1,
            "employee_no": "EMP001",
            "role": "employee",
            "company_id": "HRI",
        }

        self.chunk = {
            "doc_id": "DOC-001",
            "text": "테스트 내용",
            "metadata": {
                "doc_id": "DOC-001",
                "company_id": "HRI",
                "access_level": "internal",
                "is_group_shared": False,
            },
        }

        self.document = {
            "doc_id": "DOC-001",
            "company_id": "HRI",
            "access_level": "internal",
            "is_group_shared": False,
        }

    @patch("app.search.services.search_access_service.find_user_by_employee_no")
    def test_active_user(self, mock_find):
        mock_find.return_value = {
            **self.user,
            "name": "테스트",
            "company_name": "현대경제연구원",
            "is_active": 1,
            "password_hash": "secret",
        }

        result = get_fresh_search_user(self.user)

        self.assertEqual(result["id"], 1)
        self.assertNotIn("password_hash", result)

    @patch("app.search.services.search_access_service.find_user_by_employee_no")
    def test_inactive_user_blocked(self, mock_find):
        mock_find.return_value = {
            **self.user,
            "is_active": 0,
        }

        with self.assertRaises(PermissionError):
            get_fresh_search_user(self.user)

    @patch("app.search.services.search_access_service.check_search_permission")
    @patch("app.search.services.search_access_service.find_by_id")
    @patch("app.search.services.search_access_service.get_approved_doc_ids")
    def test_authorized_document(
        self, mock_grants, mock_find, mock_check
    ):
        mock_grants.return_value = []
        mock_find.return_value = self.document
        mock_check.return_value = True

        chunks, snapshot = inspect_search_access(
            self.user, [self.chunk]
        )

        self.assertEqual(len(chunks), 1)
        self.assertIsInstance(snapshot, tuple)

    @patch("app.search.services.search_access_service.check_search_permission")
    @patch("app.search.services.search_access_service.find_by_id")
    @patch("app.search.services.search_access_service.get_approved_doc_ids")
    def test_revoked_permission(
        self, mock_grants, mock_find, mock_check
    ):
        mock_grants.return_value = []
        mock_find.return_value = self.document
        mock_check.return_value = False

        chunks, _ = inspect_search_access(
            self.user, [self.chunk]
        )

        self.assertEqual(chunks, [])

    @patch("app.search.services.search_access_service.check_search_permission")
    @patch("app.search.services.search_access_service.find_by_id")
    @patch("app.search.services.search_access_service.get_approved_doc_ids")
    def test_metadata_changed(
        self, mock_grants, mock_find, mock_check
    ):
        mock_grants.return_value = []
        mock_find.return_value = {
            **self.document,
            "access_level": "confidential",
        }
        mock_check.return_value = True

        chunks, _ = inspect_search_access(
            self.user, [self.chunk]
        )

        self.assertEqual(chunks, [])

    @patch("app.search.services.search_access_service.find_by_id")
    @patch("app.search.services.search_access_service.get_approved_doc_ids")
    def test_db_failure_propagates(self, mock_grants, mock_find):
        mock_grants.return_value = []
        mock_find.side_effect = RuntimeError("DB 연결 실패")

        with self.assertRaises(RuntimeError):
            inspect_search_access(self.user, [self.chunk])


if __name__ == "__main__":
    unittest.main()
