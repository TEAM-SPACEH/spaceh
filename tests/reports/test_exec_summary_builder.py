"""R-04 1페이지 요약(exec_summary_builder) 테스트. 저장소 루트에서 `python -m unittest`."""

# ─────────────────────────────────────────────────────────────
# 진짜 AI 대신 _get_llm()을 "정해진 답만 하는 가짜 AI"로 바꿔서 테스트해요. (API 키 없이 돌아가요)
# 회사 목록(get_company_options)은 DB를 읽어서 가짜로 바꿔 끼워요.
# ─────────────────────────────────────────────────────────────

import json
import unittest
from unittest.mock import MagicMock, patch

from app.reports.mock_data import MOCK_COLLECTION, MOCK_REQUEST, make_quote
from app.reports.models.report_models import (
    ExecSummary, Footnote, Report, Section, SectionType, SummaryItem,
)
from app.reports.services import exec_summary_builder
from app.reports.services.prompts import (
    NO_EVIDENCE_TEXT, NOTE_ITEM_DROPPED, NOTE_SUMMARY_FAILED,
)

GET_LLM = "app.reports.services.exec_summary_builder._get_llm"
COMPANY_OPTIONS = "app.reports.services.report_generator.get_company_options"


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


def make_footnote(number: int, chunk) -> Footnote:
    return Footnote(
        number=number, company=chunk.metadata["company_name"], company_id=chunk.metadata["company_id"],
        filename=chunk.metadata["file_name"], location=chunk.metadata["location"],
        quote=make_quote(chunk.text), text=chunk.text, doc_id=chunk.metadata["doc_id"],
        chunk_id=chunk.chunk_id,
    )


def make_report(footnote_chunks=None) -> Report:
    """보고서 전체 번호가 매겨진 가짜 보고서. 각주 [1]=ELV, [2]=MVX, [3]=HRI. 시너지는 근거 없음."""
    chunks = MOCK_COLLECTION.chunks if footnote_chunks is None else footnote_chunks
    sections = [
        Section(SectionType.OVERVIEW, "개요", "물류 자동화 수요가 늘고 있음.[1][3]", has_evidence=True),
        Section(SectionType.STATUS, "현황", "현대무벡스는 설비 공급을 늘림.[2]", has_evidence=True, partial=True),
        Section(SectionType.SYNERGY, "시너지", NO_EVIDENCE_TEXT, has_evidence=False),
        Section(SectionType.ADVICE, "제언", "묶음 제안을 검토함.[1][2]", has_evidence=True),
    ]
    footnotes = [make_footnote(number, chunk) for number, chunk in enumerate(chunks, start=1)]
    return Report(request=MOCK_REQUEST, sections=sections, footnotes=footnotes)


def answer_json(*items: dict) -> str:
    return json.dumps({"items": list(items)}, ensure_ascii=False)


GOOD_ANSWER = answer_json(
    {"kind": "key", "section": "overview", "company_id": None, "text": "물류 자동화 수요가 늘고 있음.[1][3]"},
    {"kind": "company", "section": "status", "company_id": "MVX", "text": "현대무벡스는 설비 공급을 늘림.[2]"},
    {"kind": "advice", "section": "advice", "company_id": None, "text": "묶음 제안을 검토함.[1][2]"},
)


def make_answers(*answers: str) -> MagicMock:
    """부를 때마다 answers를 차례대로 돌려주는 가짜 AI."""
    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = [
        MagicMock(content=answer, response_metadata={"finish_reason": "stop"}) for answer in answers
    ]
    return fake_llm


class SummarizeReportTest(unittest.TestCase):

    def summarize(self, fake_llm: MagicMock, report: Report | None = None) -> ExecSummary:
        with patch(GET_LLM, return_value=fake_llm):
            return exec_summary_builder.summarize_report(report or make_report())

    def test_good_summary(self):
        fake_llm = make_answers(GOOD_ANSWER)
        summary = self.summarize(fake_llm)

        self.assertEqual(fake_llm.invoke.call_count, 1)
        self.assertEqual([item.kind for item in summary.items], ["key", "company", "advice"])
        self.assertEqual(summary.items[1].company_id, "MVX")
        self.assertEqual(summary.items[1].section_ref, SectionType.STATUS)
        # 근거 없는 섹션·일부 제외 섹션은 코드가 유의사항으로 적어요.
        self.assertIn("시너지 섹션은 근거 자료가 없어 요약에서 제외됨", summary.notes)
        self.assertIn("현황 섹션은 일부 문장이 근거 검증에 실패해 제외됨", summary.notes)

    def test_prompt_has_report_and_footnotes(self):
        fake_llm = make_answers(GOOD_ANSWER)
        self.summarize(fake_llm)
        prompt = fake_llm.invoke.call_args[0][0]
        self.assertIn("## 현황 (status)", prompt)
        self.assertIn("[2] 현대무벡스 · 2025 반기보고서(가상) · II. 사업의 내용", prompt)
        self.assertIn("MVX=현대무벡스", prompt)
        self.assertNotIn("## 시너지", prompt)  # 근거 없는 섹션은 넣지 않아요

    def test_bad_section_and_company_fixed(self):
        # 근거 없는 섹션(synergy)으로 가라고 하거나, 모르는 회사 코드를 주면 바로잡아요.
        fake_llm = make_answers(answer_json(
            {"kind": "key", "section": "synergy", "company_id": None, "text": "수요가 늘고 있음.[1]"},
            {"kind": "company", "section": "status", "company_id": "XYZ", "text": "공급을 늘림.[2]"},
        ))
        summary = self.summarize(fake_llm)
        self.assertEqual(summary.items[0].section_ref, SectionType.OVERVIEW)
        self.assertIsNone(summary.items[1].company_id)

    def test_bad_json_is_retried(self):
        fake_llm = make_answers("요약입니다: 물류가 늘었음.", GOOD_ANSWER)
        summary = self.summarize(fake_llm)

        self.assertEqual(fake_llm.invoke.call_count, 2)
        self.assertIn("JSON 형식이 아님", fake_llm.invoke.call_args_list[1][0][0])
        self.assertEqual(len(summary.items), 3)

    def test_bad_json_twice_fails_softly(self):
        summary = self.summarize(make_answers("형식 없음", "또 형식 없음"))
        self.assertEqual(summary.items, [])
        self.assertIn(NOTE_SUMMARY_FAILED, summary.notes)

    def test_bad_sentences_removed(self):
        # [9]는 각주 범위 밖, 1,234억원은 근거에 없는 수치 → 그 문장만 빼요. 재시도도 같은 답이에요.
        bad = answer_json(
            {"kind": "key", "section": "overview", "company_id": None,
             "text": "수요가 늘고 있음.[1] 매출이 1,234억원 증가함.[1]"},
            {"kind": "advice", "section": "advice", "company_id": None, "text": "협력을 검토함.[9]"},
        )
        fake_llm = make_answers(bad, bad)
        summary = self.summarize(fake_llm)

        self.assertEqual(fake_llm.invoke.call_count, 2)  # 재시도 1번
        retry_prompt = fake_llm.invoke.call_args_list[1][0][0]
        self.assertIn("핵심 내용 1번 항목, 2번째 문장", retry_prompt)
        self.assertIn("권고안 1번 항목, 1번째 문장", retry_prompt)
        # 핵심 내용은 맞는 문장만 남고, 권고안은 남은 문장이 없어 빠져요.
        self.assertEqual([item.text for item in summary.items], ["수요가 늘고 있음.[1]"])
        self.assertIn(NOTE_ITEM_DROPPED, summary.notes)

    def test_no_evidence_skips_llm(self):
        report = make_report(footnote_chunks=[])
        with patch(GET_LLM) as get_llm:
            summary = exec_summary_builder.summarize_report(report)
        get_llm.assert_not_called()
        self.assertEqual(summary.items, [])

    def test_company_without_footnote_noted(self):
        # 각주에 HRI가 없으면 "현대경제연구원: 해당 주제의 근거 자료 없음" 유의사항
        report = make_report(footnote_chunks=MOCK_COLLECTION.chunks[:2])
        summary = self.summarize(make_answers(answer_json(
            {"kind": "key", "section": "overview", "company_id": None, "text": "수요가 늘고 있음.[1]"},
        )), report)
        self.assertIn("현대경제연구원: 해당 주제의 근거 자료 없음", summary.notes)

    def test_build_exec_summary_waits_for_repository(self):
        # 저장 기능이 생기기 전까지는 명세 모양 함수가 오류로 알려 줘요.
        with self.assertRaises(NotImplementedError):
            exec_summary_builder.build_exec_summary({"id": 1}, 1)


class FitOnePageTest(unittest.TestCase):

    def item(self, kind: str, text: str, section=SectionType.STATUS) -> SummaryItem:
        return SummaryItem(kind=kind, text=text, section_ref=section)

    def test_fits_without_llm(self):
        summary = ExecSummary(items=[self.item("key", "짧은 문장임.[1]")])
        with patch(GET_LLM) as get_llm:
            result = exec_summary_builder.fit_one_page(summary)
        get_llm.assert_not_called()
        self.assertIs(result, summary)

    def test_safe_shortening_accepted(self):
        long_text = "가" * 40 + "임.[1] " + "나" * 40 + "임.[2]"
        summary = ExecSummary(items=[self.item("key", long_text)], notes=["유의"])
        fake_llm = make_answers(answer_json({"kind": "key", "text": "가임.[1] 나임.[2]"}))
        with patch(GET_LLM, return_value=fake_llm):
            result = exec_summary_builder.fit_one_page(summary, max_chars=50, max_paragraph_chars=50)
        self.assertEqual(result.items[0].text, "가임.[1] 나임.[2]")
        self.assertEqual(result.notes, ["유의"])  # 유의사항은 그대로

    def test_unsafe_shortening_rejected_then_reference(self):
        # 압축본이 원래 없던 번호 [5]를 만들면 받지 않아요 → 그래도 넘치니 "첫 문장 + 상세보고서 참고"
        long_text = "가" * 40 + "임.[1] " + "나" * 40 + "임.[2]"
        summary = ExecSummary(items=[self.item("company", long_text)])
        fake_llm = make_answers(answer_json({"kind": "company", "text": "가임.[5]"}))
        with patch(GET_LLM, return_value=fake_llm):
            result = exec_summary_builder.fit_one_page(summary, max_chars=60, max_paragraph_chars=60)
        self.assertEqual(result.items[0].text, "가" * 40 + "임.[1] (상세보고서 현황 섹션 참고)")

    def test_item_count_kept(self):
        # 줄일 수 없을 만큼 넘쳐도 결론·권고안 항목 수는 그대로예요.
        items = [self.item("key", "가" * 100 + "임.[1]"), self.item("advice", "나" * 100 + "임.[2]")]
        fake_llm = make_answers("형식 없음")
        with patch(GET_LLM, return_value=fake_llm):
            result = exec_summary_builder.fit_one_page(ExecSummary(items=items), max_chars=50, max_paragraph_chars=50)
        self.assertEqual(len(result.items), 2)


if __name__ == "__main__":
    unittest.main()
