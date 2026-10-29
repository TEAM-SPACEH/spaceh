"""A-02 문서 목록 조회·삭제·재색인 서비스 검증. DB·Chroma·임베딩은 대체하고 순서·권한·상태 전이를 본다."""

import unittest
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from app.admin.services import document_service as service
from core.constants import ACCESS_LEVELS, DOC_TYPES

SUPER = {"id": 1}
COMPANY_ADMIN = {"id": 7}


def _row(**overrides):
    """목록 한 줄. 기본은 무벡스의 색인 완료 사내 문서."""
    row = {"doc_id": "doc-1", "company_id": "MVX", "title": "AGV 사양서", "file_name": "agv.pdf",
           "file_format": "pdf", "doc_type": "spec", "source_type": "internal",
           "access_level": "internal", "is_group_shared": 1, "chunk_count": 5,
           "index_status": "done", "error_message": None, "is_stale": 0}
    row.update(overrides)
    return row


def _document(path: str = "agv.pdf", **overrides):
    """get_managed_document 가 돌려주는 문서."""
    document = {"doc_id": "doc-1", "company_id": "MVX", "company_name": "현대무벡스",
                "doc_type": "spec", "title": "AGV 사양서", "file_name": "agv.pdf",
                "file_format": "pdf", "source_type": "internal", "source_url": None,
                "published_date": date(2026, 10, 1), "access_level": "internal",
                "is_group_shared": 1, "file_path": path, "index_status": "done",
                "chunk_count": 5, "error_message": None}
    document.update(overrides)
    return document


class _Base(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.repo = Mock()
        self.repo.find_active_admin.side_effect = lambda user_id: {
            1: {"id": 1, "role": "super_admin", "company_id": None},
            7: {"id": 7, "role": "company_admin", "company_id": "MVX"},
            8: {"id": 8, "role": "employee", "company_id": "MVX"},
            9: {"id": 9, "role": "company_admin", "company_id": None},
        }.get(user_id)
        self.repo.list_active_companies.return_value = [{"company_id": "MVX", "name": "현대무벡스"}]
        self.audit = Mock()
        for target, value in (("repository", self.repo), ("record_audit_log", self.audit),
                              ("config.UPLOAD_DIR", self.root), ("config.ROOT_DIR", self.root.parent)):
            patcher = patch("app.admin.services.document_service." + target, value)
            patcher.start()
            self.addCleanup(patcher.stop)


class DocumentListTests(_Base):
    def setUp(self):
        super().setUp()
        self.repo.list_managed_documents.return_value = ([_row()], 1)

    def test_company_admin_is_forced_to_own_company(self):
        service.get_document_list(COMPANY_ADMIN, {"company_id": "ELV"})
        self.assertEqual(self.repo.list_managed_documents.call_args.args[0], "MVX")

    def test_super_admin_can_choose_company_or_all(self):
        service.get_document_list(SUPER, {"company_id": "ELV"})
        self.assertEqual(self.repo.list_managed_documents.call_args.args[0], "ELV")
        service.get_document_list(SUPER, {})
        self.assertIsNone(self.repo.list_managed_documents.call_args.args[0])

    def test_employee_and_unknown_user_and_orphan_admin_are_denied(self):
        for user in ({"id": 8}, {"id": 99}, {}, None, {"id": 9}):
            with self.assertRaises(PermissionError):
                service.get_document_list(user, {})
        self.repo.list_managed_documents.assert_not_called()

    def test_unknown_filter_values_are_ignored_and_keyword_is_trimmed(self):
        service.get_document_list(SUPER, {"doc_type": "x'; DROP", "access_level": "secret",
                                          "index_status": "weird", "keyword": "  AGV  "})
        self.assertEqual(self.repo.list_managed_documents.call_args.args[1:5], ("", "", "", "AGV"))

    def test_row_gets_status_label_and_action_flags(self):
        result = service.get_document_list(SUPER, {})
        document = result["documents"][0]
        self.assertEqual(document["status_label"], "완료")
        self.assertTrue(document["can_delete"] and document["can_reindex"])
        self.assertIs(document["is_group_shared"], True)

    def test_busy_document_cannot_be_managed_but_stale_one_can(self):
        self.repo.list_managed_documents.return_value = (
            [_row(index_status="indexing"), _row(index_status="indexing", is_stale=1)], 2)
        busy, stale = service.get_document_list(SUPER, {})["documents"]
        self.assertFalse(busy["can_delete"] or busy["can_reindex"])
        self.assertTrue(stale["can_delete"] and stale["can_reindex"])

    def test_dart_document_can_be_deleted_but_not_reindexed(self):
        self.repo.list_managed_documents.return_value = ([_row(source_type="dart")], 1)
        document = service.get_document_list(SUPER, {})["documents"][0]
        self.assertTrue(document["can_delete"])
        self.assertFalse(document["can_reindex"])

    def test_page_beyond_last_is_moved_to_last_page(self):
        self.repo.list_managed_documents.side_effect = [([], 45), ([_row()], 45)]
        result = service.get_document_list(SUPER, {}, page=9, size=20)
        self.assertEqual((result["page"], result["total_pages"]), (3, 3))
        self.assertEqual(self.repo.list_managed_documents.call_args.args[6], 40)  # offset

    def test_bad_page_and_size_are_clamped(self):
        result = service.get_document_list(SUPER, {}, page="abc", size=100000)
        self.assertEqual((result["page"], result["size"]), (1, service.MAX_PAGE_SIZE))

    def test_filter_options_are_codes_from_shared_constants(self):
        """문서 유형·보안 등급은 공통 상수의 코드 그대로이고(이름은 화면이 붙인다), 색인 상태만 {코드: 이름}이다."""
        options = service.get_document_filter_options()
        self.assertEqual(options["doc_types"], DOC_TYPES)
        self.assertEqual(options["security_levels"], ACCESS_LEVELS)
        self.assertEqual(options["index_statuses"]["failed"], "실패")


class DocumentDeleteTests(_Base):
    def setUp(self):
        super().setUp()
        self.original = self.root / "agv.pdf"
        self.original.write_bytes(b"pdf")
        self.repo.get_managed_document.return_value = _document()
        self.repo.claim_document.return_value = {"index_status": "done", "chunk_count": 5,
                                                 "error_message": None}
        self.order = []
        self.repo.delete_document_chunks.side_effect = lambda doc_id: self.order.append("chroma")
        self.repo.delete_document_row.side_effect = lambda doc_id: self.order.append("mysql") or True

    def test_deletes_chroma_then_mysql_then_file(self):
        result = service.delete_document("doc-1", COMPANY_ADMIN)
        self.assertEqual(result["status"], "deleted")
        self.assertEqual(self.order, ["chroma", "mysql"])
        self.assertFalse(self.original.exists())
        self.assertEqual(self.audit.call_args.args[1], "document_delete")
        self.assertEqual(self.audit.call_args.kwargs["context_detail"]["result"], "success")

    def test_other_company_admin_is_blocked_and_nothing_changes(self):
        self.repo.get_managed_document.return_value = _document(company_id="ELV")
        result = service.delete_document("doc-1", COMPANY_ADMIN)
        self.assertEqual(result["status"], "failed")
        self.repo.claim_document.assert_not_called()
        self.repo.delete_document_chunks.assert_not_called()
        self.assertTrue(self.original.exists())
        self.assertTrue(self.audit.call_args.args[4])  # blocked

    def test_employee_is_denied(self):
        result = service.delete_document("doc-1", {"id": 8})
        self.assertEqual(result["status"], "failed")
        self.repo.get_managed_document.assert_not_called()

    def test_unknown_document(self):
        self.repo.get_managed_document.return_value = None
        result = service.delete_document("nope", SUPER)
        self.assertEqual(result["status"], "failed")
        self.assertIn("찾을 수 없습니다", result["error_message"])

    def test_busy_document_is_not_deleted(self):
        self.repo.claim_document.return_value = None
        result = service.delete_document("doc-1", SUPER)
        self.assertEqual(result["status"], "failed")
        self.repo.delete_document_chunks.assert_not_called()
        self.assertTrue(self.original.exists())

    def test_chroma_failure_keeps_row_and_restores_status(self):
        self.repo.delete_document_chunks.side_effect = RuntimeError("secret path C:\\x")
        result = service.delete_document("doc-1", SUPER)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("secret", result["error_message"])
        self.repo.delete_document_row.assert_not_called()
        self.repo.update_index_status.assert_called_once_with("doc-1", "done", 5, "")
        self.assertTrue(self.original.exists())

    def test_mysql_failure_after_chroma_marks_failed_and_keeps_file(self):
        self.repo.delete_document_row.side_effect = RuntimeError("db down")
        result = service.delete_document("doc-1", SUPER)
        self.assertEqual(result["status"], "failed")
        args = self.repo.update_index_status.call_args.args
        self.assertEqual((args[1], args[2]), ("failed", 0))
        self.assertTrue(self.original.exists())

    def test_file_removal_failure_is_only_a_warning(self):
        with patch.object(Path, "unlink", side_effect=OSError("locked")):
            result = service.delete_document("doc-1", SUPER)
        self.assertEqual(result["status"], "deleted")
        self.assertIn("원본 파일", result["warning"])

    def test_file_outside_upload_dir_is_never_deleted(self):
        outside = self.root.parent / "outside-a02.txt"
        outside.write_text("x")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        self.repo.get_managed_document.return_value = _document(path="../outside-a02.txt")
        result = service.delete_document("doc-1", SUPER)
        self.assertEqual(result["status"], "deleted")
        self.assertTrue(outside.exists())

    def test_audit_failure_does_not_undo_deletion(self):
        self.audit.side_effect = RuntimeError("audit down")
        result = service.delete_document("doc-1", SUPER)
        self.assertEqual(result["status"], "deleted")

    def test_dart_document_without_file_is_deleted(self):
        self.repo.get_managed_document.return_value = _document(
            path="", source_type="dart", file_format="dart_xml")
        result = service.delete_document("doc-1", SUPER)
        self.assertEqual(result["status"], "deleted")
        self.assertEqual(result["warning"], "")


class DocumentReindexTests(_Base):
    def setUp(self):
        super().setUp()
        (self.root / "agv.pdf").write_bytes(b"pdf")
        self.repo.get_managed_document.return_value = _document()
        self.repo.claim_document.return_value = {"index_status": "failed", "chunk_count": 0,
                                                 "error_message": "x"}
        self.ingest = Mock(return_value={"doc_id": "doc-1", "index_status": "done",
                                         "chunk_count": 3, "error_message": ""})
        self.indexer = Mock()

        @contextmanager
        def fake_indexer():
            yield self.indexer

        for target, value in (("ingest_document", self.ingest), ("DocumentIndexer", fake_indexer),
                              ("DocumentEmbedder", Mock())):
            patcher = patch("app.admin.services.document_service." + target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_success_saves_done_status_with_chunk_count(self):
        result = service.request_reindex("doc-1", COMPANY_ADMIN)
        self.assertEqual(result["index_status"], "done")
        self.repo.update_index_status.assert_called_once_with("doc-1", "done", 3, "")
        self.assertEqual(self.audit.call_args.args[1], "document_reindex")

    def test_keeps_current_share_and_access_level_in_metadata(self):
        service.request_reindex("doc-1", SUPER)
        info = self.ingest.call_args.args[2]
        self.assertIs(info["is_group_shared"], True)
        self.assertEqual(info["access_level"], "internal")
        self.assertEqual(info["company_name"], "현대무벡스")
        self.assertEqual(self.ingest.call_args.args[1], "doc-1")

    def test_document_is_read_again_after_claim_inside_share_lock(self):
        """선점 전에 A-03 이 공유를 바꿔도, 선점 뒤 다시 읽은 값이 Chroma 에 실린다 (옛 값이면 껐는데 타사에 노출된다)."""
        from app.admin.services import access_service

        held = []
        self.repo.get_managed_document.side_effect = [_document(is_group_shared=1), _document(is_group_shared=0)]
        self.repo.claim_document.side_effect = lambda *a: held.append(access_service._GROUP_SHARE_LOCK.locked()) or {
            "index_status": "done", "chunk_count": 5, "error_message": None}
        service.request_reindex("doc-1", SUPER)
        self.assertIs(self.ingest.call_args.args[2]["is_group_shared"], False)
        self.assertEqual(held, [True])  # 선점은 A-03 과 같은 잠금 안에서 이뤄진다
        self.assertFalse(access_service._GROUP_SHARE_LOCK.locked())  # 끝난 뒤에는 풀려 있다

    def test_failure_cleans_chunks_and_marks_failed(self):
        self.ingest.return_value = {"doc_id": "doc-1", "index_status": "failed", "chunk_count": 0,
                                    "error_message": "임베딩 단계 실패 (RuntimeError)"}
        result = service.request_reindex("doc-1", SUPER)
        self.assertEqual(result["index_status"], "failed")
        self.repo.update_index_status.assert_called_once_with(
            "doc-1", "failed", 0, "임베딩 단계 실패 (RuntimeError)")
        self.repo.delete_document_chunks.assert_called_once_with("doc-1")

    def test_cleanup_failure_is_reported(self):
        self.ingest.return_value = {"doc_id": "doc-1", "index_status": "failed", "chunk_count": 0,
                                    "error_message": "청킹 단계 실패 (ValueError)"}
        self.repo.delete_document_chunks.side_effect = RuntimeError("chroma down")
        result = service.request_reindex("doc-1", SUPER)
        self.assertIn("청크 정리 실패", result["error_message"])

    def test_status_save_failure_is_reported_without_claiming_success(self):
        self.repo.update_index_status.side_effect = RuntimeError("db down")
        result = service.request_reindex("doc-1", SUPER)
        self.assertEqual(result["index_status"], "failed")
        self.assertIn("DB 상태 저장 실패", result["error_message"])

    def test_other_company_is_blocked_before_claim(self):
        self.repo.get_managed_document.return_value = _document(company_id="ELV")
        result = service.request_reindex("doc-1", COMPANY_ADMIN)
        self.assertEqual(result["index_status"], "failed")
        self.repo.claim_document.assert_not_called()
        self.ingest.assert_not_called()

    def test_dart_document_is_refused(self):
        self.repo.get_managed_document.return_value = _document(source_type="dart", file_path="")
        result = service.request_reindex("doc-1", SUPER)
        self.assertIn("DART", result["error_message"])
        self.repo.claim_document.assert_not_called()

    def test_missing_original_is_refused_without_claim(self):
        (self.root / "agv.pdf").unlink()
        result = service.request_reindex("doc-1", SUPER)
        self.assertIn("원본 파일", result["error_message"])
        self.repo.claim_document.assert_not_called()

    def test_busy_document_is_not_reindexed_twice(self):
        self.repo.claim_document.return_value = None
        result = service.request_reindex("doc-1", SUPER)
        self.assertEqual(result["index_status"], "failed")
        self.ingest.assert_not_called()
        self.repo.update_index_status.assert_not_called()

    def test_embedder_setup_failure_after_claim_ends_as_failed_not_stuck(self):
        with patch("app.admin.services.document_service.DocumentEmbedder",
                   side_effect=RuntimeError("no api key sk-secret")):
            result = service.request_reindex("doc-1", SUPER)
        self.assertEqual(result["index_status"], "failed")
        self.assertNotIn("sk-secret", result["error_message"])
        self.assertEqual(self.repo.update_index_status.call_args.args[1], "failed")


if __name__ == "__main__":
    unittest.main()
