"""M-02 user_service 테스트. 저장소·세션은 목으로 바꿔 DB 없이 돈다."""

import unittest
from unittest import mock

from app.users.services import user_service
from core.security import hash_password


class ValidatePasswordTest(unittest.TestCase):
    def test_length_boundaries(self):
        self.assertFalse(user_service.validate_password("abc1234"))   # 7자
        self.assertTrue(user_service.validate_password("abcd1234"))   # 8자
        self.assertTrue(user_service.validate_password("a" * 18 + "12"))   # 20자
        self.assertFalse(user_service.validate_password("a" * 19 + "12"))  # 21자

    def test_format_rules(self):
        self.assertFalse(user_service.validate_password("abcdefgh"))   # 숫자 없음
        self.assertFalse(user_service.validate_password("12345678"))   # 영문 없음
        self.assertFalse(user_service.validate_password("abcd 123"))   # 공백
        self.assertFalse(user_service.validate_password("가나다12345"))  # ASCII 영문 없음
        self.assertFalse(user_service.validate_password(""))           # 빈값


@mock.patch("app.users.services.user_service.get_current_user_id")
@mock.patch("app.users.services.user_service.user_repository")
class GetUserInfoTest(unittest.TestCase):
    _ROW = {
        "id": 1, "employee_no": "MVX-0001", "name": "이물류",
        "role": "employee", "company_id": "MVX", "company_name": "현대무벡스",
    }

    def test_self_returns_profile(self, repo, current_id):
        current_id.return_value = 1
        repo.find_profile_by_id.return_value = dict(self._ROW)
        info = user_service.get_user_info(1)
        self.assertEqual(info["employee_no"], "MVX-0001")
        self.assertEqual(info["company_name"], "현대무벡스")
        self.assertIsNone(info["email"])

    def test_other_user_denied(self, repo, current_id):
        current_id.return_value = 2  # 로그인한 사람은 2번인데 1번을 요청
        self.assertIsNone(user_service.get_user_info(1))
        repo.find_profile_by_id.assert_not_called()

    def test_not_found(self, repo, current_id):
        current_id.return_value = 1
        repo.find_profile_by_id.return_value = None
        self.assertIsNone(user_service.get_user_info(1))


@mock.patch("app.users.services.user_service.user_repository")
class VerifyCurrentPasswordTest(unittest.TestCase):
    def test_match(self, repo):
        repo.find_password_hash_by_id.return_value = hash_password("pw-123456")
        self.assertTrue(user_service.verify_current_password(1, "pw-123456"))

    def test_mismatch(self, repo):
        repo.find_password_hash_by_id.return_value = hash_password("pw-123456")
        self.assertFalse(user_service.verify_current_password(1, "nope"))

    def test_no_user(self, repo):
        repo.find_password_hash_by_id.return_value = None
        self.assertFalse(user_service.verify_current_password(1, "x"))


@mock.patch("app.users.services.user_service.get_current_user_id")
@mock.patch("app.users.services.user_service.user_repository")
class ChangePasswordTest(unittest.TestCase):
    def setUp(self):
        self.stored = hash_password("old-pass-1")

    def test_success(self, repo, current_id):
        current_id.return_value = 1
        repo.find_password_hash_by_id.return_value = self.stored
        repo.update_password.return_value = 1
        self.assertTrue(user_service.change_password(1, "old-pass-1", "new-pass-99"))
        repo.update_password.assert_called_once()

    def test_other_user_denied(self, repo, current_id):
        current_id.return_value = 2  # 남의 user_id 변경 시도
        self.assertFalse(user_service.change_password(1, "old-pass-1", "new-pass-99"))
        repo.find_password_hash_by_id.assert_not_called()
        repo.update_password.assert_not_called()

    def test_wrong_current_password(self, repo, current_id):
        current_id.return_value = 1
        repo.find_password_hash_by_id.return_value = self.stored
        self.assertFalse(user_service.change_password(1, "wrong", "new-pass-99"))
        repo.update_password.assert_not_called()

    def test_invalid_new_password(self, repo, current_id):
        current_id.return_value = 1
        repo.find_password_hash_by_id.return_value = self.stored
        self.assertFalse(user_service.change_password(1, "old-pass-1", "short"))
        repo.update_password.assert_not_called()


if __name__ == "__main__":
    unittest.main()
