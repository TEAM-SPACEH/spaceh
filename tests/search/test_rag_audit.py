import unittest
from unittest.mock import patch

from app.search.services.rag_service import (
    answer_question,
    generate_answer_with_audit,
)


class TestRAGAudit(unittest.TestCase):

    def setUp(self):
        self.user = {"id": 1, "company_id": "HRI"}
        self.filters = {"company_id": "HRI"}

    def test_ask_audit_log(self):
        """질문과 실제 인용 문서가 ask 로그에 기록되는지 확인"""

        result = {
            "answer": "테스트 답변",
            "sources": [
                {"doc_id": "DOC-001", "company_id": "HRI"},
                {"doc_id": "DOC-001", "company_id": "HRI"},
                {"doc_id": "DOC-002", "company_id": "MVX"},
            ],
        }

        with patch(
            "app.search.services.rag_service.generate_answer",
            return_value=result,
        ), patch(
            "app.search.services.rag_service.record_audit_log"
        ) as mock_audit:

            actual = generate_answer_with_audit(
                "  테스트 질문  ",
                [],
                self.user,
                self.filters,
            )

        self.assertEqual(actual, result)

        mock_audit.assert_called_once_with(
            user_id=1,
            action_type="ask",
            target_id=None,
            ip_address=None,
            blocked=False,
            block_reason=None,
            query="테스트 질문",
            filters=self.filters,
            doc_ids=["DOC-001", "DOC-002"],
            doc_companies=["HRI", "MVX"],
            result_count=2,
        )

    def test_no_answer_audit_log(self):
        """근거가 없는 답변도 정상 질의 이력으로 기록되는지 확인"""

        result = {
            "answer": "찾을 수 없음",
            "sources": [],
        }

        with patch(
            "app.search.services.rag_service.generate_answer",
            return_value=result,
        ), patch(
            "app.search.services.rag_service.record_audit_log"
        ) as mock_audit:

            actual = generate_answer_with_audit(
                "테스트 질문",
                [],
                self.user,
            )

        self.assertEqual(actual, result)
        self.assertEqual(mock_audit.call_args.kwargs["doc_ids"], [])
        self.assertEqual(mock_audit.call_args.kwargs["result_count"], 0)

    def test_audit_failure_does_not_block_answer(self):
        """감사 로그 저장에 실패해도 AI 답변을 반환하는지 확인"""

        result = {
            "answer": "정상 답변",
            "sources": [],
        }

        with patch(
            "app.search.services.rag_service.generate_answer",
            return_value=result,
        ), patch(
            "app.search.services.rag_service.record_audit_log",
            side_effect=Exception("DB 오류"),
        ), patch(
            "app.search.services.rag_service.logger"
        ) as mock_logger:

            actual = generate_answer_with_audit(
                "테스트 질문",
                [],
                self.user,
            )

        self.assertEqual(actual, result)
        mock_logger.exception.assert_called_once_with(
            "감사 로그 기록 실패(ask)"
        )

    def test_answer_question_uses_audit_service(self):
        """기존 answer_question도 감사 로그 공통 함수를 사용하는지 확인"""

        result = {
            "answer": "테스트 답변",
            "sources": [],
        }
        chunks = [{"doc_id": "DOC-001"}]

        with patch(
            "app.search.services.rag_service._search_documents_for_user",
            return_value=chunks,
        ) as mock_search, patch(
            "app.search.services.rag_service.generate_answer_with_audit",
            return_value=result,
        ) as mock_answer:

            actual = answer_question(
                "테스트 질문",
                self.filters,
                self.user,
            )

        self.assertEqual(actual, result)
        mock_search.assert_called_once_with(
            "테스트 질문",
            self.filters,
            self.user,
        )
        mock_answer.assert_called_once_with(
            "테스트 질문",
            chunks,
            self.user,
            self.filters,
        )


if __name__ == "__main__":
    unittest.main()