import copy
import unittest

from app.ingestion.preprocessing.masking import mask_sensitive_data


def _mask(text: str) -> tuple[str, dict[str, int]]:
    blocks, counts = mask_sensitive_data([{"text": text}])
    return blocks[0]["text"], counts


class MaskSensitiveDataTest(unittest.TestCase):
    def test_masks_phone_and_email(self):
        text, counts = _mask("010-1234-5678 / a.b@x.co.kr")
        self.assertEqual(text, "[마스킹: 연락처] / [마스킹: 이메일]")
        self.assertEqual(counts, {"연락처": 1, "이메일": 1, "계좌": 0})

    def test_masks_international_phone(self):
        for number in ("+8210-1234-5678", "+82 10-1234-5678", "+82-10-1234-5678", "+82 010-1234-5678"):
            with self.subTest(number=number):
                text, counts = _mask(f"연락처 {number}")
                self.assertEqual(text, "연락처 [마스킹: 연락처]")
                self.assertEqual(counts["연락처"], 1)

    def test_resident_registration_number_is_not_masked(self):
        # 주민등록번호는 서비스에서 쓰지 않기로 해서 마스킹 대상이 아니다.
        original = "대표 900101-1234567, 외국인 900101-5234567"
        text, counts = _mask(original)
        self.assertEqual(text, original)
        self.assertEqual(sum(counts.values()), 0)
        self.assertNotIn("주민번호", counts)

    def test_corporate_number_not_masked_as_account_after_label(self):
        for label in ("법인등록번호 ", "법인등록번호: ", "법인번호 "):
            with self.subTest(label=label):
                original = f"{label}110111-1234567 (국민은행 거래)"
                text, counts = _mask(original)
                self.assertEqual(text, original)
                self.assertEqual(sum(counts.values()), 0)

    def test_account_still_masked_on_corporate_line(self):
        text, counts = _mask("법인등록번호 110111-1234567, 국민은행 계좌 110-123-456789")
        self.assertEqual(text, "법인등록번호 110111-1234567, 국민은행 계좌 [마스킹: 계좌]")
        self.assertEqual(counts["계좌"], 1)

    def test_corporate_number_under_table_header_is_kept(self):
        header = "회사명 | 법인등록번호 | 거래은행"
        row = "A사 | 110111-1234567 | 국민은행 110-123-456789"
        text, counts = _mask(f"{header}\n{row}")
        self.assertEqual(
            text, f"{header}\nA사 | 110111-1234567 | 국민은행 [마스킹: 계좌]"
        )
        self.assertEqual(counts["계좌"], 1)

    def test_corporate_number_under_whitespace_separated_header(self):
        original = "회사명  법인등록번호  거래은행\nA사  110111-1234567  국민은행\nB사  120111-7654321  우리은행"
        text, counts = _mask(original)
        self.assertEqual(text, original)
        self.assertEqual(counts["계좌"], 0)

    def test_header_only_cell_lists_corporate_numbers_vertically(self):
        original = "법인등록번호\n110111-1234567 (국민은행)\n120111-7654321 (우리은행)"
        text, counts = _mask(original)
        self.assertEqual(text, original)
        self.assertEqual(counts["계좌"], 0)

    def test_sentence_mentioning_label_is_not_a_header(self):
        sentence = "법인등록번호는 별도 표에 기재한다."
        text, counts = _mask(f"{sentence}\n국민은행 110111-1234567")
        self.assertEqual(text, f"{sentence}\n국민은행 [마스킹: 계좌]")
        self.assertEqual(counts["계좌"], 1)

    def test_sentence_after_corporate_header_releases_it(self):
        text, counts = _mask(
            "법인등록번호\n110111-1234567 (국민은행)\n"
            "법인등록번호는 별도 표에 기재한다.\n국민은행 110111-1234567"
        )
        self.assertEqual(
            text,
            "법인등록번호\n110111-1234567 (국민은행)\n"
            "법인등록번호는 별도 표에 기재한다.\n국민은행 [마스킹: 계좌]",
        )
        self.assertEqual(counts["계좌"], 1)

    def test_corporate_header_carries_over_table_blocks_only(self):
        table = {"text": "회사명 | 법인등록번호 | 거래은행", "block_type": "table"}
        next_table = {"text": "A사 | 110111-1234567 | 국민은행", "block_type": "table"}
        masked, _ = mask_sensitive_data([table, next_table])
        self.assertEqual(masked[1]["text"], "A사 | 110111-1234567 | 국민은행")

        body = {"text": "A사 | 110111-1234567 | 국민은행", "block_type": "text"}
        masked, counts = mask_sensitive_data([table, body])
        self.assertEqual(masked[1]["text"], "A사 | [마스킹: 계좌] | 국민은행")
        self.assertEqual(counts["계좌"], 1)

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

    def test_sections_are_masked_without_duplicate_counts_or_input_changes(self):
        """제목의 개인정보와 복사된 절 이름을 모두 치환하되 원문 건수만 집계한다."""
        title = "문의 010-1234-5678 test@example.com"
        blocks = [{"text": title, "section": title, "block_type": "title", "page": 1},
                  {"text": "본문", "section": title, "block_type": "text", "page": 2},
                  {"text": "표 내용", "section": title, "block_type": "table", "page": 3}]
        before = copy.deepcopy(blocks)
        masked, counts = mask_sensitive_data(blocks)
        for item in masked:
            self.assertEqual(item["section"], "문의 [마스킹: 연락처] [마스킹: 이메일]")
        self.assertEqual(counts, {"연락처": 1, "이메일": 1, "계좌": 0})
        self.assertEqual(blocks, before)
        self.assertEqual([b["page"] for b in masked], [1, 2, 3])

    def test_section_whitespace_is_normalized_without_joining_lines(self):
        """여러 공백·탭 전화번호를 치환하고 계좌 키워드의 줄 경계는 보존한다."""
        blocks = [{"text": "본문", "section":
                   " 문의 010  1234\t\t5678\r\n입금\r\n110-123-456789 "}]
        before = copy.deepcopy(blocks)
        masked, counts = mask_sensitive_data(blocks)
        self.assertEqual(masked[0]["section"],
                         "문의 [마스킹: 연락처]\n입금\n110-123-456789")
        self.assertEqual(sum(counts.values()), 0)
        self.assertEqual(blocks, before)

    def test_section_does_not_change_body_table_header_state(self):
        """절 이름의 법인등록번호 라벨을 본문 표의 머리글로 오인하지 않는다."""
        blocks = [{"text": "표 안내", "section": "법인등록번호", "block_type": "table"},
                  {"text": "국민은행 110-123-456789", "section": "법인등록번호",
                   "block_type": "table"}]
        masked, counts = mask_sensitive_data(blocks)
        self.assertEqual(masked[1]["text"], "국민은행 [마스킹: 계좌]")
        self.assertEqual(counts["계좌"], 1)

    def test_body_table_header_state_does_not_exempt_section_account(self):
        """본문의 법인번호 열 상태를 절 이름에 적용해 계좌 마스킹을 놓치지 않는다."""
        blocks = [{"text": "법인등록번호", "block_type": "table", "section": ""},
                  {"text": "110111-1234567 (국민은행)", "block_type": "table",
                   "section": "입금 계좌 110-123-456789"}]
        masked, counts = mask_sensitive_data(blocks)
        self.assertEqual(masked[1]["text"], blocks[1]["text"])
        self.assertEqual(masked[1]["section"], "입금 계좌 [마스킹: 계좌]")
        self.assertEqual(sum(counts.values()), 0)

    def test_input_not_mutated_and_other_keys_kept(self):
        blocks = [{"text": "010-1234-5678", "page": 3}, {"text": ""}]
        masked, _ = mask_sensitive_data(blocks)
        self.assertEqual(blocks[0]["text"], "010-1234-5678")
        self.assertEqual(masked[0], {"text": "[마스킹: 연락처]", "page": 3})
        self.assertEqual(masked[1], {"text": ""})


if __name__ == "__main__":
    unittest.main()
