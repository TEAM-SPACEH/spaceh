"""M-01 login() 테스트. users 저장소·세션·감사 로그는 목으로 바꾸고, 해시는 core/security로 생성한다."""

import threading
import unittest
from unittest import mock

from app.auth.services import auth_service
from core.security import hash_password


def _user(**over) -> dict:
    """users 테이블 한 행(DictCursor)과 같은 모양의 테스트 사용자."""
    user = {
        "id": 1,
        "employee_no": "HRI-0001",
        "password_hash": hash_password("pw-1234"),
        "name": "김연구",
        "role": "employee",
        "company_id": "HRI",
        "is_active": 1,
        "company_name": "현대경제연구원",
    }
    user.update(over)
    return user


class LoginTest(unittest.TestCase):
    def setUp(self) -> None:
        # login이 감사 로그(A-04)를 부르므로, 테스트에서는 실제 DB를 건드리지 않게 목으로 막는다.
        patcher = mock.patch("app.auth.services.auth_service.record_audit_log")
        self.record = patcher.start()
        self.addCleanup(patcher.stop)

    @mock.patch("app.auth.services.auth_service.session.set_current_user")
    @mock.patch("app.auth.services.auth_service.user_repository.find_user_by_employee_no")
    def test_success_saves_role_and_company_without_hash(self, find, set_user) -> None:
        find.return_value = _user()

        self.assertTrue(auth_service.login("HRI-0001", "pw-1234"))

        saved = set_user.call_args.args[0]
        self.assertEqual(saved["id"], 1)
        self.assertEqual(saved["role"], "employee")
        self.assertEqual(saved["company_id"], "HRI")  # 소속이 세션에 들어간다
        self.assertEqual(saved["company_name"], "현대경제연구원")  # 헤더·사이드바 표시용
        self.assertNotIn("password_hash", saved)  # 해시는 세션에 넣지 않는다

    @mock.patch("app.auth.services.auth_service.session.set_current_user")
    @mock.patch("app.auth.services.auth_service.user_repository.find_user_by_employee_no")
    def test_wrong_password(self, find, set_user) -> None:
        find.return_value = _user()
        self.assertFalse(auth_service.login("HRI-0001", "wrong"))
        set_user.assert_not_called()

    @mock.patch("app.auth.services.auth_service.session.set_current_user")
    @mock.patch("app.auth.services.auth_service.user_repository.find_user_by_employee_no")
    def test_unknown_employee_no(self, find, set_user) -> None:
        find.return_value = None
        self.assertFalse(auth_service.login("NONE-0000", "pw-1234"))
        set_user.assert_not_called()

    @mock.patch("app.auth.services.auth_service.session.set_current_user")
    @mock.patch("app.auth.services.auth_service.user_repository.find_user_by_employee_no")
    def test_inactive_account_rejected(self, find, set_user) -> None:
        find.return_value = _user(is_active=0)
        self.assertFalse(auth_service.login("HRI-0001", "pw-1234"))
        set_user.assert_not_called()

    @mock.patch("app.auth.services.auth_service.session.set_current_user")
    @mock.patch("app.auth.services.auth_service.user_repository.find_user_by_employee_no")
    def test_empty_input_short_circuits(self, find, set_user) -> None:
        self.assertFalse(auth_service.login("", ""))
        find.assert_not_called()
        set_user.assert_not_called()


class LoginAuditTest(unittest.TestCase):
    """A-04 감사 로그: 성공 1 + 실패 3종의 기록 인자와, 기록 실패가 로그인 결과를 바꾸지 않는지 확인."""

    def setUp(self) -> None:
        patcher = mock.patch("app.auth.services.auth_service.record_audit_log")
        self.record = patcher.start()
        self.addCleanup(patcher.stop)
        s = mock.patch("app.auth.services.auth_service.session.set_current_user")
        self.set_user = s.start()
        self.addCleanup(s.stop)
        f = mock.patch("app.auth.services.auth_service.user_repository.find_user_by_employee_no")
        self.find = f.start()
        self.addCleanup(f.stop)

    def test_success_recorded(self) -> None:
        self.find.return_value = _user()
        self.assertTrue(auth_service.login("HRI-0001", "pw-1234"))
        # 성공: blocked=False, reason=None, user_id는 사용자 id, employee_no는 남기지 않음
        self.record.assert_called_once_with(1, "login", None, None, False, None, employee_no=None)

    def test_unknown_employee_no_recorded_with_safe_value(self) -> None:
        self.find.return_value = None
        self.assertFalse(auth_service.login("MVX-0001", "whatever"))
        # 없는 사번: user_id=None, 형식이 맞는 입력값은 남긴다
        self.record.assert_called_once_with(None, "login", None, None, True, "등록되지 않은 사원번호", employee_no="MVX-0001")

    def test_unknown_employee_no_bad_format_not_kept(self) -> None:
        self.find.return_value = None
        # 사번 칸에 비밀번호를 잘못 넣은 경우(형식 불일치) → 입력값을 남기지 않는다(None)
        self.assertFalse(auth_service.login("my-secret-pass!!", "x"))
        self.record.assert_called_once_with(None, "login", None, None, True, "등록되지 않은 사원번호", employee_no=None)

    def test_long_input_handled_without_error(self) -> None:
        self.find.return_value = None
        # 21자 이상 입력도 예외 없이 처리되고, 형식(1~20자)에 안 맞으니 employee_no는 None
        self.assertFalse(auth_service.login("A" * 21, "x"))
        self.record.assert_called_once_with(None, "login", None, None, True, "등록되지 않은 사원번호", employee_no=None)

    def test_inactive_recorded(self) -> None:
        self.find.return_value = _user(is_active=0)
        self.assertFalse(auth_service.login("HRI-0001", "pw-1234"))
        self.record.assert_called_once_with(1, "login", None, None, True, "비활성 계정", employee_no=None)

    def test_wrong_password_recorded(self) -> None:
        self.find.return_value = _user()
        self.assertFalse(auth_service.login("HRI-0001", "wrong"))
        self.record.assert_called_once_with(1, "login", None, None, True, "비밀번호 불일치", employee_no=None)

    def test_audit_failure_does_not_change_result(self) -> None:
        # 감사 로그 기록이 예외를 내도 로그인 결과는 그대로여야 한다.
        self.record.side_effect = RuntimeError("audit down")

        self.find.return_value = _user()
        self.assertTrue(auth_service.login("HRI-0001", "pw-1234"))  # 성공 유지

        self.find.return_value = _user()
        self.assertFalse(auth_service.login("HRI-0001", "wrong"))  # 실패 유지

    def test_audit_hang_does_not_block_login(self) -> None:
        # 감사 로그 기록(DB)이 응답하지 않아도, 제한 시간 뒤 로그인은 결과를 돌려줘야 한다.
        import time

        started = threading.Event()

        def _hang(*args, **kwargs):
            started.set()
            time.sleep(5)  # DB가 멈춘 상황을 흉내

        self.record.side_effect = _hang
        self.find.return_value = _user()

        with mock.patch.object(auth_service, "_AUDIT_TIMEOUT_SECONDS", 0.2):
            start = time.monotonic()
            result = auth_service.login("HRI-0001", "pw-1234")
            elapsed = time.monotonic() - start

        self.assertTrue(result)  # 기록이 멈춰도 로그인 성공은 반환된다
        self.assertTrue(started.is_set())  # 기록을 실제로 시도했다
        self.assertLess(elapsed, 2.0)  # 5초(멈춤)보다 훨씬 빨리, 제한 시간(0.2초)쯤에 돌아온다


if __name__ == "__main__":
    unittest.main()
