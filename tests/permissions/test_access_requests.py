"""M-03 문서 열람 권한 확인·요청 테스트. 저장소(DB 접근)·감사 로그는 목으로 바꿔 DB 없이 돈다.

S-03 권한 규칙 자체(열람 매트릭스·Chroma 사전 필터)는 test_permission_service.py에서 확인한다.
여기서는 M-03(확인·요청 가능 여부·요청 등록·사유 검증·감사 로그)만 다룬다.
"""

import unittest
from unittest import mock

from app.permissions import validators
from app.permissions.services import permission_service as ps

# 테스트용 사용자/문서 (users·documents 한 줄과 같은 모양)
EMPLOYEE = {"id": 1, "role": "employee", "company_id": "MVX"}
ADMIN = {"id": 2, "role": "company_admin", "company_id": "MVX"}
SUPER_ADMIN = {"id": 9, "role": "super_admin", "company_id": None}

DOC_MVX_INTERNAL = {"doc_id": "mvx1", "company_id": "MVX", "access_level": "internal", "is_group_shared": 0}
DOC_ELV_CONFIDENTIAL = {"doc_id": "elvC", "company_id": "ELV", "access_level": "confidential", "is_group_shared": 0}


class ValidateRequestReasonTest(unittest.TestCase):
    """사유 검증은 validators(형식 검증 계층)에 있고, 순수 함수라 DB 없이 바로 확인한다."""

    def test_blank_or_too_short_rejected(self):
        self.assertFalse(validators.validate_request_reason(""))
        self.assertFalse(validators.validate_request_reason("   "))
        self.assertFalse(validators.validate_request_reason("abc"))      # 3자
        self.assertFalse(validators.validate_request_reason("  ab  "))   # strip 후 2자

    def test_too_long_rejected(self):
        self.assertFalse(validators.validate_request_reason("가" * 501))

    def test_valid_accepted(self):
        self.assertTrue(validators.validate_request_reason("12345"))     # 5자(경계)
        self.assertTrue(validators.validate_request_reason("계약 단가 확인이 필요합니다"))
        self.assertTrue(validators.validate_request_reason("가" * 500))  # 500자(경계)


@mock.patch("app.permissions.services.permission_service.get_approved_doc_ids", return_value=[])
@mock.patch("app.permissions.services.permission_service.find_document")
@mock.patch("app.permissions.services.permission_service.find_user")
class CheckDocumentAccessTest(unittest.TestCase):
    def test_delegates_to_search_permission(self, find_user, find_document, _approved):
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_MVX_INTERNAL  # 자사 내부 → 열람 가능
        self.assertTrue(ps.check_document_access(1, "mvx1"))

    def test_no_access_other_confidential(self, find_user, find_document, _approved):
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_ELV_CONFIDENTIAL  # 타사 기밀 → 불가
        self.assertFalse(ps.check_document_access(1, "elvC"))

    def test_missing_user_or_document(self, find_user, find_document, _approved):
        find_user.return_value = None
        find_document.return_value = DOC_MVX_INTERNAL
        self.assertFalse(ps.check_document_access(99, "mvx1"))
        find_user.return_value = EMPLOYEE
        find_document.return_value = None
        self.assertFalse(ps.check_document_access(1, "nope"))


@mock.patch("app.permissions.services.permission_service.get_approved_doc_ids", return_value=[])
@mock.patch("app.permissions.services.permission_service.has_pending_request", return_value=False)
@mock.patch("app.permissions.services.permission_service.find_document")
@mock.patch("app.permissions.services.permission_service.find_user")
class CanRequestAccessTest(unittest.TestCase):
    def test_accessible_doc_cannot_request(self, find_user, find_document, _pending, _approved):
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_MVX_INTERNAL  # 이미 열람 가능
        self.assertFalse(ps.can_request_access(1, "mvx1"))

    def test_super_admin_cannot_request(self, find_user, find_document, _pending, _approved):
        find_user.return_value = SUPER_ADMIN
        find_document.return_value = DOC_ELV_CONFIDENTIAL
        self.assertFalse(ps.can_request_access(9, "elvC"))

    def test_employee_without_access_can_request(self, find_user, find_document, _pending, _approved):
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_ELV_CONFIDENTIAL  # 못 보는 문서
        self.assertTrue(ps.can_request_access(1, "elvC"))

    def test_admin_without_access_can_request(self, find_user, find_document, _pending, _approved):
        find_user.return_value = ADMIN
        find_document.return_value = DOC_ELV_CONFIDENTIAL
        self.assertTrue(ps.can_request_access(2, "elvC"))

    def test_pending_blocks_request(self, find_user, find_document, pending, _approved):
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_ELV_CONFIDENTIAL
        pending.return_value = True  # 이미 대기 중
        self.assertFalse(ps.can_request_access(1, "elvC"))

    def test_missing_document(self, find_user, find_document, _pending, _approved):
        find_user.return_value = EMPLOYEE
        find_document.return_value = None
        self.assertFalse(ps.can_request_access(1, "nope"))


@mock.patch("app.permissions.services.permission_service.record_audit_log")
@mock.patch("app.permissions.services.permission_service.insert_access_request")
@mock.patch("app.permissions.services.permission_service.get_approved_doc_ids", return_value=[])
@mock.patch("app.permissions.services.permission_service.has_pending_request", return_value=False)
@mock.patch("app.permissions.services.permission_service.find_document")
@mock.patch("app.permissions.services.permission_service.find_user")
class RequestDocumentAccessTest(unittest.TestCase):
    def test_valid_request_saved_and_audited(self, find_user, find_document, _pending, _approved, insert, record):
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_ELV_CONFIDENTIAL
        insert.return_value = 42  # 저장 성공 → 새 요청 id

        self.assertTrue(ps.request_document_access(1, "elvC", "  계약 단가 확인 필요  "))

        # 소유 회사(owner_company_code)는 문서의 company_id, 사유는 strip되어 저장된다.
        insert.assert_called_once_with(1, "elvC", "ELV", "계약 단가 확인 필요")
        # A-04 감사 로그: access_request, 대상 문서, 소유 회사, request_id
        record.assert_called_once_with(
            1, "access_request", "elvC", None, False, None,
            target_type="document", doc_ids=["elvC"], doc_companies=["ELV"],
            context_detail={"request_id": 42},
        )

    def test_invalid_reason_not_saved(self, find_user, find_document, _pending, _approved, insert, record):
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_ELV_CONFIDENTIAL
        self.assertFalse(ps.request_document_access(1, "elvC", "짧음"))  # 2자
        insert.assert_not_called()
        record.assert_not_called()

    def test_cannot_request_not_saved(self, find_user, find_document, _pending, _approved, insert, record):
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_MVX_INTERNAL  # 이미 열람 가능 → 요청 불가
        self.assertFalse(ps.request_document_access(1, "mvx1", "보고 싶어요 정말로"))
        insert.assert_not_called()
        record.assert_not_called()

    def test_duplicate_insert_returns_false(self, find_user, find_document, _pending, _approved, insert, record):
        # 저장 함수가 None(이미 대기 요청 존재)을 주면 요청도 False이고 감사 로그도 남기지 않는다.
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_ELV_CONFIDENTIAL
        insert.return_value = None
        self.assertFalse(ps.request_document_access(1, "elvC", "계약 단가 확인 필요"))
        record.assert_not_called()

    def test_find_called_once_each(self, find_user, find_document, _pending, _approved, insert, record):
        # 중복 조회 제거 확인: 요청 한 번에 find_user·find_document는 각 1회만 호출된다.
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_ELV_CONFIDENTIAL
        insert.return_value = 7
        ps.request_document_access(1, "elvC", "계약 단가 확인 필요")
        self.assertEqual(find_user.call_count, 1)
        self.assertEqual(find_document.call_count, 1)


@mock.patch("app.permissions.services.permission_service.get_pending_doc_ids")
@mock.patch("app.permissions.services.permission_service.get_approved_doc_ids")
class FilterRequestableDocumentsTest(unittest.TestCase):
    """배치 판정: 후보 문서마다 DB를 다시 열지 않고 승인·대기 요청을 한 번만 조회하는지 확인."""

    # Chroma 메타데이터 모양의 후보 문서들
    _DOCS = [
        {"doc_id": "mvx-int", "company_id": "MVX", "access_level": "internal", "is_group_shared": False},    # 자사 내부 → 이미 봄
        {"doc_id": "pub", "company_id": "HRI", "access_level": "public", "is_group_shared": False},          # 공개 → 이미 봄
        {"doc_id": "elv-conf", "company_id": "ELV", "access_level": "confidential", "is_group_shared": False}, # 못 봄 → 요청 가능
        {"doc_id": "elv-pending", "company_id": "ELV", "access_level": "confidential", "is_group_shared": False}, # 대기 중 → 제외
        {"doc_id": "approved-1", "company_id": "ELV", "access_level": "confidential", "is_group_shared": False}, # 승인됨 → 이미 봄
    ]

    def test_only_requestable_and_batched(self, approved, pending):
        approved.return_value = ["approved-1"]
        pending.return_value = ["elv-pending"]

        out = ps.filter_requestable_documents(EMPLOYEE, self._DOCS)

        self.assertEqual([d["doc_id"] for d in out], ["elv-conf"])  # 요청 가능한 것만
        # 배치: 문서가 5개라도 승인·대기 조회는 각각 딱 한 번
        self.assertEqual(approved.call_count, 1)
        self.assertEqual(pending.call_count, 1)

    def test_super_admin_has_nothing_to_request(self, approved, pending):
        self.assertEqual(ps.filter_requestable_documents(SUPER_ADMIN, self._DOCS), [])
        approved.assert_not_called()  # 어드민은 조회조차 하지 않는다
        pending.assert_not_called()

    def test_own_company_confidential_not_exposed(self, approved, pending):
        """자사 기밀 문서는 못 봐도 요청 목록(제목)에 노출하지 않는다 (§2.3-6: 타사만)."""
        approved.return_value = []
        pending.return_value = []
        docs = [
            # 자사(MVX) 기밀 → 못 보지만 '자사'라 요청 목록에서 제외돼야 한다
            {"doc_id": "mvx-conf", "company_id": "MVX", "access_level": "confidential", "is_group_shared": False},
            # 타사(ELV) 기밀 → 요청 가능
            {"doc_id": "elv-conf", "company_id": "ELV", "access_level": "confidential", "is_group_shared": False},
        ]
        out = ps.filter_requestable_documents(EMPLOYEE, docs)
        self.assertEqual([d["doc_id"] for d in out], ["elv-conf"])  # 자사 기밀은 빠지고 타사만


if __name__ == "__main__":
    unittest.main()
