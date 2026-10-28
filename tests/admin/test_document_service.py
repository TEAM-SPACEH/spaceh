"""A-01 권한·중복·실패 보존 및 파이프라인 연결 검증."""

from datetime import date
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from app.admin.services import document_service as service


class DocumentServiceTests(unittest.TestCase):
    """서비스 경계에서 DB와 외부 API를 대체해 상태 전이를 검증한다."""

    def setUp(self):
        """테스트마다 서비스 데이터와 분리된 원본 폴더를 준비한다."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.repo = Mock()
        self.repo.find_active_admin.return_value = {
            "id": 7, "role": "company_admin", "company_id": "MVX",
        }
        self.repo.list_active_companies.return_value = [
            {"company_id": "MVX", "name": "현대무벡스"},
            {"company_id": "HRI", "name": "현대경제연구원"},
        ]
        self.repo.find_duplicate.return_value = None
        self.repo.insert_document.return_value = None
        self.file = BytesIO(b"mock document")
        self.file.name = "sample.docx"
        self.user = {"id": 7}
        self.metadata = {"company_id": "MVX", "title": "", "doc_type": "memo",
                         "access_level": "internal"}
        for target, value in (("repository", self.repo), ("config.UPLOAD_DIR", self.root)):
            patcher = patch.object(service, target, value) if "." not in target else patch(
                "app.admin.services.document_service." + target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.indexer_patch = patch.object(service, "DocumentIndexer")
        self.indexer = self.indexer_patch.start()
        self.addCleanup(self.indexer_patch.stop)
        patcher = patch.object(service, "DocumentEmbedder")
        self.embedder = patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.object(service, "ingest_document", side_effect=self._success)
        self.pipeline = patcher.start()
        self.addCleanup(patcher.stop)

    def _success(self, path, doc_id, info, settings, embedder, indexer):
        """호출 전에 원본과 pending 행이 저장됐는지 확인한다."""
        self.assertEqual(Path(path).read_bytes(), b"mock document")
        self.repo.insert_document.assert_called_once()
        return {"doc_id": doc_id, "index_status": "done", "chunk_count": 2, "error_message": ""}

    def test_upload_saves_confirmed_date_and_state(self):
        """정상 업로드는 동일한 확정 날짜와 UUID로 DB·색인을 연결한다."""
        self.file.seek(3)
        result = service.upload_document(self.file, self.metadata, self.user)
        self.assertEqual(result["index_status"], "done")
        self.assertEqual(self.file.tell(), 3)
        document = self.repo.insert_document.call_args.args[0]
        self.assertEqual(document["published_date"], document["created_at"].date())
        self.assertEqual(document["title"], "sample")
        self.assertEqual(document["index_status"], "pending")
        self.assertFalse(document["is_group_shared"])
        self.assertEqual(len(document["doc_id"]), 32)
        self.repo.update_index_status.assert_any_call(result["doc_id"], "indexing", 0, "")
        self.repo.update_index_status.assert_called_with(result["doc_id"], "done", 2, "")
        self.repo.delete_document_chunks.assert_not_called()
        self.indexer.return_value.__exit__.assert_called_once()
        self.assertEqual(self.metadata["title"], "")

    def test_employee_inactive_and_other_company_denied_before_file_access(self):
        """권한 없는 계정은 원본·중복 정보·API에 접근하지 못한다."""
        for admin in (None, {"role": "employee"},
                      {"role": "company_admin", "company_id": "HRI"}):
            with self.subTest(admin=admin):
                self.repo.find_active_admin.return_value = admin
                result = service.upload_document(None, self.metadata, self.user)
                self.assertEqual(result["index_status"], "failed")
                result = service.check_duplicate_document(None, "MVX", self.user)
                self.assertTrue(result["error_message"])
        self.repo.find_duplicate.assert_not_called()
        self.repo.insert_document.assert_not_called()
        self.pipeline.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_duplicate_preserves_existing_file_and_skips_api(self):
        """기존 중복이나 동시 등록 중복은 새 색인을 실행하지 않는다."""
        duplicate = {"doc_id": "existing", "title": "old", "index_status": "failed"}
        for concurrent in (False, True):
            with self.subTest(concurrent=concurrent):
                self.repo.find_duplicate.return_value = None if concurrent else duplicate
                self.repo.insert_document.return_value = duplicate if concurrent else None
                result = service.upload_document(self.file, self.metadata, self.user)
                self.assertEqual(result["index_status"], "duplicate")
                self.assertEqual(result["doc_id"], "existing")
                self.assertEqual(list(self.root.iterdir()), [])
        self.pipeline.assert_not_called()

    def test_failed_pipeline_retains_original_and_failed_row(self):
        """색인 실패는 원본을 남기고 실패 결과를 DB에 저장한다."""
        self.pipeline.side_effect = lambda path, doc_id, *args: {
            "doc_id": doc_id, "index_status": "failed", "chunk_count": 0,
            "error_message": "임베딩 단계 실패 (RuntimeError)",
        }
        result = service.upload_document(self.file, self.metadata, self.user)
        self.assertEqual(result["index_status"], "failed")
        self.assertEqual(len(list(self.root.iterdir())), 1)
        self.repo.update_index_status.assert_called_with(
            result["doc_id"], "failed", 0, result["error_message"])
        self.repo.delete_document_chunks.assert_called_once_with(result["doc_id"])
        calls = [call[0] for call in self.repo.mock_calls]
        self.assertLess(calls.index("update_index_status", calls.index("update_index_status") + 1),
                        calls.index("delete_document_chunks"))

    def test_done_status_error_cleans_only_after_failed_status_is_saved(self):
        """완료 상태 쓰기 오류 후 실패 저장이 성공한 경우에만 정리한다."""
        def update(doc_id, status, count, message):
            if status == "done":
                raise RuntimeError("private commit response")
            if status == "failed":
                self.repo.delete_document_chunks.assert_not_called()
        self.repo.update_index_status.side_effect = update
        result = service.upload_document(self.file, self.metadata, self.user)
        self.assertEqual(result["index_status"], "failed")
        self.repo.delete_document_chunks.assert_called_once_with(result["doc_id"])
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_failed_pipeline_db_error_keeps_chunks_when_status_is_uncertain(self):
        """파이프라인 실패라도 DB 실패 저장이 확인되지 않으면 삭제하지 않는다."""
        self.pipeline.side_effect = lambda path, doc_id, *args: {
            "doc_id": doc_id, "index_status": "failed", "chunk_count": 0,
            "error_message": "색인 저장 단계 실패 (RuntimeError)",
        }
        self.repo.update_index_status.side_effect = [None, RuntimeError(), RuntimeError()]
        result = service.upload_document(self.file, self.metadata, self.user)
        self.assertIn("DB 상태 저장 실패", result["error_message"])
        self.repo.delete_document_chunks.assert_not_called()

    def test_cleanup_error_is_reported_without_private_details(self):
        """정리 실패를 숨기거나 원본을 지우지 않고 두 실패 경로에서 안내한다."""
        for raised in (False, True):
            with self.subTest(raised=raised):
                self.repo.delete_document_chunks.reset_mock()
                self.repo.delete_document_chunks.side_effect = RuntimeError("private/path/body")
                if raised:
                    self.pipeline.side_effect = RuntimeError("private pipeline error")
                else:
                    self.pipeline.side_effect = lambda path, doc_id, *args: {
                        "doc_id": doc_id, "index_status": "failed", "chunk_count": 0,
                        "error_message": "색인 저장 단계 실패 (RuntimeError)",
                    }
                result = service.upload_document(self.file, self.metadata, self.user)
                self.assertEqual(result["index_status"], "failed")
                self.assertIn("색인 청크 정리 실패", result["error_message"])
                self.assertNotIn("private", result["error_message"])
                self.repo.delete_document_chunks.assert_called_once_with(result["doc_id"])
                self.assertTrue((self.root / (result["doc_id"] + ".docx")).exists())

    def test_setup_failure_is_safe_and_closes_indexer(self):
        """API 객체 생성 실패도 본문·키 없이 실패로 기록하고 Chroma를 닫는다."""
        self.embedder.side_effect = RuntimeError("secret/path/body")
        result = service.upload_document(self.file, self.metadata, self.user)
        self.assertNotIn("secret", result["error_message"])
        self.assertEqual(result["index_status"], "failed")
        self.assertEqual(len(list(self.root.iterdir())), 1)
        self.indexer.return_value.__exit__.assert_called_once()

    def test_invalid_input_rejected_before_writes(self):
        """지원 형식·경로·빈 파일·등록 정보 오류는 등록 전에 차단한다."""
        for name, content, changes in (
            ("../x.docx", b"x", {}), ("x.xlsx", b"x", {}),
            ("x.pdf", b"", {}), ("x.pdf", b"x", {"access_level": "wrong"}),
            ("x.pdf", b"x", {"published_date": "wrong"}),
            ("x.pdf", b"x", {"is_mock": "false"}),
        ):
            with self.subTest(name=name, changes=changes):
                file = BytesIO(content)
                file.name = name
                result = service.upload_document(file, dict(self.metadata, **changes), self.user)
                self.assertEqual(result["index_status"], "failed")
        self.repo.insert_document.assert_not_called()
        self.pipeline.assert_not_called()

    def test_registration_or_state_commit_failure_preserves_original(self):
        """DB 응답 유실 시 등록 가능성이 있는 원본을 삭제하지 않는다."""
        self.repo.insert_document.side_effect = RuntimeError("private database info")
        result = service.upload_document(self.file, self.metadata, self.user)
        self.assertIn("DB 등록 여부", result["error_message"])
        self.assertNotIn("private", result["error_message"])
        self.assertEqual(len(list(self.root.iterdir())), 1)
        self.pipeline.assert_not_called()

    def test_super_admin_and_company_options(self):
        """계열사 관리자는 자사만, 최종 관리자는 전체 활성 회사를 받는다."""
        self.assertEqual([c["company_id"] for c in service.get_upload_companies(self.user)], ["MVX"])
        self.repo.find_active_admin.return_value = {"id": 7, "role": "super_admin", "company_id": None}
        self.assertEqual(len(service.get_upload_companies(self.user)), 2)
        self.metadata["company_id"] = "HRI"
        self.metadata["published_date"] = date(2026, 1, 1)
        self.assertEqual(service.upload_document(self.file, self.metadata, self.user)["index_status"], "done")

    def test_db_state_failure_preserves_original(self):
        """색인 후 DB 상태 쓰기 실패는 성공으로 안내하지 않는다."""
        self.repo.update_index_status.side_effect = [None, RuntimeError("secret"), RuntimeError("secret")]
        result = service.upload_document(self.file, self.metadata, self.user)
        self.assertEqual(result["index_status"], "failed")
        self.assertIn("DB 상태 저장 실패", result["error_message"])
        self.assertNotIn("secret", result["error_message"])
        self.assertEqual(len(list(self.root.iterdir())), 1)
        self.repo.delete_document_chunks.assert_not_called()

    def test_existing_uuid_path_is_never_deleted(self):
        """배타적 파일 생성 실패 시 원래 있던 파일은 보존한다."""
        existing = self.root / "fixed.docx"
        existing.write_bytes(b"existing")
        with patch.object(service, "uuid4", return_value=Mock(hex="fixed")):
            result = service.upload_document(self.file, self.metadata, self.user)
        self.assertEqual(result["index_status"], "failed")
        self.assertEqual(existing.read_bytes(), b"existing")
        self.repo.insert_document.assert_not_called()
