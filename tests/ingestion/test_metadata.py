"""I-02 공통 메타데이터와 제목 대체·권한·날짜 매핑을 검증한다."""

import copy
from datetime import date, datetime
import unittest

from app.ingestion.preprocessing.metadata import build_metadata


class MetadataTest(unittest.TestCase):
    """외부 DB·API 없이 등록 정보가 검색 메타데이터로 유지되는지 확인한다."""

    def setUp(self):
        """등록 화면·DB가 제공할 문서 정보와 I-01 블록을 준비한다."""
        self.doc_id = "a" * 32
        self.info = {
            "company_id": "MVX", "company_name": "현대무벡스",
            "file_name": "[현대무벡스]반기보고서(2026.08.14).pdf",
            "file_format": "pdf", "doc_type": "report",
            "access_level": "internal", "is_group_shared": 0,
            "title": "등록한 제목", "published_date": date(2026, 8, 14),
            "created_at": datetime(2026, 10, 27, 9, 30),
            "source_type": "internal", "source_url": None,
        }
        self.block = {"block_type": "table", "text": "표 내용",
                      "page": 38, "location": "p.38", "section": "재무"}

    def test_maps_registered_values_and_preserves_input(self):
        """DB 날짜·공유 정수를 변환하고 위치를 보존하며 입력을 바꾸지 않는다."""
        before = copy.deepcopy((self.info, self.block))
        result = build_metadata(self.doc_id, self.info, self.block)
        self.assertEqual(result["title"], "등록한 제목")
        self.assertEqual(result["published_date"], 20260814)
        self.assertIs(result["is_group_shared"], False)
        self.assertEqual(result["page"], 38)
        self.assertEqual(result["source_url"], "")
        self.assertNotIn("text", result)
        self.assertNotIn("content_hash", result)
        self.assertTrue(all(type(v) in (str, int, float, bool)
                            for v in result.values()))
        self.assertEqual((self.info, self.block), before)

    def test_missing_or_blank_title_uses_filename_without_final_extension(self):
        """없는 제목·None·공백 제목은 파일명의 마지막 확장자만 제거한다."""
        for title in (None, "", "   "):
            with self.subTest(title=title):
                info = {**self.info, "title": title}
                result = build_metadata(self.doc_id, info, {})
                self.assertEqual(result["title"],
                                 "[현대무벡스]반기보고서(2026.08.14)")
        info = {k: v for k, v in self.info.items() if k != "title"}
        self.assertEqual(build_metadata(self.doc_id, info, {})["title"],
                         "[현대무벡스]반기보고서(2026.08.14)")

    def test_dates_are_mapped_without_guessing_from_filename(self):
        """작성일을 우선하고 미확인 날짜는 파일명 대신 원래 업로드일로 대체한다."""
        for value, expected in [("2026-08-14", 20260814),
                                (None, 20261027), ("", 20261027)]:
            with self.subTest(value=value):
                result = build_metadata(self.doc_id,
                                        {**self.info, "published_date": value}, {})
                self.assertEqual(result["published_date"], expected)
        for value in ("2026-02-30", "unknown", 20260814, True):
            with self.subTest(invalid=value):
                with self.assertRaises(ValueError):
                    build_metadata(self.doc_id,
                                   {**self.info, "published_date": value}, {})

    def test_missing_date_uses_registered_upload_date_formats(self):
        """작성일 키가 없어도 DB DATETIME·날짜·ISO 업로드일을 같은 날짜로 변환한다."""
        info = {k: v for k, v in self.info.items() if k != "published_date"}
        for uploaded in (datetime(2026, 10, 27, 23, 59), date(2026, 10, 27),
                         "2026-10-27 09:30:00", "2026-10-27"):
            with self.subTest(uploaded=uploaded):
                result = build_metadata(self.doc_id,
                                        {**info, "created_at": uploaded}, {})
                self.assertEqual(result["published_date"], 20261027)

    def test_missing_dates_are_rejected_instead_of_using_zero_or_today(self):
        """날짜가 둘 다 없거나 업로드일 형식이 잘못되면 검색 날짜를 임의로 만들지 않는다."""
        for uploaded in (None, "", "unknown", "2026-02-30", 20261027, True):
            with self.subTest(uploaded=uploaded):
                with self.assertRaises(ValueError):
                    build_metadata(self.doc_id,
                                   {**self.info, "published_date": None,
                                    "created_at": uploaded}, {})
        info = {k: v for k, v in self.info.items()
                if k not in {"published_date", "created_at"}}
        with self.assertRaises(ValueError):
            build_metadata(self.doc_id, info, {})

    def test_known_published_date_does_not_require_upload_date(self):
        """이미 확정된 작성일이 있으면 업로드일과 무관하게 그대로 사용한다."""
        result = build_metadata(self.doc_id,
                                {**self.info, "created_at": None}, {})
        self.assertEqual(result["published_date"], 20260814)

    def test_extraction_cannot_override_permissions(self):
        """문서 내용의 public·공유 값이 등록된 보안 조건을 덮어쓰지 않는다."""
        extracted = {**self.block, "access_level": "public",
                     "company_id": "OTHER", "is_group_shared": True}
        result = build_metadata(self.doc_id, self.info, extracted)
        self.assertEqual(result["company_id"], "MVX")
        self.assertEqual(result["access_level"], "internal")
        self.assertIs(result["is_group_shared"], False)

    def test_internal_sharing_is_allowed_and_other_levels_are_rejected(self):
        """공유는 internal에만 허용하며 잘못된 문자열·정수 값을 거부한다."""
        for shared in (True, 1):
            result = build_metadata(self.doc_id,
                                    {**self.info, "is_group_shared": shared}, {})
            self.assertIs(result["is_group_shared"], True)
        for level in ("public", "confidential"):
            with self.assertRaises(ValueError):
                build_metadata(self.doc_id,
                               {**self.info, "access_level": level,
                                "is_group_shared": True}, {})
        for shared in ("0", "false", None, 2):
            with self.subTest(shared=shared):
                with self.assertRaises(ValueError):
                    build_metadata(self.doc_id,
                                   {**self.info, "is_group_shared": shared}, {})

    def test_invalid_required_fields_and_choices_are_rejected(self):
        """필수 등록 값 누락과 잘못된 타입·범주·파일 경로를 차단한다."""
        for key, value in [("company_id", ""), ("company_id", "mvx"),
                           ("company_name", None),
                           ("file_name", "folder/file.pdf"),
                           ("file_name", "folder\\file.pdf"),
                           ("doc_type", "unknown"), ("access_level", []),
                           ("file_format", "exe"), ("source_type", "web"),
                           ("title", 12), ("source_url", 12)]:
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    build_metadata(self.doc_id, {**self.info, key: value}, {})
        for doc_id in (None, "", "   "):
            with self.assertRaises(ValueError):
                build_metadata(doc_id, self.info, {})

    def test_dynamic_companies_and_empty_common_positions(self):
        """신규 회사 코드를 고정 목록으로 막지 않고 공통 위치는 비워 둔다."""
        info = {**self.info, "company_id": "NEW", "company_name": "새 회사"}
        result = build_metadata(self.doc_id, info, {})
        self.assertEqual(result["company_id"], "NEW")
        self.assertEqual(result["page"], 0)
        self.assertEqual(result["location"], "")

    def test_invalid_extracted_positions_are_rejected(self):
        """위치 타입과 블록 유형을 검증해 중첩 값이 메타데이터에 섞이지 않는다."""
        for key, value in [("page", -1), ("page", True), ("page", "1"),
                           ("location", None), ("section", []),
                           ("block_type", "image")]:
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    build_metadata(self.doc_id, self.info,
                                   {**self.block, key: value})


if __name__ == "__main__":
    unittest.main()
