"""A-05 실제 Streamlit 렌더링과 승인·반려 입력 흐름 검증."""

import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

LIST = "app.admin.views.components.access_request_list.get_access_request_list"
PROCESS = "app.admin.views.components.access_request_actions.process_access_request"


def admin_page():
    from app.admin.views.access_requests import render_admin_permissions
    render_admin_permissions({"id": 2, "role": "company_admin", "company_id": "MVX"})


def employee_page():
    from app.admin.views.access_requests import render_admin_permissions
    render_admin_permissions({"id": 3, "role": "employee", "company_id": "MVX"})


def result(status="pending"):
    return {"requests": [{
        "id": 5, "title": "[제목](https://example.com)", "requester_name": "요청자",
        "employee_no": "TEST003", "company_id": "MVX", "created_at": "2026-10-28",
        "reason": "업무 확인", "status": status, "reviewed_at": "2026-10-28",
        "review_comment": "업무 범위 외",
    }], "total_count": 1, "page": 1, "total_pages": 1}


class AccessRequestViewTests(unittest.TestCase):
    @patch(LIST, return_value=result())
    def test_request_text_is_escaped_and_approval_submits_once(self, listing):
        with patch(PROCESS, return_value={"request_id": 5, "status": "approved"}) as process:
            app = AppTest.from_function(admin_page).run()
            self.assertFalse(app.exception)
            self.assertTrue(any("[제목](https://example.com)" in item.value for item in app.get("html")))
            next(button for button in app.button if button.label == "승인").click().run()
            self.assertFalse(app.exception)
            process.assert_called_once_with(5, "approved", {"id": 2, "role": "company_admin", "company_id": "MVX"}, "")
            self.assertTrue(app.success)

    @patch(LIST, return_value=result())
    def test_rejection_validation_stays_on_page(self, listing):
        with patch(PROCESS, side_effect=ValueError("반려 사유를 입력해 주세요.")) as process:
            app = AppTest.from_function(admin_page).run()
            next(button for button in app.button if button.label == "반려").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.error[0].value, "반려 사유를 입력해 주세요.")
            self.assertEqual(process.call_args.args[1], "rejected")

    @patch(LIST, return_value=result("rejected"))
    def test_processed_requests_have_no_action_buttons(self, listing):
        app = AppTest.from_function(admin_page).run()
        self.assertFalse(app.exception)
        self.assertNotIn("승인", [button.label for button in app.button])
        self.assertNotIn("반려", [button.label for button in app.button])

    @patch(LIST)
    def test_employee_page_never_reads_requests(self, listing):
        app = AppTest.from_function(employee_page).run()
        self.assertFalse(app.exception)
        self.assertTrue(app.error)
        listing.assert_not_called()
