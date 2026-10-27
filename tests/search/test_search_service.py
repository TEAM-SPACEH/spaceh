"""S-02 apply_metadata_filters 테스트. 순수 함수라 DB 없이 바로 돈다."""

import unittest

from app.search.services.search_service import apply_metadata_filters


class ApplyMetadataFiltersTest(unittest.TestCase):
    def test_empty_filter_returns_empty_dict(self):
        # 고른 조건이 없으면 필터를 걸지 않는다.
        self.assertEqual(apply_metadata_filters({}), {})
        self.assertEqual(apply_metadata_filters(None), {})

    def test_single_condition_returned_as_is(self):
        # 조건이 1개면 $and로 묶지 않고 그대로 돌려준다.
        self.assertEqual(
            apply_metadata_filters({"companies": ["HRI", "MVX"]}),
            {"company_id": {"$in": ["HRI", "MVX"]}},
        )
        self.assertEqual(
            apply_metadata_filters({"doc_types": ["report"]}),
            {"doc_type": {"$in": ["report"]}},
        )

    def test_string_value_normalized_to_list(self):
        # 문자열 하나가 와도 글자 단위로 쪼개지 않고 한 항목으로 센다.
        self.assertEqual(
            apply_metadata_filters({"companies": "HRI"}),
            {"company_id": {"$in": ["HRI"]}},
        )

    def test_multiple_conditions_wrapped_in_and(self):
        result = apply_metadata_filters(
            {"companies": ["MVX"], "doc_types": ["report"], "date_from": 20250101, "date_to": 20251231}
        )
        self.assertEqual(
            result,
            {
                "$and": [
                    {"company_id": {"$in": ["MVX"]}},
                    {"doc_type": {"$in": ["report"]}},
                    {"published_date": {"$gte": 20250101}},
                    {"published_date": {"$lte": 20251231}},
                ]
            },
        )

    def test_only_start_date(self):
        self.assertEqual(
            apply_metadata_filters({"date_from": 20250101}),
            {"published_date": {"$gte": 20250101}},
        )

    def test_only_end_date(self):
        self.assertEqual(
            apply_metadata_filters({"date_to": 20251231}),
            {"published_date": {"$lte": 20251231}},
        )

    def test_start_after_end_raises(self):
        # 시작일이 종료일보다 늦으면 아무 문서도 못 찾으니 잘못된 입력으로 본다.
        with self.assertRaises(ValueError):
            apply_metadata_filters({"date_from": 20251231, "date_to": 20250101})

    def test_same_start_and_end_is_allowed(self):
        # 같은 날짜는 역전이 아니므로 통과한다.
        self.assertEqual(
            apply_metadata_filters({"date_from": 20250101, "date_to": 20250101}),
            {"$and": [{"published_date": {"$gte": 20250101}}, {"published_date": {"$lte": 20250101}}]},
        )


if __name__ == "__main__":
    unittest.main()
