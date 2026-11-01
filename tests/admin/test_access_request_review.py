"""A-05 권한 범위·중복 처리·실패 시 트랜잭션과 감사 로그 검증."""

import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from app.admin.services import access_service as service
from app.admin.repositories import access_request_repository as repository

ADMIN = {"id": 2, "role": "company_admin", "company_id": "MVX"}
REQUEST = {"id": 5, "user_id": 3, "doc_id": "doc-1", "company_id": "MVX", "status": "pending"}


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.cursor = MagicMock()
        self.cursor.fetchone.side_effect = lambda: self.rows.pop(0)
        self.cursor.rowcount = 1
        self.rows = [ADMIN.copy(), REQUEST.copy()]
        self.committed = False
        self.rolled_back = False

        @contextmanager
        def connection():
            try:
                yield MagicMock(cursor=MagicMock(return_value=self.cursor_context))
                self.committed = True
            except Exception:
                self.rolled_back = True
                raise

        self.cursor_context = MagicMock()
        self.cursor_context.__enter__.return_value = self.cursor
        for target, replacement in (
            ("app.admin.repositories.access_request_repository.get_connection", connection),
            ("app.admin.services.access_service.record_audit_log", None),
        ):
            patcher = patch(target, replacement) if replacement else patch(target)
            value = patcher.start()
            self.addCleanup(patcher.stop)
            if replacement is None:
                self.audit = value

    def writes(self):
        return [call.args for call in self.cursor.execute.call_args_list
                if call.args[0].startswith(("INSERT", "UPDATE"))]

    def test_approval_grant_and_status_commit_together(self):
        self.assertEqual(service.process_access_request(5, "approved", ADMIN, ""),
                         {"request_id": 5, "status": "approved"})
        writes = self.writes()
        self.assertEqual(writes[0][1], (3, "doc-1", 5, 2))
        self.assertEqual(writes[1][1][:3], ("approved", 2, None))
        self.assertTrue(self.committed)
        self.assertTrue(all("FOR UPDATE" in call.args[0]
                            for call in self.cursor.execute.call_args_list[:2]))
        self.assertEqual(self.audit.call_args.args[:5], (2, "access_review", "5", None, False))

    def test_rejection_saves_reason_without_grant(self):
        service.process_access_request(5, "rejected", ADMIN, "  업무 관련 없음  ")
        self.assertEqual(len(self.writes()), 1)
        self.assertEqual(self.writes()[0][1][:3], ("rejected", 2, "업무 관련 없음"))
        self.assertEqual(self.audit.call_args.kwargs["context_detail"], {"decision": "rejected"})

    def test_non_admin_inactive_missing_company_and_other_company_blocked(self):
        for reviewer in (None, {**ADMIN, "role": "employee"},
                         {**ADMIN, "company_id": None}, {**ADMIN, "company_id": "ELV"}):
            with self.subTest(reviewer=reviewer):
                self.rows = [reviewer, REQUEST.copy()]
                with self.assertRaises(PermissionError):
                    service.process_access_request(5, "approved", ADMIN, "")
                self.assertFalse(self.writes())
                self.assertTrue(self.audit.call_args.args[4])

    def test_super_admin_can_review_other_company(self):
        self.rows[0] = {"id": 1, "role": "super_admin", "company_id": None}
        self.assertTrue(service.update_document_access(5, {"id": 1}))
        self.assertEqual(self.writes()[0][1][-1], 1)

    def test_duplicate_and_missing_request_never_grant(self):
        for request in (None, {**REQUEST, "status": "approved"}, {**REQUEST, "status": "rejected"}):
            with self.subTest(request=request):
                self.rows = [ADMIN.copy(), request]
                with self.assertRaises((LookupError, ValueError)):
                    service.update_document_access(5, ADMIN)
                self.assertFalse(self.writes())

    def test_invalid_decision_reason_and_request_id(self):
        for args in ((5, "approve", ADMIN, ""), (5, "rejected", ADMIN, "  "),
                     (True, "approved", ADMIN, ""), (0, "approved", ADMIN, "")):
            with self.subTest(args=args), self.assertRaises(ValueError):
                service.process_access_request(*args)
        self.assertFalse(self.writes())

    def test_status_save_failure_rolls_back_grant(self):
        self.cursor.rowcount = 0
        with self.assertRaises(ValueError):
            service.update_document_access(5, ADMIN)
        self.assertTrue(self.rolled_back)
        self.assertFalse(self.committed)
        self.audit.assert_not_called()

    def test_grant_failure_rolls_back_without_success_audit(self):
        def execute(sql, params):
            if sql.startswith("INSERT"):
                raise RuntimeError("database unavailable")
        self.cursor.execute.side_effect = execute
        with self.assertRaises(RuntimeError):
            service.update_document_access(5, ADMIN)
        self.assertTrue(self.rolled_back)
        self.assertFalse(self.committed)
        self.audit.assert_not_called()

    def test_audit_failure_does_not_change_committed_approval(self):
        self.audit.side_effect = RuntimeError("audit unavailable")
        with self.assertLogs(service.logger, level="ERROR"):
            self.assertTrue(service.update_document_access(5, ADMIN))
        self.assertTrue(self.committed)


class ListTests(unittest.TestCase):
    @patch.object(service, "find_active_admin", return_value=ADMIN)
    @patch.object(repository, "list_requests", return_value=([], 1))
    def test_database_company_overrides_session_and_filter(self, listing, active):
        result = service.get_access_request_list(
            {**ADMIN, "role": "super_admin", "company_id": "ELV"},
            {"status": "pending", "company_id": "ELV"}, 99, 20,
        )
        self.assertEqual(result["page"], 1)
        self.assertEqual(listing.call_args.args, ("MVX", "pending", 20, 0))

    @patch.object(service, "record_audit_log")
    @patch.object(service, "find_active_admin")
    @patch.object(repository, "list_requests")
    def test_denied_list_access_is_audited(self, listing, active, audit):
        """비활성·강등·소속 없는 관리자의 목록 접근은 기록하고 차단한다."""
        for reviewer in (None, {**ADMIN, "role": "employee"}, {**ADMIN, "company_id": None}):
            with self.subTest(reviewer=reviewer):
                active.return_value = reviewer
                audit.reset_mock()
                with self.assertRaises(PermissionError) as raised:
                    service.get_access_request_list(ADMIN, {}, 1, 20)
                audit.assert_called_once_with(
                    ADMIN["id"], "access_review", None, None, True, str(raised.exception),
                    target_type="access_request", context_detail={"decision": "list"},
                )
        listing.assert_not_called()

    @patch.object(service, "record_audit_log", side_effect=RuntimeError("audit unavailable"))
    @patch.object(service, "find_active_admin", return_value=None)
    @patch.object(repository, "list_requests")
    def test_audit_failure_keeps_list_access_denied(self, listing, active, audit):
        """감사 로그 실패가 원래 권한 오류를 가리거나 목록 조회를 허용하지 않는다."""
        with self.assertLogs(service.logger, level="ERROR"):
            with self.assertRaisesRegex(PermissionError, "활성 관리자"):
                service.get_access_request_list(ADMIN, {}, 1, 20)
        listing.assert_not_called()


class DetailHelperTests(unittest.TestCase):
    """목록 탭 숫자와 이전 요청 요약: 관리 범위 밖은 읽지 못한다."""

    @patch.object(repository, "count_by_status", return_value={"pending": 1, "approved": 2, "rejected": 0})
    @patch.object(service, "find_active_admin", return_value=ADMIN)
    def test_counts_use_database_company_scope(self, active, counts):
        service.get_access_request_counts({**ADMIN, "company_id": "ELV"})
        counts.assert_called_once_with("MVX")

    @patch.object(repository, "count_by_status", return_value={})
    @patch.object(service, "find_active_admin", return_value={"id": 2, "role": "super_admin", "company_id": None})
    def test_super_admin_counts_everything(self, active, counts):
        service.get_access_request_counts(ADMIN)
        counts.assert_called_once_with(None)

    @patch.object(repository, "count_by_status")
    @patch.object(service, "find_active_admin", return_value={**ADMIN, "role": "employee"})
    def test_counts_reject_non_admin(self, active, counts):
        with self.assertRaises(PermissionError):
            service.get_access_request_counts(ADMIN)
        counts.assert_not_called()

    @patch.object(repository, "summarize_requester", return_value={"total": 2})
    @patch.object(repository, "find_request_scope", return_value={"id": 5, "user_id": 9, "company_id": "MVX"})
    @patch.object(service, "find_active_admin", return_value=ADMIN)
    def test_summary_for_own_company_request(self, active, scope, summarize):
        self.assertEqual(service.get_requester_summary(ADMIN, 5), {"total": 2})
        summarize.assert_called_once_with(9, "MVX", 5)

    @patch.object(repository, "summarize_requester")
    @patch.object(repository, "find_request_scope", return_value={"id": 5, "user_id": 9, "company_id": "ELV"})
    @patch.object(service, "find_active_admin", return_value=ADMIN)
    def test_summary_blocks_other_company_request(self, active, scope, summarize):
        with self.assertRaises(PermissionError):
            service.get_requester_summary(ADMIN, 5)
        summarize.assert_not_called()

    @patch.object(repository, "find_request_scope", return_value=None)
    @patch.object(service, "find_active_admin", return_value=ADMIN)
    def test_summary_missing_request(self, active, scope):
        with self.assertRaises(LookupError):
            service.get_requester_summary(ADMIN, 5)
        with self.assertRaises(ValueError):
            service.get_requester_summary(ADMIN, 0)


if __name__ == "__main__":
    unittest.main()
