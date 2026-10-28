"""S-06 하이브리드 검색 테스트.

실행: python -m unittest tests.search.test_hybrid_search

무엇을 확인하나
- 벡터 검색만으로는 아래에 깔리는 모델명 청크가 하이브리드 검색에서는 1등으로 올라오는지
- BM25·하이브리드 결과에 권한 밖 청크가 0건인지 (임시 폴더의 진짜 Chroma로 확인)
- 중복 제거, 점수 범위, 빈 검색어, 색인 전(컬렉션 없음)

OpenAI·MySQL 없이 돌도록 질문 임베딩(_embed_query)과 승인 문서 조회는 patch로 가짜 값을 넣는다.
임베딩은 2차원 벡터로 단순화해, 질문 [1, 0]에 가까울수록 벡터 검색 순위가 높게 만든다.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.permissions.services.permission_service import apply_rbac_filter
from app.search.services.search_service import _tokenize, bm25_search, hybrid_search, vector_search
from core import config
from core.chroma import open_chroma_client

EMBED_PATH = "app.search.services.search_service._embed_query"
APPROVED_PATH = "app.permissions.services.permission_service.get_approved_doc_ids"
GET_CHUNKS_PATH = "app.search.services.search_service.get_chunks"
QUERY_VECTOR = [1.0, 0.0]
QUERY = "WBST-500 점검 주기"

MVX_EMPLOYEE = {"id": 1, "role": "employee", "company_id": "MVX"}
SUPER_ADMIN = {"id": 7, "role": "super_admin", "company_id": None}

MVX_INTERNAL = {"doc_id": "MVX-internal", "company_id": "MVX", "access_level": "internal", "is_group_shared": False}
ELV_PUBLIC = {"doc_id": "ELV-public", "company_id": "ELV", "access_level": "public", "is_group_shared": False}
ELV_INTERNAL = {"doc_id": "ELV-internal", "company_id": "ELV", "access_level": "internal", "is_group_shared": False}
ELV_CONFIDENTIAL = {"doc_id": "ELV-confidential", "company_id": "ELV", "access_level": "confidential", "is_group_shared": False}

# chunk_id: (메타데이터, 임베딩, 본문)
# MVX 사원 기준 벡터 순위: MVX#0000 > ELV-public#0001 > MVX#0001 > ELV-public#0000
# 모델명 WBST-500은 MVX#0001과 권한 밖 ELV 청크 2개에만 있다.
CHUNKS = {
    "MVX-internal#0000": (MVX_INTERNAL, [0.9, 0.1], "물류 자동화 설비 운영 매뉴얼"),
    "MVX-internal#0001": (MVX_INTERNAL, [0.5, 0.5], "WBST-500 스태커 크레인 점검 주기는 6개월이다"),
    "ELV-public#0000": (ELV_PUBLIC, [0.2, 0.8], "엘리베이터 안전 점검 기준"),
    "ELV-public#0001": (ELV_PUBLIC, [0.7, 0.3], "승강기 유지보수 계약 현황"),
    "ELV-internal#0000": (ELV_INTERNAL, [1.0, 0.0], "WBST-500 연동 엘리베이터 내부 설계"),
    "ELV-confidential#0000": (ELV_CONFIDENTIAL, [1.0, 0.0], "WBST-500 기밀 단가"),
}
FORBIDDEN_FOR_MVX = {"ELV-internal#0000", "ELV-confidential#0000"}


class HybridSearchTest(unittest.TestCase):
    def setUp(self):
        # repository가 config.CHROMA_DIR을 읽으므로 테스트 동안만 임시 폴더로 바꾼다.
        self.tmp = tempfile.TemporaryDirectory()
        patcher = patch.object(config, "CHROMA_DIR", Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def _index_chunks(self):
        # 검색 코드와 같은 잠금으로 열고, 임시 폴더를 지우기 전에 닫는다 (Windows 파일 잠금).
        with open_chroma_client(self.tmp.name) as client:
            collection = client.create_collection(config.CHROMA_COLLECTION)
            collection.add(
                ids=list(CHUNKS),
                metadatas=[metadata for metadata, _, _ in CHUNKS.values()],
                embeddings=[embedding for _, embedding, _ in CHUNKS.values()],
                documents=[text for _, _, text in CHUNKS.values()],
            )

    def _hybrid(self, query, user, filters=None):
        with patch(EMBED_PATH, return_value=QUERY_VECTOR), patch(APPROVED_PATH, return_value=[]):
            return hybrid_search(query, filters, user)

    def _where(self, user):
        with patch(APPROVED_PATH, return_value=[]):
            return apply_rbac_filter(user, None)

    def test_model_name_chunk_rises_to_top(self):
        """벡터 검색에서 3등인 모델명 청크가 하이브리드 검색에서는 1등이 된다."""
        self._index_chunks()
        with patch(EMBED_PATH, return_value=QUERY_VECTOR):
            vector_ids = [result["chunk_id"] for result in vector_search(QUERY, self._where(MVX_EMPLOYEE))]
        self.assertEqual(vector_ids[0], "MVX-internal#0000")

        results = self._hybrid(QUERY, MVX_EMPLOYEE)
        self.assertEqual(results[0]["chunk_id"], "MVX-internal#0001")

    def test_results_are_unique_and_sorted(self):
        """같은 청크가 두 검색에 모두 나와도 한 번만 나오고, 점수는 0~1 사이 내림차순."""
        self._index_chunks()
        results = self._hybrid(QUERY, MVX_EMPLOYEE)
        chunk_ids = [result["chunk_id"] for result in results]
        self.assertEqual(len(chunk_ids), len(set(chunk_ids)))
        self.assertEqual(set(results[0]), {"chunk_id", "doc_id", "text", "score", "metadata"})
        scores = [result["score"] for result in results]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertTrue(all(0 < score <= 1 for score in scores))

    def test_bm25_excludes_unauthorized_chunks(self):
        """모델명이 들어 있는 권한 밖 ELV 청크가 BM25 결과에 나오지 않는다."""
        self._index_chunks()
        chunk_ids = {result["chunk_id"] for result in bm25_search(QUERY, self._where(MVX_EMPLOYEE))}
        self.assertEqual(chunk_ids, {"MVX-internal#0001", "ELV-public#0000"})

    def test_hybrid_excludes_unauthorized_chunks(self):
        """MVX 사원의 하이브리드 결과에 권한 밖 청크 0건, 최고 관리자는 모두 볼 수 있다."""
        self._index_chunks()
        mvx_ids = {result["chunk_id"] for result in self._hybrid(QUERY, MVX_EMPLOYEE)}
        self.assertFalse(mvx_ids & FORBIDDEN_FOR_MVX)

        admin_ids = {result["chunk_id"] for result in self._hybrid(QUERY, SUPER_ADMIN)}
        self.assertTrue(FORBIDDEN_FOR_MVX <= admin_ids)

    def test_bm25_ranks_correctly_with_few_chunks(self):
        """허용 청크가 2개뿐이어도 검색어가 더 많이 든 청크가 위에 온다 (BM25Okapi는 여기서 뒤집혔다)."""
        chunks = [
            {"chunk_id": "a", "text": "WBST-500 점검 주기 WBST-500", "metadata": {"doc_id": "A"}},
            {"chunk_id": "b", "text": "엘리베이터 점검", "metadata": {"doc_id": "B"}},
        ]
        with patch(GET_CHUNKS_PATH, return_value=chunks):
            results = bm25_search("WBST-500 점검", {})
        self.assertEqual([result["chunk_id"] for result in results], ["a", "b"])
        self.assertTrue(all(result["score"] > 0 for result in results))

    def test_bm25_chunks_without_tokens_return_empty(self):
        """허용 청크가 모두 토큰 없는 텍스트여도 오류 없이 빈 목록."""
        chunks = [{"chunk_id": "a", "text": "", "metadata": {}}, {"chunk_id": "b", "text": "...", "metadata": {}}]
        with patch(GET_CHUNKS_PATH, return_value=chunks):
            self.assertEqual(bm25_search("WBST-500", {}), [])

    def test_s02_filters_are_applied(self):
        """S-02 필터(ELV만)를 걸면 BM25 쪽에서도 MVX 청크가 나오지 않는다."""
        self._index_chunks()
        results = self._hybrid(QUERY, MVX_EMPLOYEE, filters={"company_id": "ELV"})
        self.assertEqual({result["doc_id"] for result in results}, {"ELV-public"})

    def test_blank_query_returns_empty(self):
        """빈 검색어는 임베딩 호출 없이 빈 목록."""
        with patch(EMBED_PATH) as embed, patch(APPROVED_PATH, return_value=[]):
            self.assertEqual(hybrid_search("   ", None, MVX_EMPLOYEE), [])
        embed.assert_not_called()

    def test_invalid_user_raises(self):
        """로그인 정보가 없으면 검색어와 관계없이 PermissionError."""
        for query in (QUERY, ""):
            with self.subTest(query=query), self.assertRaises(PermissionError):
                self._hybrid(query, None)

    def test_no_collection_returns_empty(self):
        """색인(I-02) 전이라 컬렉션이 없으면 오류 대신 빈 목록."""
        self.assertEqual(self._hybrid(QUERY, MVX_EMPLOYEE), [])


class TokenizeTest(unittest.TestCase):
    """BM25 토큰화 테스트. 순수 함수라 DB 없이 바로 돈다."""

    def test_model_name_kept_whole_and_lowercased(self):
        # 모델명은 쪼개지 않고 소문자 하나로 남겨야 대소문자가 달라도 찾는다.
        self.assertEqual(_tokenize("WBST-500 HD2000"), ["wbst-500", "hd2000"])

    def test_korean_split_into_bigrams(self):
        # 조사가 붙은 단어도 앞쪽 조각이 같아 서로 찾을 수 있다.
        self.assertEqual(_tokenize("엘리베이터의"), ["엘리", "리베", "베이", "이터", "터의"])
        self.assertTrue(set(_tokenize("엘리베이터")) <= set(_tokenize("엘리베이터의")))

    def test_punctuation_and_empty(self):
        self.assertEqual(_tokenize("?! ,"), [])
        self.assertEqual(_tokenize(None), [])


if __name__ == "__main__":
    unittest.main()
