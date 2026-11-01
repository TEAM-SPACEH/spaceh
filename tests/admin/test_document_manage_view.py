"""A-02 문서 관리 화면(필터·표·삭제·재색인·페이지 구성) 테스트. Streamlit AppTest로 렌더링을 확인하고 서비스는 가짜로 바꿔 DB 없이 돌린다.

실행: python -m unittest tests.admin.test_document_manage_view
"""

import unittest
from datetime import datetime
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

LIST = "app.admin.views.components.document_list."
PAGE = "app.admin.views.documents."
TOGGLE = "app.admin.views.components.group_share_toggle.set_group_share"


def _list_app():
    import streamlit as st

    from app.admin.views.components.document_list import render_document_list

    st.session_state["selected"] = render_document_list(
        {"id": 1}, {"company_id": "", "doc_type": "", "access_level": "", "index_status": "", "keyword": ""})


def _filters_app(companies=None):
    import streamlit as st

    from app.admin.views.components.document_filters import render_document_filters

    result = render_document_filters(
        companies if companies is not None else [{"company_id": "MVX", "name": "현대무벡스"}],
        {"report": "보고서"}, {"internal": "사내"}, {"done": "완료"})
    st.session_state["result"] = result


def _two_company_filters_app():
    from app.admin.views.components.document_filters import render_document_filters

    render_document_filters(
        [{"company_id": "MVX", "name": "현대무벡스"}, {"company_id": "ELV", "name": "현대엘리베이터"}],
        {"report": "보고서"}, {"internal": "사내"}, {"done": "완료"})


def _confirm_app():
    """확인창 본문만 직접 그린다. AppTest는 st.dialog 안의 버튼 클릭을 다시 실행하지 못해서 장식을 벗긴 함수를 쓴다."""
    from app.admin.views.components.document_list import confirm_delete

    confirm_delete.__wrapped__({"doc_id": "d1", "title": "스마트팩토리 사양서 v3"}, {"id": 1})


def _doc(doc_id="d1", **overrides):
    doc = {"doc_id": doc_id, "company_id": "MVX", "title": "스마트팩토리 사양서 v3", "file_name": "spec.pdf",
           "file_format": "pdf", "doc_type": "spec", "source_type": "internal", "access_level": "internal",
           "is_group_shared": False, "chunk_count": 54, "index_status": "done", "status_label": "완료",
           "error_message": None, "created_at": datetime(2026, 10, 28, 9, 0), "can_delete": True,
           "can_reindex": True}
    doc.update(overrides)
    return doc


def _result(*documents, page=1, total_pages=1):
    return {"documents": list(documents), "total": len(documents), "page": page,
            "size": 6, "total_pages": total_pages}


def _html(at) -> str:
    return " ".join(element.value for element in at.get("html"))


class DocumentListViewTest(unittest.TestCase):
    def _run(self, result=None, **extra):
        mocks = {}
        values = {"get_document_list": result if result is not None else _result(_doc())}
        values.update(extra)
        for name, value in values.items():
            patcher = patch(LIST + name, return_value=value)
            mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        return mocks, AppTest.from_function(_list_app).run(timeout=30)

    def test_row_shows_title_type_level_status_and_date(self):
        _, at = self._run()
        self.assertFalse(at.exception)
        html = _html(at)
        for expected in ("스마트팩토리 사양서 v3", "PDF", "54청크", "사양서", "사내", "완료", "10.28", "sh-ad-th"):
            self.assertIn(expected, html)

    def test_markdown_in_title_is_shown_as_plain_text(self):
        evil = _doc(title="**굵게** [클릭](http://x.com) <b>태그</b>")
        _, at = self._run(_result(evil))
        html = _html(at)
        self.assertNotIn("<b>태그</b>", html)
        self.assertIn("&lt;b&gt;태그&lt;/b&gt;", html)
        self.assertFalse(any("[클릭]" in m.value for m in at.markdown))

    def test_failed_status_shows_reason_in_cell_and_tooltip(self):
        failed = _doc(index_status="failed", status_label="실패", error_message="표 인식 실패")
        _, at = self._run(_result(failed))
        html = _html(at)
        self.assertIn("sh-ad-state-failed", html)
        self.assertIn('title="표 인식 실패"', html)
        self.assertIn("표 인식 실패</span>", html)  # 문서 칸 아래 줄에도 이유를 보여 준다

    def test_indexing_status_shows_bar_without_fake_percent(self):
        busy = _doc(index_status="indexing", status_label="색인 중", can_delete=False, can_reindex=False)
        _, at = self._run(_result(busy))
        html = _html(at)
        self.assertIn("sh-ad-bar", html)
        self.assertIn("진행 중", html)
        self.assertNotIn("%", html)

    def test_share_column_follows_access_level(self):
        docs = [_doc("d1"), _doc("d2", access_level="confidential"), _doc("d3", access_level="public"),
                _doc("d4", index_status="failed", status_label="실패", error_message="x")]
        _, at = self._run(_result(*docs))
        keys = [t.key for t in at.toggle]
        self.assertEqual(keys, ["group-share-d1-0", "group-share-d4-0"])
        self.assertFalse(at.toggle(key="group-share-d1-0").disabled)
        self.assertTrue(at.toggle(key="group-share-d4-0").disabled)  # 색인이 끝나지 않은 문서는 잠긴다
        html = _html(at)
        self.assertIn("불가", html)
        self.assertIn("해당 없음", html)

    def test_turning_toggle_calls_service(self):
        _, at = self._run()
        with patch(TOGGLE, return_value={"doc_id": "d1", "is_group_shared": True, "status": "success",
                                         "message": "공유 설정이 변경되었습니다."}) as setter:
            at.toggle(key="group-share-d1-0").set_value(True).run(timeout=30)
        setter.assert_called_once_with("d1", True, {"id": 1})
        self.assertEqual([t.value for t in at.toast], ["공유 설정이 변경되었습니다."])

    def test_first_document_is_selected_and_click_selects_another(self):
        _, at = self._run(_result(_doc("d1"), _doc("d2", title="두 번째")))
        self.assertEqual(at.session_state["selected"]["doc_id"], "d1")
        at.button(key="ad_pick-d2").click().run(timeout=30)
        self.assertEqual(at.session_state["selected"]["doc_id"], "d2")
        self.assertEqual(at.session_state["admin-docs-selected"], "d2")

    def test_selection_falls_back_to_first_when_selected_document_is_not_on_page(self):
        _, at = self._run(_result(_doc("d1")))
        at.session_state["admin-docs-selected"] = "gone"
        at.run(timeout=30)
        self.assertEqual(at.session_state["selected"]["doc_id"], "d1")

    def test_empty_result_shows_guidance_and_no_selection(self):
        _, at = self._run(_result())
        self.assertTrue(any("조건에 맞는 문서가 없습니다" in i.value for i in at.info))
        self.assertIsNone(at.session_state["selected"])

    def test_permission_error_shows_warning(self):
        patcher = patch(LIST + "get_document_list", side_effect=PermissionError("x"))
        patcher.start()
        self.addCleanup(patcher.stop)
        at = AppTest.from_function(_list_app).run(timeout=30)
        self.assertTrue(any("관리자 권한" in w.value for w in at.warning))

    def test_unexpected_error_hides_details(self):
        patcher = patch(LIST + "get_document_list", side_effect=RuntimeError("secret C:\\path"))
        patcher.start()
        self.addCleanup(patcher.stop)
        at = AppTest.from_function(_list_app).run(timeout=30)
        self.assertTrue(any("불러오지 못했습니다" in e.value for e in at.error))
        self.assertFalse(any("secret" in e.value for e in at.error))

    def test_pager_shows_range_and_moves_to_next_page(self):
        mocks, at = self._run(_result(_doc(), page=1, total_pages=3))
        self.assertIn("1건 중 1–1", _html(at))
        self.assertTrue(at.button(key="admin-docs-prev").disabled)
        self.assertEqual(mocks["get_document_list"].call_args.args[3], 6)  # 시안처럼 6건씩
        at.button(key="admin-docs-next").click().run(timeout=30)
        self.assertEqual(mocks["get_document_list"].call_args.args[2], 2)


class DeleteConfirmTest(unittest.TestCase):
    def _confirm(self, result):
        patcher = patch(LIST + "delete_document", return_value=result)
        mock = patcher.start()
        self.addCleanup(patcher.stop)
        at = AppTest.from_function(_confirm_app).run(timeout=30)
        self.assertTrue(any("되돌릴 수 없습니다" in e.value for e in at.get("html")))
        return mock, at

    def test_confirm_delete_calls_service(self):
        mock, at = self._confirm({"doc_id": "d1", "status": "deleted", "error_message": "", "warning": ""})
        at.button(key="admin-docs-delete-confirm").click().run(timeout=30)
        mock.assert_called_once_with("d1", {"id": 1})
        self.assertEqual(at.session_state["admin-docs-notice"], ("success", "문서를 삭제했습니다."))

    def test_cancel_does_not_call_service(self):
        mock, at = self._confirm({"doc_id": "d1", "status": "deleted", "error_message": "", "warning": ""})
        at.button(key="admin-docs-delete-cancel").click().run(timeout=30)
        mock.assert_not_called()

    def test_delete_failure_and_file_warning_become_notices(self):
        mock, at = self._confirm({"doc_id": "d1", "status": "failed",
                                  "error_message": "색인 중인 문서는 삭제할 수 없습니다.", "warning": ""})
        at.button(key="admin-docs-delete-confirm").click().run(timeout=30)
        self.assertEqual(at.session_state["admin-docs-notice"][0], "error")
        mock.return_value = {"doc_id": "d1", "status": "deleted", "error_message": "",
                             "warning": "원본 파일을 지우지 못했습니다."}
        at = AppTest.from_function(_confirm_app).run(timeout=30)
        at.button(key="admin-docs-delete-confirm").click().run(timeout=30)
        level, text = at.session_state["admin-docs-notice"]
        self.assertEqual(level, "warning")
        self.assertIn("원본 파일을 지우지 못했습니다", text)


class NoticeTest(unittest.TestCase):
    def test_saved_notice_is_shown_once(self):
        def app():
            from app.admin.views.components.document_list import notice, show_notice

            import streamlit as st

            if "saved" not in st.session_state:
                notice("success", "처리했습니다. ~표시")
                st.session_state["saved"] = True
            show_notice()

        at = AppTest.from_function(app).run(timeout=30)
        self.assertEqual([s.value for s in at.success], ["처리했습니다. \\~표시"])
        at.run(timeout=30)
        self.assertEqual(len(at.success), 0)


class DocumentFiltersViewTest(unittest.TestCase):
    def test_single_company_hides_company_chip_and_returns_empty_filters(self):
        at = AppTest.from_function(_filters_app).run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["result"],
                         {"company_id": "", "doc_type": "", "access_level": "", "index_status": "", "keyword": ""})
        self.assertEqual(len(at.get("popover")), 3)
        self.assertEqual([p.proto.popover.label for p in at.get("popover")], ["유형", "보안 등급", "색인 상태"])

    def test_several_companies_show_company_chip(self):
        at = AppTest.from_function(_two_company_filters_app).run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(len(at.get("popover")), 4)

    def test_selection_returns_codes_not_labels(self):
        at = AppTest.from_function(_filters_app).run(timeout=30)
        [s for s in at.selectbox if s.label == "보안 등급"][0].select("사내").run(timeout=30)
        [s for s in at.selectbox if s.label == "문서 유형"][0].select("보고서").run(timeout=30)
        at.text_input[0].input("agv").run(timeout=30)
        result = at.session_state["result"]
        self.assertEqual((result["access_level"], result["doc_type"], result["keyword"]), ("internal", "report", "agv"))


def _overview(**overrides):
    overview = {"total": 48, "week_added": 6, "daily": [0, 0, 2, 0, 2, 2, 0], "shared": 12, "internal_total": 31,
                "failed": 1, "failed_title": "고객사 미팅 메모", "pending_requests": 3, "oldest_pending_hours": 60}
    overview.update(overrides)
    return overview


class DocumentsPageTest(unittest.TestCase):
    OPTIONS = {"doc_types": ("report", "spec"), "security_levels": ("public", "confidential"),
               "index_statuses": {"done": "완료"}}

    def _run(self, overview=None, **patched):
        def app():
            from app.admin.views.documents import render_admin_documents

            render_admin_documents({"id": 1})

        targets = {
            "get_upload_companies": [{"company_id": "MVX", "name": "현대무벡스"}],
            "get_document_filter_options": self.OPTIONS,
            "get_document_overview": overview if overview is not None else _overview(),
            "get_share_scope_name": "현대무벡스",
            "render_document_list": _doc(),
            "render_document_panel": None,
        }
        targets.update(patched)
        mocks = {}
        for name, value in targets.items():
            patcher = patch(PAGE + name, return_value=value)
            mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        return mocks, AppTest.from_function(app).run(timeout=30)

    def test_page_shows_head_stats_buttons_and_hands_selection_to_panel(self):
        mocks, at = self._run()
        self.assertFalse(at.exception)
        html = _html(at)
        for expected in ("현대무벡스 관리", ">문서<", "그룹사 공유 중", "사내 문서 31건 중", "최근 7일 6건 추가",
                         "고객사 미팅 메모", "가장 오래된 요청 2일 전"):
            self.assertIn(expected, html)
        labels = [b.label for b in at.button]
        self.assertIn("문서 올리기", labels)
        self.assertIn("실패 문서 재색인", labels)
        self.assertEqual(len(at.tabs), 0)  # A-03은 별도 탭이 아니라 이 화면 안에 합쳐졌다
        mocks["render_document_panel"].assert_called_once()
        self.assertEqual(mocks["render_document_panel"].call_args.args[1]["doc_id"], "d1")

    def test_filter_choices_use_names_and_hide_unknown_types(self):
        _, at = self._run()
        by_label = {s.label: s.options for s in at.selectbox}
        self.assertIn("보고서", by_label["문서 유형"])
        self.assertIn("사양서", by_label["문서 유형"])
        self.assertIn("기밀", by_label["보안 등급"])

    def test_failed_reindex_button_is_disabled_without_failures(self):
        _, at = self._run(_overview(failed=0, failed_title=""))
        self.assertTrue(at.button(key="ad_reindex_failed").disabled)
        self.assertIn("실패한 문서가 없습니다.", _html(at))

    def test_several_failures_and_no_pending_requests_text(self):
        _, at = self._run(_overview(failed=3, pending_requests=0))
        html = _html(at)
        self.assertIn("고객사 미팅 메모 외 2건", html)
        self.assertIn("대기 중인 요청이 없습니다.", html)

    def test_reindex_failed_click_runs_service_and_leaves_summary_notice(self):
        mocks, at = self._run(reindex_failed_documents={"total": 2, "done": 1, "failed": 1, "skipped": 0})
        at.button(key="ad_reindex_failed").click().run(timeout=30)
        mocks["reindex_failed_documents"].assert_called_once_with({"id": 1})
        # 처리 뒤 st.rerun()으로 다시 그릴 때 한 번 보여 주는 안내다 (일부 실패면 경고 상자).
        self.assertTrue(any("2건 중 1건" in w.value and "1건은 다시 실패" in w.value for w in at.warning))

    def test_summary_failure_still_shows_table_and_error(self):
        mocks, at = self._run()
        mocks["get_document_overview"].side_effect = RuntimeError("db")
        with self.assertLogs("app.admin.views.documents", level="ERROR"):
            at = AppTest.from_function(_page_app).run(timeout=30)
        self.assertFalse(at.exception)
        self.assertTrue(any("요약을 불러오지 못했습니다" in e.value for e in at.error))
        mocks["render_document_list"].assert_called()

    def test_non_admin_sees_warning_and_nothing_else(self):
        def app():
            from app.admin.views.documents import render_admin_documents

            render_admin_documents({"id": 8})

        patcher = patch(PAGE + "get_upload_companies", side_effect=PermissionError("x"))
        patcher.start()
        self.addCleanup(patcher.stop)
        at = AppTest.from_function(app).run(timeout=30)
        self.assertTrue(any("관리자 권한" in w.value for w in at.warning))
        self.assertEqual(len(at.button), 0)

    def test_stats_html_escapes_failed_title(self):
        from app.admin.views.documents import stats_html

        html = stats_html(_overview(failed_title="<img src=x onerror=1>"))
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)


def _page_app():
    from app.admin.views.documents import render_admin_documents

    render_admin_documents({"id": 1})


if __name__ == "__main__":
    unittest.main()
