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


def _log(log_id=1, **overrides):
    """서비스가 돌려주는 로그 dict 모양 (화면용 값 포함)."""
    log = {
        "log_id": log_id,
        "created_at": "2026-10-28 14:22:08",
        "user_id": 1,
        "employee_no": "MVX-0001",
        "user_name": "홍길동",
        "company_code": "MVX",
        "action_type": "view_document",
        "action_label": "원문 열기",
        "target_type": "document",
        "target_id": "doc-1",
        "target_label": "스마트팩토리 사양서 v3",
        "blocked": True,
        "block_reason": "기밀, 승인 없음",
    }
    log.update(overrides)
    return log


SUMMARY = {
    "today_count": 312,
    "yesterday_count": 288,
    "blocked_count": 5,
    "blocked_reasons": [("기밀", 3), ("공유 꺼짐", 1)],
    "download_count": 14,
    "blocked_download_count": 0,
    "hourly": [8, 14, 30, 40, 34, 22, 38, 44, 26, 12],
}


class AuditLogPageViewTest(unittest.TestCase):
    OPTIONS = {"users": ["MVX-0001", "MVX-0002"], "action_types": ["login", "search"]}
    RESULT = {"logs": [_log()], "total_count": 1, "page": 1, "total_pages": 5}

    def _patches(self, **overrides):
        """서비스 함수를 가짜로 바꾼다. 화면이 DB 없이 그려지는지만 본다."""
        base = "app.admin.views.audit_logs."
        values = {
            "get_audit_filter_options": self.OPTIONS,
            "get_audit_scope_name": "현대무벡스",
            "get_audit_summary": SUMMARY,
            "search_audit_logs": self.RESULT,
            # 목록의 첫 기록이 자동 선택되어 상세 조회가 일어나므로 이것도 가짜로 바꾼다.
            "get_audit_log_detail": {
                **_log(),
                "role": "employee",
                "query": None,
                "result_count": None,
                "filters": None,
                "doc_ids": None,
                "doc_companies": None,
                "context_detail": None,
            },
        }
        values.update(overrides)
        return [patch(base + name, return_value=value) for name, value in values.items()]

    def _run(self, **overrides):
        patches = self._patches(**overrides)
        mocks = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        return mocks, AppTest.from_function(_page_app).run(timeout=30)

    def test_page_shows_title_scope_summary_and_row(self):
        """제목·관리 범위·요약 카드·목록 행(이름·행동·대상·차단 사유)이 그려진다."""
        _, at = self._run()

        self.assertFalse(at.exception)
        self.assertEqual(at.title[0].value, "감사 로그")
        self.assertEqual([m.label for m in at.metric][:3], ["오늘 기록", ":red[●] 차단된 접근", "원문 내려받기"])
        self.assertEqual(at.metric[0].value, "312")
        html_values = " ".join(element.value for element in at.get("html"))
        for expected in ("현대무벡스 관리", "홍길동", "원문 열기", "스마트팩토리 사양서 v3", "기밀, 승인 없음", "기밀 3, 공유 꺼짐 1"):
            self.assertIn(expected, html_values)

    def test_default_period_is_today(self):
        """처음 화면은 Figma 시안처럼 "오늘" 기간으로 조회한다."""
        mocks, at = self._run()
        search = mocks[3]
        filters = search.call_args.args[1]
        self.assertEqual(filters["start_date"], filters["end_date"])

    def test_untrusted_log_values_are_escaped(self):
        """이름·사유·대상에 들어 있는 HTML·Markdown 은 해석되지 않고 글자 그대로 나온다."""
        evil = _log(user_name="<b>굵게</b>", block_reason="<img src=x onerror=alert(1)>", target_label="[링크](http://example.com)")
        _, at = self._run(search_audit_logs={"logs": [evil], "total_count": 1, "page": 1, "total_pages": 1})

        html_values = " ".join(element.value for element in at.get("html"))
        self.assertNotIn("<b>굵게</b>", html_values)
        self.assertNotIn("<img", html_values)
        self.assertIn("&lt;b&gt;굵게&lt;/b&gt;", html_values)

    def test_changing_a_filter_returns_to_first_page(self):
        """3페이지를 보다가 필터를 바꾸면 1페이지부터 다시 조회한다."""
        mocks, at = self._run()
        search = mocks[3]

        at.number_input[0].set_value(3).run(timeout=30)
        self.assertEqual(search.call_args.args[2], 3)  # 필터가 그대로면 고른 페이지를 유지한다

        at.selectbox(key="admin-audit-user").select("MVX-0001").run(timeout=30)
        self.assertEqual(search.call_args.args[1]["employee_no"], "MVX-0001")
        self.assertEqual(search.call_args.args[2], 1)

    def test_blocked_only_toggle_is_passed_as_filter(self):
        """"차단만" 토글이 blocked_only 필터로 넘어간다."""
        mocks, at = self._run()
        at.toggle(key="admin-audit-blocked").set_value(True).run(timeout=30)
        self.assertIs(mocks[3].call_args.args[1]["blocked_only"], True)

    def test_empty_result_shows_notice_without_error(self):
        """조건에 맞는 로그가 없으면 안내 문구가 나온다."""
        _, at = self._run(search_audit_logs={"logs": [], "total_count": 0, "page": 1, "total_pages": 1})
        self.assertFalse(at.exception)
        self.assertTrue(any("조건에 맞는 감사 로그가 없습니다" in info.value for info in at.info))

    def test_employee_sees_permission_error(self):
        """일반 사원이면 서비스가 PermissionError 를 올리고, 화면은 안내 문구만 보여 준다."""
        patches = self._patches()
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        patch("app.admin.views.audit_logs.get_audit_filter_options", side_effect=PermissionError).start()
        self.addCleanup(patch.stopall)
        at = AppTest.from_function(_page_app).run(timeout=30)
        self.assertEqual([e.value for e in at.error], ["감사 로그는 관리자만 조회할 수 있습니다."])


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
