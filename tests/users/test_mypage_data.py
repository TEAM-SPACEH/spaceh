"""내 정보 화면 순수 계산 테스트: 통계 3개, 최근 30일 요청, 사용 기록 묶음. DB·Streamlit 없이 돈다.

실행: python -m unittest tests.users.test_mypage_data
"""

import unittest
from datetime import date, datetime

from app.users.views import mypage_data

NOW = datetime(2026, 10, 29, 22, 0)
TODAY = NOW.date()


def history(kind: str, when: str, **extra) -> dict:
    return {"history_type": kind, "summary": extra.pop("summary", kind), "created_at": when,
            "result_count": extra.pop("result_count", None), "is_blocked": extra.pop("is_blocked", False), **extra}


def request(status: str, created: str, **extra) -> dict:
    return {"status": status, "title": extra.pop("title", "문서"), "created_at": created, **extra}


class ParseTimeTest(unittest.TestCase):
    def test_parses_service_format(self):
        self.assertEqual(mypage_data.parse_time("2026-10-29 14:02"), datetime(2026, 10, 29, 14, 2))

    def test_none_empty_and_bad_values_return_none(self):
        for value in (None, "", "10/29 14:02", "2026-10-29"):
            self.assertIsNone(mypage_data.parse_time(value))


class UsageCountsTest(unittest.TestCase):
    def test_counts_only_this_months_questions_all_reports_and_approved_requests(self):
        items = [
            history("ask", "2026-10-02 09:00"),
            history("ask", "2026-10-29 09:00"),
            history("ask", "2026-09-30 23:59"),          # 지난달 질문은 뺀다
            history("search", "2026-10-10 09:00"),       # 검색은 질문이 아니다
            history("report_create", "2026-08-01 09:00"),  # 보고서는 달과 상관없이 센다
            history("report_create", "2026-10-20 09:00"),
        ]
        requests = [request("approved", "2026-10-01 10:00"), request("pending", "2026-10-02 10:00"),
                    request("rejected", "2026-10-03 10:00"), request("approved", "2026-07-01 10:00")]

        self.assertEqual(mypage_data.usage_counts(items, requests, TODAY), {"asked": 2, "reports": 2, "approved": 2})

    def test_empty_inputs_give_zeros(self):
        self.assertEqual(mypage_data.usage_counts([], [], TODAY), {"asked": 0, "reports": 0, "approved": 0})

    def test_unreadable_time_is_not_counted_as_this_month(self):
        self.assertEqual(mypage_data.usage_counts([history("ask", None)], [], TODAY)["asked"], 0)


class RecentRequestsTest(unittest.TestCase):
    def test_keeps_only_last_30_days_and_order(self):
        requests = [request("pending", "2026-10-27 10:12", title="a"), request("approved", "2026-09-29 22:00", title="b"),
                    request("pending", "2026-09-29 21:59", title="c")]

        self.assertEqual([r["title"] for r in mypage_data.recent_requests(requests, NOW)], ["a", "b"])

    def test_request_without_readable_time_is_dropped(self):
        self.assertEqual(mypage_data.recent_requests([request("pending", None)], NOW), [])


class TimelineTest(unittest.TestCase):
    def test_merges_history_and_requests_newest_first_and_skips_unreadable_times(self):
        items = [history("ask", "2026-10-29 14:02", summary="질문", result_count=3), history("ask", None, summary="깨짐")]
        requests = [request("pending", "2026-10-29 17:55", title="요청")]

        timeline = mypage_data.build_timeline(items, requests)

        self.assertEqual([(e["kind"], e["title"]) for e in timeline],
                         [("access_request", "요청"), ("ask", "질문")])
        self.assertEqual(timeline[1]["result_count"], 3)

    def test_blocked_flag_is_kept(self):
        timeline = mypage_data.build_timeline([history("view_document", "2026-10-29 10:00", is_blocked=True)], [])

        self.assertTrue(timeline[0]["is_blocked"])


class GroupByDayTest(unittest.TestCase):
    def test_labels_today_yesterday_and_older_dates(self):
        entries = [{"when": datetime(2026, 10, 29, 14, 0)}, {"when": datetime(2026, 10, 29, 9, 0)},
                   {"when": datetime(2026, 10, 28, 17, 0)}, {"when": datetime(2026, 10, 2, 8, 0)}]

        groups = mypage_data.group_by_day(entries, TODAY)

        self.assertEqual([(label, len(items)) for label, items in groups], [("오늘", 2), ("어제", 1), ("10.02", 1)])

    def test_empty_gives_no_groups(self):
        self.assertEqual(mypage_data.group_by_day([], date(2026, 10, 29)), [])


if __name__ == "__main__":
    unittest.main()
