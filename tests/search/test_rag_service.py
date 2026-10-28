"""S-07 generate_followup_questions 테스트. LLM 호출(_generate_followups_with_openai)은 목으로 바꾼다."""

import unittest
from unittest import mock

from app.search.services import rag_service as rag

_GEN = "app.search.services.rag_service._generate_followups_with_openai"


def _chunk(text: str = "3분기 스마트팩토리 수주 1,284억 원") -> dict:
    """검색 결과 청크 한 개(prepare_context가 읽는 모양)."""
    return {
        "text": text,
        "metadata": {
            "company_name": "현대무벡스", "file_name": "q3.pdf",
            "page": 3, "doc_id": "MVX-report-1", "chunk_id": "MVX-report-1#0000",
        },
    }


class ParseFollowupsTest(unittest.TestCase):
    def test_strips_numbering_and_bullets(self):
        raw = "1. 수주 전망은?\n- 위험 요인은?\n• 경쟁사 비교는?"
        self.assertEqual(rag._parse_followups(raw), ["수주 전망은?", "위험 요인은?", "경쟁사 비교는?"])

    def test_preamble_without_question_mark_dropped(self):
        # "다음은 추천 질문입니다:" 같은 머리말이 질문 자리를 차지하지 않아야 한다.
        raw = "다음은 추천 질문입니다:\n1. 수주 전망은?\n2. 위험 요인은?\n3. 경쟁사 비교는?"
        self.assertEqual(rag._parse_followups(raw), ["수주 전망은?", "위험 요인은?", "경쟁사 비교는?"])

    def test_excludes_original_query(self):
        # 모델이 원래 질문을 그대로 되내면 제외한다(공백 정규화 후 비교).
        out = rag._parse_followups("수주   전망은?\n위험 요인은?", query="수주 전망은?")
        self.assertEqual(out, ["위험 요인은?"])

    def test_dedup_and_limit_three(self):
        self.assertEqual(rag._parse_followups("A?\nA?\nB?\nC?\nD?"), ["A?", "B?", "C?"])

    def test_returns_fewer_when_fewer(self):
        # 적게 나오면 적은 대로 돌려준다(억지로 채우지 않는다).
        self.assertEqual(rag._parse_followups("하나만 있나요?"), ["하나만 있나요?"])


class SelectChunksWithinBudgetTest(unittest.TestCase):
    def test_limits_by_budget_and_keeps_first(self):
        chunks = [_chunk("A" * 300), _chunk("B" * 300), _chunk("C" * 300)]
        self.assertEqual(len(rag._select_chunks_within_budget(chunks, 500)), 1)   # 300+300>500
        self.assertEqual(len(rag._select_chunks_within_budget(chunks, 650)), 2)   # 300+300<=650
        # 첫 청크가 예산보다 커도 하나는 넣는다(근거가 통째로 비지 않게).
        self.assertEqual(len(rag._select_chunks_within_budget([_chunk("X" * 9999)], 10)), 1)


class GenerateFollowupQuestionsTest(unittest.TestCase):
    def setUp(self):
        self.chunks = [_chunk()]

    def test_empty_query_or_answer_returns_empty(self):
        self.assertEqual(rag.generate_followup_questions("", "답변[1]", self.chunks), [])
        self.assertEqual(rag.generate_followup_questions("질문?", "", self.chunks), [])

    def test_no_answer_sentinel_returns_empty(self):
        self.assertEqual(rag.generate_followup_questions("질문?", rag.NO_ANSWER, self.chunks), [])

    def test_no_sources_returns_empty(self):
        self.assertEqual(rag.generate_followup_questions("질문?", "답변[1]", []), [])

    @mock.patch(_GEN)
    def test_normal_returns_parsed_three(self, gen):
        gen.return_value = "4분기 물량은?\n설비 투자 지연 시점은?\n2차전지 고객사 비중은?"
        out = rag.generate_followup_questions("수주 현황은?", "3분기 수주 1,284억 [1]", self.chunks)
        self.assertEqual(out, ["4분기 물량은?", "설비 투자 지연 시점은?", "2차전지 고객사 비중은?"])

    @mock.patch(_GEN)
    def test_fewer_than_three_returned_as_is_no_fallback(self, gen):
        # 모델이 1개만 줘도 억지로 3개로 채우지 않고 1개만 돌려준다.
        gen.return_value = "4분기 물량은?"
        out = rag.generate_followup_questions("수주 현황은?", "답변[1]", self.chunks)
        self.assertEqual(out, ["4분기 물량은?"])

    @mock.patch(_GEN)
    def test_called_once_no_retry(self, gen):
        # 적게 나와도 재시도하지 않는다 → LLM 호출은 정확히 한 번.
        gen.return_value = "하나만?"
        rag.generate_followup_questions("수주 현황은?", "답변[1]", self.chunks)
        self.assertEqual(gen.call_count, 1)

    @mock.patch(_GEN)
    def test_api_error_raises_service_error(self, gen):
        from openai import APIError

        # APIError 생성자 인자가 버전마다 달라, __new__로 인스턴스만 만들어 던진다.
        gen.side_effect = APIError.__new__(APIError)
        with self.assertRaises(rag.RAGServiceError):
            rag.generate_followup_questions("질문?", "답변[1]", self.chunks)


if __name__ == "__main__":
    unittest.main()
