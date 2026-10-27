import unittest

from app.ingestion.preprocessing.masking import mask_sensitive_data


def _mask(text: str) -> tuple[str, dict[str, int]]:
    blocks, counts = mask_sensitive_data([{"text": text}])
    return blocks[0]["text"], counts


class MaskSensitiveDataTest(unittest.TestCase):
    def test_masks_rrn_phone_email(self):
        text, counts = _mask("900101-1234567 / 010-1234-5678 / a.b@x.co.kr")
        self.assertEqual(text, "[마스킹: 주민번호] / [마스킹: 연락처] / [마스킹: 이메일]")
        self.assertEqual(counts, {"주민번호": 1, "연락처": 1, "이메일": 1, "계좌": 0})

    def test_masks_international_phone(self):
        for number in ("+8210-1234-5678", "+82 10-1234-5678", "+82-10-1234-5678", "+82 010-1234-5678"):
            with self.subTest(number=number):
                text, counts = _mask(f"연락처 {number}")
                self.assertEqual(text, "연락처 [마스킹: 연락처]")
                self.assertEqual(counts["연락처"], 1)

    def test_corporate_registration_number_is_kept(self):
        for original in ("법인등록번호 110111-1234567", "법인등록번호: 110111-1234567", "법인번호 110111-1234567"):
            with self.subTest(original=original):
                text, counts = _mask(original)
                self.assertEqual(text, original)
                self.assertEqual(counts["주민번호"], 0)

    def test_rrn_still_masked_on_corporate_line(self):
        text, counts = _mask("법인등록번호 110111-1234567, 대표 900101-1234567")
        self.assertEqual(text, "법인등록번호 110111-1234567, 대표 [마스킹: 주민번호]")
        self.assertEqual(counts["주민번호"], 1)

    def test_corporate_number_under_table_header_is_kept(self):
        header = "회사명 | 법인등록번호 | 대표자 주민등록번호"
        row = "A사 | 110111-1234567 | 900101-1234567"
        text, counts = _mask(f"{header}\n{row}")
        self.assertEqual(text, f"{header}\nA사 | 110111-1234567 | [마스킹: 주민번호]")
        self.assertEqual(counts["주민번호"], 1)

    def test_corporate_number_under_whitespace_separated_header(self):
        original = "회사명  법인등록번호\nA사  110111-1234567\nB사  120111-7654321"
        text, counts = _mask(original)
        self.assertEqual(text, original)
        self.assertEqual(counts["주민번호"], 0)

    def test_header_only_cell_lists_corporate_numbers_vertically(self):
        original = "법인등록번호\n110111-1234567\n120111-7654321"
        text, counts = _mask(original)
        self.assertEqual(text, original)
        self.assertEqual(counts["주민번호"], 0)

    def test_rrn_column_masked_when_header_is_rrn(self):
        text, counts = _mask("성명 | 주민등록번호\n홍길동 | 900101-1234567")
        self.assertEqual(text, "성명 | 주민등록번호\n홍길동 | [마스킹: 주민번호]")
        self.assertEqual(counts["주민번호"], 1)

    def test_new_rrn_header_replaces_corporate_header(self):
        text, _ = _mask("법인등록번호\n110111-1234567\n성명 | 주민등록번호\n홍길동 | 900101-1234567")
        self.assertEqual(
            text, "법인등록번호\n110111-1234567\n성명 | 주민등록번호\n홍길동 | [마스킹: 주민번호]"
        )

    def test_corporate_header_carries_over_table_blocks_only(self):
        table = {"text": "회사명 | 법인등록번호", "block_type": "table"}
        next_table = {"text": "A사 | 110111-1234567", "block_type": "table"}
        masked, _ = mask_sensitive_data([table, next_table])
        self.assertEqual(masked[1]["text"], "A사 | 110111-1234567")

        body = {"text": "A사 | 110111-1234567", "block_type": "text"}
        masked, counts = mask_sensitive_data([table, body])
        self.assertEqual(masked[1]["text"], "A사 | [마스킹: 주민번호]")
        self.assertEqual(counts["주민번호"], 1)

    def test_corporate_number_not_masked_as_account_on_keyword_line(self):
        original = "법인등록번호 110111-0012345 (국민은행 거래)"
        text, counts = _mask(original)
        self.assertEqual(text, original)
        self.assertEqual(sum(counts.values()), 0)

    def test_account_masked_only_with_keyword_on_same_line(self):
        text, counts = _mask("입금 계좌 110-123-456789\n참고 110-123-456789")
        self.assertEqual(text, "입금 계좌 [마스킹: 계좌]\n참고 110-123-456789")
        self.assertEqual(counts["계좌"], 1)

    def test_company_numbers_are_kept_even_on_keyword_line(self):
        original = "국민은행 대표 02-1234-5678, 1588-1234, 사업자 123-45-67890, 2024-03-12 입금"
        text, counts = _mask(original)
        self.assertEqual(text, original)
        self.assertEqual(sum(counts.values()), 0)

    def test_receipt_number_is_kept(self):
        original = "접수번호 20240312000123"
        self.assertEqual(_mask(original)[0], original)

    def test_input_not_mutated_and_other_keys_kept(self):
        blocks = [{"text": "010-1234-5678", "page": 3}, {"text": ""}]
        masked, _ = mask_sensitive_data(blocks)
        self.assertEqual(blocks[0]["text"], "010-1234-5678")
        self.assertEqual(masked[0], {"text": "[마스킹: 연락처]", "page": 3})
        self.assertEqual(masked[1], {"text": ""})


if __name__ == "__main__":
    unittest.main()
