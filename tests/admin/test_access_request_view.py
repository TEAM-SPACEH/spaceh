"""A-05 실제 Streamlit 렌더링과 승인·반려 입력 흐름 검증."""

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

LIST = "app.admin.views.components.access_request_list.get_access_request_list"
COUNTS = "app.admin.views.components.access_request_list.get_access_request_counts"
SUMMARY = "app.admin.views.components.access_request_detail.get_requester_summary"
SCOPE = "app.admin.views.access_requests.get_share_scope_name"
PROCESS = "app.admin.views.components.access_request_actions.process_access_request"

ADMIN = {"id": 2, "role": "company_admin", "company_id": "MVX"}


def admin_page():
    from app.admin.views.access_requests import render_admin_permissions
    render_admin_permissions({"id": 2, "role": "company_admin", "company_id": "MVX"})


def employee_page():
    from app.admin.views.access_requests import render_admin_permissions
    render_admin_permissions({"id": 3, "role": "employee", "company_id": "MVX"})


def request_row(status="pending", **extra):
    row = {
        "id": 5, "user_id": 9, "doc_id": "doc-1", "title": "[제목](https://example.com)",
        "requester_name": "요청자", "employee_no": "TEST003", "company_id": "MVX",
        "requester_company_id": "ELV", "requester_company_name": "현대엘리베이터", "requester_role": "employee",
        "company_name": "현대무벡스", "file_format": "docx", "access_level": "confidential",
        "published_date": datetime(2025, 10, 8), "created_at": datetime.now() - timedelta(hours=2),
        "reason": "업무 확인", "status": status, "reviewed_at": datetime(2026, 10, 28, 9, 30),
        "review_comment": "업무 범위 외",
    }
    return {**row, **extra}


def result(status="pending"):
    return {"requests": [request_row(status)], "total_count": 1, "page": 1, "total_pages": 1}


SUMMARY_VALUE = {"total": 2, "approved": 2, "rejected": 0, "pending": 0, "last_approved_at": datetime(2026, 9, 30)}
COUNT_VALUE = {"pending": 1, "approved": 0, "rejected": 0}


def patches(listing_value):
    return (patch(LIST, return_value=listing_value), patch(COUNTS, return_value=COUNT_VALUE),
            patch(SUMMARY, return_value=SUMMARY_VALUE), patch(SCOPE, return_value="현대무벡스"))


class AccessRequestViewTests(unittest.TestCase):
    def run_page(self, listing_value, process=None):
        listing, counts, summary, scope = patches(listing_value)
        with listing, counts, summary, scope:
            if process is None:
                return AppTest.from_function(admin_page).run()
            with process:
                app = AppTest.from_function(admin_page).run()
                return app

    def test_request_text_is_escaped(self):
        app = self.run_page(result())
        self.assertFalse(app.exception)
        self.assertTrue(any("[제목](https://example.com)" in item.value for item in app.get("html")))
        self.assertFalse(any("<a " in item.value for item in app.get("html")))

    def test_approval_submits_once_with_blank_reason(self):
        listing, counts, summary, scope = patches(result())
        with listing, counts, summary, scope, patch(PROCESS, return_value={"request_id": 5, "status": "approved"}) as process:
            app = AppTest.from_function(admin_page).run()
            next(button for button in app.button if button.label == "승인").click().run()
            self.assertFalse(app.exception)
            process.assert_called_once_with(5, "approved", ADMIN, "")

    def test_rejection_validation_stays_on_page(self):
        listing, counts, summary, scope = patches(result())
        with listing, counts, summary, scope, patch(PROCESS, side_effect=ValueError("반려 사유를 입력해 주세요.")) as process:
            app = AppTest.from_function(admin_page).run()
            next(button for button in app.button if button.label == "반려").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.error[0].value, "반려 사유를 입력해 주세요.")
            self.assertEqual(process.call_args.args[1], "rejected")

    def test_processed_requests_have_no_action_buttons(self):
        app = self.run_page(result("rejected"))
        self.assertFalse(app.exception)
        labels = [button.label for button in app.button]
        self.assertNotIn("승인", labels)
        self.assertNotIn("반려", labels)
        self.assertTrue(any("업무 범위 외" in item.value for item in app.get("html")))

    def test_employee_page_never_reads_requests(self):
        with patch(LIST) as listing:
            app = AppTest.from_function(employee_page).run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        listing.assert_not_called()

    def test_empty_list_shows_guidance(self):
        app = self.run_page({"requests": [], "total_count": 0, "page": 1, "total_pages": 1})
        self.assertFalse(app.exception)
        self.assertTrue(any("열람 요청이 없습니다" in item.value for item in app.info))


class FormatAgoTests(unittest.TestCase):
    NOW = datetime(2026, 10, 29, 12, 0)

    def test_labels(self):
        from app.admin.views.components.access_request_list import format_ago
        cases = [
            (self.NOW - timedelta(seconds=30), "방금 전"),
            (self.NOW - timedelta(minutes=5), "5분 전"),
            (self.NOW - timedelta(hours=2), "2시간 전"),
            (datetime(2026, 10, 28, 20, 0), "어제"),
            (datetime(2026, 10, 27, 9, 0), "2일 전"),
            (datetime(2026, 9, 1, 9, 0), "09.01"),
        ]
        for created, expected in cases:
            self.assertEqual(format_ago(created, self.NOW), expected)
        self.assertEqual(format_ago(None, self.NOW), "")


class PreviousRequestTextTests(unittest.TestCase):
    def test_summaries(self):
        from app.admin.views.components.access_request_detail import previous_request_text
        none = {"total": 0, "approved": 0, "rejected": 0, "pending": 0, "last_approved_at": None}
        self.assertEqual(previous_request_text(none)[0], "처음 요청")
        self.assertEqual(previous_request_text(SUMMARY_VALUE), ("2건 모두 승인", "마지막 승인 09.30"))
        mixed = {"total": 3, "approved": 1, "rejected": 1, "pending": 1, "last_approved_at": datetime(2026, 9, 1)}
        self.assertEqual(previous_request_text(mixed)[0], "승인 1건 · 반려 1건 · 대기 1건")


if __name__ == "__main__":
    unittest.main()
