"""A-02·A-03 관리자 문서 화면 요약·상세·실패 문서 일괄 재색인 서비스·저장소 검증. DB·Chroma는 대체한다.

실행: python -m unittest tests.admin.test_document_overview
"""

import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from app.admin.repositories import document_repository
from app.admin.services import document_service as service

SUPER = {"id": 1}
COMPANY_ADMIN = {"id": 7}
EMPLOYEE = {"id": 8}


class _Base(unittest.TestCase):
    def setUp(self):
        self.repo = Mock()
        self.repo.find_active_admin.side_effect = lambda user_id: {
            1: {"id": 1, "role": "super_admin", "company_id": None},
            7: {"id": 7, "role": "company_admin", "company_id": "MVX"},
            8: {"id": 8, "role": "employee", "company_id": "MVX"},
            9: {"id": 9, "role": "company_admin", "company_id": None},
        }.get(user_id)
        patcher = patch("app.admin.services.document_service.repository", self.repo)
        patcher.start()
        self.addCleanup(patcher.stop)


class DocumentOverviewTest(_Base):
    OVERVIEW = {"total": 48, "internal_total": 31, "shared": 12, "failed": 1, "failed_title": "고객사 미팅 메모",
                "daily": [0, 0, 2, 0, 2, 2, 0], "pending_requests": 3, "oldest_pending_hours": 60}

    def test_company_admin_is_limited_to_own_company_and_gets_week_total(self):
        self.repo.count_document_overview.return_value = dict(self.OVERVIEW)
        result = service.get_document_overview(COMPANY_ADMIN)
        self.repo.count_document_overview.assert_called_once_with("MVX")
        self.assertEqual(result["week_added"], 6)
        self.assertEqual(result["total"], 48)

    def test_super_admin_sees_all_companies(self):
        self.repo.count_document_overview.return_value = dict(self.OVERVIEW)
        service.get_document_overview(SUPER)
        self.repo.count_document_overview.assert_called_once_with(None)

    def test_employee_and_company_admin_without_company_are_rejected_before_query(self):
        for user in (EMPLOYEE, {"id": 9}, {"id": 99}, {}):
            with self.subTest(user=user), self.assertRaises(PermissionError):
                service.get_document_overview(user)
        self.repo.count_document_overview.assert_not_called()


class DocumentDetailTest(_Base):
    def _detail(self, **overrides):
        row = {"doc_id": "d1", "company_id": "MVX", "company_name": "현대무벡스", "access_level": "confidential",
               "is_group_shared": 0, "created_at": datetime(2026, 9, 12), "uploader_name": "최관리"}
        row.update(overrides)
        self.repo.find_document_detail.return_value = row
        self.repo.count_document_viewers.return_value = {
            "employees": 5, "company_admins": 2, "super_admins": 1,
            "grants": [{"name": "정승강", "company_id": "ELV", "granted_at": datetime(2026, 10, 23, 9, 0)}]}

    def test_confidential_lists_admins_approved_users_and_super_admin(self):
        self._detail()
        detail = service.get_document_detail("d1", COMPANY_ADMIN)
        self.assertEqual(detail["uploader_name"], "최관리")
        labels = [(v["label"], v["company_id"], v["note"]) for v in detail["viewers"]]
        self.assertEqual(labels, [("현대무벡스 관리자 2명", None, "역할"), ("정승강", "ELV", "10.23 승인"),
                                  ("최종 어드민", None, "전체")])

    def test_internal_adds_employees_and_group_share_row(self):
        self._detail(access_level="internal", is_group_shared=1)
        labels = [v["label"] for v in service.get_document_detail("d1", COMPANY_ADMIN)["viewers"]]
        self.assertIn("현대무벡스 사원 5명", labels)
        self.assertIn("다른 계열사 임직원", labels)

    def test_internal_without_sharing_has_no_group_share_row(self):
        self._detail(access_level="internal", is_group_shared=0)
        labels = [v["label"] for v in service.get_document_detail("d1", COMPANY_ADMIN)["viewers"]]
        self.assertNotIn("다른 계열사 임직원", labels)

    def test_public_is_visible_to_everyone(self):
        self._detail(access_level="public")
        viewers = service.get_document_detail("d1", COMPANY_ADMIN)["viewers"]
        self.assertEqual(viewers[0]["label"], "모든 계열사 임직원")

    def test_other_company_document_is_rejected_for_company_admin(self):
        self._detail(company_id="ELV")
        with self.assertRaises(PermissionError):
            service.get_document_detail("d1", COMPANY_ADMIN)
        self.repo.count_document_viewers.assert_not_called()

    def test_super_admin_can_open_any_company(self):
        self._detail(company_id="ELV")
        self.assertEqual(service.get_document_detail("d1", SUPER)["doc_id"], "d1")

    def test_missing_document_and_employee(self):
        self.repo.find_document_detail.return_value = None
        with self.assertRaises(LookupError):
            service.get_document_detail("nope", COMPANY_ADMIN)
        with self.assertRaises(PermissionError):
            service.get_document_detail("d1", EMPLOYEE)


class ReindexFailedTest(_Base):
    def _docs(self, *docs):
        listed = {"documents": list(docs), "total": len(docs), "page": 1, "size": 100, "total_pages": 1}
        patcher = patch.object(service, "get_document_list", return_value=listed)
        self.list_mock = patcher.start()
        self.addCleanup(patcher.stop)

    def test_reindexes_each_failed_document_and_sums_results(self):
        self._docs({"doc_id": "a", "can_reindex": True}, {"doc_id": "b", "can_reindex": True},
                   {"doc_id": "c", "can_reindex": False})
        results = {"a": {"index_status": "done"}, "b": {"index_status": "failed"}}
        with patch.object(service, "request_reindex", side_effect=lambda doc_id, user: results[doc_id]) as reindex:
            summary = service.reindex_failed_documents(COMPANY_ADMIN)
        self.assertEqual(summary, {"total": 3, "done": 1, "failed": 1, "skipped": 1})
        self.assertEqual([call.args for call in reindex.call_args_list], [("a", COMPANY_ADMIN), ("b", COMPANY_ADMIN)])
        self.assertEqual(self.list_mock.call_args.args[1], {"index_status": "failed"})

    def test_employee_is_rejected_without_touching_documents(self):
        self._docs()
        with patch.object(service, "request_reindex") as reindex, self.assertRaises(PermissionError):
            service.reindex_failed_documents(EMPLOYEE)
        reindex.assert_not_called()
        self.list_mock.assert_not_called()


class FakeCursor:
    """실행된 SQL·바인딩 값을 기록하고 미리 정한 결과를 순서대로 돌려준다."""

    def __init__(self, ones=(), alls=()):
        self.executed = []
        self._ones = list(ones)
        self._alls = list(alls)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._ones.pop(0) if self._ones else None

    def fetchall(self):
        return self._alls.pop(0) if self._alls else []


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def cursor(self):
        return self._cursor


class OverviewRepositoryTest(unittest.TestCase):
    def _run(self, company_id, cursor):
        with patch.object(document_repository, "get_connection", return_value=FakeConnection(cursor)):
            return document_repository.count_document_overview(company_id)

    def _cursor(self):
        return FakeCursor(
            ones=[{"total": 48, "internal_total": 31, "shared": 12, "failed": 1}, {"title": "고객사 미팅 메모"},
                  {"pending": 3, "oldest_hours": 60}],
            alls=[[{"days_ago": 0, "n": 1}, {"days_ago": 2, "n": 2}, {"days_ago": 6, "n": 3}]])

    def test_company_scope_binds_company_everywhere_and_orders_days_oldest_first(self):
        cursor = self._cursor()
        result = self._run("MVX", cursor)
        self.assertEqual(result["daily"], [3, 0, 0, 0, 2, 0, 1])
        self.assertEqual((result["total"], result["shared"], result["failed"], result["pending_requests"]), (48, 12, 1, 3))
        self.assertEqual(result["failed_title"], "고객사 미팅 메모")
        self.assertEqual(result["oldest_pending_hours"], 60)
        for sql, params in cursor.executed:
            self.assertNotIn("MVX", sql)  # 값은 SQL 글자가 아니라 바인딩으로 넘긴다
            self.assertIn("MVX", params)

    def test_all_companies_scope_adds_no_company_condition(self):
        cursor = self._cursor()
        self._run(None, cursor)
        for sql, params in cursor.executed[:3]:
            self.assertNotIn("company_id = %s", sql)
        self.assertEqual(cursor.executed[0][1], [])

    def test_no_failed_document_gives_empty_title(self):
        cursor = FakeCursor(ones=[{"total": 0, "internal_total": 0, "shared": 0, "failed": 0}, None,
                                  {"pending": 0, "oldest_hours": None}])
        result = self._run("MVX", cursor)
        self.assertEqual((result["failed_title"], result["oldest_pending_hours"], result["daily"]), ("", 0, [0] * 7))


class ViewersRepositoryTest(unittest.TestCase):
    def test_counts_and_grants_use_bound_values(self):
        cursor = FakeCursor(ones=[{"employees": 5, "company_admins": 2, "super_admins": 1}],
                            alls=[[{"name": "정승강", "company_id": "ELV", "granted_at": datetime(2026, 10, 23)}]])
        with patch.object(document_repository, "get_connection", return_value=FakeConnection(cursor)):
            result = document_repository.count_document_viewers("d1", "MVX")
        self.assertEqual((result["employees"], result["company_admins"], result["super_admins"]), (5, 2, 1))
        self.assertEqual(result["grants"][0]["name"], "정승강")
        self.assertEqual(cursor.executed[0][1], ("MVX", "MVX"))
        self.assertEqual(cursor.executed[1][1], ("d1",))


if __name__ == "__main__":
    unittest.main()
