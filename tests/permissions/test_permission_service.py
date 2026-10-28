"""M-03 문서 열람 권한 확인·요청 테스트. 저장소(DB 접근)는 목으로 바꿔 DB 없이 돈다."""

import unittest
from unittest import mock

from app.permissions.services import permission_service as ps

# 테스트용 사용자/문서 (users·documents 한 줄과 같은 모양)
EMPLOYEE = {"id": 1, "role": "employee", "company_id": "MVX"}
ADMIN = {"id": 2, "role": "company_admin", "company_id": "MVX"}
SUPER_ADMIN = {"id": 9, "role": "super_admin", "company_id": None}

DOC_MVX_INTERNAL = {"doc_id": "mvx1", "company_id": "MVX", "access_level": "internal", "is_group_shared": 0}
DOC_ELV_CONFIDENTIAL = {"doc_id": "elvC", "company_id": "ELV", "access_level": "confidential", "is_group_shared": 0}


class ValidateRequestReasonTest(unittest.TestCase):
    """사유 검증은 순수 함수라 DB 없이 바로 확인한다."""

    def test_blank_or_too_short_rejected(self):
        self.assertFalse(ps.validate_request_reason(""))
        self.assertFalse(ps.validate_request_reason("   "))
        self.assertFalse(ps.validate_request_reason("abc"))      # 3자
        self.assertFalse(ps.validate_request_reason("  ab  "))   # strip 후 2자

    def test_too_long_rejected(self):
        self.assertFalse(ps.validate_request_reason("가" * 501))

    def test_valid_accepted(self):
        self.assertTrue(ps.validate_request_reason("12345"))     # 5자(경계)
        self.assertTrue(ps.validate_request_reason("계약 단가 확인이 필요합니다"))
        self.assertTrue(ps.validate_request_reason("가" * 500))  # 500자(경계)


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


@mock.patch("app.permissions.services.permission_service.insert_access_request")
@mock.patch("app.permissions.services.permission_service.get_approved_doc_ids", return_value=[])
@mock.patch("app.permissions.services.permission_service.has_pending_request", return_value=False)
@mock.patch("app.permissions.services.permission_service.find_document")
@mock.patch("app.permissions.services.permission_service.find_user")
class RequestDocumentAccessTest(unittest.TestCase):
    def test_valid_request_saved_with_owner_company(self, find_user, find_document, _pending, _approved, insert):
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_ELV_CONFIDENTIAL
        insert.return_value = True

        self.assertTrue(ps.request_document_access(1, "elvC", "  계약 단가 확인 필요  "))

        # 소유 회사(owner_company_code)는 문서의 company_id, 사유는 strip되어 저장된다.
        insert.assert_called_once_with(1, "elvC", "ELV", "계약 단가 확인 필요")

    def test_invalid_reason_not_saved(self, find_user, find_document, _pending, _approved, insert):
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_ELV_CONFIDENTIAL
        self.assertFalse(ps.request_document_access(1, "elvC", "짧음"))  # 2자
        insert.assert_not_called()

    def test_cannot_request_not_saved(self, find_user, find_document, _pending, _approved, insert):
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_MVX_INTERNAL  # 이미 열람 가능 → 요청 불가
        self.assertFalse(ps.request_document_access(1, "mvx1", "보고 싶어요 정말로"))
        insert.assert_not_called()

    def test_duplicate_insert_returns_false(self, find_user, find_document, _pending, _approved, insert):
        # 저장 함수가 0건 저장(이미 대기 요청 존재)을 뜻하는 False를 주면 요청도 False.
        find_user.return_value = EMPLOYEE
        find_document.return_value = DOC_ELV_CONFIDENTIAL
        insert.return_value = False
        self.assertFalse(ps.request_document_access(1, "elvC", "계약 단가 확인 필요"))


if __name__ == "__main__":
    unittest.main()
