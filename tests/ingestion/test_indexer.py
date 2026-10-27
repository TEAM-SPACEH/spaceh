"""I-02 임시 디스크의 실제 Chroma로 저장·교체·실패·연결 종료를 검증한다."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.ingestion.indexing.indexer import DocumentIndexer


def chunk(doc_id, number, text="검증 본문"):
    """실제 청킹 출력의 문서·권한 필드를 가진 목청크를 만든다."""
    return {"chunk_id": f"{doc_id}#{number:04d}", "text": text,
            "metadata": {"doc_id": doc_id, "company_id": "MVX",
                         "access_level": "internal", "is_group_shared": False,
                         "page": 1, "location": "p.1"}}


class IndexerTest(unittest.TestCase):
    """서비스 Chroma와 API 키를 사용하지 않고 실제 저장 결과를 확인한다."""

    def setUp(self):
        """연결을 닫은 다음 임시 폴더가 삭제되도록 정리 순서를 지정한다."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.indexer = DocumentIndexer({"path": self.temp.name}, "documents")
        self.addCleanup(self.indexer.close)

    def test_saved_text_metadata_and_vector_are_queryable(self):
        """본문·원문 위치·권한·벡터가 같은 ID로 저장되고 검색되는지 확인한다."""
        chunks = [chunk("A", 1), chunk("A", 2, "다음 본문")]
        before = copy.deepcopy(chunks)
        result = self.indexer.index_chunks("A", chunks, [[1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(result, {"doc_id": "A", "chunk_count": 2,
                                  "index_status": "done"})
        found = self.indexer.collection.query(
            query_embeddings=[[1.0, 0.0]], n_results=1,
            where={"company_id": "MVX"}, include=["documents", "metadatas"],
        )
        self.assertEqual(found["ids"], [["A#0001"]])
        self.assertEqual(found["documents"], [[chunks[0]["text"]]])
        self.assertEqual(found["metadatas"][0][0], chunks[0]["metadata"])
        self.assertEqual(chunks, before)

    def test_reindex_updates_removes_stale_and_keeps_other_documents(self):
        """재색인으로 청크 수가 줄어도 오래된 청크만 지우고 다른 문서는 보존한다."""
        self.indexer.index_chunks("A", [chunk("A", i) for i in (1, 2, 3)],
                                  [[1.0, 0.0]] * 3)
        self.indexer.index_chunks("B", [chunk("B", 1)], [[0.0, 1.0]])
        for _ in range(2):
            self.indexer.index_chunks("A", [chunk("A", 1, "갱신된 본문")],
                                      [[0.5, 0.5]])
        found = self.indexer.collection.get(include=["documents"])
        self.assertEqual(dict(zip(found["ids"], found["documents"])),
                         {"A#0001": "갱신된 본문", "B#0001": "검증 본문"})

    def test_batches_follow_client_limit(self):
        """클라이언트의 작은 배치 상한으로도 모든 청크를 순서에 맞게 저장한다."""
        chunks = [chunk("A", i) for i in range(1, 6)]
        with patch.object(self.indexer.client, "get_max_batch_size", return_value=2):
            result = self.indexer.index_chunks("A", chunks, [[1.0, 0.0]] * 5)
        self.assertEqual(result["chunk_count"], 5)
        self.assertEqual(self.indexer.collection.count(), 5)

    def test_invalid_inputs_do_not_modify_existing_chunks(self):
        """문서 불일치·권한·중복 ID·잘못된 벡터를 기존 데이터 변경 전에 거부한다."""
        valid = chunk("A", 1)
        self.indexer.index_chunks("A", [valid], [[1.0, 0.0]])
        bad_metadata = [
            {**valid["metadata"], "doc_id": "B"},
            {**valid["metadata"], "company_id": ""},
            {**valid["metadata"], "access_level": "unknown"},
            {**valid["metadata"], "is_group_shared": 1},
            {**valid["metadata"], "access_level": "confidential", "is_group_shared": True},
            {**valid["metadata"], "nested": []},
            {**valid["metadata"], "number": float("nan")},
        ]
        cases = [(None, [valid], [[1.0, 0.0]]), ("A", [], []),
                 ("A", [valid], []), ("A", [None], [[1.0, 0.0]]),
                 ("A", [chunk("B", 1)], [[1.0, 0.0]]),
                 ("A", [{**valid, "text": " "}], [[1.0, 0.0]]),
                 ("A", [valid, valid], [[1.0, 0.0]] * 2),
                 ("A", [valid], [[]]), ("A", [valid], [[float("inf")]]),
                 ("A", [valid], [[True]]),
                 ("A", [valid, chunk("A", 2)], [[1.0], [1.0, 0.0]])]
        cases.extend(("A", [{**valid, "metadata": metadata}], [[1.0, 0.0]])
                     for metadata in bad_metadata)
        for doc_id, chunks, vectors in cases:
            with self.subTest(doc_id=doc_id, chunks=chunks, vectors=vectors):
                with self.assertRaises(ValueError):
                    self.indexer.index_chunks(doc_id, chunks, vectors)
        found = self.indexer.collection.get(include=["documents"])
        self.assertEqual(found["ids"], [valid["chunk_id"]])
        self.assertEqual(found["documents"], [valid["text"]])

    def test_batch_failure_keeps_old_chunks_and_retry_finishes_replacement(self):
        """중간 저장 실패 시 기존 청크를 선삭제하지 않으며 재시도로 교체를 끝낸다."""
        self.indexer.index_chunks("A", [chunk("A", i) for i in (1, 2, 3)],
                                  [[1.0, 0.0]] * 3)
        original = type(self.indexer.collection).upsert
        calls = 0

        def fail_second(collection, **kwargs):
            """첫 배치만 실제 저장하고 두 번째 배치에서 오류를 재현한다."""
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("mock storage failure")
            return original(collection, **kwargs)

        chunks = [chunk("A", i, "교체 본문") for i in (1, 4, 5)]
        with patch.object(self.indexer.client, "get_max_batch_size", return_value=2):
            with patch.object(type(self.indexer.collection), "upsert", autospec=True,
                              side_effect=fail_second):
                with self.assertRaisesRegex(RuntimeError, "mock storage failure"):
                    self.indexer.index_chunks("A", chunks, [[0.0, 1.0]] * 3)
        old_ids = self.indexer.collection.get(include=[])["ids"]
        self.assertTrue({"A#0001", "A#0002", "A#0003"}.issubset(old_ids))
        self.indexer.index_chunks("A", chunks, [[0.0, 1.0]] * 3)
        self.assertEqual(set(self.indexer.collection.get(include=[])["ids"]),
                         {c["chunk_id"] for c in chunks})

    def test_context_closes_on_error_and_data_persists(self):
        """예외 후 연결을 닫고 다시 열어도 저장된 데이터가 유지되는지 확인한다."""
        path = Path(self.temp.name) / "reopen"
        with self.assertRaisesRegex(RuntimeError, "mock"):
            with DocumentIndexer({"path": path}, "other_docs") as indexer:
                indexer.index_chunks("A", [chunk("A", 1)], [[1.0, 0.0]])
                raise RuntimeError("mock")
        self.assertTrue(indexer.client._closed)
        with DocumentIndexer({"path": path}, "other_docs") as reopened:
            self.assertEqual(reopened.collection.count(), 1)
        self.indexer.close()
        self.indexer.close()
        with self.assertRaises(RuntimeError):
            self.indexer.index_chunks("A", [chunk("A", 1)], [[1.0, 0.0]])

    def test_initialization_failure_closes_client(self):
        """컬렉션 준비 실패도 클라이언트의 파일 잠금을 남기지 않는다."""
        with patch("app.ingestion.indexing.indexer.open_chroma_client") as opened:
            client = opened.return_value.__enter__.return_value
            client.get_or_create_collection.side_effect = RuntimeError("mock")
            with self.assertRaises(RuntimeError):
                DocumentIndexer({"path": Path(self.temp.name)})
            opened.return_value.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
