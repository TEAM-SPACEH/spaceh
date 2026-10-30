"""R-03·R-04·R-05 보고서 보기 서비스(report_view_service) 테스트: 열기 권한 재확인, 표시용 값.

실행: python -m unittest tests.reports.test_report_view_service
DB·Streamlit 없이 돈다. 저장소·권한 함수는 patch로 가짜를 쓴다.
"""

import unittest
from datetime import date, datetime
from unittest.mock import patch

from app.reports.models.report_models import (
    ExecSummary, Footnote, Report, ReportRequest, ReportTemplate, Section, SectionType, SummaryItem,
)
from app.reports.services import report_view_service as service

FIND_BY_ID = "app.reports.services.report_view_service.report_repository.find_by_id"
CHECK_ACCESS = "app.reports.services.report_view_service.check_document_access"
CREATED_AT = "app.reports.services.report_view_service.report_view_repository.find_created_at"
SOURCE_TYPES = "app.reports.services.report_view_service.report_view_repository.find_source_types"


def make_note(number: int, doc_id: str, location: str = "p.1") -> Footnote:
    return Footnote(number=number, company="현대무벡스", company_id="MVX", filename=f"{doc_id}.pdf", location=location,
                    quote="인용", text="본문", doc_id=doc_id, chunk_id=f"{doc_id}#{number}")


def make_report(footnotes=None, summary=None, level="internal") -> Report:
    request = ReportRequest(ReportTemplate.COMPREHENSIVE, "스마트 물류", ["MVX"], date(2025, 7, 1), date(2025, 10, 31))
    return Report(request=request, sections=[Section(SectionType.OVERVIEW, "개요", "본문 [1]")],
                  footnotes=footnotes or [], exec_summary=summary, report_id=7, user_id=3, max_access_level=level)


USER = {"id": 3, "role": "employee", "company_id": "MVX"}


class OpenReportTest(unittest.TestCase):

    def test_anonymous_user_gets_not_found_without_querying(self):
        with patch(FIND_BY_ID) as find:
            result = service.open_report(None, 7)

        self.assertEqual(result["status"], service.OPEN_NOT_FOUND)
        find.assert_not_called()

    @patch(FIND_BY_ID, return_value=None)
    def test_report_of_someone_else_is_not_found(self, find):
        result = service.open_report(USER, 7)

        self.assertEqual(result["status"], service.OPEN_NOT_FOUND)
        find.assert_called_once_with(7, 3)  # 작성자 id까지 함께 조건으로 건다

    @patch(SOURCE_TYPES, return_value={"d1": "internal", "d2": "dart"})
    @patch(CREATED_AT, return_value=datetime(2026, 10, 29, 13, 40))
    @patch(CHECK_ACCESS, return_value=True)
    @patch(FIND_BY_ID)
    def test_viewable_report_is_opened_with_checks_per_document(self, find, access, _created, _types):
        find.return_value = make_report([make_note(1, "d1"), make_note(2, "d2"), make_note(3, "d1", "p.2")])

        result = service.open_report(USER, 7)

        self.assertEqual(result["status"], service.OPEN_OK)
        self.assertEqual(result["source_types"]["d2"], "dart")
        # 같은 문서는 한 번만 확인한다
        self.assertEqual([call.args for call in access.call_args_list], [(3, "d1"), (3, "d2")])

    @patch(CHECK_ACCESS, side_effect=lambda user_id, doc_id: doc_id != "secret")
    @patch(FIND_BY_ID)
    def test_one_unviewable_document_blocks_the_whole_report(self, find, _access):
        find.return_value = make_report([make_note(1, "d1"), make_note(2, "secret")])

        result = service.open_report(USER, 7)

        self.assertEqual(result["status"], service.OPEN_BLOCKED)
        self.assertEqual(result["blocked_count"], 1)
        self.assertIsNone(result["report"])  # 막힌 보고서는 내용을 돌려주지 않는다

    @patch(SOURCE_TYPES, return_value={})
    @patch(CREATED_AT, return_value=None)
    @patch(FIND_BY_ID)
    def test_report_without_footnotes_has_nothing_to_check(self, find, _created, _types):
        find.return_value = make_report([])

        with patch(CHECK_ACCESS) as access:
            result = service.open_report(USER, 7)

        self.assertEqual(result["status"], service.OPEN_OK)
        access.assert_not_called()


class DisplayTest(unittest.TestCase):

    def test_period_shows_year_and_month(self):
        self.assertEqual(service.format_period(make_report()), "2025.07 – 2025.10")

    def test_template_title(self):
        self.assertEqual(service.template_title(make_report()), "종합 보고서")

    def test_created_today_yesterday_and_older(self):
        now = datetime(2026, 10, 29, 20, 0)

        self.assertEqual(service.format_created(datetime(2026, 10, 29, 13, 40), now), "오늘 13:40")
        self.assertEqual(service.format_created(datetime(2026, 10, 28, 17, 55), now), "어제 17:55")
        self.assertEqual(service.format_created(datetime(2026, 10, 2, 9, 5), now), "10.02 09:05")
        self.assertEqual(service.format_created(None, now), "")

    def test_link_label_distinguishes_dart(self):
        self.assertEqual(service.link_label("dart"), "DART")
        self.assertEqual(service.link_label("internal"), "원문")
        self.assertEqual(service.link_label(None), "원문")


class SplitSummaryTest(unittest.TestCase):

    def test_company_items_join_key_summary_and_advice_stays_apart(self):
        summary = ExecSummary(
            items=[
                SummaryItem("key", "핵심 [1]", SectionType.OVERVIEW),
                SummaryItem("company", "시사점 [2]", SectionType.STATUS, "MVX"),
                SummaryItem("advice", "권고 [3]", SectionType.ADVICE),
            ],
            notes=["근거 없음"],
        )

        key_items, advice_items, notes = service.split_summary(summary)

        self.assertEqual([item.text for item in key_items], ["핵심 [1]", "시사점 [2]"])
        self.assertEqual([item.text for item in advice_items], ["권고 [3]"])
        self.assertEqual(notes, ["근거 없음"])

    def test_missing_summary_is_empty(self):
        self.assertEqual(service.split_summary(None), ([], [], []))


class GroupSourcesTest(unittest.TestCase):

    def test_same_document_is_grouped_in_first_cited_order(self):
        notes = [make_note(1, "d1", "p.1"), make_note(2, "d2"), make_note(3, "d1", "p.9")]

        groups = service.group_sources(notes)

        self.assertEqual([group["doc_id"] for group in groups], ["d1", "d2"])
        self.assertEqual([note.number for note in groups[0]["notes"]], [1, 3])


class DownloadNoticeTest(unittest.TestCase):

    def test_internal_mentions_watermark_and_is_not_blocked(self):
        notice = service.download_notice("internal")

        self.assertFalse(notice["blocked"])
        self.assertIn("'사내'입니다", notice["text"])
        self.assertIn("워터마크가 들어가고", notice["text"])
        self.assertIn("열람 권한이 없는 근거 문서가 있으면 내려받기가 막힙니다", notice["text"])

    def test_public_uses_its_own_level_name(self):
        self.assertIn("'공개'입니다", service.download_notice("public")["text"])

    def test_confidential_is_not_blocked_by_level_alone(self):
        # A-06은 열람 권한으로만 막는다. 기밀 문서를 볼 수 있는 사용자는 내려받을 수 있다.
        notice = service.download_notice("confidential")

        self.assertFalse(notice["blocked"])
        self.assertIn("'기밀'입니다", notice["text"])
        self.assertNotIn("'기밀' 문서가 있으면", notice["text"])


if __name__ == "__main__":
    unittest.main()
