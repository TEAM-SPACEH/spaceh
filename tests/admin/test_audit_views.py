"""감사 로그 화면 컴포넌트 테스트. Streamlit AppTest 로 실제 렌더링 결과를 확인한다."""

import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

# Markdown 으로 해석되면 굵은 글씨·링크로 바뀌는 값. 글자 그대로 보여야 한다.
RISKY = "**굵게** [클릭](http://example.com)"


def _detail_app():
    from app.admin.views.components.audit_log_detail import render_audit_log_detail

    render_audit_log_detail(
        {
            "log_id": 1,
            "created_at": "2026-10-27 09:30:05",
            "employee_no": "**굵게** [클릭](http://example.com)",
            "role": None,
            "company_code": None,
            "action_type": "login",
            "target_type": None,
            "target_id": None,
            "query": "**굵게** [클릭](http://example.com)",
            "result_count": 3,
            "blocked": True,
            "block_reason": "**굵게** [클릭](http://example.com)",
            "filters": None,
            "doc_ids": None,
            "doc_companies": None,
            "context_detail": None,
        }
    )


def _page_app():
    from app.admin.views.audit_logs import render_admin_audit_logs

    render_admin_audit_logs({"id": 1, "role": "company_admin", "company_id": "MVX"})


class AuditLogPageViewTest(unittest.TestCase):
    OPTIONS = {"users": ["MVX-0001", "MVX-0002"], "action_types": ["login", "search"]}
    RESULT = {"logs": [], "total_count": 0, "page": 1, "total_pages": 5}

    def test_changing_a_filter_returns_to_first_page(self):
        """3페이지를 보다가 필터를 바꾸면 1페이지부터 다시 조회한다."""
        with patch("app.admin.views.audit_logs.get_audit_filter_options", return_value=self.OPTIONS), patch(
            "app.admin.views.audit_logs.search_audit_logs", return_value=self.RESULT
        ) as search:
            at = AppTest.from_function(_page_app).run(timeout=20)
            self.assertFalse(at.exception)
            self.assertEqual(at.title[0].value, "감사 로그")  # page_header 가 제목을 그린다

            at.number_input[0].set_value(3).run(timeout=20)
            self.assertEqual(search.call_args.args[2], 3)  # 필터가 그대로면 고른 페이지를 유지한다

            at.selectbox[0].select("MVX-0001").run(timeout=20)
            self.assertEqual(search.call_args.args[1], {"employee_no": "MVX-0001"})
            self.assertEqual(search.call_args.args[2], 1)


class AuditLogDetailViewTest(unittest.TestCase):
    def test_untrusted_values_are_shown_as_plain_text(self):
        """사원번호·차단 사유·검색어는 Markdown 으로 해석되지 않고 st.text 로만 나온다."""
        at = AppTest.from_function(_detail_app).run(timeout=20)

        self.assertFalse(at.exception)
        text_values = [element.value for element in at.text]
        # 세 값이 모두 글자 그대로 text 요소에 들어 있다.
        self.assertTrue(any(RISKY in value for value in text_values))
        self.assertTrue(any(value.startswith("차단 사유:") and RISKY in value for value in text_values))
        self.assertTrue(any(value.startswith("검색어·질문:") and RISKY in value for value in text_values))
        # Markdown·오류 요소에는 위험한 값이 들어가지 않는다 (고정 문구만 남는다).
        rendered_as_markdown = [element.value for element in at.markdown] + [
            element.value for element in at.error
        ]
        self.assertFalse(any("example.com" in value for value in rendered_as_markdown))
        self.assertEqual([element.value for element in at.error], ["차단됨"])


if __name__ == "__main__":
    unittest.main()
