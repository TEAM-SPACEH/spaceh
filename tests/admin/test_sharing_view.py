"""A-03 그룹사 공유 화면 테스트. Streamlit AppTest 로 실제 렌더링 결과를 확인하고, 서비스는 가짜로 바꿔 DB 없이 돌린다.

실행: python -m unittest tests.admin.test_sharing_view
"""

import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

PAGE = "app.admin.views.sharing."
TOGGLE = "app.admin.views.components.group_share_toggle.set_group_share"

ADMIN = {"id": 2, "role": "company_admin", "company_id": "MVX"}


def _page_app():
    from app.admin.views.sharing import render_admin_sharing

    render_admin_sharing({"id": 2, "role": "company_admin", "company_id": "MVX"})


def _employee_app():
    from app.admin.views.sharing import render_admin_sharing

    render_admin_sharing({"id": 4, "role": "employee", "company_id": "MVX"})


def _doc(doc_id="d1", **overrides):
    doc = {
        "doc_id": doc_id,
        "company_id": "MVX",
        "title": "스마트팩토리 사양서 v3",
        "file_name": "spec.pdf",
        "file_format": "pdf",
        "doc_type": "spec",
        "access_level": "internal",
        "is_group_shared": False,
        "chunk_count": 54,
        "index_status": "done",
        "created_at": "2026-10-28",
    }
    doc.update(overrides)
    return doc


INTERNAL = _doc("d1")
CONFIDENTIAL = _doc("d2", title="고객사 계약 단가표", access_level="confidential", chunk_count=0)
RESULT = {"documents": [INTERNAL, CONFIDENTIAL], "total_count": 2, "page": 1, "total_pages": 1}
SUMMARY = {"shared": 12, "unshared": 19, "confidential": 4, "internal_total": 31}


def _html(at) -> str:
    return " ".join(element.value for element in at.get("html"))


class SharingViewTest(unittest.TestCase):
    def _run(self, app=_page_app, **overrides):
        """서비스 함수를 가짜로 바꿔 화면을 한 번 그린다. (호출 기록 mock 딕셔너리, AppTest) 를 돌려준다."""
        values = {
            "get_company_filter_options": [],
            "get_share_scope_name": "현대무벡스",
            "get_share_summary": SUMMARY,
            "get_manageable_documents": RESULT,
        }
        values.update(overrides)
        mocks = {}
        for name, value in values.items():
            patcher = patch(PAGE + name, return_value=value)
            mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        return mocks, AppTest.from_function(app).run(timeout=30)

    def test_page_shows_title_summary_table_and_panel(self):
        """관리 범위·제목·요약 카드·문서 행·오른쪽 패널이 그려진다."""
        _, at = self._run()

        self.assertFalse(at.exception)
        self.assertEqual(at.title[0].value, "그룹사 공유")
        self.assertEqual([m.value for m in at.metric], ["12", "19", "4"])
        html_values = _html(at)
        for expected in ("현대무벡스 관리", "스마트팩토리 사양서 v3", "54청크", "사내 문서 31건 중", "2건 중 1–2", "10.28"):
            self.assertIn(expected, html_values)

    def test_internal_row_has_toggle_and_confidential_row_says_unavailable(self):
        """사내 문서 행에는 토글이, 기밀 문서 행에는 "불가" 글자가 나온다."""
        _, at = self._run()

        row_toggle_keys = [t.key for t in at.toggle if t.key.startswith("group-share-")]
        self.assertEqual(row_toggle_keys, ["group-share-d1-0"])
        self.assertIn("불가", _html(at))

    def test_panel_for_internal_document_has_enabled_toggle(self):
        """처음에는 첫 문서(사내)가 패널에 선택되고, 패널 토글은 켤 수 있다."""
        _, at = self._run()
        panel = at.toggle(key="share-panel-d1-0")
        self.assertFalse(panel.disabled)

    def test_panel_for_confidential_document_is_locked_with_notice(self):
        """기밀 문서를 고르면 패널 토글이 잠기고 안내 문구가 나온다."""
        _, at = self._run()
        selector = [s for s in at.selectbox if s.label == "설정할 문서"][0]
        selector.select("d2").run(timeout=30)

        self.assertTrue(at.toggle(key="share-panel-d2-0").disabled)
        self.assertIn("기밀 문서는 공유할 수 없습니다. 사내 문서만 켤 수 있어요.", _html(at))
        self.assertTrue(any("기밀 공유 불가" in caption.value for caption in at.caption))

    def test_internal_document_not_indexed_yet_is_locked_with_notice(self):
        """색인이 끝나지 않은 사내 문서는 표·패널 토글이 모두 잠기고 안내가 나온다."""
        pending = _doc("d3", index_status="pending")
        _, at = self._run(get_manageable_documents={"documents": [pending], "total_count": 1, "page": 1, "total_pages": 1})

        self.assertTrue(at.toggle(key="group-share-d3-0").disabled)
        self.assertTrue(at.toggle(key="share-panel-d3-0").disabled)
        self.assertTrue(any("색인이 끝난 뒤 바꿀 수 있습니다." in caption.value for caption in at.caption))

    def test_turning_toggle_on_calls_service_and_shows_toast(self):
        """토글을 켜면 서비스가 호출되고 성공 토스트가 뜬다."""
        _, at = self._run()
        with patch(TOGGLE, return_value={"doc_id": "d1", "is_group_shared": True, "status": "success", "message": "공유 설정이 변경되었습니다."}) as setter:
            at.toggle(key="group-share-d1-0").set_value(True).run(timeout=30)

        setter.assert_called_once_with("d1", True, ADMIN)
        self.assertEqual([t.value for t in at.toast], ["공유 설정이 변경되었습니다."])

    def test_failed_change_reverts_toggle_and_shows_message(self):
        """서비스가 거부하면 토글은 원래 값으로 돌아가고 안내 문구가 뜬다."""
        _, at = self._run()
        with patch(TOGGLE, side_effect=PermissionError("자사 문서만 공유 설정을 변경할 수 있습니다.")):
            at.toggle(key="group-share-d1-0").set_value(True).run(timeout=30)

        self.assertFalse(at.toggle(key="group-share-d1-0").value)
        self.assertEqual([t.value for t in at.toast], ["자사 문서만 공유 설정을 변경할 수 있습니다."])

    def test_unexpected_error_shows_generic_message_without_details(self):
        """예상 못 한 오류는 내용을 화면에 보이지 않고 일반 안내만 보인다."""
        _, at = self._run()
        with patch(TOGGLE, side_effect=RuntimeError("secret db detail")), self.assertLogs("app.admin.views.components.group_share_toggle", level="ERROR"):
            at.toggle(key="group-share-d1-0").set_value(True).run(timeout=30)

        toasts = [t.value for t in at.toast]
        self.assertEqual(len(toasts), 1)
        self.assertNotIn("secret", toasts[0])
        self.assertFalse(at.toggle(key="group-share-d1-0").value)

    def test_untrusted_text_is_escaped(self):
        """제목에 든 HTML·Markdown 은 해석되지 않고 글자 그대로 나온다."""
        evil = _doc("d1", title="<img src=x onerror=alert(1)> **굵게** [링크](http://example.com)")
        _, at = self._run(get_manageable_documents={"documents": [evil], "total_count": 1, "page": 1, "total_pages": 1})

        html_values = _html(at)
        self.assertNotIn("<img", html_values)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", html_values)

    def test_filters_are_passed_to_service_and_filter_change_returns_to_first_page(self):
        """검색어·보안 등급·공유 상태가 서비스로 넘어가고, 필터를 바꾸면 1페이지부터 다시 읽는다."""
        mocks, at = self._run(get_manageable_documents={**RESULT, "total_count": 50, "total_pages": 3})
        service = mocks["get_manageable_documents"]

        # 다음 페이지로 이동한 뒤
        [b for b in at.button if b.key == "admin-sharing-next"][0].click().run(timeout=30)
        self.assertEqual(service.call_args.kwargs["page"], 2)

        # 필터를 바꾸면 1페이지
        at.selectbox(key="admin-sharing-share").select("공유 ON").run(timeout=30)
        kwargs = service.call_args.kwargs
        self.assertIs(kwargs["share_filter"], True)
        self.assertEqual(kwargs["page"], 1)

        at.selectbox(key="admin-sharing-level").select("기밀").run(timeout=30)
        self.assertEqual(service.call_args.kwargs["access_level"], "confidential")
        at.text_input(key="admin-sharing-keyword").set_value(" 단가 ").run(timeout=30)
        self.assertEqual(service.call_args.kwargs["keyword"], "단가")

    def test_company_filter_only_for_super_admin(self):
        """계열사 선택 칩은 서비스가 계열사 목록을 줄 때(최종 어드민)만 나온다."""
        _, at = self._run()
        self.assertEqual([s for s in at.selectbox if s.key == "admin-sharing-company"], [])

        _, at = self._run(get_company_filter_options=["ELV", "HRI", "MVX"])
        company = at.selectbox(key="admin-sharing-company")
        self.assertEqual(list(company.options), ["전체", "ELV", "HRI", "MVX"])

    def test_empty_result_shows_notice_and_no_panel_toggle(self):
        """조건에 맞는 문서가 없으면 안내 문구가 나오고 토글은 없다."""
        _, at = self._run(get_manageable_documents={"documents": [], "total_count": 0, "page": 1, "total_pages": 1})

        self.assertFalse(at.exception)
        self.assertTrue(any("조건에 맞는 문서가 없습니다" in info.value for info in at.info))
        self.assertEqual(len(at.toggle), 0)

    def test_employee_is_blocked_before_any_service_call(self):
        """일반 사원은 안내 문구만 보고, 서비스는 한 번도 호출되지 않는다."""
        mocks, at = self._run(app=_employee_app)

        self.assertEqual([e.value for e in at.error], ["관리자만 접근할 수 있는 페이지입니다."])
        for mock in mocks.values():
            mock.assert_not_called()

    def test_list_failure_shows_error_not_traceback(self):
        """목록 조회가 실패하면 일반 안내만 보이고 예외는 화면에 나오지 않는다."""
        mocks, at = self._run()
        mocks["get_manageable_documents"].side_effect = RuntimeError("db down")
        with self.assertLogs("app.admin.views.sharing", level="ERROR"):
            at = AppTest.from_function(_page_app).run(timeout=30)

        self.assertFalse(at.exception)
        self.assertEqual([e.value for e in at.error], ["문서 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."])


if __name__ == "__main__":
    unittest.main()
