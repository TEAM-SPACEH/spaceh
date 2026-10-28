"""A-01 실패 청크 정리를 임시 Chroma에서 실제 저장·검색으로 검증한다."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.admin.repositories.document_repository import delete_document_chunks
from app.ingestion.indexing.indexer import DocumentIndexer
from app.search.repositories.chunk_repository import get_chunks
from core import config
from tests.ingestion.test_indexer import chunk


class DocumentChunkCleanupTests(unittest.TestCase):
    """배치 실패의 부분 청크만 삭제하고 다른 문서는 보존한다."""

    def test_partial_batch_cleanup_removes_search_candidates_only_for_failed_document(self):
        """두 번째 배치 실패 뒤 남은 청크가 정리 후 검색에서 사라진다."""
        with TemporaryDirectory() as directory, patch.object(config, "CHROMA_DIR", Path(directory)):
            with DocumentIndexer() as indexer:
                indexer.index_chunks("existing", [chunk("existing", 1)], [[1.0, 0.0]])
                upsert = indexer.collection.upsert
                calls = 0

                def store(**kwargs):
                    nonlocal calls
                    calls += 1
                    if calls == 2:
                        raise RuntimeError("second batch failed")
                    return upsert(**kwargs)

                with patch.object(indexer.client, "get_max_batch_size", return_value=1), \
                        patch.object(indexer.collection, "upsert", side_effect=store):
                    with self.assertRaises(RuntimeError):
                        indexer.index_chunks("failed", [chunk("failed", i) for i in (1, 2)],
                                             [[1.0, 0.0]] * 2)
            where = {"company_id": "MVX"}
            self.assertEqual(len(get_chunks(where)), 2)
            delete_document_chunks("failed")
            self.assertEqual([c["metadata"]["doc_id"] for c in get_chunks(where)], ["existing"])
            delete_document_chunks("failed")
            self.assertEqual(len(get_chunks(where)), 1)

    def test_missing_collection_needs_no_cleanup(self):
        """청크가 전혀 저장되지 않은 실패도 정리 성공으로 처리한다."""
        with TemporaryDirectory() as directory, patch.object(config, "CHROMA_DIR", Path(directory)):
            delete_document_chunks("failed")
