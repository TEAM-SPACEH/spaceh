"""S-05 원문 보기 서비스 단위 테스트."""

# ─────────────────────────────────────────────────────────────
# DB와 진짜 파일 없이 테스트하려고
#   - find_by_id(DB 조회)는 patch로 가짜 문서를 돌려주게 하고
#   - 임시 폴더를 data/uploads로 바꿔 끼운 뒤 그 안에 3페이지짜리 빈 PDF를 만들어요.
# 권한 확인은 팀장님의 진짜 check_search_permission()을 그대로 써요.
# 그래야 "다른 회사 기밀 문서가 새지 않는다"는 권한 누출 테스트가 진짜 규칙으로 돌아가요.
# ─────────────────────────────────────────────────────────────

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pypdfium2 as pdfium

from app.documents.services import document_service

FIND_BY_ID = "app.documents.services.document_service.find_by_id"
# 승인 문서 목록은 DB를 읽으므로 "승인 문서 없음"으로 바꿔 끼워요.
APPROVED_DOC_IDS = "app.permissions.services.permission_service.get_approved_doc_ids"
# 감사 로그(A-04)도 DB에 쓰므로 가짜로 바꿔 끼워요. 안 막으면 DB를 찾다 실패해요.
RECORD_AUDIT_LOG = "app.documents.services.document_service.record_audit_log"

ELV_EMPLOYEE = {"id": 1, "role": "employee", "company_id": "ELV"}
MVX_EMPLOYEE = {"id": 2, "role": "employee", "company_id": "MVX"}


def make_document(doc_id="doc-elv", access_level="internal", **overrides) -> dict:
    """documents 테이블 1행 모양의 가짜 문서 (현대엘리베이터 PDF)."""
    document = {
        "doc_id": doc_id,
        "company_id": "ELV",
        "title": "2025 사업보고서(가상)",
        "file_name": "elv_report.pdf",
        "file_format": "pdf",
        "source_type": "internal",
        "source_url": None,
        "doc_no": None,
        "access_level": access_level,
        "is_group_shared": 0,
        "file_path": "data/uploads/elv_report.pdf",
        "page_count": 3,
    }
    document.update(overrides)
    return document


@patch(APPROVED_DOC_IDS, return_value=[])
class DocumentServiceTest(unittest.TestCase):
    # 클래스 위의 @patch는 아래 모든 test_ 함수에 적용되고, 가짜 객체가 마지막 인자로 들어와요.

    def setUp(self):
        # 임시 폴더를 저장소 루트처럼 쓰고, 그 안의 data/uploads에 PDF를 만들어요.
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        upload_dir = root / "data" / "uploads"
        upload_dir.mkdir(parents=True)

        pdf = pdfium.PdfDocument.new()
        for _ in range(3):
            pdf.new_page(595, 842)  # A4 빈 페이지
        self.pdf_path = upload_dir / "elv_report.pdf"
        pdf.save(str(self.pdf_path))
        pdf.close()

        # core.config의 경로를 임시 폴더로 바꿔 끼워요. 테스트가 끝나면 원래대로 돌아가요.
        for name, value in (("ROOT_DIR", root), ("UPLOAD_DIR", upload_dir)):
            patcher = patch(f"core.config.{name}", value)
            patcher.start()
            self.addCleanup(patcher.stop)

        # 감사 로그 기록 함수를 가짜로 바꿔요. self.audit로 "어떤 인자로 불렸는지" 확인할 수 있어요.
        audit_patcher = patch(RECORD_AUDIT_LOG)
        self.audit = audit_patcher.start()
        self.addCleanup(audit_patcher.stop)

    def assert_audit(self, action: str, user: dict, blocked: bool, reason=None):
        """감사 로그가 정확히 1번, 이 인자로 기록됐는지 확인한다."""
        self.audit.assert_called_once_with(
            user.get("id"), action, "doc-elv", None, blocked, reason,
            target_type="document", doc_ids=["doc-elv"], doc_companies=["ELV"],
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    # ── 권한 누출 ─────────────────────────────────────────────

    def test_other_company_internal_document_is_blocked(self, _approved):
        # 현대무벡스 사원이 현대엘리베이터 내부(공유 OFF) 문서를 열려는 상황
        with patch(FIND_BY_ID, return_value=make_document()):
            self.assertIsNone(document_service.download_document("doc-elv", MVX_EMPLOYEE))
            self.assertIsNone(document_service.get_page_image("doc-elv", 1, MVX_EMPLOYEE))
            viewer = document_service.get_viewer_document("doc-elv", MVX_EMPLOYEE)

        # 권한 없는 사람에게는 제목·회사만 가고, 파일 위치·형식은 가지 않아야 해요.
        self.assertFalse(viewer["can_view"])
        self.assertNotIn("file_name", viewer)
        self.assertNotIn("file_format", viewer)

    def test_unknown_user_is_blocked(self, _approved):
        with patch(FIND_BY_ID, return_value=make_document(access_level="public")):
            self.assertIsNone(document_service.download_document("doc-elv", {}))

    # ── 정상 열람 ─────────────────────────────────────────────

    def test_own_company_document_download(self, _approved):
        with patch(FIND_BY_ID, return_value=make_document()):
            result = document_service.download_document("doc-elv", ELV_EMPLOYEE)
        self.assertEqual(result, self.pdf_path.read_bytes())

    def test_page_image_is_png(self, _approved):
        with patch(FIND_BY_ID, return_value=make_document()):
            image = document_service.get_page_image("doc-elv", 2, ELV_EMPLOYEE)
        # PNG 파일은 항상 이 8바이트로 시작해요.
        self.assertTrue(image.startswith(b"\x89PNG\r\n\x1a\n"))

    def test_page_out_of_range(self, _approved):
        with patch(FIND_BY_ID, return_value=make_document()):
            self.assertIsNone(document_service.get_page_image("doc-elv", 0, ELV_EMPLOYEE))
            self.assertIsNone(document_service.get_page_image("doc-elv", 4, ELV_EMPLOYEE))

    def test_unknown_document(self, _approved):
        with patch(FIND_BY_ID, return_value=None):
            self.assertIsNone(document_service.get_viewer_document("nope", ELV_EMPLOYEE))
            self.assertIsNone(document_service.download_document("nope", ELV_EMPLOYEE))

    # ── 파일 경로 보안 ────────────────────────────────────────

    def test_path_outside_uploads_is_rejected(self, _approved):
        # file_path에 "../"를 넣어 uploads 밖 파일을 꺼내려는 상황
        (Path(self.temp_dir.name) / "secret.txt").write_text("secret")
        bad = make_document(access_level="public", file_path="../../secret.txt")
        with patch(FIND_BY_ID, return_value=bad):
            self.assertIsNone(document_service.download_document("doc-elv", ELV_EMPLOYEE))

    def test_file_path_relative_to_uploads(self, _approved):
        # file_path가 "elv_report.pdf"처럼 uploads 기준으로 저장돼 있어도 찾아야 해요.
        document = make_document(file_path="elv_report.pdf")
        with patch(FIND_BY_ID, return_value=document):
            self.assertIsNotNone(document_service.download_document("doc-elv", ELV_EMPLOYEE))

    # ── 감사 로그 (A-04) ──────────────────────────────────────

    def test_audit_view_allowed(self, _approved):
        with patch(FIND_BY_ID, return_value=make_document()):
            document_service.get_viewer_document("doc-elv", ELV_EMPLOYEE)
        self.assert_audit("view_document", ELV_EMPLOYEE, blocked=False)

    def test_audit_view_blocked(self, _approved):
        # 막힌 열람도 "권한 없음"으로 남아야 해요.
        with patch(FIND_BY_ID, return_value=make_document()):
            document_service.get_viewer_document("doc-elv", MVX_EMPLOYEE)
        self.assert_audit("view_document", MVX_EMPLOYEE, blocked=True, reason="권한 없음")

    def test_audit_false_not_recorded(self, _approved):
        # audit=False면 허용·차단 모두 기록하지 않아요. (화면이 다시 그려질 때 쓰는 방식)
        with patch(FIND_BY_ID, return_value=make_document()):
            allowed = document_service.get_viewer_document("doc-elv", ELV_EMPLOYEE, audit=False)
            blocked = document_service.get_viewer_document("doc-elv", MVX_EMPLOYEE, audit=False)
        self.audit.assert_not_called()
        # 기록만 안 할 뿐, 권한 판단 결과는 그대로예요.
        self.assertTrue(allowed["can_view"])
        self.assertFalse(blocked["can_view"])

    def test_audit_download_allowed(self, _approved):
        with patch(FIND_BY_ID, return_value=make_document()):
            document_service.download_document("doc-elv", ELV_EMPLOYEE)
        self.assert_audit("download", ELV_EMPLOYEE, blocked=False)

    def test_audit_download_blocked(self, _approved):
        with patch(FIND_BY_ID, return_value=make_document()):
            document_service.download_document("doc-elv", MVX_EMPLOYEE)
        self.assert_audit("download", MVX_EMPLOYEE, blocked=True, reason="권한 없음")

    def test_page_image_not_audited(self, _approved):
        # 페이지를 넘길 때마다 불리므로 허용·차단 모두 기록하지 않아요.
        with patch(FIND_BY_ID, return_value=make_document()):
            document_service.get_page_image("doc-elv", 1, ELV_EMPLOYEE)
            document_service.get_page_image("doc-elv", 1, MVX_EMPLOYEE)
        self.audit.assert_not_called()

    def test_unknown_document_not_audited(self, _approved):
        # 없는 문서는 권한 차단이 아니라서 기록하지 않아요(경고 로그만).
        with patch(FIND_BY_ID, return_value=None):
            document_service.get_viewer_document("nope", ELV_EMPLOYEE)
            document_service.download_document("nope", ELV_EMPLOYEE)
        self.audit.assert_not_called()

    def test_audit_failure_does_not_block(self, _approved):
        # 기록이 오류를 내도 열람·다운로드 결과는 그대로여야 해요.
        self.audit.side_effect = RuntimeError("DB 연결 실패")
        with patch(FIND_BY_ID, return_value=make_document()), \
             self.assertLogs("app.documents.services.document_service", level="ERROR"):
            viewer = document_service.get_viewer_document("doc-elv", ELV_EMPLOYEE)
            result = document_service.download_document("doc-elv", ELV_EMPLOYEE)
            blocked = document_service.get_viewer_document("doc-elv", MVX_EMPLOYEE)
        self.assertTrue(viewer["can_view"])
        self.assertEqual(result, self.pdf_path.read_bytes())
        self.assertFalse(blocked["can_view"])

    # ── DART ──────────────────────────────────────────────────

    def test_dart_document_uses_receipt_number(self, _approved):
        dart = make_document(
            access_level="public", source_type="dart", file_format="dart_xml",
            file_path="", doc_no="20250814000123",
        )
        with patch(FIND_BY_ID, return_value=dart):
            viewer = document_service.get_viewer_document("doc-elv", MVX_EMPLOYEE)
        self.assertEqual(viewer["dart_url"], "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20250814000123")

    def test_dart_url_rejects_invalid_number(self, _approved):
        self.assertEqual(document_service.get_dart_viewer_url("", "abc"), "")
        self.assertEqual(document_service.get_dart_viewer_url("", "123"), "")

    # ── 출처 페이지 번호 ──────────────────────────────────────

    def test_source_page(self, _approved):
        self.assertEqual(document_service.get_source_page({"location": "p.3"}), 3)
        self.assertEqual(document_service.get_source_page({"location": "페이지 12"}), 12)
        self.assertEqual(document_service.get_source_page({"location": "슬라이드 5"}), 0)
        self.assertEqual(document_service.get_source_page({"page": 7, "location": "p.3"}), 7)


def _viewer_app():
    """AppTest로 띄울 화면: 원문 뷰어 + 화면을 다시 그리게 하는 아무 버튼."""
    import streamlit as st

    from app.documents.views.components.document_viewer import render_selected_source

    render_selected_source({"id": 1, "role": "employee", "company_id": "ELV"})
    st.button("다른 버튼", key="other")  # 누르면 화면 전체가 다시 실행돼요


@patch(APPROVED_DOC_IDS, return_value=[])
@patch(RECORD_AUDIT_LOG)
@patch(FIND_BY_ID, return_value=make_document(file_path=""))  # 파일 없이 근거 문단만 보여 줘요
class ViewerAuditOnceTest(unittest.TestCase):
    """화면이 다시 그려져도 같은 출처의 열람 기록은 1건만 남는지 확인한다."""
    # 클래스 위 @patch 3개는 아래에서 위 순서로 가짜 객체가 들어와요: find_by_id, record_audit_log, 승인 목록

    SOURCE = {"text": "근거 문단", "company": "현대엘리베이터", "filename": "elv_report.pdf",
              "location": "p.2", "doc_id": "doc-elv", "chunk_id": "doc-elv#0001", "citation_number": 1}

    def view_logs(self, audit) -> int:
        """지금까지 남은 view_document 기록 수."""
        return sum(1 for call in audit.call_args_list if call.args[1] == "view_document")

    def test_rerun_records_once(self, _find, audit, _approved):
        from streamlit.testing.v1 import AppTest

        from app.documents.views.components.source_badge import SELECTED_SOURCE_KEY

        # default_timeout: 전체 테스트를 같이 돌리면 컴퓨터가 바빠 기본 3초를 넘길 수 있어 넉넉히 줘요.
        app = AppTest.from_function(_viewer_app, default_timeout=15)
        app.session_state[SELECTED_SOURCE_KEY] = self.SOURCE  # [원문 보기]를 누른 상태
        app.run()
        app.button(key="other").click().run()  # 다른 버튼 2번 → 화면 2번 다시 그림
        app.button(key="other").click().run()
        self.assertEqual(self.view_logs(audit), 1)

        # [돌아가기](원문 닫기) 뒤 같은 출처를 다시 열면 새 열람이라 1건 더 남아요.
        app.button(key="s05_back").click().run()
        app.session_state[SELECTED_SOURCE_KEY] = self.SOURCE
        app.run()
        self.assertEqual(self.view_logs(audit), 2)


if __name__ == "__main__":
    unittest.main()
