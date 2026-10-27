"""감사 로그 화면 컴포넌트 테스트. Streamlit AppTest 로 실제 렌더링 결과를 확인한다."""

import unittest

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
