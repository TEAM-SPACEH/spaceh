"""M-01 login() 테스트. users 저장소·세션은 목으로 바꾸고, 해시는 core/security로 실제 생성한다."""

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


if __name__ == "__main__":
    unittest.main()
