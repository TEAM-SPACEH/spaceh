"""R-05 보고서 내보내기(report_exporter) 테스트. 저장소 루트에서 `python -m unittest`."""

# ─────────────────────────────────────────────────────────────
# 회사 목록(get_company_options)과 감사 로그(record_audit_log)는 DB를 써서 가짜로 바꿔 끼워요.
# DOCX는 만든 bytes를 python-docx로 다시 열어서 안을 확인해요. (디스크에 파일을 만들지 않아요)
# ─────────────────────────────────────────────────────────────

import io
import unittest
from datetime import datetime
from unittest.mock import patch

from docx import Document
from docx.oxml.ns import qn

from app.reports.mock_data import MOCK_COLLECTION, MOCK_REQUEST, make_quote
from app.reports.models.report_models import (
    ExecSummary, Footnote, Report, Section, SectionType, SummaryItem,
)
from app.reports.services import report_exporter
from app.reports.services.prompts import NO_EVIDENCE_TEXT

COMPANY_OPTIONS = "app.reports.services.report_generator.get_company_options"
RECORD_AUDIT_LOG = "app.reports.services.report_exporter.record_audit_log"
GET_POLICY = "app.reports.services.report_exporter.get_download_policy"

USER = {"id": 7, "name": "박예원", "employee_no": "E2025001", "role": "employee", "company_id": "ELV"}


def setUpModule():
    global _company_patcher
    _company_patcher = patch(COMPANY_OPTIONS, return_value=[
        {"id": "ELV", "name": "현대엘리베이터"},
        {"id": "MVX", "name": "현대무벡스"},
        {"id": "HRI", "name": "현대경제연구원"},
    ])
    _company_patcher.start()


def tearDownModule():
    _company_patcher.stop()


def make_report(exec_summary: ExecSummary | None = None, report_id: int | None = 12) -> Report:
    """보고서 전체 번호가 매겨진 가짜 보고서. 각주 [1]=ELV, [2]=MVX, [3]=HRI. 시너지는 근거 없음."""
    footnotes = [
        Footnote(
            number=number, company=chunk.metadata["company_name"], company_id=chunk.metadata["company_id"],
            filename=chunk.metadata["file_name"], location=chunk.metadata["location"],
            quote=make_quote(chunk.text), text=chunk.text, doc_id=chunk.metadata["doc_id"],
            chunk_id=chunk.chunk_id,
        )
        for number, chunk in enumerate(MOCK_COLLECTION.chunks, start=1)
    ]
    sections = [
        Section(SectionType.OVERVIEW, "개요", "물류 자동화 수요가 늘고 있음.[1][3]"),
        Section(SectionType.STATUS, "현황",
                "현대엘리베이터는 승강기 공급을 늘림.[1]\n\n현대무벡스는 설비 공급을 늘림.[2]", partial=True),
        Section(SectionType.SYNERGY, "시너지", NO_EVIDENCE_TEXT, has_evidence=False),
        Section(SectionType.ADVICE, "제언", "묶음 제안을 검토함.[1][2] <script>alert(1)</script>"),
    ]
    if exec_summary is None:
        exec_summary = ExecSummary(
            items=[
                SummaryItem("key", "물류 자동화 수요가 늘고 있음.[1][3]", SectionType.OVERVIEW),
                SummaryItem("company", "설비 공급을 늘림.[2]", SectionType.STATUS, company_id="MVX"),
                SummaryItem("advice", "묶음 제안을 검토함.[1][2]", SectionType.ADVICE),
            ],
            notes=["시너지 섹션은 근거 자료가 없어 요약에서 제외됨"],
        )
    return Report(request=MOCK_REQUEST, sections=sections, footnotes=footnotes,
                  exec_summary=exec_summary, report_id=report_id)


def docx_texts(content: bytes) -> list[str]:
    """DOCX 본문 문단 글자 목록."""
    return [paragraph.text for paragraph in Document(io.BytesIO(content)).paragraphs]


class ToMarkdownTest(unittest.TestCase):

    def setUp(self):
        self.markdown = report_exporter.to_markdown(make_report())

    def test_order(self):
        # 제목·조건 → 1페이지 요약 → 상세보고서 → 각주 순서
        positions = [self.markdown.index(text) for text in (
            "# 스마트 물류 종합 보고서", "## 1페이지 요약", "## 상세보고서", "## 각주",
        )]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("- 대상 회사: 현대엘리베이터, 현대무벡스, 현대경제연구원", self.markdown)
        self.assertIn("- 기간: 2025-01-01 ~ 2025-12-31", self.markdown)

    def test_detail_links_match_anchors(self):
        # 요약의 [상세 보기](#sec-status)가 같은 파일 안 <a id="sec-status">를 가리켜요.
        self.assertIn("[상세 보기](#sec-status)", self.markdown)
        self.assertIn('<a id="sec-status"></a>', self.markdown)
        self.assertIn("- **현대무벡스** 설비 공급을 늘림.[2] [상세 보기](#sec-status)", self.markdown)

    def test_sections_and_footnotes(self):
        self.assertIn(f"### 시너지\n\n{NO_EVIDENCE_TEXT}", self.markdown)
        self.assertIn("> 일부 문장이 근거 검증에 실패해 제외되었습니다.", self.markdown)  # 현황 partial
        self.assertIn("- 시너지 섹션은 근거 자료가 없어 요약에서 제외됨", self.markdown)  # 유의사항
        self.assertIn("- [1] 현대엘리베이터 · elv_2025_report.pdf · p.12", self.markdown)
        self.assertIn("  “물류센터용 고속 화물 승강기", self.markdown)

    def test_html_escaped(self):
        # 본문 속 <script>가 Markdown 뷰어에서 HTML로 실행되지 않게 바꿔요.
        self.assertNotIn("<script>", self.markdown)
        self.assertIn("&lt;script&gt;", self.markdown)

    def test_no_summary(self):
        report = make_report()
        report.exec_summary = None
        self.assertIn("1페이지 요약이 없습니다.", report_exporter.to_markdown(report))


class ToDocxTest(unittest.TestCase):

    def setUp(self):
        self.content = report_exporter.to_docx(make_report())
        self.document = Document(io.BytesIO(self.content))
        self.body = self.document.element.body  # Word XML 본문

    def test_order_and_text(self):
        texts = docx_texts(self.content)
        positions = [texts.index(text) for text in ("스마트 물류 종합 보고서", "1페이지 요약", "상세보고서", "각주")]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("현대엘리베이터는 승강기 공급을 늘림.[1]", texts)  # 빈 줄로 나뉜 문단이 따로 들어가요
        self.assertIn("현대무벡스는 설비 공급을 늘림.[2]", texts)
        self.assertIn(NO_EVIDENCE_TEXT, texts)

    def test_page_break_after_summary(self):
        # 페이지 나누기(w:br type=page)가 "상세보고서" 제목보다 앞에 있어야 해요.
        texts = docx_texts(self.content)
        paragraphs = self.document.paragraphs
        break_index = next(
            index for index, paragraph in enumerate(paragraphs)
            if paragraph._p.findall(f".//{qn('w:br')}[@{qn('w:type')}='page']")
        )
        self.assertLess(break_index, texts.index("상세보고서"))
        self.assertGreater(break_index, texts.index("1페이지 요약"))

    def test_bookmarks_and_internal_links(self):
        bookmarks = {element.get(qn("w:name")) for element in self.body.iter(qn("w:bookmarkStart"))}
        self.assertEqual(bookmarks, {"sec_overview", "sec_status", "sec_synergy", "sec_advice"})
        anchors = [element.get(qn("w:anchor")) for element in self.body.iter(qn("w:hyperlink"))]
        self.assertEqual(anchors, ["sec_overview", "sec_status", "sec_advice"])
        # 링크는 모두 실제 있는 책갈피를 가리켜야 해요.
        self.assertTrue(set(anchors) <= bookmarks)

    def test_footnote(self):
        footnote = next(text for text in docx_texts(self.content) if text.startswith("[1] "))
        self.assertIn("현대엘리베이터 · elv_2025_report.pdf · p.12", footnote)
        self.assertIn("“물류센터용 고속 화물 승강기", footnote)


class WatermarkTest(unittest.TestCase):

    def test_text(self):
        text = report_exporter.build_watermark_text(USER, now=datetime(2026, 10, 29, 15, 30))
        self.assertEqual(text, "워터마크: 박예원(E2025001) · 2026-10-29 15:30 다운로드 · 외부 유출 금지")

    def test_markdown_body_unchanged(self):
        body = report_exporter.to_markdown(make_report())
        marked = report_exporter.apply_watermark(body.encode("utf-8"), "md", USER).decode("utf-8")
        self.assertTrue(marked.startswith("> 워터마크: 박예원(E2025001)"))
        self.assertIn(body, marked)  # 본문·각주는 그대로 안에 들어 있어요
        self.assertTrue(marked.rstrip().endswith("외부 유출 금지"))

    def test_docx_header_only(self):
        content = report_exporter.to_docx(make_report())
        marked = report_exporter.apply_watermark(content, "docx", USER)
        document = Document(io.BytesIO(marked))
        self.assertIn("워터마크: 박예원(E2025001)", document.sections[0].header.paragraphs[0].text)
        self.assertEqual(docx_texts(marked), docx_texts(content))  # 본문 문단은 그대로

    def test_unknown_format(self):
        with self.assertRaises(ValueError):
            report_exporter.apply_watermark(b"", "pdf", USER)


@patch(RECORD_AUDIT_LOG)
class ExportReportFileTest(unittest.TestCase):

    def test_markdown_download_logged(self, audit):
        content = report_exporter.export_report_file(USER, make_report(), "md")
        self.assertTrue(content.decode("utf-8").startswith("> 워터마크: 박예원"))
        audit.assert_called_once_with(
            7, "download", "12", None, False, None,
            target_type="report", doc_ids=["doc-elv", "doc-mvx", "doc-hri"],
            doc_companies=["ELV", "MVX", "HRI"], context_detail={"file_format": "md"},
        )

    def test_docx_download(self, audit):
        content = report_exporter.export_report_file(USER, make_report(report_id=None), "docx")
        self.assertIn("스마트 물류 종합 보고서", docx_texts(content))
        self.assertIsNone(audit.call_args[0][2])  # 저장 전 보고서는 target_id 없음

    def test_blocked(self, audit):
        policy = {"allowed": False, "watermark": False, "reason": "기밀 문서 포함"}
        with patch(GET_POLICY, return_value=policy), \
             patch.object(report_exporter, "to_docx") as to_docx:
            result = report_exporter.export_report_file(USER, make_report(), "docx")
        self.assertIsNone(result)
        to_docx.assert_not_called()  # 차단이면 파일을 만들지 않아요
        self.assertEqual(audit.call_args[0][4:6], (True, "기밀 문서 포함"))

    def test_no_watermark(self, audit):
        policy = {"allowed": True, "watermark": False, "reason": None}
        with patch(GET_POLICY, return_value=policy):
            content = report_exporter.export_report_file(USER, make_report(), "md")
        self.assertTrue(content.decode("utf-8").startswith("# 스마트 물류 종합 보고서"))

    def test_audit_failure_does_not_block(self, audit):
        audit.side_effect = RuntimeError("DB 연결 실패")
        with self.assertLogs("app.reports.services.report_exporter", level="ERROR"):
            content = report_exporter.export_report_file(USER, make_report(), "md")
        self.assertIsNotNone(content)

    def test_unknown_format(self, audit):
        with self.assertRaises(ValueError):
            report_exporter.export_report_file(USER, make_report(), "pdf")
        audit.assert_not_called()

    def test_export_report_waits_for_repository(self, audit):
        with self.assertRaises(NotImplementedError):
            report_exporter.export_report(USER, 12, "md")


class FileNameTest(unittest.TestCase):

    def test_file_name(self):
        self.assertEqual(report_exporter.build_file_name(make_report(), "md"), "스마트_물류_종합_보고서.md")
        report = make_report()
        report.request = type(MOCK_REQUEST)(**{**MOCK_REQUEST.__dict__, "topic": 'AI/로봇: "협업"?'})
        self.assertEqual(report_exporter.build_file_name(report, "docx"), "AI_로봇_협업_종합_보고서.docx")


if __name__ == "__main__":
    unittest.main()
