
"""R-01 요청 검증, 문서 수집, 균형 배치, 섹션 근거 테스트."""

import unittest
from datetime import date, datetime
from unittest.mock import patch

from app.reports.models.report_models import (
    Chunk,
    CollectionResult,
    ReportRequest,
    ReportTemplate,
    SectionType,
)
from app.reports.services.report_service import validate_request
from app.reports.services.report_collector import (
    collect_documents,
    balance_by_company,
    select_section_evidence,
)


def make_chunk(company_id, number, text="스마트 물류 사업"):
    return Chunk(
        chunk_id=f"{company_id}#{number:04d}",
        text=text,
        metadata={
            "company_id": company_id,
            "doc_id": f"doc-{company_id}",
        },
    )


class TestReportCollector(unittest.TestCase):

    def setUp(self):
        self.request = ReportRequest(
            template=ReportTemplate.COMPREHENSIVE,
            topic="스마트 물류",
            company_ids=["HRI", "MVX"],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 12, 31),
        )

        self.user = {
            "id": 1,
            "role": "super_admin",
            "company_id": None,
        }

    @patch(
        "app.reports.services.report_service.get_company_options",
        return_value=[
            {"id": "HRI", "name": "현대경제연구원"},
            {"id": "MVX", "name": "현대무벡스"},
        ],
    )
    def test_validate_request(self, mock_companies):
        self.assertEqual(validate_request(self.request), [])

        self.request.topic = " "
        self.assertTrue(validate_request(self.request))

        self.request.topic = "스마트 물류"
        self.request.company_ids = []
        self.assertTrue(validate_request(self.request))

        self.request.company_ids = ["HRI"]
        self.request.start_date = date(2025, 12, 31)
        self.request.end_date = date(2025, 1, 1)
        self.assertTrue(validate_request(self.request))

    @patch(
        "app.reports.services.report_service.get_company_options",
        return_value=[
            {"id": "HRI", "name": "현대경제연구원"},
            {"id": "MVX", "name": "현대무벡스"},
        ],
    )
    def test_datetime_rejected(self, mock_companies):
        self.request.start_date = datetime(2025, 1, 1)

        errors = validate_request(self.request)

        self.assertIn(
            "올바른 보고서 기간을 선택해 주세요.",
            errors,
        )

    @patch(
        "app.reports.services.report_collector.hybrid_search"
    )
    def test_collect_documents(self, mock_search):
        hri = make_chunk("HRI", 1)
        mvx = make_chunk("MVX", 1)

        def to_result(chunk):
            return {
                "chunk_id": chunk.chunk_id,
                "text": chunk.text,
                "score": 0.9,
                "metadata": chunk.metadata,
                "doc_id": chunk.metadata["doc_id"],
            }

        mock_search.side_effect = [
            [to_result(hri), to_result(hri)],
            [to_result(mvx)],
        ]

        chunks = collect_documents(self.user, self.request)

        self.assertEqual(mock_search.call_count, 2)
        self.assertEqual(len(chunks), 2)

        for call in mock_search.call_args_list:
            self.assertFalse(call.kwargs["audit"])
            self.assertEqual(call.args[0], "스마트 물류")

        # 회사 필터가 각각 적용됐는지 확인
        filters = [
            call.args[1] for call in mock_search.call_args_list
        ]

        self.assertIn({"company_id": "HRI"}, filters[0]["$and"])
        self.assertIn({"company_id": "MVX"}, filters[1]["$and"])

    def test_balance_by_company(self):
        chunks = [
            make_chunk("HRI", i)
            for i in range(1, 11)
        ]
        chunks.append(make_chunk("MVX", 1))

        result = balance_by_company(
            chunks,
            ["HRI", "MVX", "ELV"],
        )

        # HRI 10개 + MVX 1개 모두 유지
        self.assertEqual(len(result.chunks), 11)

        # 앞쪽은 회사별 교차 배치
        self.assertEqual(
            [c.metadata["company_id"] for c in result.chunks[:3]],
            ["HRI", "MVX", "HRI"],
        )

        self.assertEqual(result.empty_companies, ["ELV"])

    def test_balance_all_empty(self):
        result = balance_by_company([], ["HRI", "MVX"])

        self.assertEqual(result.chunks, [])
        self.assertEqual(
            result.empty_companies,
            ["HRI", "MVX"],
        )

    def test_section_evidence_preserves_chunks(self):
        chunks = [
            make_chunk("HRI", 1, "스마트 물류 관련 자료"),
            make_chunk("MVX", 1, "자동화 관련 자료"),
        ]
        collection = CollectionResult(chunks=chunks)

        for section_type in (
            SectionType.OVERVIEW,
            SectionType.STATUS,
            SectionType.SYNERGY,
            SectionType.ADVICE,
        ):
            self.assertEqual(
                select_section_evidence(section_type, collection),
                chunks,
            )

    def test_synergy_single_company(self):
        collection = CollectionResult(
            chunks=[make_chunk("HRI", 1)]
        )

        result = select_section_evidence(
            SectionType.SYNERGY,
            collection,
        )

        self.assertEqual(result, [])

    def test_performance_internal_document(self):
        collection = CollectionResult(
            chunks=[
                make_chunk(
                    "HRI",
                    1,
                    "사업 실적 매출액 120억원",
                )
            ]
        )

        result = select_section_evidence(
            SectionType.PERFORMANCE,
            collection,
        )

        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
