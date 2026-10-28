
"""S-04 검색 권한 필터 연동 테스트"""

import unittest
from unittest.mock import patch

from app.permissions.services.permission_service import (
    apply_rbac_filter,
    check_search_permission,
)
from app.search.services.search_service import search_documents
from core import config


# 테스트 사용자: 현대엘리베이터 일반 사원
USER = {
    "id": 3,
    "role": "employee",
    "company_id": "ELV",
}


class TestS04Permissions(unittest.TestCase):

    # 테스트 1. 일반 사원의 문서 접근 권한 확인
    @patch(
        "app.permissions.services.permission_service.get_approved_doc_ids",
        return_value=[]
    )
    def test_employee_permission(self, mock_approved):

        # 자사 내부 문서
        own_document = {
            "company_id": "ELV",
            "access_level": "internal",
            "is_group_shared": False,
        }

        # 타사 비공유 내부 문서
        other_document = {
            "company_id": "MVX",
            "access_level": "internal",
            "is_group_shared": False,
        }

        # 타사 그룹사 공유 문서
        shared_document = {
            "company_id": "MVX",
            "access_level": "internal",
            "is_group_shared": True,
        }

        # 타사 기밀 문서 (공유 플래그가 켜져도 차단)
        confidential_document = {
            "company_id": "MVX",
            "access_level": "confidential",
            "is_group_shared": True,
        }

        self.assertTrue(
            check_search_permission(USER, own_document)
        )

        self.assertFalse(
            check_search_permission(USER, other_document)
        )

        self.assertTrue(
            check_search_permission(USER, shared_document)
        )

        self.assertFalse(
            check_search_permission(USER, confidential_document)
        )

        print("테스트 1 통과: 일반 사원 문서 접근 권한")


    # 테스트 2. 승인된 타사 기밀 문서 접근 확인
    @patch(
        "app.permissions.services.permission_service.get_approved_doc_ids",
        return_value=["doc-001"]
    )
    def test_approved_document(self, mock_approved):

        document = {
            "doc_id": "doc-001",
            "company_id": "MVX",
            "access_level": "confidential",
            "is_group_shared": False,
        }

        self.assertTrue(
            check_search_permission(USER, document)
        )

        print("테스트 2 통과: 승인된 문서 접근")


    # 테스트 3. 화면 필터로 권한을 우회할 수 없는지 확인
    @patch(
        "app.permissions.services.permission_service.get_approved_doc_ids",
        return_value=[]
    )
    def test_filter_combination(self, mock_approved):

        # 현대엘리베이터 직원이 현대무벡스 문서를 검색
        filters = {"company_id": "MVX"}

        where = apply_rbac_filter(USER, filters)

        # 권한 조건과 사용자 필터가 AND로 결합되어야 함
        self.assertIn("$and", where)

        # 사용자 검색 필터 확인
        self.assertEqual(
            where["$and"][1],
            filters
        )

        # RBAC 권한 조건 확인
        self.assertIn(
            "$or",
            where["$and"][0]
        )

        print("테스트 3 통과: 검색 필터와 권한 조건 결합")


    # 테스트 4. 검색 저장소에 권한 필터가 전달되는지 확인
    @patch(
        "app.permissions.services.permission_service.get_approved_doc_ids",
        return_value=[]
    )
    @patch(
        "app.search.services.search_service._embed_query",
        return_value=[0.1, 0.2]
    )
    @patch(
        "app.search.services.search_service.query_chunks"
    )
    def test_chroma_where(
        self,
        mock_query_chunks,
        mock_embed,
        mock_approved
    ):

        # 검색 저장소에서 반환할 가상 청크
        mock_query_chunks.return_value = [
            {
                "chunk_id": "chunk-001",
                "text": "승강기 제조 사업",
                "metadata": {
                    "doc_id": "doc-001",
                    "company_id": "ELV",
                    "access_level": "internal",
                    "is_group_shared": False,
                },
                "distance": 0.2,
            }
        ]

        # S-01 검색 서비스 실행
        results = search_documents(
            "승강기 사업",
            None,
            USER
        )

        # S-03 권한 필터에서 생성되는 조건
        expected_where = apply_rbac_filter(USER, None)

        # 권한 조건이 검색 저장소에 전달됐는지 검증
        mock_query_chunks.assert_called_once_with(
            [0.1, 0.2],
            expected_where,
            config.SEARCH_TOP_K
        )

        # 검색 결과 확인
        self.assertEqual(
            len(results),
            1
        )

        self.assertEqual(
            results[0]["text"],
            "승강기 제조 사업"
        )

        self.assertEqual(
            results[0]["doc_id"],
            "doc-001"
        )

        print("테스트 4 통과: 검색 저장소 권한 조건 전달")


    # 테스트 5. 잘못된 역할의 사용자 검색 차단
    @patch(
        "app.search.services.search_service._embed_query"
    )
    def test_invalid_user(self, mock_embed):

        invalid_user = {
            "id": 3,
            "role": "unknown",
            "company_id": "ELV",
        }

        # 잘못된 사용자는 PermissionError 발생
        with self.assertRaises(PermissionError):
            search_documents(
                "승강기 사업",
                None,
                invalid_user
            )

        # 권한 검증 실패 시 임베딩도 실행하지 않아야 함
        mock_embed.assert_not_called()

        print("테스트 5 통과: 잘못된 사용자 차단")


if __name__ == "__main__":
    unittest.main()
