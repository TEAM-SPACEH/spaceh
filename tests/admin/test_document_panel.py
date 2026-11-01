"""A-02·A-03 문서 상세 패널(보안 등급·그룹사 공유·볼 수 있는 사람·삭제·재색인) 화면 테스트.

Streamlit AppTest로 실제 렌더링을 확인하고 서비스는 가짜로 바꿔 DB 없이 돌린다.
실행: python -m unittest tests.admin.test_document_panel
"""

import unittest
from datetime import datetime
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

PANEL = "app.admin.views.components.document_panel."
USER = {"id": 2, "role": "company_admin", "company_id": "MVX"}


def _panel_app():
    import streamlit as st

    from app.admin.views.components.document_panel import render_document_panel

    render_document_panel({"id": 2, "role": "company_admin", "company_id": "MVX"}, st.session_state["doc"])


def _doc(doc_id="d1", **overrides):
    doc = {"doc_id": doc_id, "company_id": "MVX", "title": "스마트팩토리 사양서 v3", "file_name": "spec.pdf",
           "file_format": "pdf", "doc_type": "spec", "source_type": "internal", "access_level": "internal",
           "is_group_shared": False, "chunk_count": 54, "index_status": "done", "status_label": "완료",
           "error_message": None, "created_at": datetime(2026, 9, 12, 9, 0), "can_delete": True, "can_reindex": True}
    doc.update(overrides)
    return doc


DETAIL = {"doc_id": "d1", "uploader_name": "최관리", "viewers": [
    {"label": "현대무벡스 관리자 2명", "company_id": None, "note": "역할"},
    {"label": "정승강", "company_id": "ELV", "note": "10.23 승인"},
    {"label": "최종 어드민", "company_id": None, "note": "전체"}]}


def _html(at) -> str:
    return " ".join(element.value for element in at.get("html"))


class DocumentPanelTest(unittest.TestCase):
    def _run(self, doc=None, detail=DETAIL, **extra):
        mocks = {}
        values = {"get_document_detail": detail}
        values.update(extra)
        for name, value in values.items():
            kwargs = {"side_effect": value} if isinstance(value, Exception) else {"return_value": value}
            patcher = patch(PANEL + name, **kwargs)
            mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        at = AppTest.from_function(_panel_app)
        at.session_state["doc"] = doc if doc is not None else _doc()
        return mocks, at.run(timeout=30)

    def test_shows_title_uploader_viewers_and_read_only_level(self):
        _, at = self._run()
        self.assertFalse(at.exception)
        html = _html(at)
        for expected in ("스마트팩토리 사양서 v3", "올린 사람 최관리, 09.12", "현대무벡스 관리자 2명", "10.23 승인",
                         "최종 어드민", "sh-ad-tag-int", "볼 수 있는 사람"):
            self.assertIn(expected, html)
        level = at.selectbox(key="ad-panel-level-d1")
        self.assertTrue(level.disabled)  # 보안 등급 변경은 지원하지 않는다 (명세 밖)
        self.assertEqual(level.value, "사내")

    def test_untrusted_title_and_names_are_escaped(self):
        detail = {**DETAIL, "uploader_name": "<b>x</b>",
                  "viewers": [{"label": "<img src=x>", "company_id": None, "note": "<i>"}]}
        _, at = self._run(_doc(title="<img src=x onerror=1> **굵게**"), detail=detail)
        html = _html(at)
        self.assertNotIn("<img", html)
        self.assertNotIn("<b>x</b>", html)
        self.assertIn("&lt;img src=x onerror=1&gt;", html)

    def test_internal_done_document_toggle_is_enabled_and_save_calls_service(self):
        _, at = self._run()
        toggle = at.toggle(key="ad-panel-share-d1-0")
        self.assertFalse(toggle.disabled)
        done = {"doc_id": "d1", "is_group_shared": True, "status": "success", "message": "공유 설정이 변경되었습니다."}
        with patch(PANEL + "set_group_share", return_value=done) as setter:
            toggle.set_value(True).run(timeout=30)
            at.button(key="ad-panel-save-d1").click().run(timeout=30)
        setter.assert_called_once_with("d1", True, USER)

    def test_save_without_change_does_not_call_service(self):
        _, at = self._run()
        with patch(PANEL + "set_group_share") as setter:
            at.button(key="ad-panel-save-d1").click().run(timeout=30)
        setter.assert_not_called()
        self.assertEqual([t.value for t in at.toast], ["바꾼 내용이 없습니다."])

    def test_rejected_change_shows_service_message(self):
        _, at = self._run()
        with patch(PANEL + "set_group_share", side_effect=PermissionError("자사 문서만 공유 설정을 변경할 수 있습니다.")):
            at.toggle(key="ad-panel-share-d1-0").set_value(True).run(timeout=30)
            at.button(key="ad-panel-save-d1").click().run(timeout=30)
        self.assertEqual([t.value for t in at.toast], ["자사 문서만 공유 설정을 변경할 수 있습니다."])

    def test_unexpected_error_shows_generic_message_without_details(self):
        _, at = self._run()
        with patch(PANEL + "set_group_share", side_effect=RuntimeError("secret db detail")), \
                self.assertLogs("app.admin.views.components.document_panel", level="ERROR"):
            at.toggle(key="ad-panel-share-d1-0").set_value(True).run(timeout=30)
            at.button(key="ad-panel-save-d1").click().run(timeout=30)
        toasts = [t.value for t in at.toast]
        self.assertEqual(len(toasts), 1)
        self.assertNotIn("secret", toasts[0])

    def test_confidential_toggle_is_locked_with_notice(self):
        _, at = self._run(_doc("d2", access_level="confidential"))
        self.assertTrue(at.toggle(key="ad-panel-share-d2-0").disabled)
        self.assertIn("기밀 문서는 공유할 수 없습니다. 사내 문서만 켤 수 있어요.", _html(at))
        self.assertIn("sh-ad-tag-con", _html(at))

    def test_not_indexed_internal_document_is_locked_with_notice(self):
        _, at = self._run(_doc("d3", index_status="pending", status_label="대기"))
        self.assertTrue(at.toggle(key="ad-panel-share-d3-0").disabled)
        self.assertIn("색인이 끝난 뒤 바꿀 수 있습니다.", _html(at))

    def test_toggle_key_follows_current_share_state(self):
        _, at = self._run(_doc("d4", is_group_shared=True))
        self.assertTrue(at.toggle(key="ad-panel-share-d4-1").value)

    def test_buttons_follow_service_flags(self):
        _, at = self._run(_doc(can_delete=False, can_reindex=False))
        self.assertTrue(at.button(key="admin-docs-delete-d1").disabled)
        self.assertTrue(at.button(key="admin-docs-reindex-d1").disabled)

    def test_reindex_click_calls_service_and_leaves_notice(self):
        _, at = self._run()
        result = {"doc_id": "d1", "index_status": "done", "chunk_count": 7, "error_message": ""}
        with patch("app.admin.views.components.document_list.request_reindex", return_value=result) as reindex:
            at.button(key="admin-docs-reindex-d1").click().run(timeout=30)
        reindex.assert_called_once_with("d1", USER)
        self.assertEqual(at.session_state["admin-docs-notice"], ("success", "재색인을 마쳤습니다. 청크 7개"))

    def test_reindex_failure_leaves_error_notice(self):
        _, at = self._run()
        result = {"doc_id": "d1", "index_status": "failed", "chunk_count": 0, "error_message": "색인 단계 실패 (ValueError)"}
        with patch("app.admin.views.components.document_list.request_reindex", return_value=result):
            at.button(key="admin-docs-reindex-d1").click().run(timeout=30)
        self.assertEqual(at.session_state["admin-docs-notice"], ("error", "색인 단계 실패 (ValueError)"))

    def test_delete_button_opens_confirmation_without_deleting(self):
        _, at = self._run()
        with patch("app.admin.views.components.document_list.delete_document") as delete:
            at.button(key="admin-docs-delete-d1").click().run(timeout=30)
        self.assertFalse(at.exception)
        delete.assert_not_called()  # 확인창만 열린다

    def test_no_selection_shows_guidance(self):
        at = AppTest.from_function(_panel_app)
        at.session_state["doc"] = None
        at.run(timeout=30)
        self.assertFalse(at.exception)
        self.assertTrue(any("문서를 고르면" in i.value for i in at.info))
        self.assertEqual(len(at.toggle), 0)

    def test_detail_failure_still_shows_document_and_safe_message(self):
        with self.assertLogs("app.admin.views.components.document_panel", level="ERROR"):
            _, at = self._run(detail=RuntimeError("db secret"))
        self.assertFalse(at.exception)
        self.assertIn("스마트팩토리 사양서 v3", _html(at))
        self.assertIn("목록을 불러오지 못했습니다", _html(at))
        self.assertNotIn("secret", _html(at))

    def test_detail_permission_error_shows_warning_and_no_controls(self):
        _, at = self._run(detail=PermissionError("자사 문서만 관리할 수 있습니다."))
        self.assertTrue(any("자사 문서만" in w.value for w in at.warning))
        self.assertEqual(len(at.toggle), 0)


if __name__ == "__main__":
    unittest.main()
