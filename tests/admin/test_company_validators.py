"""A-07 계열사 입력값 검증 테스트.

실행: python -m unittest tests.admin.test_company_validators
"""

import unittest

from app.admin import validators


class CompanyNameTest(unittest.TestCase):
    def test_strips_spaces(self):
        """앞뒤 공백은 떼고 돌려준다."""
        self.assertEqual(validators.validate_company_name("  현대투자파트너스 "), "현대투자파트너스")

    def test_rejects_empty_and_too_long(self):
        """비었거나 공백뿐이거나 100자를 넘으면 ValueError 다."""
        for bad in (None, "", "   "):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                validators.validate_company_name(bad)
        with self.assertRaises(ValueError):
            validators.validate_company_name("가" * 101)
        self.assertEqual(len(validators.validate_company_name("가" * 100)), 100)


class CompanyCodeTest(unittest.TestCase):
    def test_accepts_2_to_5_letters_and_uppercases(self):
        """영문 2–5자는 대문자로 바꿔 받는다 (소문자 입력 허용)."""
        for given, expected in (("HIP", "HIP"), (" hip ", "HIP"), ("Mv", "MV"), ("abcde", "ABCDE")):
            with self.subTest(value=given):
                self.assertEqual(validators.validate_company_code(given), expected)

    def test_rejects_wrong_length_digits_symbols_and_non_ascii(self):
        """길이가 맞지 않거나, 숫자·기호·한글·전각 영문이 섞이면 ValueError 다."""
        for bad in (None, "", "A", "ABCDEF", "H1P", "H-P", "H P", "한글", "ＡＢ", "ıı"):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                validators.validate_company_code(bad)


class DartCodeTest(unittest.TestCase):
    def test_empty_means_not_entered(self):
        """비어 있으면 입력 전(None)이다."""
        for empty in (None, "", "   "):
            self.assertIsNone(validators.validate_dart_code(empty))

    def test_accepts_eight_digits(self):
        """숫자 8자리는 앞의 0을 포함해 그대로 받는다."""
        self.assertEqual(validators.validate_dart_code(" 00126380 "), "00126380")

    def test_rejects_other_formats(self):
        """7자리·9자리·문자·전각 숫자는 ValueError 다."""
        for bad in ("1234567", "123456789", "abcdefgh", "1234 678", "１２３４５６７８"):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                validators.validate_dart_code(bad)


if __name__ == "__main__":
    unittest.main()
