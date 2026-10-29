"""A-01 업로드 모달의 파일별 처리와 권한 오류 검증."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


def upload_page():
    """A-01 테스트용 관리자 화면을 연다."""
    from app.admin.views.components.document_upload import render_document_upload
    render_document_upload({"id": 1})


def documents_page():
    """A-01 이전 관리자 역할이 남아 있는 세션으로 문서 페이지를 연다."""
    from app.admin.views.documents import render_admin_documents
    render_admin_documents({"id": 1, "role": "company_admin", "company_id": "MVX"})


class DocumentUploadViewTest(unittest.TestCase):
    """A-01 실제 API 호출 없이 모달의 제출 흐름을 확인한다."""

    def test_uploader_keeps_queue_when_adding_and_removing_files(self):
        """A-01 업로더를 비워도 원본 바이트를 보존하며 다음 선택을 목록에 추가한다."""
        with patch("app.admin.views.components.document_upload.get_upload_companies",
                   return_value=[{"company_id": "MVX", "name": "현대무벡스"}]):
            app = AppTest.from_function(upload_page).run()
            app.get("file_uploader")[0].upload("first.pdf", b"first", "application/pdf").run()
            self.assertFalse(app.exception)
            self.assertEqual(app.get("file_uploader")[0].value, [])
            app.get("file_uploader")[0].upload("second.pdf", b"second", "application/pdf").run()
            queue = dict(app.session_state["upload-files"])
            self.assertEqual([f.getvalue() for f in queue.values()], [b"first", b"second"])
            app.button(key=f"remove-{next(iter(queue))}").click().run()
            self.assertFalse(app.exception)
            self.assertEqual([f.name for f in app.session_state["upload-files"].values()], ["second.pdf"])
            next(b for b in app.button if b.label == "전체 지우기").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(dict(app.session_state["upload-files"]), {})

    def test_open_dialog_from_documents(self):
        """A-01 문서 올리기 버튼으로 모달을 열고 닫는다."""
        def page():
            """A-01 관리자 문서 화면을 렌더링한다."""
            from app.admin.views.documents import render_admin_documents
            render_admin_documents({"id": 1})

        with patch("app.admin.views.components.document_upload.get_upload_companies",
                   return_value=[{"company_id": "MVX", "name": "현대무벡스"}]), \
             patch("app.admin.views.documents.get_upload_companies",
                   return_value=[{"company_id": "MVX", "name": "현대무벡스"}]),              patch("app.admin.views.documents.render_document_list"),              patch("app.admin.views.documents.render_admin_sharing"):
            app = AppTest.from_function(page).run()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(app.selectbox(key="upload-access").value, "internal")
            self.assertTrue(next(b for b in app.button if b.label == "업로드").disabled)
            next(b for b in app.button if b.label == "닫기").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.radio), 0)

    def test_inactive_or_demoted_admin_cannot_open_upload(self):
        """A-01 DB에서 비활성화·강등되면 오래된 관리자 세션에도 업로드 버튼을 숨긴다."""
        for current in (None, {"id": 1, "role": "employee", "company_id": "MVX"}):
            with self.subTest(current=current), \
                 patch("app.admin.services.document_service.repository.find_active_admin",
                       return_value=current) as find_admin, \
                 patch("app.admin.services.document_service.repository.list_active_companies") as companies:
                app = AppTest.from_function(documents_page).run()
                self.assertFalse(app.exception)
                self.assertEqual(len(app.warning), 1)
                self.assertNotIn("문서 올리기", [b.label for b in app.button])
                self.assertEqual(len(app.get("file_uploader")), 0)
                find_admin.assert_called_once_with(1)
                companies.assert_not_called()

    def test_database_error_does_not_look_like_permission_revocation(self):
        """A-01 DB 오류는 권한 변경 안내와 구분하며 버튼을 제공하지 않는다."""
        with patch("app.admin.services.document_service.repository.find_active_admin",
                   side_effect=RuntimeError("private connection details")):
            app = AppTest.from_function(documents_page).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.error), 1)
            self.assertEqual(len(app.warning), 0)
            self.assertNotIn("문서 올리기", [b.label for b in app.button])
            self.assertNotIn("private", app.error[0].value)

    def test_multiple_files_keep_individual_results(self):
        """A-01 일부 실패해도 다음 파일을 처리하고 재실행 시 중복 제출하지 않는다."""
        files = [SimpleNamespace(name=f"sample{i}.pdf", size=100, file_id=str(i))
                 for i in range(3)]
        results = [
            {"index_status": "done", "chunk_count": 2},
            {"index_status": "failed", "error_message": "색인 실패"},
            {"index_status": "duplicate", "document": {"title": "기존 문서"}},
        ]
        with patch("app.admin.views.components.document_upload.get_upload_companies",
                   return_value=[{"company_id": "MVX", "name": "현대무벡스"}]), \
             patch("app.admin.views.components.document_upload.st.file_uploader",
                   side_effect=[files] + [[]] * 10), \
             patch("app.admin.views.components.document_upload.upload_document",
                   side_effect=results) as upload:
            app = AppTest.from_function(upload_page).run()
            self.assertFalse(app.exception)
            next(b for b in app.button if b.label == "업로드").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(upload.call_count, 3)
            self.assertEqual(upload.call_args.args[1]["access_level"], "internal")
            status_html = "".join(element.proto.body for element in app.get("html"))
            self.assertIn('sh-upload-status-done', status_html)
            self.assertIn('sh-upload-status-failed', status_html)
            self.assertIn('sh-upload-status-duplicate', status_html)
            app.selectbox(key="upload-access").set_value("confidential").run()
            self.assertEqual(upload.call_count, 3)
            self.assertTrue(next(b for b in app.button if b.label == "업로드").disabled)
            next(b for b in app.button if b.label == "전체 지우기").click().run()
            self.assertEqual(dict(app.session_state["upload-results"]), {})
            self.assertEqual(dict(app.session_state["upload-files"]), {})

    def test_remove_selected_file(self):
        """A-01 개별 제거는 선택 목록에서만 빼고 업로드 서비스를 호출하지 않는다."""
        files = [SimpleNamespace(name="sample.pdf", size=100, file_id="file-1")]
        with patch("app.admin.views.components.document_upload.get_upload_companies",
                   return_value=[{"company_id": "MVX", "name": "현대무벡스"}]), \
             patch("app.admin.views.components.document_upload.st.file_uploader",
                   side_effect=[files, []]), \
             patch("app.admin.views.components.document_upload.upload_document") as upload:
            app = AppTest.from_function(upload_page).run()
            app.button(key="remove-file-1").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(dict(app.session_state["upload-files"]), {})
            self.assertTrue(next(b for b in app.button if b.label == "업로드").disabled)
            upload.assert_not_called()

    def test_permission_error(self):
        """A-01 관리 권한이 없으면 업로드 입력을 표시하지 않는다."""
        with patch("app.admin.views.components.document_upload.get_upload_companies",
                   side_effect=PermissionError):
            app = AppTest.from_function(upload_page).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.error), 1)
            self.assertEqual(len(app.radio), 0)
