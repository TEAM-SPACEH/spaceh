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


if __name__ == "__main__":
    unittest.main()
