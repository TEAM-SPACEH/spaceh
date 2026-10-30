"""R-01~R-04 보고서 생성 흐름(create_report) 테스트. DB·OpenAI 없이 돌도록 바깥 함수는 가짜로 바꾼다."""

import unittest
from datetime import date
from unittest.mock import patch

from app.reports.models.report_models import (
    Chunk,
    CollectionResult,
    ExecSummary,
    ReportRequest,
    ReportTemplate,
    Section,
    SectionType,
)
from app.reports.services import report_service

SERVICE = "app.reports.services.report_service"
USER = {"id": 3, "role": "employee", "company_id": "MVX"}
COMPANY_OPTIONS = [{"id": "MVX", "name": "현대무벡스"}, {"id": "ELV", "name": "현대엘리베이터"}]


def make_request(**overrides) -> ReportRequest:
    values = {
        "template": ReportTemplate.COMPREHENSIVE,
        "topic": "스마트 물류",
        "company_ids": ["MVX", "ELV"],
        "start_date": date(2025, 1, 1),
        "end_date": date(2025, 12, 31),
    }
    values.update(overrides)
    return ReportRequest(**values)


def make_chunk(company_id: str, number: int, access_level: str = "public") -> Chunk:
    return Chunk(
        chunk_id=f"doc-{company_id}#{number:04d}",
        text=f"[{company_id} · 문서 · p.{number}] 근거 {number}",
        metadata={"company_id": company_id, "doc_id": f"doc-{company_id}", "access_level": access_level},
    )


def make_section(chunks: list[Chunk], body: str) -> Section:
    """[1]=chunks[0] 처럼 섹션 번호가 근거 순서를 가리키는 R-02 섹션."""
    sources = [
        {"company": c.metadata["company_id"], "company_id": c.metadata["company_id"], "filename": "문서",
         "location": "p.1", "doc_id": c.metadata["doc_id"], "chunk_id": c.chunk_id, "citation_number": i}
        for i, c in enumerate(chunks, start=1)
    ]
    return Section(SectionType.OVERVIEW, "개요", body, evidence=chunks, sources=sources)


class CreateReportTest(unittest.TestCase):

    def setUp(self):
        # 바깥 기능을 모두 가짜로 바꾼다. 각주(assemble_report)·균형 배치는 진짜를 쓴다.
        self.mvx = make_chunk("MVX", 1)
        self.elv = make_chunk("ELV", 1, access_level="internal")
        patchers = {
            "options": patch(f"{SERVICE}.get_company_options", return_value=COMPANY_OPTIONS),
            "collect": patch(f"{SERVICE}.collect_documents", return_value=[self.mvx, self.elv]),
            "draft": patch(f"{SERVICE}.generate_draft",
                           return_value=[make_section([self.mvx, self.elv], "가.[1] 나.[2]")]),
            "summarize": patch(f"{SERVICE}.summarize_report", return_value=ExecSummary(notes=["요약"])),
            "fit": patch(f"{SERVICE}.fit_one_page", side_effect=lambda summary: summary),
            "save": patch(f"{SERVICE}.report_repository.save", side_effect=self._fake_save),
            "audit": patch(f"{SERVICE}.record_audit_log"),
        }
        self.mocks = {}
        for name, patcher in patchers.items():
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)

    @staticmethod
    def _fake_save(report):
        report.report_id = 42  # 진짜 save()처럼 DB 번호를 채운다
        return 42

    def test_creates_saves_and_audits_once(self):
        report = report_service.create_report(USER, make_request())

        self.assertEqual(report.report_id, 42)
        self.assertEqual(report.user_id, 3)
        # 각주는 보고서 전체 번호로 매겨져 있어야 한다 (R-03)
        self.assertEqual([note.chunk_id for note in report.footnotes], [self.mvx.chunk_id, self.elv.chunk_id])
        self.assertEqual(report.exec_summary.notes, ["요약"])
        # 회사별 검색은 collect_documents 안에서 audit=False로 하고, 감사 로그는 생성 1건만 남긴다
        self.mocks["save"].assert_called_once()
        audit = self.mocks["audit"]
        audit.assert_called_once()
        args, kwargs = audit.call_args
        self.assertEqual(args[:6], (3, "report_create", "42", None, False, None))
        self.assertEqual(kwargs["target_type"], "report")
        self.assertEqual(kwargs["query"], "스마트 물류")
        self.assertEqual(kwargs["doc_ids"], ["doc-MVX", "doc-ELV"])
        self.assertEqual(kwargs["result_count"], 2)

    def test_audit_after_save(self):
        # 저장이 실패하면 "생성함" 기록이 남지 않아야 한다
        self.mocks["save"].side_effect = RuntimeError("DB 오류")
        with self.assertRaises(RuntimeError):
            report_service.create_report(USER, make_request())
        self.mocks["audit"].assert_not_called()

    def test_invalid_request_stops_before_search(self):
        with self.assertRaises(ValueError) as caught:
            report_service.create_report(USER, make_request(topic=" ", company_ids=[]))
        self.assertIn("보고서 주제를 입력해 주세요.", str(caught.exception))
        self.mocks["collect"].assert_not_called()
        self.mocks["audit"].assert_not_called()

    def test_permission_error_is_audited_as_blocked(self):
        self.mocks["collect"].side_effect = PermissionError("알 수 없는 사용자입니다.")
        with self.assertRaises(PermissionError):
            report_service.create_report(USER, make_request())
        args, _ = self.mocks["audit"].call_args
        self.assertEqual(args[:6], (3, "report_create", None, None, True, "알 수 없는 사용자입니다."))
        self.mocks["save"].assert_not_called()

    def test_audit_failure_does_not_block(self):
        self.mocks["audit"].side_effect = RuntimeError("감사 로그 DB 오류")
        with self.assertLogs(SERVICE, level="ERROR"):
            report = report_service.create_report(USER, make_request())
        self.assertEqual(report.report_id, 42)

    def test_no_evidence_still_creates_report(self):
        # 근거가 0건이어도 오류가 아니라 "근거 자료 없음" 섹션의 보고서가 만들어진다
        self.mocks["collect"].return_value = []
        self.mocks["draft"].return_value = [
            Section(SectionType.OVERVIEW, "개요", "근거 자료 없음", has_evidence=False),
        ]
        report = report_service.create_report(USER, make_request())
        self.assertEqual(report.footnotes, [])
        self.assertEqual(report.max_access_level, "public")
        _, kwargs = self.mocks["audit"].call_args
        self.assertEqual(kwargs["context_detail"]["empty_companies"], ["MVX", "ELV"])


class MaxAccessLevelTest(unittest.TestCase):

    def _level(self, cited: list[Chunk], uncited: list[Chunk]) -> str:
        collection = CollectionResult(chunks=cited + uncited)
        body = " ".join(f"문장.[{i}]" for i in range(1, len(cited) + 1))
        report = report_service.assemble_report(make_request(), collection, [make_section(cited, body)])
        return report_service._max_access_level(report, collection)

    def test_highest_cited_level(self):
        cited = [make_chunk("MVX", 1), make_chunk("ELV", 1, "confidential"), make_chunk("MVX", 2, "internal")]
        self.assertEqual(self._level(cited, []), "confidential")

    def test_uncited_chunks_are_ignored(self):
        # 수집만 되고 본문에 인용되지 않은 기밀 청크는 보고서 등급을 올리지 않는다
        self.assertEqual(self._level([make_chunk("MVX", 1)], [make_chunk("ELV", 9, "confidential")]), "public")

    def test_unknown_level_counts_as_highest(self):
        self.assertEqual(self._level([make_chunk("MVX", 1, "secret")], []), "confidential")


if __name__ == "__main__":
    unittest.main()
