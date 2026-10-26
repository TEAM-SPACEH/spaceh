from app.ingestion.preprocessing.masking import mask_sensitive_data


def _mask(text: str) -> tuple[str, dict[str, int]]:
    blocks, counts = mask_sensitive_data([{"text": text}])
    return blocks[0]["text"], counts


def test_masks_rrn_phone_email():
    text, counts = _mask("900101-1234567 / 010-1234-5678 / a.b@x.co.kr")
    assert text == "[마스킹: 주민번호] / [마스킹: 연락처] / [마스킹: 이메일]"
    assert counts == {"주민번호": 1, "연락처": 1, "이메일": 1, "계좌": 0}


def test_account_masked_only_with_keyword_on_same_line():
    text, counts = _mask("입금 계좌 110-123-456789\n참고 110-123-456789")
    assert text == "입금 계좌 [마스킹: 계좌]\n참고 110-123-456789"
    assert counts["계좌"] == 1


def test_company_numbers_are_kept_even_on_keyword_line():
    original = "국민은행 대표 02-1234-5678, 1588-1234, 사업자 123-45-67890, 2024-03-12 입금"
    text, counts = _mask(original)
    assert text == original
    assert sum(counts.values()) == 0


def test_receipt_number_is_kept():
    original = "접수번호 20240312000123"
    assert _mask(original)[0] == original


def test_input_not_mutated_and_other_keys_kept():
    blocks = [{"text": "010-1234-5678", "page": 3}, {"text": ""}]
    masked, _ = mask_sensitive_data(blocks)
    assert blocks[0]["text"] == "010-1234-5678"
    assert masked[0] == {"text": "[마스킹: 연락처]", "page": 3}
    assert masked[1] == {"text": ""}
