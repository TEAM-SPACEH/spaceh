"""evidence_preview(R-01 근거 문서 수 미리보기) 테스트. Chroma 조회는 mock 으로 바꿔 DB·Chroma 없이 돈다.

실행: python -m unittest tests.reports.test_evidence_preview

확인 대상: 회사별로 문서 수를 세고(같은 문서의 청크는 1건), 문서가 없는 회사도 0건으로 돌려주며,
권한 조건이 where 에 들어가서 조회되고, 시작일이 종료일보다 늦으면 거부한다.
"""

import unittest
from datetime import date
from unittest.mock import patch

from app.reports.services import evidence_preview as preview

REPOSITORY = "app.reports.services.evidence_preview.get_chunk_metadatas"

EMPLOYEE = {"id": 4, "role": "employee", "company_id": "MVX"}
SUPER = {"id": 1, "role": "super_admin", "company_id": None}
JULY = date(2025, 7, 1)
OCTOBER = date(2025, 10, 31)


def _chunk(doc_id: str, company_id: str) -> dict:
    return {"doc_id": doc_id, "company_id": company_id}


class CountVisibleDocumentsTest(unittest.TestCase):

    @patch(REPOSITORY)
    def test_counts_distinct_documents_per_company(self, repository):
        repository.return_value = [
            _chunk("a", "HRI"), _chunk("a", "HRI"), _chunk("b", "HRI"),  # 같은 문서 a 의 청크 둘은 1건
            _chunk("c", "MVX"),
        ]

        result = preview.count_visible_documents(EMPLOYEE, ["HRI", "MVX", "ELV"], JULY, OCTOBER)

        self.assertEqual(result, {"HRI": 2, "MVX": 1, "ELV": 0})
        self.assertEqual(list(result), ["HRI", "MVX", "ELV"])

    @patch(REPOSITORY)
    def test_where_has_permission_condition_and_filters(self, repository):
        repository.return_value = []

        preview.count_visible_documents(EMPLOYEE, ["HRI"], JULY, OCTOBER)

        where = repository.call_args.args[0]
        rbac, filters = where["$and"]
        self.assertIn({"access_level": "public"}, rbac["$or"])  # 권한 조건이 where 안에 있다
        self.assertIn({"company_id": "HRI"}, filters["$and"])
        self.assertIn({"published_date": {"$gte": 20250701}}, filters["$and"])
        self.assertIn({"published_date": {"$lte": 20251031}}, filters["$and"])

    @patch(REPOSITORY)
    def test_chunks_of_unrequested_company_are_ignored(self, repository):
        repository.return_value = [_chunk("a", "ELV")]

        result = preview.count_visible_documents(EMPLOYEE, ["HRI"], JULY, OCTOBER)

        self.assertEqual(result, {"HRI": 0})

    @patch(REPOSITORY)
    def test_duplicate_company_codes_are_merged(self, repository):
        repository.return_value = [_chunk("a", "HRI")]

        result = preview.count_visible_documents(SUPER, ["HRI", "HRI"], JULY, OCTOBER)

        self.assertEqual(result, {"HRI": 1})

    @patch(REPOSITORY)
    def test_no_company_does_not_query(self, repository):
        self.assertEqual(preview.count_visible_documents(EMPLOYEE, [], JULY, OCTOBER), {})
        repository.assert_not_called()

    @patch(REPOSITORY)
    def test_start_after_end_is_rejected_before_query(self, repository):
        with self.assertRaises(ValueError):
            preview.count_visible_documents(EMPLOYEE, ["HRI"], OCTOBER, JULY)

        repository.assert_not_called()

    @patch(REPOSITORY)
    def test_unknown_user_is_rejected_before_query(self, repository):
        with self.assertRaises(PermissionError):
            preview.count_visible_documents({}, ["HRI"], JULY, OCTOBER)

        repository.assert_not_called()


if __name__ == "__main__":
    unittest.main()
