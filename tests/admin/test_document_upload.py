"""A-01 업로드 모달의 파일별 처리와 권한 오류 검증."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest


def upload_page():
    """A-01 테스트용 관리자 화면을 연다."""
    from app.admin.views.components.document_upload import render_document_upload
    render_document_upload({"id": 1})


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
                   return_value=[{"company_id": "MVX", "name": "현대무벡스"}]):
            app = AppTest.from_function(page).run()
            app.button[0].click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.radio), 2)
            self.assertTrue(next(b for b in app.button if b.label == "업로드").disabled)
            next(b for b in app.button if b.label == "닫기").click().run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.radio), 0)

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
            self.assertEqual(len(app.success), 1)
            self.assertEqual(len(app.error), 1)
            self.assertEqual(len(app.warning), 1)
            app.radio[1].set_value("confidential").run()
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
