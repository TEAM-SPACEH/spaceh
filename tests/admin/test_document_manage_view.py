"""A-02 문서 관리 화면(필터·목록·삭제·재색인) 테스트. Streamlit AppTest로 렌더링을 확인하고 서비스는 가짜로 바꿔 DB 없이 돌린다.

실행: python -m unittest tests.admin.test_document_manage_view
"""

import unittest
from datetime import datetime
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

LIST = "app.admin.views.components.document_list."
PAGE = "app.admin.views.documents."


def _list_app():
    from app.admin.views.components.document_list import render_document_list

    render_document_list({"id": 1}, {"company_id": "", "doc_type": "", "access_level": "",
                                     "index_status": "", "keyword": ""})


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
    from app.admin.views.components.document_list import _confirm_delete

    _confirm_delete.__wrapped__({"doc_id": "d1", "title": "스마트팩토리 사양서 v3"}, {"id": 1})


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
            "size": 20, "total_pages": total_pages}


def _html(at) -> str:
    return " ".join(element.value for element in at.get("html"))


class DocumentListViewTest(unittest.TestCase):
    def _run(self, result=None, **extra):
        mocks = {}
        values = {"get_document_list": result if result is not None else _result(_doc()),
                  "request_reindex": {"doc_id": "d1", "index_status": "done", "chunk_count": 7, "error_message": ""},
                  "delete_document": {"doc_id": "d1", "status": "deleted", "error_message": "", "warning": ""}}
        values.update(extra)
        for name, value in values.items():
            patcher = patch(LIST + name, return_value=value)
            mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        return mocks, AppTest.from_function(_list_app).run(timeout=30)

    def test_row_shows_title_company_status_and_date(self):
        _, at = self._run()
        self.assertFalse(at.exception)
        html = _html(at)
        for expected in ("스마트팩토리 사양서 v3", "MVX", "PDF", "spec.pdf · 54청크", "완료", "10.28", "사내"):
            self.assertIn(expected, html)

    def test_markdown_in_title_is_shown_as_plain_text(self):
        evil = _doc(title="**굵게** [클릭](http://x.com) <b>태그</b>")
        _, at = self._run(_result(evil))
        html = _html(at)
        self.assertNotIn("<b>태그</b>", html)
        self.assertIn("&lt;b&gt;태그&lt;/b&gt;", html)
        self.assertFalse(any("[클릭]" in m.value for m in at.markdown))

    def test_buttons_follow_service_flags(self):
        busy = _doc("d2", index_status="indexing", status_label="색인 중", can_delete=False, can_reindex=False)
        dart = _doc("d3", source_type="dart", can_reindex=False)
        _, at = self._run(_result(_doc(), busy, dart))
        self.assertFalse(at.button(key="admin-docs-reindex-d1").disabled)
        self.assertFalse(at.button(key="admin-docs-delete-d1").disabled)
        self.assertTrue(at.button(key="admin-docs-reindex-d2").disabled)
        self.assertTrue(at.button(key="admin-docs-delete-d2").disabled)
        self.assertTrue(at.button(key="admin-docs-reindex-d3").disabled)
        self.assertFalse(at.button(key="admin-docs-delete-d3").disabled)

    def test_failed_status_shows_reason(self):
        failed = _doc(index_status="failed", status_label="실패", error_message="임베딩 단계 실패 (RuntimeError)")
        _, at = self._run(_result(failed))
        self.assertIn("임베딩 단계 실패 (RuntimeError)", _html(at))
        self.assertIn("sh-con", _html(at))

    def test_reindex_click_calls_service_and_shows_success(self):
        mocks, at = self._run()
        at.button(key="admin-docs-reindex-d1").click().run(timeout=30)
        mocks["request_reindex"].assert_called_once_with("d1", {"id": 1})
        self.assertFalse(at.exception)
        self.assertTrue(any("재색인을 마쳤습니다" in s.value and "7" in s.value for s in at.success))

    def test_reindex_failure_shows_error(self):
        mocks, at = self._run(request_reindex={"doc_id": "d1", "index_status": "failed", "chunk_count": 0,
                                               "error_message": "색인 단계 실패 (ValueError)"})
        at.button(key="admin-docs-reindex-d1").click().run(timeout=30)
        self.assertTrue(any("색인 단계 실패" in e.value for e in at.error))

    def test_delete_button_opens_confirmation_without_deleting(self):
        mocks, at = self._run()
        at.button(key="admin-docs-delete-d1").click().run(timeout=30)
        self.assertFalse(at.exception)
        mocks["delete_document"].assert_not_called()  # 확인창만 열렸다

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

    def test_empty_result_shows_guidance(self):
        _, at = self._run(_result())
        self.assertTrue(any("조건에 맞는 문서가 없습니다" in i.value for i in at.info))

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

    def test_pager_moves_to_next_page(self):
        mocks, at = self._run(_result(_doc(), page=1, total_pages=3))
        self.assertTrue(at.button(key="admin-docs-prev").disabled)
        at.button(key="admin-docs-next").click().run(timeout=30)
        self.assertEqual(mocks["get_document_list"].call_args.args[2], 2)


class DocumentFiltersViewTest(unittest.TestCase):
    def test_single_company_hides_company_chip_and_returns_empty_filters(self):
        at = AppTest.from_function(_filters_app).run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state["result"],
                         {"company_id": "", "doc_type": "", "access_level": "", "index_status": "", "keyword": ""})
        self.assertEqual(len(at.get("popover")), 3)

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


class DocumentsPageTest(unittest.TestCase):
    def test_page_composes_upload_filters_list_and_sharing_tab(self):
        def app():
            from app.admin.views.documents import render_admin_documents

            render_admin_documents({"id": 1})

        options = {"doc_types": {"report": "보고서"}, "security_levels": {"internal": "사내"},
                   "index_statuses": {"done": "완료"}}
        patcher = patch(PAGE + "get_upload_companies", return_value=[{"company_id": "MVX", "name": "현대무벡스"}])
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch(PAGE + "get_document_filter_options", return_value=options)
        patcher.start()
        self.addCleanup(patcher.stop)
        for target in (PAGE + "render_document_list", PAGE + "render_admin_sharing"):
            patcher = patch(target)
            patcher.start()
            self.addCleanup(patcher.stop)
        at = AppTest.from_function(app).run(timeout=30)
        self.assertFalse(at.exception)
        self.assertEqual([t.label for t in at.tabs], ["문서 목록", "그룹사 공유"])
        self.assertTrue(any(b.label == "문서 올리기" for b in at.button))

    def test_non_admin_sees_warning_and_no_tabs(self):
        def app():
            from app.admin.views.documents import render_admin_documents

            render_admin_documents({"id": 8})

        patcher = patch(PAGE + "get_upload_companies", side_effect=PermissionError("x"))
        patcher.start()
        self.addCleanup(patcher.stop)
        at = AppTest.from_function(app).run(timeout=30)
        self.assertTrue(any("관리자 권한" in w.value for w in at.warning))
        self.assertEqual(len(at.tabs), 0)


if __name__ == "__main__":
    unittest.main()
