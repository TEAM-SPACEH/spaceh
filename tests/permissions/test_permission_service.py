"""S-03 권한 필터 테스트.

실행: python -m unittest tests.permissions.test_permission_service

무엇을 확인하나
- check_search_permission(): 시드 계정 7개 × 문서마다 열람 매트릭스대로 허용·차단되는지
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

# data-model.md §6 시드 계정 7개 (scripts/seed_users.py와 같은 역할·소속). id는 테스트용 값.
SEED_USERS = {
    "HRI-0001": {"id": 1, "role": "employee", "company_id": "HRI"},
    "HRI-0002": {"id": 2, "role": "company_admin", "company_id": "HRI"},
    "MVX-0001": {"id": 3, "role": "employee", "company_id": "MVX"},
    "MVX-0002": {"id": 4, "role": "company_admin", "company_id": "MVX"},
    "ELV-0001": {"id": 5, "role": "employee", "company_id": "ELV"},
    "ELV-0002": {"id": 6, "role": "company_admin", "company_id": "ELV"},
    "ADM-0001": {"id": 7, "role": "super_admin", "company_id": None},
}
MVX_EMPLOYEE = SEED_USERS["MVX-0001"]
SUPER_ADMIN = SEED_USERS["ADM-0001"]

# 회사마다 같은 종류의 문서를 둔다. 어느 계정이든 "자사"·"타사" 문서가 모두 있게 된다.
# confidential_shared: 공유 플래그가 잘못 켜진 기밀 문서. 승인 없이는 타사에 열리면 안 된다.
DOC_KINDS = {
    "public": ("public", False),
    "internal_off": ("internal", False),
    "internal_on": ("internal", True),
    "confidential": ("confidential", False),
    "confidential_shared": ("confidential", True),
}
DOCUMENTS = {
    f"{company}-{kind}": {
        "doc_id": f"{company}-{kind}",
        "company_id": company,
        "access_level": access_level,
        "is_group_shared": shared,
    }
    for company in ("HRI", "MVX", "ELV")
    for kind, (access_level, shared) in DOC_KINDS.items()
}

# overview §2.1 열람 매트릭스에서 승인 없이 ✅인 칸
MATRIX = {
    "employee": {"public", "own_internal", "other_internal_on"},
    "company_admin": {"public", "own_internal", "other_internal_on", "own_confidential"},
    "super_admin": {
        "public", "own_internal", "other_internal_off", "other_internal_on",
        "own_confidential", "other_confidential",
    },
}


def _matrix_column(user, doc):
    """문서가 이 사용자에게 열람 매트릭스의 어느 칸(열)에 해당하는지 돌려준다."""
    if doc["access_level"] == "public":
        return "public"
    owner = "own" if doc["company_id"] == user["company_id"] else "other"
    if doc["access_level"] == "internal":
        if owner == "own":
            return "own_internal"
        return "other_internal_on" if doc["is_group_shared"] else "other_internal_off"
    # confidential은 공유할 수 없으므로 공유 플래그와 관계없이 같은 칸이다.
    return f"{owner}_confidential"


def _expected(user, approved=()):
    """매트릭스와 승인 문서로 계산한, user가 볼 수 있어야 하는 doc_id 집합."""
    return {
        doc_id
        for doc_id, doc in DOCUMENTS.items()
        if _matrix_column(user, doc) in MATRIX[user["role"]] or doc_id in approved
    }


def _chroma_collection():
    """테스트 문서를 넣은 메모리 Chroma 컬렉션을 만든다 (파일로 저장하지 않음)."""
    collection = chromadb.EphemeralClient().create_collection(
        "permission_test", embedding_function=None, get_or_create=True
    )
    ids = list(DOCUMENTS)
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
        """승인 문서를 approved로 가정하고, user가 볼 수 있는 doc_id 집합을 돌려준다."""
        with patch(APPROVED_PATH, return_value=list(approved)):
            return {doc_id for doc_id, doc in DOCUMENTS.items() if check_search_permission(user, doc)}

    def test_matrix_without_approval(self):
        """시드 계정 7개 모두 승인 없이 매트릭스의 ✅ 칸만 열린다."""
        for employee_no, user in SEED_USERS.items():
            with self.subTest(user=employee_no):
                self.assertEqual(self._allowed(user), _expected(user))

    def test_shared_confidential_is_closed_to_other_companies(self):
        """공유 플래그가 켜진 confidential도 타사 계정에는 승인 없이 열리지 않는다."""
        for employee_no, user in SEED_USERS.items():
            if user["role"] == "super_admin":
                continue
            with self.subTest(user=employee_no):
                leaked = {
                    doc_id for doc_id in self._allowed(user)
                    if doc_id.endswith("-confidential_shared") and not doc_id.startswith(user["company_id"])
                }
                self.assertEqual(leaked, set())

    def test_approved_document_opens(self):
        """매트릭스의 "승인 시 ✅" 칸: 승인받은 문서만 추가로 열린다."""
        approved = ["ELV-internal_off", "MVX-confidential", "HRI-confidential"]
        for employee_no, user in SEED_USERS.items():
            with self.subTest(user=employee_no):
                self.assertEqual(self._allowed(user, approved), _expected(user, approved))

    def test_mysql_tinyint_shared_flag(self):
        """MySQL에서 읽은 행은 is_group_shared가 True가 아니라 1로 와도 같게 판정한다."""
        doc = dict(DOCUMENTS["ELV-internal_on"], is_group_shared=1)
        with patch(APPROVED_PATH, return_value=[]):
            self.assertTrue(check_search_permission(MVX_EMPLOYEE, doc))

    def test_invalid_user_or_document_is_denied(self):
        """로그인 정보 없음 / 모르는 역할 / 소속 없는 일반 사원 / 문서 없음은 모두 차단한다."""
        public_doc = DOCUMENTS["ELV-public"]
        with patch(APPROVED_PATH, return_value=[]):
            self.assertFalse(check_search_permission(None, public_doc))
            self.assertFalse(check_search_permission({"id": 1, "role": "guest", "company_id": "MVX"}, public_doc))
            self.assertFalse(check_search_permission({"id": 1, "role": "employee", "company_id": None}, public_doc))
            self.assertFalse(check_search_permission(MVX_EMPLOYEE, None))


class ApplyRbacFilterTest(unittest.TestCase):
    """apply_rbac_filter()가 만든 where를 진짜 Chroma에 넣어 보는 테스트."""

    @classmethod
    def setUpClass(cls):
        """컬렉션은 테스트마다 새로 만들 필요가 없어 클래스에서 한 번만 만든다."""
        cls.collection = _chroma_collection()

    def _visible(self, where):
        """where 조건으로 Chroma에서 꺼낸 doc_id 집합. 빈 where는 None으로 넘긴다."""
        return set(self.collection.get(where=where or None)["ids"])

    def test_chroma_prefilter_matches_matrix(self):
        """시드 계정 7개 모두 검색 단계에서 이미 매트릭스대로 걸러진다 (사후 필터가 아님)."""
        for employee_no, user in SEED_USERS.items():
            with self.subTest(user=employee_no), patch(APPROVED_PATH, return_value=[]):
                self.assertEqual(self._visible(apply_rbac_filter(user, {})), _expected(user))

    def test_chroma_prefilter_includes_approved(self):
        """승인 문서는 doc_id $in 조건으로 검색 후보에 들어온다."""
        approved = ["HRI-confidential"]
        with patch(APPROVED_PATH, return_value=approved):
            where = apply_rbac_filter(MVX_EMPLOYEE, {})
        self.assertEqual(self._visible(where), _expected(MVX_EMPLOYEE, approved))

    def test_filter_and_check_agree_for_every_document(self):
        """검색에서 보인 문서 = 원문 보기에서 열리는 문서 (두 함수의 판정이 같아야 한다)."""
        for employee_no, user in SEED_USERS.items():
            with self.subTest(user=employee_no), patch(APPROVED_PATH, return_value=["ELV-internal_off"]):
                visible = self._visible(apply_rbac_filter(user, {}))
                checked = {doc_id for doc_id, doc in DOCUMENTS.items() if check_search_permission(user, doc)}
                self.assertEqual(visible, checked)

    def test_s02_filters_are_combined_with_and(self):
        """S-02 "현대엘리베이터만 보기" 필터를 걸어도 권한 밖 문서는 나오지 않는다."""
        filters = {"company_id": {"$in": ["ELV"]}}
        with patch(APPROVED_PATH, return_value=[]):
            where = apply_rbac_filter(MVX_EMPLOYEE, filters)
            super_where = apply_rbac_filter(SUPER_ADMIN, filters)
        self.assertEqual(self._visible(where), {"ELV-public", "ELV-internal_on"})
        # 어드민은 권한 조건 없이 화면 필터만 그대로 남는다
        self.assertEqual(super_where, filters)

    def test_super_admin_without_filters_has_no_condition(self):
        """최종 어드민이 필터 없이 검색하면 where 조건이 비어 있다."""
        with patch(APPROVED_PATH, return_value=[]):
            self.assertEqual(apply_rbac_filter(SUPER_ADMIN, None), {})

    def test_invalid_user_raises(self):
        """검색 조건을 만들 수 없는 사용자는 검색 자체를 못 하게 예외를 낸다."""
        for user in (None, {"id": 1, "role": "guest", "company_id": "MVX"}, {"id": 1, "role": "employee", "company_id": None}):
            with self.subTest(user=user), patch(APPROVED_PATH, return_value=[]):
                with self.assertRaises(PermissionError):
                    apply_rbac_filter(user, {})


if __name__ == "__main__":
    unittest.main()
