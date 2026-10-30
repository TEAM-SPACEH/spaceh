"""보고서 보기 화면(report_view)·폼 연결 테스트: HTML 조각의 안전성, 이동 콜백, 화면 그리기.

실행: python -m unittest tests.reports.test_report_view
"""

import unittest
from datetime import date, datetime
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from app.reports.models.report_models import (
    ExecSummary, Footnote, Report, ReportRequest, ReportTemplate, Section, SectionType, SummaryItem,
)
from app.reports.views import report_form
from app.reports.views import report_view as view
from app.reports.views import report_form_state as state

OPEN_REPORT = "app.reports.views.report_view.open_report"


def make_note(number: int = 1, **overrides) -> Footnote:
    values = dict(number=number, company="현대무벡스", company_id="MVX", filename="3분기 실적 보고서.pdf",
                  location="p.7", quote="인용", text="본문", doc_id="d1", chunk_id=f"d1#{number}")
    values.update(overrides)
    return Footnote(**values)


def make_report(level: str = "internal") -> Report:
    request = ReportRequest(ReportTemplate.COMPREHENSIVE, "스마트 물류", ["MVX", "HRI"], date(2025, 7, 1), date(2025, 10, 31))
    summary = ExecSummary(
        items=[
            SummaryItem("key", "수주가 늘었습니다. [1]", SectionType.STATUS),
            SummaryItem("advice", "고객군을 넓힙니다. [2]", SectionType.ADVICE),
        ],
        notes=["현대엘리베이터 근거 없음"],
    )
    return Report(
        request=request,
        sections=[Section(SectionType.OVERVIEW, "개요", "배경입니다. [1]"),
                  Section(SectionType.STATUS, "계열사별 현황", "현황입니다. [1][2]"),
                  Section(SectionType.ADVICE, "제언", "제언입니다. [2]")],
        footnotes=[make_note(1), make_note(2, filename="2025 반기보고서", doc_id="d2", chunk_id="d2#2")],
        exec_summary=summary, report_id=7, user_id=3, max_access_level=level,
    )


def opened(report: Report) -> dict:
    return {"status": "ok", "report": report, "created_at": datetime(2026, 10, 29, 13, 40),
            "source_types": {"d1": "internal", "d2": "dart"}, "blocked_count": 0}


class HtmlTest(unittest.TestCase):

    def test_citation_numbers_become_badges_and_text_is_escaped(self):
        out = view._cited_html("<script>x</script> 늘었습니다 [3]")

        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)
        self.assertIn('<span class="sh-cite">3</span>', out)

    def test_head_escapes_topic_and_shows_period_count_and_time(self):
        report = make_report()
        report.request.topic = "<b>주제</b>"

        out = view._head_html(report, datetime(2026, 10, 29, 13, 40))

        self.assertNotIn("<b>주제", out)
        self.assertIn("종합 보고서", out)
        self.assertIn("2025.07 – 2025.10, 근거 2건,", out)

    def test_footnote_row_escapes_file_name(self):
        out = view._footnote_row_html(make_note(filename="<img src=x onerror=1>.pdf"))

        self.assertNotIn("<img src=x", out)
        self.assertIn("&lt;img", out)


class RequestedReportIdTest(unittest.TestCase):
    """주소의 ?report_id= 해석. 숫자가 아니면 새 보고서 폼으로 간다."""

    def requested(self, query: dict):
        with patch.object(report_form.st, "query_params", query):
            return report_form._requested_report_id()

    def test_number_is_used(self):
        self.assertEqual(self.requested({"report_id": "7"}), 7)

    def test_missing_zero_negative_and_text_are_ignored(self):
        for query in ({}, {"report_id": "0"}, {"report_id": "-1"}, {"report_id": "abc"}, {"report_id": ""}):
            with self.subTest(query=query):
                self.assertIsNone(self.requested(query))


class CallbackTest(unittest.TestCase):
    """이동 콜백은 세션 값만 바꾼다. Streamlit 세션 대신 가짜 사전으로 확인한다."""

    def test_go_to_detail_opens_full_report_tab_at_that_section(self):
        session = {}
        with patch.object(view.st, "session_state", session):
            view.go_to_detail(SectionType.STATUS)

        self.assertEqual(session[view.TAB_KEY], view.TAB_FULL)
        self.assertEqual(session[view.FOCUS_KEY], "status")
        self.assertEqual(session[view.CURRENT_KEY], "status")

    def test_go_to_summary_clears_focus(self):
        session = {view.FOCUS_KEY: "status", view.TAB_KEY: view.TAB_FULL}
        with patch.object(view.st, "session_state", session):
            view.go_to_summary()

        self.assertEqual(session[view.TAB_KEY], view.TAB_SUMMARY)
        self.assertNotIn(view.FOCUS_KEY, session)

    def test_open_source_uses_s05_shape_and_remembers_it_as_this_screens(self):
        session = {}
        with patch.object(view.st, "session_state", session):
            view._open_source(make_note(2))

        source = session[view.SELECTED_SOURCE_KEY]
        self.assertEqual((source["doc_id"], source["citation_number"], source["location"]), ("d1", 2, "p.7"))
        self.assertIs(session[view.OPEN_SOURCE_KEY], source)

    def test_rebuild_prefills_form_and_clears_report_id(self):
        session = {view.TAB_KEY: view.TAB_FULL}
        with patch.object(view.st, "session_state", session), patch.object(view.st, "query_params") as params:
            view._rebuild(make_report())

        self.assertEqual(session[state.TOPIC_KEY], "스마트 물류")
        self.assertEqual(session[state.COMPANIES_KEY], ["MVX", "HRI"])
        self.assertEqual(session[state.START_KEY], date(2025, 7, 1))
        self.assertEqual(session[state.TEMPLATE_KEY], "comprehensive")
        self.assertNotIn(view.TAB_KEY, session)  # 보던 탭은 다음 보고서에 남지 않는다
        params.clear.assert_called_once()


def render_app(opened_result: dict):
    """report_view를 실제로 그려 본다(Streamlit AppTest). open_report만 가짜로 바꾼다."""
    def script():
        from app.reports.views.report_view import render_report_view
        render_report_view({"id": 3, "role": "employee", "company_id": "MVX"}, 7)

    with patch(OPEN_REPORT, return_value=opened_result):
        app = AppTest.from_function(script, default_timeout=20)
        app.run()
    return app


class RenderTest(unittest.TestCase):

    def test_summary_tab_shows_buttons_toc_and_footnote_links(self):
        app = render_app(opened(make_report()))

        self.assertFalse(app.exception)
        labels = [button.label for button in app.button]
        self.assertIn("다시 만들기", labels)
        self.assertIn("핵심 요약", labels)      # 목차
        self.assertIn("각주 2", labels)
        self.assertIn("DART", labels)           # d2는 DART 공시라 링크 글자가 다르다
        self.assertEqual(labels.count("상세 보기 ›"), 2)

    def test_blocked_report_shows_notice_without_content(self):
        app = render_app({"status": "blocked", "report": None, "created_at": None, "source_types": {}, "blocked_count": 1})

        self.assertFalse(app.exception)
        self.assertIn("열람할 수 없는 문서", app.warning[0].value)
        self.assertEqual([button.label for button in app.button], ["보고서 목록"])

    def test_missing_report_shows_guide(self):
        app = render_app({"status": "not_found", "report": None, "created_at": None, "source_types": {}, "blocked_count": 0})

        self.assertFalse(app.exception)
        self.assertIn("보고서를 찾을 수 없습니다", app.info[0].value)


if __name__ == "__main__":
    unittest.main()
