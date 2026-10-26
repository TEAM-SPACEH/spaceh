import unittest

from core.security import hash_password, verify_password


class PasswordHashTest(unittest.TestCase):
    def test_correct_password_verifies(self):
        stored = hash_password("seed-pass-1")
        self.assertTrue(verify_password("seed-pass-1", stored))

    def test_wrong_password_fails(self):
        stored = hash_password("seed-pass-1")
        self.assertFalse(verify_password("seed-pass-2", stored))

    def test_same_password_gets_different_salt(self):
        self.assertNotEqual(hash_password("same"), hash_password("same"))

    def test_hash_fits_users_password_column(self):
        self.assertLessEqual(len(hash_password("x" * 64)), 100)

    def test_malformed_stored_value_fails(self):
        self.assertFalse(verify_password("anything", "plain-text"))


if __name__ == "__main__":
    unittest.main()
