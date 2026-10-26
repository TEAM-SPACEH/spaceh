"""S-03 권한 필터 테스트.

실행: python -m unittest tests.permissions.test_permission_service

무엇을 확인하나
- check_search_permission(): 문서 1건씩 열람 매트릭스대로 허용·차단되는지
- apply_rbac_filter(): 만든 where 조건을 진짜 Chroma에 넣었을 때 볼 수 있는 문서만 나오는지
- 두 함수의 판정이 서로 같은지

MySQL 없이 돌도록 승인 문서 조회(get_approved_doc_ids)는 patch로 가짜 값을 넣는다.
patch: 테스트하는 동안만 특정 함수를 정해 둔 값을 돌려주는 가짜로 바꿔 끼우는 unittest 기능.
"""

import unittest
from unittest.mock import patch

import chromadb

from app.permissions.services.permission_service import (
    apply_rbac_filter,
    check_search_permission,
)

# permission_service가 import해서 쓰는 이름을 바꿔야 하므로 서비스 모듈 경로를 적는다.
APPROVED_PATH = "app.permissions.services.permission_service.get_approved_doc_ids"

# 테스트용 사용자. 모두 현대무벡스(MVX) 기준이고, 어드민은 소속이 없다.
MVX_EMPLOYEE = {"id": 3, "role": "employee", "company_id": "MVX"}
MVX_ADMIN = {"id": 4, "role": "company_admin", "company_id": "MVX"}
SUPER_ADMIN = {"id": 7, "role": "super_admin", "company_id": None}

# overview §2.1 열람 매트릭스의 문서 6유형 (MVX 사용자 입장에서 "자사"·"타사")
DOCUMENTS = {
    "public": {"doc_id": "d-public", "company_id": "ELV", "access_level": "public", "is_group_shared": False},
    "own_internal": {"doc_id": "d-own-int", "company_id": "MVX", "access_level": "internal", "is_group_shared": False},
    "other_internal_off": {"doc_id": "d-oth-off", "company_id": "ELV", "access_level": "internal", "is_group_shared": False},
    "other_internal_on": {"doc_id": "d-oth-on", "company_id": "ELV", "access_level": "internal", "is_group_shared": True},
    "own_confidential": {"doc_id": "d-own-conf", "company_id": "MVX", "access_level": "confidential", "is_group_shared": False},
    "other_confidential": {"doc_id": "d-oth-conf", "company_id": "HRI", "access_level": "confidential", "is_group_shared": False},
    # 공유 플래그가 잘못 켜진 confidential도 승인 없이는 열리면 안 된다
    "other_confidential_shared": {"doc_id": "d-oth-conf-on", "company_id": "HRI", "access_level": "confidential", "is_group_shared": True},
}

# 승인 문서가 하나도 없을 때 역할별로 보여야 하는 문서 (= 열람 매트릭스의 ✅ 칸)
EXPECTED = {
    "employee": {"public", "own_internal", "other_internal_on"},
    "company_admin": {"public", "own_internal", "other_internal_on", "own_confidential"},
    "super_admin": set(DOCUMENTS),
}


def _chroma_collection():
    """테스트 문서 7건을 넣은 메모리 Chroma 컬렉션을 만든다 (파일로 저장하지 않음)."""
    collection = chromadb.EphemeralClient().create_collection(
        "permission_test", embedding_function=None, get_or_create=True
    )
    ids = [doc["doc_id"] for doc in DOCUMENTS.values()]
    # 여기서는 where 조건만 확인하므로 임베딩(문장을 숫자 벡터로 바꾼 값)은 아무 숫자나 넣는다.
    # OpenAI 임베딩을 부르지 않아서 API 키 없이도 돈다.
    collection.upsert(
        ids=ids,
        embeddings=[[float(i), 1.0] for i in range(len(ids))],
        metadatas=[dict(doc, doc_type="report") for doc in DOCUMENTS.values()],
    )
    return collection


class CheckSearchPermissionTest(unittest.TestCase):
    """문서 1건씩 확인하는 check_search_permission() 테스트."""

    def _allowed(self, user, approved=()):
        """승인 문서를 approved로 가정하고, user가 볼 수 있는 문서 이름 집합을 돌려준다."""
        with patch(APPROVED_PATH, return_value=list(approved)):
            return {name for name, doc in DOCUMENTS.items() if check_search_permission(user, doc)}

    def test_matrix_without_approval(self):
        # 승인 없이 역할별로 매트릭스의 ✅ 칸만 열리는지
        for user in (MVX_EMPLOYEE, MVX_ADMIN, SUPER_ADMIN):
            with self.subTest(role=user["role"]):
                self.assertEqual(self._allowed(user), EXPECTED[user["role"]])

    def test_approved_document_opens(self):
        # 매트릭스의 "승인 시 ✅" 칸: 승인받은 문서만 추가로 열린다
        approved = ["d-oth-off", "d-own-conf", "d-oth-conf"]
        self.assertEqual(
            self._allowed(MVX_EMPLOYEE, approved),
            EXPECTED["employee"] | {"other_internal_off", "own_confidential", "other_confidential"},
        )

    def test_mysql_tinyint_shared_flag(self):
        # MySQL에서 읽은 행은 is_group_shared가 True가 아니라 1로 온다
        doc = dict(DOCUMENTS["other_internal_on"], is_group_shared=1)
        with patch(APPROVED_PATH, return_value=[]):
            self.assertTrue(check_search_permission(MVX_EMPLOYEE, doc))

    def test_invalid_user_or_document_is_denied(self):
        # 로그인 정보가 없음 / 모르는 역할 / 소속 없는 일반 사원 / 문서 없음 → 모두 차단
        with patch(APPROVED_PATH, return_value=[]):
            self.assertFalse(check_search_permission(None, DOCUMENTS["public"]))
            self.assertFalse(check_search_permission({"id": 1, "role": "guest", "company_id": "MVX"}, DOCUMENTS["public"]))
            self.assertFalse(check_search_permission({"id": 1, "role": "employee", "company_id": None}, DOCUMENTS["public"]))
            self.assertFalse(check_search_permission(MVX_EMPLOYEE, None))


class ApplyRbacFilterTest(unittest.TestCase):
    """apply_rbac_filter()가 만든 where를 진짜 Chroma에 넣어 보는 테스트."""

    @classmethod
    def setUpClass(cls):
        # 컬렉션은 테스트마다 새로 만들 필요가 없어 클래스에서 한 번만 만든다.
        cls.collection = _chroma_collection()
        cls.name_by_id = {doc["doc_id"]: name for name, doc in DOCUMENTS.items()}

    def _visible(self, where):
        """where 조건으로 Chroma에서 꺼낸 문서 이름 집합. 빈 where는 None으로 넘긴다."""
        result = self.collection.get(where=where or None)
        return {self.name_by_id[doc_id] for doc_id in result["ids"]}

    def test_chroma_prefilter_matches_matrix(self):
        # 검색 단계에서 이미 매트릭스대로 걸러지는지 (사후 필터가 아님)
        for user in (MVX_EMPLOYEE, MVX_ADMIN, SUPER_ADMIN):
            with self.subTest(role=user["role"]), patch(APPROVED_PATH, return_value=[]):
                self.assertEqual(self._visible(apply_rbac_filter(user, {})), EXPECTED[user["role"]])

    def test_chroma_prefilter_includes_approved(self):
        # 승인 문서는 doc_id $in 조건으로 검색 후보에 들어온다
        with patch(APPROVED_PATH, return_value=["d-oth-conf"]):
            where = apply_rbac_filter(MVX_EMPLOYEE, {})
        self.assertEqual(self._visible(where), EXPECTED["employee"] | {"other_confidential"})

    def test_filter_and_check_agree_for_every_document(self):
        # 검색에서 보인 문서 = 원문 보기에서 열리는 문서 (두 함수의 판정이 같아야 한다)
        for user in (MVX_EMPLOYEE, MVX_ADMIN, SUPER_ADMIN):
            with self.subTest(role=user["role"]), patch(APPROVED_PATH, return_value=["d-oth-off"]):
                visible = self._visible(apply_rbac_filter(user, {}))
                checked = {name for name, doc in DOCUMENTS.items() if check_search_permission(user, doc)}
                self.assertEqual(visible, checked)

    def test_s02_filters_are_combined_with_and(self):
        # S-02 "현대엘리베이터만 보기" 필터를 걸어도 권한 밖 문서는 나오지 않는다
        filters = {"company_id": {"$in": ["ELV"]}}
        with patch(APPROVED_PATH, return_value=[]):
            where = apply_rbac_filter(MVX_EMPLOYEE, filters)
            super_where = apply_rbac_filter(SUPER_ADMIN, filters)
        self.assertEqual(self._visible(where), {"public", "other_internal_on"})
        # 어드민은 권한 조건 없이 화면 필터만 그대로 남는다
        self.assertEqual(super_where, filters)

    def test_super_admin_without_filters_has_no_condition(self):
        with patch(APPROVED_PATH, return_value=[]):
            self.assertEqual(apply_rbac_filter(SUPER_ADMIN, None), {})

    def test_invalid_user_raises(self):
        # 검색 조건을 만들 수 없는 사용자는 검색 자체를 못 하게 예외를 낸다
        for user in (None, {"id": 1, "role": "guest", "company_id": "MVX"}, {"id": 1, "role": "employee", "company_id": None}):
            with self.subTest(user=user), patch(APPROVED_PATH, return_value=[]):
                with self.assertRaises(PermissionError):
                    apply_rbac_filter(user, {})


if __name__ == "__main__":
    unittest.main()
