"""S-01 통합 검색 테스트.

실행: python -m unittest tests.search.test_search_service

무엇을 확인하나
- 권한 밖 청크가 검색 결과에 0건인지 (임시 폴더의 진짜 Chroma로 확인)
- 관련도 순 정렬, 빈 검색어, 잘못된 사용자, 색인 전(컬렉션 없음)

OpenAI·MySQL 없이 돌도록 질문 임베딩(_embed_query)과 승인 문서 조회는 patch로 가짜 값을 넣는다.
임베딩은 2차원 벡터로 단순화해, 질문 [1, 0]에 가까울수록 관련도가 높게 만든다.
"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import chromadb

from app.search.services.search_service import search_documents
from core import config

EMBED_PATH = "app.search.services.search_service._embed_query"
APPROVED_PATH = "app.permissions.services.permission_service.get_approved_doc_ids"
QUERY_VECTOR = [1.0, 0.0]

MVX_EMPLOYEE = {"id": 1, "role": "employee", "company_id": "MVX"}
ELV_EMPLOYEE = {"id": 2, "role": "employee", "company_id": "ELV"}
SUPER_ADMIN = {"id": 7, "role": "super_admin", "company_id": None}

# chunk_id: (메타데이터, 임베딩). 임베딩 첫 값이 클수록 질문과 가깝다.
CHUNKS = {
    "MVX-internal#0000": ({"doc_id": "MVX-internal", "company_id": "MVX", "access_level": "internal", "is_group_shared": False}, [0.9, 0.1]),
    "MVX-internal#0001": ({"doc_id": "MVX-internal", "company_id": "MVX", "access_level": "internal", "is_group_shared": False}, [0.5, 0.5]),
    "ELV-public#0000": ({"doc_id": "ELV-public", "company_id": "ELV", "access_level": "public", "is_group_shared": False}, [0.7, 0.3]),
    "ELV-internal#0000": ({"doc_id": "ELV-internal", "company_id": "ELV", "access_level": "internal", "is_group_shared": False}, [1.0, 0.0]),
    "ELV-confidential#0000": ({"doc_id": "ELV-confidential", "company_id": "ELV", "access_level": "confidential", "is_group_shared": False}, [1.0, 0.0]),
}


class SearchDocumentsTest(unittest.TestCase):
    def setUp(self):
        # repository가 config.CHROMA_DIR을 읽으므로 테스트 동안만 임시 폴더로 바꾼다.
        self.tmp = tempfile.TemporaryDirectory()
        patcher = patch.object(config, "CHROMA_DIR", Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def _index_chunks(self):
        client = chromadb.PersistentClient(path=self.tmp.name)
        collection = client.create_collection(config.CHROMA_COLLECTION)
        collection.add(
            ids=list(CHUNKS),
            embeddings=[embedding for _, embedding in CHUNKS.values()],
            metadatas=[metadata for metadata, _ in CHUNKS.values()],
            documents=[f"{chunk_id} 본문" for chunk_id in CHUNKS],
        )

    def _search(self, query, user, filters=None):
        with patch(EMBED_PATH, return_value=QUERY_VECTOR), patch(APPROVED_PATH, return_value=[]):
            return search_documents(query, filters, user)

    def test_results_exclude_unauthorized_chunks(self):
        """질문과 가장 가까운 ELV internal·confidential 청크도 MVX 사원에게는 나오지 않는다."""
        self._index_chunks()
        chunk_ids = {result["chunk_id"] for result in self._search("엘리베이터 사양", MVX_EMPLOYEE)}
        self.assertEqual(chunk_ids, {"MVX-internal#0000", "MVX-internal#0001", "ELV-public#0000"})

    def test_each_account_sees_only_allowed_documents(self):
        """계정별 금지 문서 0건 (권한 누출 테스트)."""
        self._index_chunks()
        expected = {
            "MVX": {"MVX-internal", "ELV-public"},
            "ELV": {"ELV-internal", "ELV-public"},
            "super": {"MVX-internal", "ELV-public", "ELV-internal", "ELV-confidential"},
        }
        for name, user in (("MVX", MVX_EMPLOYEE), ("ELV", ELV_EMPLOYEE), ("super", SUPER_ADMIN)):
            with self.subTest(user=name):
                doc_ids = {result["doc_id"] for result in self._search("사양", user)}
                self.assertEqual(doc_ids, expected[name])

    def test_results_sorted_by_relevance(self):
        """관련도 높은 순으로 정렬되고 결과 모양이 약속한 키를 갖는다."""
        self._index_chunks()
        results = self._search("사양", MVX_EMPLOYEE)
        self.assertEqual(
            [result["chunk_id"] for result in results],
            ["MVX-internal#0000", "ELV-public#0000", "MVX-internal#0001"],
        )
        self.assertEqual(set(results[0]), {"chunk_id", "doc_id", "text", "score", "metadata"})
        scores = [result["score"] for result in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_s02_filters_are_applied(self):
        """S-02 필터(ELV만)를 걸면 권한 안에서도 ELV 문서만 나온다."""
        self._index_chunks()
        results = self._search("사양", MVX_EMPLOYEE, filters={"company_id": {"$in": ["ELV"]}})
        self.assertEqual({result["doc_id"] for result in results}, {"ELV-public"})

    def test_blank_query_returns_empty(self):
        """빈 검색어는 임베딩 호출 없이 빈 목록."""
        with patch(EMBED_PATH) as embed, patch(APPROVED_PATH, return_value=[]):
            self.assertEqual(search_documents("   ", None, MVX_EMPLOYEE), [])
        embed.assert_not_called()

    def test_invalid_user_raises(self):
        """로그인 정보가 없으면 검색어와 관계없이 PermissionError."""
        for query in ("사양", ""):
            with self.subTest(query=query), self.assertRaises(PermissionError):
                self._search(query, None)

    def test_no_collection_returns_empty(self):
        """색인(I-02) 전이라 컬렉션이 없으면 오류 대신 빈 목록."""
        self.assertEqual(self._search("사양", MVX_EMPLOYEE), [])


if __name__ == "__main__":
    unittest.main()
