"""I-02 외부 API 호출 없이 입력·순서·응답 검증과 오류 전달을 확인한다."""

import copy
import unittest
from unittest.mock import patch

from app.ingestion.indexing.embedder import DocumentEmbedder
from core import config


class EmbedderTest(unittest.TestCase):
    """청크와 벡터의 대응 관계가 저장 전에 깨지지 않는지 확인한다."""

    def setUp(self):
        """실제 API 클라이언트를 만들지 않도록 생성자를 대체한다."""
        key_patcher = patch.object(config, "OPENAI_API_KEY", "test-key")
        key_patcher.start()
        self.addCleanup(key_patcher.stop)
        patcher = patch("app.ingestion.indexing.embedder.OpenAIEmbeddings")
        self.factory = patcher.start()
        self.addCleanup(patcher.stop)
        self.client = self.factory.return_value
        self.embedder = DocumentEmbedder()
        self.chunks = [
            {"chunk_id": "doc#0001", "text": "[회사 · 문서 · p.1]\n첫 본문",
             "metadata": {"access_level": "internal"}},
            {"chunk_id": "doc#0002", "text": "[회사 · 문서 · p.2]\n다음 본문",
             "metadata": {"access_level": "confidential"}},
        ]

    def test_uses_shared_model_and_keeps_order_and_input(self):
        """접두어 포함 원문 순서를 보존하고 입력 청크·권한 정보를 변경하지 않는다."""
        before = copy.deepcopy(self.chunks)
        vectors = [[0.1, 0.2], [0.3, 0.4]]
        self.client.embed_documents.return_value = vectors
        self.assertIs(self.embedder.embed_chunks(self.chunks), vectors)
        self.client.embed_documents.assert_called_once_with(
            [chunk["text"] for chunk in before])
        self.factory.assert_called_once_with(
            model=config.EMBEDDING_MODEL, api_key=config.OPENAI_API_KEY,
            chunk_size=32)
        self.assertEqual(self.chunks, before)

    def test_client_is_reused_across_calls(self):
        """문서를 다시 처리해도 객체가 보관한 클라이언트를 재사용한다."""
        self.client.embed_documents.return_value = [[0.1, 0.2]]
        self.embedder.embed_chunks(self.chunks[:1])
        self.embedder.embed_chunks(self.chunks[1:])
        self.assertEqual(self.factory.call_count, 1)
        self.assertEqual(self.client.embed_documents.call_count, 2)

    def test_empty_input_does_not_request_embeddings(self):
        """청크가 없으면 비용이 발생하는 요청 없이 빈 목록을 반환한다."""
        self.assertEqual(self.embedder.embed_chunks([]), [])
        self.client.embed_documents.assert_not_called()

    def test_invalid_chunks_are_rejected_before_any_request(self):
        """뒤쪽 청크가 잘못된 경우도 앞부분을 먼저 API로 보내지 않는다."""
        for invalid in (None, {}, (), [None], ["text"], [{}],
                        [{"text": None}], [{"text": 123}],
                        [{"text": " \n"}], [self.chunks[0], {"text": ""}]):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.embedder.embed_chunks(invalid)
        self.client.embed_documents.assert_not_called()

    def test_invalid_vector_response_is_rejected(self):
        """누락·빈 벡터·차원 불일치·비유한 수를 저장 단계로 넘기지 않는다."""
        for vectors in ([], [[0.1]], [[], []], [[0.1], [0.2, 0.3]],
                        [[float("nan")], [0.2]], [[0.1], [float("inf")]],
                        [[True], [0.2]], [["bad"], [0.2]]):
            with self.subTest(vectors=vectors):
                self.client.embed_documents.return_value = vectors
                with self.assertRaises(ValueError):
                    self.embedder.embed_chunks(self.chunks)

    def test_api_error_is_propagated_without_partial_results(self):
        """API 실패를 빈 성공 결과로 바꾸지 않아 파이프라인이 실패를 기록할 수 있다."""
        error = RuntimeError("mock API failure")
        self.client.embed_documents.side_effect = error
        with self.assertRaises(RuntimeError) as raised:
            self.embedder.embed_chunks(self.chunks)
        self.assertIs(raised.exception, error)


if __name__ == "__main__":
    unittest.main()
