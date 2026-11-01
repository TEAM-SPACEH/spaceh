"""download_policy_service(A-06 보고서 다운로드 판정) 테스트. 문서 접근 확인·감사 로그는 mock 으로 바꿔 DB 없이 돈다.

실행: python -m unittest tests.reports.test_download_policy_service

확인 대상: 전부 볼 수 있으면 허용(워터마크 포함), 하나라도 못 보면 전체 차단, 로그인 없음·근거 없음 차단,
지원하지 않는 형식 거부, 차단 시 감사 로그 기록, 허용 시 미기록, 감사 로그 실패가 판정을 막지 않음.
"""

import unittest
from unittest.mock import patch

from app.reports.services import download_policy_service as policy

ACCESS = "app.reports.services.download_policy_service.check_document_access"
AUDIT = "app.reports.services.download_policy_service.record_audit_log"

EMPLOYEE = {"id": 4, "role": "employee", "company_id": "MVX", "name": "박사원", "employee_no": "MVX-0001"}
SUPER = {"id": 1, "role": "super_admin", "company_id": None}


def _only_visible(*visible_ids):
    """주어진 문서만 볼 수 있는 check_document_access 대역."""
    return lambda user_id, doc_id: doc_id in visible_ids


@patch(AUDIT)
@patch(ACCESS)
class DecideReportDownloadTest(unittest.TestCase):

    def test_allowed_when_every_source_document_is_visible(self, access, audit):
        access.side_effect = _only_visible("d1", "d2")

        result = policy.decide_report_download(EMPLOYEE, ["d1", "d2"], "docx", report_id="r1")

        self.assertTrue(result["allowed"])
        self.assertIsNone(result["reason"])
        self.assertEqual(result["blocked_doc_ids"], [])
        # 합의한 형식: 워터마크: 이름(사원번호) · 일시 다운로드 · 외부 유출 금지
        self.assertRegex(
            result["watermark"],
            r"^워터마크: 박사원\(MVX-0001\) · \d{4}-\d{2}-\d{2} \d{2}:\d{2} 다운로드 · 외부 유출 금지$",
        )
        audit.assert_not_called()

    def test_watermark_without_name_uses_user_id(self, access, audit):
        # 세션에 이름·사원번호가 없으면 사용자 번호라도 남겨 누가 받았는지 알 수 있게 한다
        access.return_value = True

        result = policy.decide_report_download(SUPER, ["d1"], "md")

        self.assertTrue(result["allowed"])
        self.assertIn("이름 없음(사용자 1)", result["watermark"])

    def test_confidential_report_is_blocked_even_if_visible(self, access, audit):
        # 팀 결정(10/30): 근거에 기밀 문서가 있으면 볼 권한이 있어도 내려받기 차단
        access.return_value = True

        result = policy.decide_report_download(
            SUPER, ["d1"], "docx", report_id="r9", max_access_level="confidential",
        )

        self.assertFalse(result["allowed"])
        self.assertIsNone(result["watermark"])
        self.assertIn("기밀", result["reason"])
        access.assert_not_called()  # 등급만으로 막히므로 문서마다 권한을 볼 필요가 없다
        self.assertEqual(audit.call_args.args[:5], (1, "download", "r9", None, True))

    def test_internal_report_is_allowed_with_watermark(self, access, audit):
        access.return_value = True

        result = policy.decide_report_download(EMPLOYEE, ["d1"], "md", max_access_level="internal")

        self.assertTrue(result["allowed"])
        self.assertIsNotNone(result["watermark"])

    def test_one_invisible_document_blocks_whole_report(self, access, audit):
        access.side_effect = _only_visible("d1")

        result = policy.decide_report_download(EMPLOYEE, ["d1", "d2", "d3"], "md", report_id="r1")

        self.assertFalse(result["allowed"])
        self.assertIsNone(result["watermark"])
        self.assertEqual(result["blocked_doc_ids"], ["d2", "d3"])
        self.assertIn("2건", result["reason"])

    def test_blocked_attempt_is_recorded_in_audit_log(self, access, audit):
        access.side_effect = _only_visible("d1")

        result = policy.decide_report_download(EMPLOYEE, ["d1", "d2"], "md", report_id="r1")

        audit.assert_called_once()
        args, kwargs = audit.call_args
        self.assertEqual(args[:5], (4, "download", "r1", None, True))
        self.assertEqual(args[5], result["reason"])
        self.assertEqual(kwargs["target_type"], "report")
        self.assertEqual(kwargs["doc_ids"], ["d1", "d2"])

    def test_duplicate_doc_ids_are_checked_once(self, access, audit):
        access.return_value = True

        policy.decide_report_download(EMPLOYEE, ["d1", "d1", "d2", "d1"], "md")

        self.assertEqual([call.args[1] for call in access.call_args_list], ["d1", "d2"])

    def test_not_logged_in_is_blocked_without_checking_documents(self, access, audit):
        for user in (None, {}):
            with self.subTest(user=user):
                result = policy.decide_report_download(user, ["d1"], "md")

                self.assertFalse(result["allowed"])
        access.assert_not_called()
        self.assertEqual(audit.call_args.args[0], None)

    def test_empty_source_list_is_blocked(self, access, audit):
        result = policy.decide_report_download(EMPLOYEE, [], "md")

        self.assertFalse(result["allowed"])
        self.assertEqual(result["blocked_doc_ids"], [])
        audit.assert_called_once()

    def test_unsupported_format_raises_and_checks_nothing(self, access, audit):
        with self.assertRaises(ValueError):
            policy.decide_report_download(EMPLOYEE, ["d1"], "pdf")

        access.assert_not_called()
        audit.assert_not_called()

    def test_audit_failure_does_not_change_decision(self, access, audit):
        access.side_effect = _only_visible()
        audit.side_effect = RuntimeError("DB down")

        with self.assertLogs(policy.logger, level="ERROR"):
            result = policy.decide_report_download(EMPLOYEE, ["d1"], "md")

        self.assertFalse(result["allowed"])


if __name__ == "__main__":
    unittest.main()
