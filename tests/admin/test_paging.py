"""관리자 목록 공통 페이징 값 보정 테스트.

실행: python -m unittest tests.admin.test_paging
"""

import unittest

from app.admin.paging import as_int, clamp


class AsIntTest(unittest.TestCase):
    def test_converts_numbers_and_numeric_text(self):
        """숫자와 숫자 글자는 정수로 바꾼다."""
        self.assertEqual(as_int("7", 1), 7)
        self.assertEqual(as_int(3.9, 1), 3)

    def test_falls_back_to_default(self):
        """바꿀 수 없는 값(None·글자·빈 문자열)은 기본값이다."""
        for bad in (None, "abc", "", [], {}):
            with self.subTest(value=bad):
                self.assertEqual(as_int(bad, 5), 5)


class ClampTest(unittest.TestCase):
    def test_keeps_values_inside_range(self):
        """범위 안의 값은 그대로다."""
        self.assertEqual(clamp(20, 1, 100), 20)
        self.assertEqual(clamp("20", 1, 100), 20)

    def test_limits_values_outside_range(self):
        """범위를 벗어난 값은 가장 가까운 끝으로 맞춘다 (0·음수는 low, 너무 큰 수는 high)."""
        self.assertEqual(clamp(0, 1, 100), 1)
        self.assertEqual(clamp(-5, 1, 100), 1)
        self.assertEqual(clamp(100000, 1, 100), 100)

    def test_non_numeric_becomes_low(self):
        """숫자가 아니면 low 로 본다."""
        self.assertEqual(clamp("abc", 1, 100), 1)
        self.assertEqual(clamp(None, 3, 100), 3)


if __name__ == "__main__":
    unittest.main()
