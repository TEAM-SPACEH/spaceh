"""company_service(A-07 계열사) 테스트. 저장소는 mock 으로 바꿔 서비스 규칙만 확인한다.

실행: python -m unittest tests.admin.test_company_service
확인 대상: 최종 어드민만 가능, 입력 검증, 중복 문구 변환, 등록 값 정규화, 선택지.
"""

import unittest
from unittest.mock import patch

from app.admin.repositories.company_repository import DuplicateCompanyError
from app.admin.services import company_service

REPO = "app.admin.services.company_service.company_repository"
AUDIT = "app.admin.services.company_service.record_audit_log"

SUPER = {"id": 1, "role": "super_admin", "company_id": None}
MVX_ADMIN = {"id": 2, "role": "company_admin", "company_id": "MVX"}
EMPLOYEE = {"id": 3, "role": "employee", "company_id": "MVX"}
NOT_SUPER = (MVX_ADMIN, EMPLOYEE, None, {})


def _row(**overrides):
    row = {
        "company_id": "MVX",
        "name": "현대무벡스",
        "dart_code": None,
        "is_active": 1,
        "default_share_enabled": 0,
        "doc_total": 10,
        "doc_public": 1,
        "doc_internal": 6,
        "doc_confidential": 3,
        "user_count": 2,
    }
    row.update(overrides)
    return row


class _AuditMixin:
    """모든 테스트에서 감사 로그 기록을 가짜로 바꿔, 실제 DB 에 쓰지 않고 호출 내용만 확인한다."""

    def setUp(self):
        patcher = patch(AUDIT)
        self.audit = patcher.start()
        self.addCleanup(patcher.stop)


@patch(REPO)
class GetCompaniesTest(_AuditMixin, unittest.TestCase):
    def test_super_admin_gets_companies_with_bool_flags(self, repo):
        """최종 어드민은 목록을 받고, 0/1 값은 bool 로 바뀐다."""
        repo.list_companies.return_value = [_row(is_active=1, default_share_enabled=1)]

        got = company_service.get_companies(SUPER)

        self.assertIs(got[0]["is_active"], True)
        self.assertIs(got[0]["default_share_enabled"], True)
        self.assertEqual(got[0]["doc_internal"], 6)

    def test_others_are_denied_before_db(self, repo):
        """최종 어드민이 아니면(계열사 관리자·사원·로그인 전) PermissionError 이고 DB 를 읽지 않는다."""
        for user in NOT_SUPER:
            with self.subTest(user=user), self.assertRaises(PermissionError):
                company_service.get_companies(user)
        repo.list_companies.assert_not_called()

    def test_company_options_need_no_permission(self, repo):
        """필터 선택지는 로그인한 누구나 쓰므로 권한을 묻지 않고 저장소 값을 그대로 준다."""
        repo.list_active_company_options.return_value = [{"id": "MVX", "name": "현대무벡스"}]
        self.assertEqual(company_service.get_company_options(), [{"id": "MVX", "name": "현대무벡스"}])


@patch(REPO)
class CreateCompanyTest(_AuditMixin, unittest.TestCase):
    def test_creates_with_normalized_values(self, repo):
        """공백 제거·대문자 변환·빈 DART 는 None 으로 저장소에 넘기고, 결과 모양이 맞다."""
        got = company_service.create_company(SUPER, "  현대투자파트너스 ", " hip ", "", True)

        repo.insert_company.assert_called_once_with("HIP", "현대투자파트너스", None, True)
        self.assertEqual(
            got,
            {
                "company_id": "HIP",
                "name": "현대투자파트너스",
                "dart_code": None,
                "default_share_enabled": True,
                "status": "success",
                "message": "계열사가 추가되었습니다.",
            },
        )

    def test_default_share_is_off_by_default(self, repo):
        """기본 그룹사 공유는 기본 OFF 다 (명세서: 기본값 OFF)."""
        company_service.create_company(SUPER, "회사", "AB")
        self.assertEqual(repo.insert_company.call_args.args, ("AB", "회사", None, False))

    def test_denied_for_non_super_admin_and_nothing_written(self, repo):
        """최종 어드민이 아니면 입력이 올바라도 거부되고 아무것도 쓰지 않는다."""
        for user in NOT_SUPER:
            with self.subTest(user=user), self.assertRaises(PermissionError):
                company_service.create_company(user, "회사", "AB")
        repo.insert_company.assert_not_called()

    def test_permission_is_checked_before_validation(self, repo):
        """권한 없는 사용자에게는 입력 형식 오류보다 권한 오류가 먼저다 (입력 규칙 탐색 방지)."""
        with self.assertRaises(PermissionError):
            company_service.create_company(EMPLOYEE, "", "")

    def test_invalid_input_is_rejected_before_db(self, repo):
        """형식이 틀리면 ValueError 이고 DB 에 쓰지 않는다."""
        for kwargs in (
            {"name": "", "company_id": "AB"},
            {"name": "회사", "company_id": "A"},
            {"name": "회사", "company_id": "AB", "dart_code": "123"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                company_service.create_company(SUPER, **kwargs)
        repo.insert_company.assert_not_called()

    def test_duplicates_become_friendly_messages_without_input(self, repo):
        """겹친 값의 종류별 안내 문구가 나오고, 사용자가 입력한 값은 문구에 들어가지 않는다."""
        for kind, message in (
            ("company_id", "이미 사용 중인 회사 코드입니다."),
            ("name", "이미 등록된 회사명입니다."),
            ("dart_code", "이미 다른 계열사에 등록된 DART 고유번호입니다."),
        ):
            repo.insert_company.side_effect = DuplicateCompanyError(kind)
            with self.subTest(kind=kind), self.assertRaises(ValueError) as ctx:
                company_service.create_company(SUPER, "비밀회사명", "SEC", "12345678")
            self.assertEqual(str(ctx.exception), message)
            self.assertNotIn("비밀회사명", str(ctx.exception))


@patch(REPO)
class SetDartCodeTest(_AuditMixin, unittest.TestCase):
    def test_saves_and_clears(self, repo):
        """8자리를 저장하고, 빈 값은 None 으로 비운다."""
        repo.get_company.return_value = _row()

        got = company_service.set_dart_code(SUPER, "MVX", " 00126380 ")
        repo.update_dart_code.assert_called_with("MVX", "00126380")
        self.assertEqual((got["dart_code"], got["status"]), ("00126380", "success"))

        company_service.set_dart_code(SUPER, "MVX", "")
        repo.update_dart_code.assert_called_with("MVX", None)

    def test_denied_invalid_missing_and_duplicate(self, repo):
        """권한·형식·없는 회사·중복을 각각 PermissionError·ValueError·LookupError·ValueError 로 알린다."""
        with self.assertRaises(PermissionError):
            company_service.set_dart_code(MVX_ADMIN, "MVX", "00126380")
        with self.assertRaises(ValueError):
            company_service.set_dart_code(SUPER, "MVX", "123")

        repo.get_company.return_value = None
        with self.assertRaises(LookupError):
            company_service.set_dart_code(SUPER, "NOPE", "00126380")

        repo.get_company.return_value = _row()
        repo.update_dart_code.side_effect = DuplicateCompanyError("dart_code")
        with self.assertRaisesRegex(ValueError, "DART 고유번호"):
            company_service.set_dart_code(SUPER, "MVX", "00126380")


@patch(REPO)
class AuditLogTest(_AuditMixin, unittest.TestCase):
    """등록·수정과 막힌 시도가 감사 로그에 남는다."""

    def test_create_is_recorded_with_details(self, repo):
        """등록하면 company_create 로 기록하고, 회사 코드와 입력 내용(이름·DART·기본 공유)을 남긴다."""
        company_service.create_company(SUPER, "현대투자파트너스", "hip", "00126380", True)

        args, kwargs = self.audit.call_args
        # user_id, action_type, target_id, ip_address, blocked, block_reason
        self.assertEqual(args, (SUPER["id"], "company_create", "HIP", None, False, None))
        self.assertEqual(kwargs["target_type"], "company")
        self.assertEqual(
            kwargs["context_detail"],
            {"name": "현대투자파트너스", "dart_code": "00126380", "default_share_enabled": True},
        )

    def test_dart_change_is_recorded_with_previous_value(self, repo):
        """DART 고유번호를 바꾸면 company_update 로 기록하고 이전 값을 함께 남긴다."""
        repo.get_company.return_value = _row(dart_code="00000001")

        company_service.set_dart_code(SUPER, "MVX", "00126380")

        args, kwargs = self.audit.call_args
        self.assertEqual(args[:3], (SUPER["id"], "company_update", "MVX"))
        self.assertEqual(kwargs["context_detail"], {"dart_code": "00126380", "previous": "00000001"})

    def test_blocked_attempts_are_recorded_as_blocked(self, repo):
        """최종 어드민이 아닌 사용자의 등록·수정 시도는 blocked=True 로 기록되고 DB 는 바뀌지 않는다."""
        for call, action in (
            (lambda u: company_service.create_company(u, "회사", "AB"), "company_create"),
            (lambda u: company_service.set_dart_code(u, "MVX", "00126380"), "company_update"),
        ):
            for user in (MVX_ADMIN, EMPLOYEE):
                with self.subTest(action=action, role=user["role"]), self.assertRaises(PermissionError):
                    call(user)
                args = self.audit.call_args.args
                self.assertEqual((args[0], args[1], args[2], args[4]), (user["id"], action, None, True))
                self.assertIn("최종 어드민", args[5])
        repo.insert_company.assert_not_called()
        repo.update_dart_code.assert_not_called()

    def test_anonymous_attempt_is_recorded_without_user(self, repo):
        """로그인 전(None) 시도도 사용자 없이 막힌 기록이 남는다."""
        with self.assertRaises(PermissionError):
            company_service.create_company(None, "회사", "AB")
        self.assertIsNone(self.audit.call_args.args[0])
        self.assertTrue(self.audit.call_args.args[4])

    def test_failures_are_not_recorded_as_success(self, repo):
        """형식 오류·중복·없는 회사는 저장되지 않았으므로 성공 기록이 남지 않는다."""
        with self.assertRaises(ValueError):
            company_service.create_company(SUPER, "", "AB")
        repo.insert_company.side_effect = DuplicateCompanyError("name")
        with self.assertRaises(ValueError):
            company_service.create_company(SUPER, "회사", "AB")
        repo.get_company.return_value = None
        with self.assertRaises(LookupError):
            company_service.set_dart_code(SUPER, "NOPE", "00126380")
        self.audit.assert_not_called()

    def test_audit_failure_does_not_hide_success(self, repo):
        """감사 로그 기록이 실패해도 이미 저장된 등록에는 성공을 돌려주고, 실패는 로그로 남는다."""
        self.audit.side_effect = RuntimeError("db down")

        with self.assertLogs(company_service.logger, level="ERROR"):
            result = company_service.create_company(SUPER, "회사", "AB")

        self.assertEqual(result["status"], "success")


if __name__ == "__main__":
    unittest.main()
