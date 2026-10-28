"""audit_service 테스트. 저장소(audit_repository)는 mock 으로 바꿔 서비스 규칙만 확인한다.

확인 대상: 기록 시 KST 시각·IP 미저장, 역할별 조회 범위(권한), 날짜 범위 변환.
"""

import unittest
from datetime import date, datetime
from unittest.mock import patch

from app.admin.services import audit_service

# patch 대상. 서비스 모듈 안의 audit_repository 이름을 가짜로 바꾼다.
REPO = "app.admin.services.audit_service.audit_repository"

# 역할별 테스트 사용자: 전체 관리자 / 계열사 관리자(MVX) / 일반 직원.
SUPER = {"role": "super_admin", "company_id": None}
MVX_ADMIN = {"role": "company_admin", "company_id": "MVX"}
EMPLOYEE = {"role": "employee", "company_id": "MVX"}


def _row(log_id=1, blocked=0, **overrides):
    """저장소가 돌려주는 DB 행 모양의 기본값. 바꿀 컬럼만 overrides 로 넘긴다."""
    row = {
        "id": log_id,
        "created_at": datetime(2026, 10, 27, 9, 30, 5),
        "user_id": 1,
        "employee_no": "MVX-0001",
        "role": "employee",
        "company_code": "MVX",
        "action": "search",
        "target_type": None,
        "target_id": None,
        "query": None,
        "filters": None,
        "doc_ids": None,
        "doc_companies": None,
        "result_count": None,
        "is_blocked": blocked,
        "block_reason": None,
        "context_detail": None,
    }
    row.update(overrides)
    return row


class RecordAuditLogTest(unittest.TestCase):
    """record_audit_log: 로그 기록."""

    @patch(REPO)
    def test_records_values_as_given_with_kst_time(self, repo):
        """넘긴 값이 그대로 저장되고, 시각은 KST(서버 시간대와 무관)로 기록된다."""
        repo.insert_log.return_value = 7

        result = audit_service.record_audit_log(
            1, "view_document", "doc-1", "10.0.0.5", True, "권한 없음"
        )

        self.assertEqual(result, {"log_id": 7, "status": "success"})
        kwargs = repo.insert_log.call_args.kwargs
        expected = {
            "user_id": 1,
            "action": "view_document",
            "target_id": "doc-1",
            "is_blocked": True,
            "block_reason": "권한 없음",
        }
        self.assertEqual({key: kwargs[key] for key in expected}, expected)
        # 시각은 서비스가 만든다. tz 정보를 뗀 KST 시각이어야 DATETIME 에 그대로 들어간다.
        self.assertIsNone(kwargs["created_at"].tzinfo)
        kst_now = datetime.now(audit_service.KST).replace(tzinfo=None)
        self.assertLess(abs((kst_now - kwargs["created_at"]).total_seconds()), 5)

    @patch(REPO)
    def test_ip_address_is_accepted_but_never_stored(self, repo):
        """IP 는 인자로 받지만 저장소로 넘기지 않는다 (audit_logs 에 IP 컬럼이 없다)."""
        audit_service.record_audit_log(1, "login", None, "10.0.0.5", False, None)
        kwargs = repo.insert_log.call_args.kwargs
        self.assertNotIn("ip_address", kwargs)
        self.assertNotIn("10.0.0.5", str(kwargs))

    @patch(REPO)
    def test_optional_context_is_passed_through(self, repo):
        """선택 인자(대상·검색어·필터·문서·결과 수 등)가 저장소로 그대로 전달된다."""
        audit_service.record_audit_log(
            None,
            "login",
            None,
            None,
            True,
            "비밀번호 불일치",
            employee_no="MVX-0009",
            target_type="USER",
            query="q",
            filters={"year": 2025},
            doc_ids=["d1"],
            doc_companies=["MVX"],
            result_count=3,
            context_detail={"page": "login"},
        )
        kwargs = repo.insert_log.call_args.kwargs
        self.assertIsNone(kwargs["user_id"])
        self.assertEqual(kwargs["employee_no"], "MVX-0009")
        self.assertEqual(kwargs["target_type"], "USER")
        self.assertEqual(kwargs["filters"], {"year": 2025})
        self.assertEqual(kwargs["doc_ids"], ["d1"])
        self.assertEqual(kwargs["doc_companies"], ["MVX"])
        self.assertEqual(kwargs["result_count"], 3)
        self.assertEqual(kwargs["context_detail"], {"page": "login"})

    @patch(REPO)
    def test_block_reason_is_cut_to_column_length(self, repo):
        """차단 사유가 컬럼 길이를 넘으면 잘라서 저장한다 (긴 사유로 INSERT 가 실패하지 않게)."""
        audit_service.record_audit_log(1, "view_document", None, None, True, "가" * 300)
        reason = repo.insert_log.call_args.kwargs["block_reason"]
        self.assertEqual(len(reason), audit_service.BLOCK_REASON_MAX_LENGTH)

    @patch(REPO)
    def test_db_error_is_not_swallowed(self, repo):
        """DB 오류를 삼키지 않고 호출자에게 올려 기록 실패를 알 수 있게 한다."""
        repo.insert_log.side_effect = RuntimeError("db down")
        with self.assertRaises(RuntimeError):
            audit_service.record_audit_log(1, "login", None, None, False, None)


    @patch(REPO)
    def test_empty_action_type_is_rejected_before_db(self, repo):
        """행위 코드가 비어 있으면 DB 에 쓰지 않고 ValueError 로 거절한다."""
        with self.assertRaises(ValueError):
            audit_service.record_audit_log(1, "", None, None, False, None)
        repo.insert_log.assert_not_called()

    @patch(REPO)
    def test_blocked_flag_is_stored_as_bool_and_empty_reason_as_none(self, repo):
        """blocked 는 bool 로, 빈 차단 사유는 None 으로 저장한다."""
        audit_service.record_audit_log(1, "search", None, None, 0, "")
        kwargs = repo.insert_log.call_args.kwargs
        self.assertIs(kwargs["is_blocked"], False)
        self.assertIsNone(kwargs["block_reason"])


class SearchAuditLogsTest(unittest.TestCase):
    """search_audit_logs: 역할별 조회 범위와 필터 변환."""

    @patch(REPO)
    def test_company_admin_is_forced_to_own_company(self, repo):
        """계열사 관리자는 다른 계열사 사원번호를 필터로 줘도 자기 계열사로 고정된다."""
        repo.search_logs.return_value = ([_row()], 1)
        audit_service.search_audit_logs(MVX_ADMIN, {"employee_no": "ELV-0001"})
        self.assertEqual(repo.search_logs.call_args.kwargs["company_code"], "MVX")

    @patch(REPO)
    def test_super_admin_searches_all_companies(self, repo):
        """전체 관리자는 계열사 제한(None) 없이 모든 로그를 본다."""
        repo.search_logs.return_value = ([], 0)
        audit_service.search_audit_logs(SUPER, {})
        self.assertIsNone(repo.search_logs.call_args.kwargs["company_code"])

    @patch(REPO)
    def test_employee_and_companyless_admin_are_denied(self, repo):
        """일반 직원, 계열사 없는 관리자, 빈 사용자는 PermissionError 이고 DB 도 건드리지 않는다."""
        for user in (EMPLOYEE, {"role": "company_admin", "company_id": None}, {}, None):
            with self.subTest(user=user), self.assertRaises(PermissionError):
                audit_service.search_audit_logs(user, {})
        repo.search_logs.assert_not_called()

    @patch(REPO)
    def test_filters_and_date_range_are_passed_through(self, repo):
        """화면 필터 키가 저장소 인자로 바뀌어 전달되고, 날짜가 시각 범위로 변환된다."""
        repo.search_logs.return_value = ([], 0)
        audit_service.search_audit_logs(
            SUPER,
            {
                "employee_no": "MVX-0001",
                "action_type": "login",
                "start_date": date(2026, 10, 1),
                "end_date": date(2026, 10, 31),
                "blocked_only": True,
            },
        )
        kwargs = repo.search_logs.call_args.kwargs
        self.assertEqual(kwargs["employee_no"], "MVX-0001")
        self.assertEqual(kwargs["action"], "login")
        self.assertEqual(kwargs["start"], datetime(2026, 10, 1))
        # 종료일 당일을 포함하도록 다음 날 0시 미만으로 비교한다.
        self.assertEqual(kwargs["end"], datetime(2026, 11, 1))
        self.assertTrue(kwargs["blocked_only"])

    @patch(REPO)
    def test_paging_and_result_shape(self, repo):
        repo.search_logs.return_value = ([_row(1, blocked=1), _row(2)], 45)

        result = audit_service.search_audit_logs(SUPER, {}, page=2, size=20)

        kwargs = repo.search_logs.call_args.kwargs
        self.assertEqual((kwargs["limit"], kwargs["offset"]), (20, 20))
        self.assertEqual(result["total_count"], 45)
        self.assertEqual(result["total_pages"], 3)
        self.assertEqual(result["page"], 2)
        self.assertIs(result["logs"][0]["blocked"], True)
        self.assertIs(result["logs"][1]["blocked"], False)
        self.assertEqual(result["logs"][0]["log_id"], 1)
        self.assertEqual(result["logs"][0]["action_type"], "search")
        self.assertEqual(result["logs"][0]["company_code"], "MVX")
        self.assertNotIn("ip_address", result["logs"][0])
        self.assertEqual(result["logs"][0]["created_at"], "2026-10-27 09:30:05")

    @patch(REPO)
    def test_page_past_the_end_falls_back_to_last_page(self, repo):
        repo.search_logs.side_effect = [([], 5), ([_row()], 5)]

        result = audit_service.search_audit_logs(SUPER, {}, page=9, size=20)

        self.assertEqual(result["page"], 1)
        self.assertEqual(repo.search_logs.call_args.kwargs["offset"], 0)
        self.assertEqual(len(result["logs"]), 1)

    @patch(REPO)
    def test_empty_result_has_one_page(self, repo):
        repo.search_logs.return_value = ([], 0)
        result = audit_service.search_audit_logs(SUPER, {})
        self.assertEqual(
            (result["logs"], result["total_count"], result["page"], result["total_pages"]),
            ([], 0, 1, 1),
        )


    @patch(REPO)
    def test_invalid_page_and_size_are_corrected(self, repo):
        """0 이하이거나 숫자가 아닌 page, 지나치게 큰 size 는 안전한 값으로 보정한다."""
        repo.search_logs.return_value = ([], 0)
        audit_service.search_audit_logs(SUPER, {}, page=0, size=100000)
        kwargs = repo.search_logs.call_args.kwargs
        self.assertEqual((kwargs["limit"], kwargs["offset"]), (audit_service.MAX_PAGE_SIZE, 0))
        audit_service.search_audit_logs(SUPER, {}, page="abc", size="x")
        kwargs = repo.search_logs.call_args.kwargs
        self.assertEqual((kwargs["limit"], kwargs["offset"]), (1, 0))

    @patch(REPO)
    def test_empty_filter_values_are_not_applied(self, repo):
        """화면에서 빈 문자열·None 으로 온 필터는 조건으로 걸지 않는다."""
        repo.search_logs.return_value = ([], 0)
        audit_service.search_audit_logs(
            SUPER, {"employee_no": "", "action_type": None, "start_date": "", "end_date": None}
        )
        kwargs = repo.search_logs.call_args.kwargs
        self.assertEqual(
            (kwargs["employee_no"], kwargs["action"], kwargs["start"], kwargs["end"]),
            (None, None, None, None),
        )
        self.assertFalse(kwargs["blocked_only"])

    @patch(REPO)
    def test_datetime_filter_values_use_their_date_only(self, repo):
        """날짜 대신 datetime 이 와도 시각은 버리고 날짜 기준으로 범위를 만든다."""
        repo.search_logs.return_value = ([], 0)
        audit_service.search_audit_logs(
            SUPER, {"start_date": datetime(2026, 10, 1, 15, 30), "end_date": datetime(2026, 10, 31, 8, 0)}
        )
        kwargs = repo.search_logs.call_args.kwargs
        self.assertEqual((kwargs["start"], kwargs["end"]), (datetime(2026, 10, 1), datetime(2026, 11, 1)))


class AuditLogDetailTest(unittest.TestCase):
    """get_audit_log_detail: 상세 조회와 권한."""

    @patch(REPO)
    def test_detail_is_scoped_by_company(self, repo):
        """상세 조회는 사용자의 계열사 범위로 한정되고 차단 사유도 함께 돌려준다."""
        repo.get_log.return_value = _row(3, blocked=1, block_reason="타사 confidential")
        detail = audit_service.get_audit_log_detail(3, MVX_ADMIN)
        repo.get_log.assert_called_once_with(3, "MVX")
        self.assertEqual(detail["block_reason"], "타사 confidential")

    @patch(REPO)
    def test_missing_or_out_of_scope_log_raises_lookup_error(self, repo):
        """없는 로그와 범위 밖 로그는 구분 없이 같은 LookupError 로 처리한다."""
        repo.get_log.return_value = None
        with self.assertRaises(LookupError):
            audit_service.get_audit_log_detail(99, MVX_ADMIN)

    @patch(REPO)
    def test_employee_cannot_read_detail(self, repo):
        """일반 직원은 상세를 볼 수 없고, 권한 확인이 DB 조회보다 먼저 이뤄진다."""
        with self.assertRaises(PermissionError):
            audit_service.get_audit_log_detail(1, EMPLOYEE)
        repo.get_log.assert_not_called()


class RecentAndOptionsTest(unittest.TestCase):
    """대시보드 최근 로그와 필터 선택지: 조회와 같은 권한 범위를 따른다."""

    @patch(REPO)
    def test_recent_logs_scoped_and_limited(self, repo):
        """최근 로그는 계열사 범위와 건수 제한(limit)을 적용한다."""
        repo.list_recent.return_value = [_row(1), _row(2)]
        logs = audit_service.get_recent_audit_logs(MVX_ADMIN, limit=2)
        repo.list_recent.assert_called_once_with("MVX", 2)
        self.assertEqual([log["log_id"] for log in logs], [1, 2])

    @patch(REPO)
    def test_recent_logs_denied_for_employee(self, repo):
        """일반 직원은 최근 로그를 볼 수 없다."""
        with self.assertRaises(PermissionError):
            audit_service.get_recent_audit_logs(EMPLOYEE)

    @patch(REPO)
    def test_filter_options_use_same_scope(self, repo):
        """필터 선택지는 조회와 같은 계열사 범위로 모아 화면용 키(users, action_types)로 돌려준다."""
        repo.list_employee_nos.return_value = ["MVX-0001"]
        repo.list_actions.return_value = ["login", "search"]
        options = audit_service.get_audit_filter_options(MVX_ADMIN)
        repo.list_employee_nos.assert_called_once_with("MVX")
        self.assertEqual(
            options, {"users": ["MVX-0001"], "action_types": ["login", "search"]}
        )


class ScreenValuesTest(unittest.TestCase):
    """화면용 값(이름·행동 이름·대상 이름), 요약, CSV."""

    def _repo(self, repo, rows, users=None, documents=None):
        repo.search_logs.return_value = (rows, len(rows))
        repo.lookup_user_names.return_value = users or {}
        repo.lookup_documents.return_value = documents or {}

    @patch(REPO)
    def test_rows_get_user_name_action_label_and_document_title(self, repo):
        """이름·행동 이름·문서 제목이 붙는다."""
        self._repo(
            repo,
            [_row(1, action="view_document", target_type="document", target_id="d1", user_id=7)],
            users={7: "홍길동"},
            documents={"d1": {"title": "사양서", "company_id": "MVX"}},
        )
        log = audit_service.search_audit_logs(MVX_ADMIN)["logs"][0]
        self.assertEqual((log["user_name"], log["action_label"], log["target_label"]), ("홍길동", "원문 열기", "사양서"))

    @patch(REPO)
    def test_other_company_document_title_is_hidden_from_company_admin(self, repo):
        """계열사 관리자는 타사 문서의 제목을 볼 수 없다. 최종 어드민은 볼 수 있다."""
        docs = {"d1": {"title": "ELV 기밀 단가표", "company_id": "ELV"}}
        row = lambda: _row(1, action="view_document", target_type="document", target_id="d1")  # noqa: E731
        self._repo(repo, [row()], documents=docs)
        self.assertEqual(audit_service.search_audit_logs(MVX_ADMIN)["logs"][0]["target_label"], "타사 문서")
        self._repo(repo, [row()], documents=docs)
        self.assertEqual(audit_service.search_audit_logs(SUPER)["logs"][0]["target_label"], "ELV 기밀 단가표")

    @patch(REPO)
    def test_target_falls_back_to_query_then_dash(self, repo):
        """문서가 아닌 행위는 검색어, 그것도 없으면 "-" 를 대상으로 보여 준다. 삭제된 문서는 안내 문구."""
        self._repo(
            repo,
            [
                _row(1, action="search", query="AGV 사양"),
                _row(2, action="login"),
                _row(3, action="view_document", target_type="document", target_id="gone"),
            ],
        )
        labels = [log["target_label"] for log in audit_service.search_audit_logs(MVX_ADMIN)["logs"]]
        self.assertEqual(labels, ["AGV 사양", "-", "삭제된 문서"])

    @patch(REPO)
    def test_summary_counts_today_and_hours(self, repo):
        """오늘·어제 건수와 9~18시 시간대별 리스트(10칸)를 만든다. 두 번 조회한다(오늘, 어제)."""
        day = {
            "total": 5,
            "blocked": 2,
            "blocked_reasons": [("기밀", 2)],
            "downloads": 3,
            "blocked_downloads": 0,
            "hourly": {9: 1, 14: 4, 23: 9},
        }
        repo.summarize.side_effect = [day, {**day, "total": 3}]

        got = audit_service.get_audit_summary(MVX_ADMIN, date(2026, 10, 28))

        self.assertEqual((got["today_count"], got["yesterday_count"], got["blocked_count"]), (5, 3, 2))
        self.assertEqual(got["hourly"], [1, 0, 0, 0, 0, 4, 0, 0, 0, 0])  # 9시·14시만, 23시는 범위 밖
        first, second = repo.summarize.call_args_list
        self.assertEqual(first.args, ("MVX", datetime(2026, 10, 28), datetime(2026, 10, 29)))
        self.assertEqual(second.args, ("MVX", datetime(2026, 10, 27), datetime(2026, 10, 28)))

    @patch(REPO)
    def test_summary_and_scope_name_denied_for_employee(self, repo):
        """일반 사원은 요약·범위 이름을 볼 수 없고 DB 도 읽지 않는다."""
        with self.assertRaises(PermissionError):
            audit_service.get_audit_summary(EMPLOYEE)
        with self.assertRaises(PermissionError):
            audit_service.get_audit_scope_name(EMPLOYEE)
        repo.summarize.assert_not_called()

    @patch(REPO)
    def test_scope_name(self, repo):
        """계열사 관리자는 회사명, 최종 어드민은 "전체 계열사"."""
        repo.get_company_name.return_value = "현대무벡스"
        self.assertEqual(audit_service.get_audit_scope_name(MVX_ADMIN), "현대무벡스")
        self.assertEqual(audit_service.get_audit_scope_name(SUPER), "전체 계열사")
        repo.get_company_name.return_value = None
        self.assertEqual(audit_service.get_audit_scope_name(MVX_ADMIN), "MVX")

    @patch("app.admin.services.audit_service.record_audit_log")
    @patch(REPO)
    def test_csv_export_escapes_formulas_and_records_the_export(self, repo, record):
        """CSV 는 BOM 으로 시작하고, 수식으로 읽힐 값은 ' 가 붙으며, 내려받기 자체가 기록된다."""
        self._repo(repo, [_row(1, action="search", query='=HYPERLINK("http://x")')], users={1: "홍길동"})

        text = audit_service.export_audit_logs_csv(MVX_ADMIN, {"action_type": "search"})

        self.assertTrue(text.startswith("\ufeff시각,"))
        self.assertIn("'=HYPERLINK", text)
        self.assertNotIn(",=HYPERLINK", text)
        args, kwargs = record.call_args
        self.assertEqual(args[1], "audit_export")
        self.assertEqual((kwargs["result_count"], kwargs["filters"]), (1, {"action_type": "search"}))

    @patch("app.admin.services.audit_service.record_audit_log", side_effect=RuntimeError("db down"))
    @patch(REPO)
    def test_csv_export_fails_when_it_cannot_be_recorded(self, repo, record):
        """내려받기 기록이 실패하면 파일을 주지 않는다 (기록 없는 반출 금지)."""
        self._repo(repo, [_row(1)])
        with self.assertRaises(RuntimeError):
            audit_service.export_audit_logs_csv(MVX_ADMIN)

    @patch(REPO)
    def test_csv_export_denied_for_employee(self, repo):
        """일반 사원은 내려받을 수 없다."""
        with self.assertRaises(PermissionError):
            audit_service.export_audit_logs_csv(EMPLOYEE)
        repo.search_logs.assert_not_called()


if __name__ == "__main__":
    unittest.main()
