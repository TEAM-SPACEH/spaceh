
"""S-04 근거 기반 AI 답변 생성 단위 테스트."""

import unittest
from unittest.mock import patch

from app.search.services import rag_service

import httpx
from openai import APIConnectionError


NO_ANSWER = "찾을 수 없음"


def make_chunk(company_id, company_name, doc_id, chunk_id, text, page):
    """테스트용 가상 문서 청크 생성."""
    return {
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "text": text,
        "metadata": {
            "company_id": company_id,
            "company_name": company_name,
            "file_name": f"{company_id}_가상안내.pdf",
            "page": page,
        },
    }


class TestRagService(unittest.TestCase):

    def setUp(self):
        """각 테스트에서 사용할 가상 문서 3개."""
        self.chunks = [
            make_chunk(
                "HRI", "현대경제연구원",
                "doc-001", "chunk-001",
                "가상 프로젝트 정기 회의는 매주 월요일 오전 9시입니다.",
                1,
            ),
            make_chunk(
                "MVX", "현대무벡스",
                "doc-002", "chunk-002",
                "가상 프로젝트 정기 회의는 매주 화요일 오전 10시입니다.",
                2,
            ),
            make_chunk(
                "ELV", "현대엘리베이터",
                "doc-003", "chunk-003",
                "가상 프로젝트 정기 회의는 매주 수요일 오후 2시입니다.",
                3,
            ),
        ]

    def _generate_mock_answer(self, answer, chunks=None, grounded=True):
        """실제 OpenAI 호출 없이 AI 답변 생성 과정을 테스트."""
        if chunks is None:
            chunks = self.chunks

        with patch.object(
            rag_service,
            "_generate_with_openai",
            return_value=answer,
        ) as mock_llm:
            with patch.object(
                rag_service,
                "_judge_grounding",
                return_value="SUPPORTED" if grounded else "UNSUPPORTED",
            ) as mock_grounding:

                result = rag_service.generate_answer(
                    "가상 프로젝트 회의 일정은?",
                    chunks,
                )

        return result, mock_llm, mock_grounding

    # 1. 문서 청크 컨텍스트 변환
    def test_prepare_context(self):
        context, sources = rag_service.prepare_context(self.chunks)

        self.assertIn("[문서 1]", context)
        self.assertIn("현대경제연구원", context)
        self.assertIn("페이지 1", context)
        self.assertEqual(len(sources), 3)

    # 2. 정상 질문에 대한 답변 및 출처 반환
    def test_generate_valid_answer(self):
        result, mock_llm, mock_grounding = self._generate_mock_answer(
            "정기 회의는 월요일 오전 9시입니다. [1]"
        )

        self.assertNotEqual(result["answer"], NO_ANSWER)
        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(result["sources"][0]["citation_number"], 1)
        self.assertEqual(result["sources"][0]["company"], "현대경제연구원")

        mock_llm.assert_called_once()
        mock_grounding.assert_called_once()

    # 3. 근거 없는 질문 처리
    def test_no_answer(self):
        result, _, _ = self._generate_mock_answer(NO_ANSWER)

        self.assertEqual(result["answer"], NO_ANSWER)
        self.assertEqual(result["sources"], [])

    # 4. 출처 번호가 없는 답변 차단
    def test_missing_citation(self):
        result, _, _ = self._generate_mock_answer(
            "정기 회의는 매주 월요일입니다."
        )

        self.assertEqual(result["answer"], NO_ANSWER)
        self.assertEqual(result["sources"], [])

    # 5. 존재하지 않는 출처 번호 차단
    def test_invalid_citation(self):
        result, _, _ = self._generate_mock_answer(
            "정기 회의는 월요일입니다. [99]"
        )

        self.assertEqual(result["answer"], NO_ANSWER)
        self.assertEqual(result["sources"], [])

    # 6. 근거 검증에 실패한 답변 차단
    def test_unsupported_answer(self):
        result, _, mock_grounding = self._generate_mock_answer(
            "가상 프로젝트 매출은 100억 원입니다. [1]",
            grounded=False,
        )

        self.assertEqual(result["answer"], NO_ANSWER)
        self.assertEqual(result["sources"], [])
        mock_grounding.assert_called_once()

    # 7. 3개 기업의 출처 반환
    def test_multiple_company_sources(self):
        answer = (
            "현대경제연구원은 월요일 오전 9시 [1], "
            "현대무벡스는 화요일 오전 10시 [2], "
            "현대엘리베이터는 수요일 오후 2시 [3]입니다."
        )

        result, _, _ = self._generate_mock_answer(answer)

        self.assertEqual(result["answer"], answer)
        self.assertEqual(len(result["sources"]), 3)

        companies = {
            source["company"]
            for source in result["sources"]
        }

        self.assertEqual(
            companies,
            {"현대경제연구원", "현대무벡스", "현대엘리베이터"},
        )

    # 8. 인용하지 않은 출처는 반환하지 않음
    def test_only_cited_sources(self):
        result, _, _ = self._generate_mock_answer(
            "월요일 오전 9시 [1], 수요일 오후 2시 [3]"
        )

        citation_numbers = [
            source["citation_number"]
            for source in result["sources"]
        ]

        self.assertEqual(citation_numbers, [1, 3])

    # 9. 중복 인용 출처 제거
    def test_duplicate_citations(self):
        result, _, _ = self._generate_mock_answer(
            "월요일 오전 9시입니다 [1]. 관련 안내도 동일합니다 [1]."
        )

        self.assertEqual(len(result["sources"]), 1)
        self.assertEqual(result["sources"][0]["citation_number"], 1)

    # 10. 검색 결과가 없을 때 LLM 미호출
    def test_empty_chunks(self):
        result, mock_llm, mock_grounding = self._generate_mock_answer(
            "임의의 답변 [1]",
            chunks=[],
        )

        self.assertEqual(result["answer"], NO_ANSWER)
        self.assertEqual(result["sources"], [])

        mock_llm.assert_not_called()
        mock_grounding.assert_not_called()

    
    # 11. AI 답변 생성 API 연결 실패
    def test_openai_generation_failure(self):
        api_error = APIConnectionError(
            request=httpx.Request(
                "POST",
                "https://api.openai.com/v1/chat/completions",
            )
        )

        with patch.object(
            rag_service,
            "_generate_with_openai",
            side_effect=api_error,
        ):
            with self.assertRaises(rag_service.RAGServiceError):
                rag_service.generate_answer(
                    "가상 프로젝트 회의 일정은?",
                    self.chunks,
                )

    # 12. AI 근거 검증 API 연결 실패
    def test_openai_grounding_failure(self):
        api_error = APIConnectionError(
            request=httpx.Request(
                "POST",
                "https://api.openai.com/v1/chat/completions",
            )
        )

        with patch.object(
            rag_service,
            "_generate_with_openai",
            return_value="월요일 오전 9시입니다. [1]",
        ):
            with patch.object(
                rag_service,
                "_judge_grounding",
                side_effect=api_error,
            ):
                with self.assertRaises(rag_service.RAGServiceError):
                    rag_service.generate_answer(
                        "가상 프로젝트 회의 일정은?",
                        self.chunks,
                    )

if __name__ == "__main__":
    unittest.main()
