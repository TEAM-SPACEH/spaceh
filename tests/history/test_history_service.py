"""M-04 history_service 테스트. 저장소·세션·검색·사용자 조회는 목으로 바꿔 DB 없이 돈다."""

import unittest
from datetime import datetime
from unittest import mock

from app.history.services import history_service

_MODULE = "app.history.services.history_service"
_USER = {"user_id": 1, "role": "employee", "company_id": "MVX"}


def _log(log_id, action, **fields):
    row = {
        "id": log_id, "created_at": datetime(2026, 10, 27, 9, 30), "action": action,
        "target_type": None, "target_id": None, "query": None, "filters": None,
        "doc_ids": None, "result_count": None, "is_blocked": 0, "block_reason": None,
    }
    row.update(fields)
    return row


@mock.patch(f"{_MODULE}.get_current_user_id", return_value=1)
@mock.patch(f"{_MODULE}.history_repository")
class GetUserHistoryTest(unittest.TestCase):
    def test_all_types_from_audit_logs(self, repo, _current):
        repo.list_user_logs.return_value = [
            _log(4, "report_create", target_type="report", target_id="7", query="3분기 실적"),
            _log(3, "ask", query="무벡스 매출"),
            _log(2, "view_document", target_type="document", target_id="d1"),
            _log(1, "search", query="엘리베이터 사양", result_count=4),
        ]
        repo.find_documents.return_value = {"d1": {"doc_id": "d1", "title": "WBST-500 사양서"}}
        repo.find_report_titles.return_value = {7: "3분기 실적 보고서"}

        items = history_service.get_user_history(1, None)

        # 보고서 생성도 감사 로그(report_create)에서 읽는다. reports 는 제목만 찾는다.
        repo.list_user_logs.assert_called_once_with(1, list(history_service.HISTORY_TYPES), history_service.HISTORY_LIMIT)
        repo.find_report_titles.assert_called_once_with(1, [7])
        self.assertEqual(
            [item["summary"] for item in items],
            ["3분기 실적 보고서", "무벡스 매출", "WBST-500 사양서", "엘리베이터 사양"],
        )
        self.assertEqual((items[0]["history_id"], items[0]["report_id"], items[0]["type_label"]), (4, 7, "보고서 생성"))
        self.assertEqual(items[3]["created_at"], "2026-10-27 09:30")
        # 검색·질문만 다시 검색할 수 있다.
        self.assertEqual([item["can_rerun"] for item in items], [False, True, False, True])

    def test_report_log_without_report_row_uses_logged_topic(self, repo, _current):
        # 감사 로그는 있지만 reports 행이 없어도 이력에서 빠지지 않는다.
        repo.list_user_logs.return_value = [_log(5, "report_create", target_id="9", query="물류 자동화 동향")]
        repo.find_documents.return_value = {}
        repo.find_report_titles.return_value = {}
        items = history_service.get_user_history(1, "report_create")
        self.assertEqual(repo.list_user_logs.call_args.args[1], ["report_create"])
        self.assertEqual([(item["summary"], item["report_id"]) for item in items], [("물류 자동화 동향", 9)])

    def test_type_filter(self, repo, _current):
        repo.list_user_logs.return_value = []
        history_service.get_user_history(1, "ask")
        self.assertEqual(repo.list_user_logs.call_args.args[1], ["ask"])

    def test_unknown_type_returns_empty(self, repo, _current):
        self.assertEqual(history_service.get_user_history(1, "login"), [])
        repo.list_user_logs.assert_not_called()

    def test_other_user_denied(self, repo, _current):
        self.assertEqual(history_service.get_user_history(2, None), [])
        repo.list_user_logs.assert_not_called()


@mock.patch(f"{_MODULE}.get_current_user_id", return_value=1)
@mock.patch(f"{_MODULE}.history_repository")
class GetHistoryDetailTest(unittest.TestCase):
    def test_detail_with_documents(self, repo, _current):
        repo.get_user_log.return_value = _log(5, "ask", query="무벡스 매출", doc_ids=["d1", "gone"], result_count=2)
        repo.find_documents.return_value = {"d1": {"doc_id": "d1", "title": "실적 보고서"}}

        detail = history_service.get_history_detail(1, 5)

        repo.get_user_log.assert_called_once_with(1, 5, list(history_service.HISTORY_TYPES))
        self.assertEqual(detail["query"], "무벡스 매출")
        # 지금은 지워진 문서는 제목 대신 id 로 보여 준다.
        self.assertEqual(detail["documents"], [{"doc_id": "d1", "title": "실적 보고서"}, {"doc_id": "gone", "title": "gone"}])

    def test_not_found(self, repo, _current):
        repo.get_user_log.return_value = None
        self.assertIsNone(history_service.get_history_detail(1, 99))

    def test_other_user_denied(self, repo, _current):
        self.assertIsNone(history_service.get_history_detail(2, 5))
        repo.get_user_log.assert_not_called()


@mock.patch(f"{_MODULE}.hybrid_search")
@mock.patch(f"{_MODULE}.get_user_info", return_value=_USER)
@mock.patch(f"{_MODULE}.get_current_user_id", return_value=1)
@mock.patch(f"{_MODULE}.history_repository")
class RerunSearchTest(unittest.TestCase):
    def test_reruns_with_current_permission(self, repo, _current, _info, search):
        where = {"company_id": "MVX"}
        repo.get_user_log.return_value = _log(1, "search", query="물류 자동화", filters=where, doc_ids=["old"])
        search.return_value = [{"chunk_id": "d2#0001", "doc_id": "d2"}]

        result = history_service.rerun_search(1, 1)

        repo.get_user_log.assert_called_once_with(1, 1, ["search", "ask"])
        # 저장된 결과가 아니라 DB 의 지금 역할·소속으로 검색을 새로 한다.
        search.assert_called_once_with("물류 자동화", where, {"id": 1, "role": "employee", "company_id": "MVX"})
        self.assertEqual(result["results"], [{"chunk_id": "d2#0001", "doc_id": "d2"}])

    def test_reruns_ask_history(self, repo, _current, _info, search):
        # 통합 검색 화면은 검색+답변을 ask 로만 남긴다 (#100). 질문도 같은 검색어·필터로 다시 검색한다.
        repo.get_user_log.return_value = _log(4, "ask", query="무벡스 매출", filters=None)
        search.return_value = []
        result = history_service.rerun_search(1, 4)
        search.assert_called_once_with("무벡스 매출", None, {"id": 1, "role": "employee", "company_id": "MVX"})
        self.assertEqual(result["query"], "무벡스 매출")

    def test_not_search_history(self, repo, _current, _info, search):
        repo.get_user_log.return_value = None
        self.assertEqual(history_service.rerun_search(1, 2), {})
        search.assert_not_called()

    def test_other_user_denied(self, repo, _current, _info, search):
        self.assertEqual(history_service.rerun_search(2, 1), {})
        search.assert_not_called()


@mock.patch(f"{_MODULE}.check_search_permission")
@mock.patch(f"{_MODULE}.get_user_info", return_value=_USER)
@mock.patch(f"{_MODULE}.get_current_user_id", return_value=1)
@mock.patch(f"{_MODULE}.history_repository")
class GetHistoryReportTest(unittest.TestCase):
    _REPORT = {
        "id": 7, "title": "3분기 실적 보고서", "template": "quarterly", "params": {}, "content_md": "본문",
        "footnotes": None, "exec_summary": None, "doc_ids": ["d1", "d2"],
        "max_access_level": "internal", "created_at": datetime(2026, 10, 27, 10, 0),
    }

    def test_opens_when_all_sources_allowed(self, repo, _current, _info, allowed):
        repo.find_user_report.return_value = dict(self._REPORT)
        repo.find_documents.return_value = {"d1": {"doc_id": "d1"}, "d2": {"doc_id": "d2"}}
        allowed.return_value = True

        report = history_service.get_history_report(1, 7)

        repo.find_user_report.assert_called_once_with(1, 7)
        self.assertEqual(report["title"], "3분기 실적 보고서")
        self.assertEqual(report["footnotes"], [])

    def test_blocked_when_a_source_is_no_longer_allowed(self, repo, _current, _info, allowed):
        repo.find_user_report.return_value = dict(self._REPORT)
        repo.find_documents.return_value = {"d1": {"doc_id": "d1"}, "d2": {"doc_id": "d2"}}
        allowed.side_effect = lambda user, document: document["doc_id"] == "d1"
        self.assertIsNone(history_service.get_history_report(1, 7))

    def test_blocked_when_a_source_was_deleted(self, repo, _current, _info, allowed):
        repo.find_user_report.return_value = dict(self._REPORT)
        repo.find_documents.return_value = {"d1": {"doc_id": "d1"}}
        # 지워진 문서는 check_search_permission(user, None) → False 로 막힌다.
        allowed.side_effect = lambda user, document: bool(document)
        self.assertIsNone(history_service.get_history_report(1, 7))

    def test_other_users_report(self, repo, _current, _info, allowed):
        repo.find_user_report.return_value = None
        self.assertIsNone(history_service.get_history_report(1, 8))


@mock.patch(f"{_MODULE}.get_current_user_id", return_value=1)
@mock.patch(f"{_MODULE}.history_repository")
class GetAccessRequestHistoryTest(unittest.TestCase):
    def test_status_labels_and_reject_reason(self, repo, _current):
        repo.list_access_requests.return_value = [
            {"id": 2, "doc_id": "d2", "title": None, "owner_company_code": "ELV", "reason": "비교 분석",
             "status": "rejected", "review_comment": "기밀 문서", "created_at": datetime(2026, 10, 27, 11, 0),
             "reviewed_at": datetime(2026, 10, 27, 15, 0)},
            {"id": 1, "doc_id": "d1", "title": "단가표", "owner_company_code": "MVX", "reason": "견적 검토",
             "status": "pending", "review_comment": None, "created_at": datetime(2026, 10, 26, 9, 0),
             "reviewed_at": None},
        ]

        requests = history_service.get_access_request_history(1)

        repo.list_access_requests.assert_called_once_with(1)
        self.assertEqual([r["status_label"] for r in requests], ["반려", "대기"])
        self.assertEqual(requests[0]["review_comment"], "기밀 문서")
        self.assertEqual(requests[0]["title"], "d2")  # 문서가 지워져 제목이 없으면 id
        self.assertIsNone(requests[1]["reviewed_at"])

    def test_other_user_denied(self, repo, _current):
        self.assertEqual(history_service.get_access_request_history(2), [])
        repo.list_access_requests.assert_not_called()


if __name__ == "__main__":
    unittest.main()
