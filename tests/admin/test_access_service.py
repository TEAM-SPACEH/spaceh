"""access_service(A-03 그룹사 공유) 테스트. 저장소(access_repository)·감사 로그는 mock 으로 바꿔 서비스 규칙만 확인한다.

실행: python -m unittest tests.admin.test_access_service

확인 대상: 공유 ON/OFF 정상 변경, confidential 거부, 타사 계열사 관리자 거부, 최종 어드민 허용,
일반 사원 거부, 차단 시 DB 미변경·감사 로그 기록, 목록 조회 범위.
"""

import unittest
from datetime import datetime
from unittest.mock import patch

from app.admin.services import access_service

REPO = "app.admin.services.access_service.access_repository"
AUDIT = "app.admin.services.access_service.record_audit_log"

SUPER = {"id": 1, "role": "super_admin", "company_id": None}
MVX_ADMIN = {"id": 2, "role": "company_admin", "company_id": "MVX"}
ELV_ADMIN = {"id": 3, "role": "company_admin", "company_id": "ELV"}
MVX_EMPLOYEE = {"id": 4, "role": "employee", "company_id": "MVX"}


def _doc(company_id="MVX", access_level="internal", is_group_shared=0):
    """저장소가 돌려주는 documents 행 모양."""
    return {
        "doc_id": "doc-1",
        "company_id": company_id,
        "access_level": access_level,
        "is_group_shared": is_group_shared,
    }


@patch(AUDIT)
@patch(REPO)
class SetGroupShareTest(unittest.TestCase):
    """set_group_share: 공유 변경."""

    def test_company_admin_can_turn_share_on_and_off_for_own_internal_document(self, repo, audit):
        """자사 internal 문서는 ON·OFF 모두 바뀌고 결과 모양이 명세와 같다."""
        for enabled, before in ((True, 0), (False, 1)):
            with self.subTest(enabled=enabled):
                repo.get_document.return_value = _doc(is_group_shared=before)

                result = access_service.set_group_share("doc-1", enabled, MVX_ADMIN)

                self.assertEqual(
                    result,
                    {
                        "doc_id": "doc-1",
                        "is_group_shared": enabled,
                        "status": "success",
                        "message": "공유 설정이 변경되었습니다.",
                    },
                )
                args = repo.update_group_share.call_args.args
                self.assertEqual(args[:3], ("doc-1", enabled, MVX_ADMIN["id"]))
                self.assertIsNone(args[3].tzinfo)  # DATETIME 컬럼에 그대로 들어가는 시각

    def test_confidential_document_cannot_be_shared(self, repo, audit):
        """confidential 은 계열사 관리자·최종 어드민 모두 ValueError 이고 DB 는 바뀌지 않는다."""
        repo.get_document.return_value = _doc(access_level="confidential")
        for user in (MVX_ADMIN, SUPER):
            with self.subTest(role=user["role"]):
                with self.assertRaisesRegex(ValueError, "기밀"):
                    access_service.set_group_share("doc-1", True, user)
        repo.update_group_share.assert_not_called()

    def test_public_document_cannot_be_shared(self, repo, audit):
        """public 문서도 공유 대상이 아니다 (이미 전 사원이 본다)."""
        repo.get_document.return_value = _doc(access_level="public")
        with self.assertRaises(ValueError):
            access_service.set_group_share("doc-1", True, SUPER)
        repo.update_group_share.assert_not_called()

    def test_company_admin_of_other_company_is_denied(self, repo, audit):
        """타 계열사 관리자는 PermissionError 이고 DB 는 바뀌지 않는다."""
        repo.get_document.return_value = _doc(company_id="MVX")

        with self.assertRaisesRegex(PermissionError, "자사 문서만 공유 설정을 변경할 수 있습니다."):
            access_service.set_group_share("doc-1", True, ELV_ADMIN)

        repo.update_group_share.assert_not_called()

    def test_company_admin_without_company_is_denied(self, repo, audit):
        """소속이 없는 계열사 관리자가 소속 없는 문서와 None == None 으로 통과하지 못한다."""
        repo.get_document.return_value = _doc(company_id=None)
        with self.assertRaises(PermissionError):
            access_service.set_group_share("doc-1", True, {"id": 9, "role": "company_admin", "company_id": None})
        repo.update_group_share.assert_not_called()

    def test_super_admin_can_toggle_other_company_internal_document(self, repo, audit):
        """최종 어드민은 타 계열사 internal 문서도 바꿀 수 있다."""
        repo.get_document.return_value = _doc(company_id="ELV")

        result = access_service.set_group_share("doc-1", True, SUPER)

        self.assertTrue(result["is_group_shared"])
        self.assertEqual(repo.update_group_share.call_args.args[:3], ("doc-1", True, SUPER["id"]))

    def test_employee_is_denied_before_any_db_access(self, repo, audit):
        """일반 사원은 문서를 조회하기도 전에 거부된다."""
        with self.assertRaises(PermissionError):
            access_service.set_group_share("doc-1", True, MVX_EMPLOYEE)
        repo.get_document.assert_not_called()
        repo.update_group_share.assert_not_called()

    def test_missing_document_raises_lookup_error(self, repo, audit):
        """없는 문서는 LookupError 이다."""
        repo.get_document.return_value = None
        with self.assertRaises(LookupError):
            access_service.set_group_share("nope", True, SUPER)
        repo.update_group_share.assert_not_called()

    def test_success_is_recorded_in_audit_log(self, repo, audit):
        """성공하면 share_change 로 기록하고 문서 회사·이전 값을 남긴다."""
        repo.get_document.return_value = _doc(is_group_shared=0)

        access_service.set_group_share("doc-1", True, MVX_ADMIN)

        args, kwargs = audit.call_args
        # user_id, action_type, target_id, ip_address, blocked, block_reason
        self.assertEqual(args, (MVX_ADMIN["id"], "share_change", "doc-1", None, False, None))
        self.assertEqual(kwargs["target_type"], "document")
        self.assertEqual(kwargs["doc_companies"], ["MVX"])
        self.assertEqual(kwargs["context_detail"], {"is_group_shared": True, "previous": False})

    def test_blocked_attempt_is_recorded_in_audit_log(self, repo, audit):
        """막힌 시도도 blocked=True 와 사유로 기록된다."""
        repo.get_document.return_value = _doc(access_level="confidential")

        with self.assertRaises(ValueError):
            access_service.set_group_share("doc-1", True, MVX_ADMIN)

        args = audit.call_args.args
        self.assertTrue(args[4])
        self.assertIn("기밀", args[5])

    def test_audit_failure_does_not_hide_success(self, repo, audit):
        """감사 로그 기록이 실패해도 이미 바뀐 값에 대해 성공을 돌려준다 (실패는 로그로 남는다)."""
        repo.get_document.return_value = _doc()
        audit.side_effect = RuntimeError("db down")

        with self.assertLogs(access_service.logger, level="ERROR"):
            result = access_service.set_group_share("doc-1", True, MVX_ADMIN)

        self.assertEqual(result["status"], "success")


@patch(REPO)
class GetManageableDocumentsTest(unittest.TestCase):
    """get_manageable_documents: 관리자 범위 목록."""

    def _row(self, doc_id="doc-1", company_id="MVX"):
        return {
            "doc_id": doc_id,
            "company_id": company_id,
            "title": "제목",
            "file_name": "a.pdf",
            "file_format": "pdf",
            "doc_type": "report",
            "access_level": "internal",
            "is_group_shared": 1,
            "chunk_count": 54,
            "index_status": "done",
            "created_at": datetime(2026, 10, 27, 9, 30),
        }

    def test_company_admin_is_limited_to_own_company_even_with_filter(self, repo):
        """계열사 관리자는 company_filter 를 다른 회사로 줘도 자사 문서만 조회한다."""
        repo.list_documents.return_value = ([self._row()], 1)

        access_service.get_manageable_documents(MVX_ADMIN, company_filter="ELV")

        kwargs = repo.list_documents.call_args.kwargs
        self.assertEqual(kwargs["company_id"], "MVX")
        self.assertEqual(kwargs["access_levels"], ("internal", "confidential"))

    def test_super_admin_can_filter_company_or_see_all(self, repo):
        """최종 어드민은 계열사를 고르면 그 회사, 안 고르면 전체를 본다."""
        repo.list_documents.return_value = ([], 0)

        access_service.get_manageable_documents(SUPER, company_filter="ELV")
        self.assertEqual(repo.list_documents.call_args.kwargs["company_id"], "ELV")

        access_service.get_manageable_documents(SUPER)
        self.assertIsNone(repo.list_documents.call_args.kwargs["company_id"])

    def test_employee_is_denied(self, repo):
        """일반 사원은 PermissionError 이고 DB 를 읽지 않는다."""
        with self.assertRaises(PermissionError):
            access_service.get_manageable_documents(MVX_EMPLOYEE)
        repo.list_documents.assert_not_called()

    def test_result_shape_and_conversion(self, repo):
        """반환 모양, bool·날짜 문자열 변환, 페이지 계산."""
        repo.list_documents.return_value = ([self._row()], 45)

        result = access_service.get_manageable_documents(SUPER, page=2, size=20)

        self.assertEqual((result["total_count"], result["page"], result["total_pages"]), (45, 2, 3))
        doc = result["documents"][0]
        self.assertEqual((doc["doc_type"], doc["chunk_count"], doc["index_status"]), ("report", 54, "done"))
        self.assertIs(doc["is_group_shared"], True)
        self.assertEqual(doc["created_at"], "2026-10-27")
        self.assertEqual(repo.list_documents.call_args.kwargs["offset"], 20)

    def test_page_beyond_last_is_corrected(self, repo):
        """범위를 벗어난 페이지는 마지막 페이지로 다시 읽는다."""
        repo.list_documents.side_effect = [([], 5), ([self._row()], 5)]

        result = access_service.get_manageable_documents(SUPER, page=9, size=20)

        self.assertEqual(result["page"], 1)
        self.assertEqual(repo.list_documents.call_count, 2)

    def test_keyword_and_share_filter_are_passed_through(self, repo):
        """검색어는 앞뒤 공백을 떼고, 공유 상태 필터는 그대로 넘긴다."""
        repo.list_documents.return_value = ([], 0)

        access_service.get_manageable_documents(SUPER, keyword="  실적 ", share_filter=False)

        kwargs = repo.list_documents.call_args.kwargs
        self.assertEqual(kwargs["keyword"], "실적")
        self.assertIs(kwargs["is_group_shared"], False)


@patch(REPO)
class ShareSummaryAndFilterTest(unittest.TestCase):
    """공유 요약 집계와 보안 등급 필터."""

    def test_summary_is_scoped_to_company_admins_company(self, repo):
        """계열사 관리자는 계열사 선택값과 무관하게 자사 문서만 센다. 합계도 함께 준다."""
        repo.count_share_status.return_value = {"shared": 3, "unshared": 5, "confidential": 2}

        got = access_service.get_share_summary(MVX_ADMIN, "ELV")

        repo.count_share_status.assert_called_once_with("MVX")
        self.assertEqual(got, {"shared": 3, "unshared": 5, "confidential": 2, "internal_total": 8})

    def test_super_admin_summary_can_pick_company_or_all(self, repo):
        """최종 어드민은 계열사를 고르면 그 회사, 안 고르면 전체를 센다."""
        repo.count_share_status.return_value = {"shared": 0, "unshared": 0, "confidential": 0}
        access_service.get_share_summary(SUPER, "ELV")
        repo.count_share_status.assert_called_with("ELV")
        access_service.get_share_summary(SUPER)
        repo.count_share_status.assert_called_with(None)

    def test_summary_denied_for_employee_before_db(self, repo):
        """일반 사원은 거부되고 DB 를 읽지 않는다."""
        with self.assertRaises(PermissionError):
            access_service.get_share_summary(MVX_EMPLOYEE)
        repo.count_share_status.assert_not_called()

    def test_access_level_filter_narrows_only_to_share_target_levels(self, repo):
        """internal·confidential 만 그 등급으로 좁히고, public 같은 값은 무시해 전체 대상 등급을 읽는다."""
        repo.list_documents.return_value = ([], 0)

        access_service.get_manageable_documents(SUPER, access_level="confidential")
        self.assertEqual(repo.list_documents.call_args.kwargs["access_levels"], ("confidential",))
        access_service.get_manageable_documents(SUPER, access_level="public")
        self.assertEqual(repo.list_documents.call_args.kwargs["access_levels"], ("internal", "confidential"))


@patch(REPO)
class ShareScopeNameTest(unittest.TestCase):
    def test_company_admin_gets_company_name_and_falls_back_to_code(self, repo):
        """계열사 관리자는 회사명, 회사명을 못 찾으면 코드를 보여 준다."""
        repo.get_company_name.return_value = "현대무벡스"
        self.assertEqual(access_service.get_share_scope_name(MVX_ADMIN), "현대무벡스")
        repo.get_company_name.return_value = None
        self.assertEqual(access_service.get_share_scope_name(MVX_ADMIN), "MVX")

    def test_super_admin_scope_is_all_companies(self, repo):
        """최종 어드민은 "전체 계열사"이고 회사명을 조회하지 않는다."""
        self.assertEqual(access_service.get_share_scope_name(SUPER), "전체 계열사")
        repo.get_company_name.assert_not_called()

    def test_employee_is_denied(self, repo):
        """일반 사원은 거부된다."""
        with self.assertRaises(PermissionError):
            access_service.get_share_scope_name(MVX_EMPLOYEE)


if __name__ == "__main__":
    unittest.main()
