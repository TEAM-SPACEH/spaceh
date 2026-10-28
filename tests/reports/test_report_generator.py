"""R-02 report_generator 테스트. 저장소 루트에서 `python -m unittest` 로 실행한다."""

# ─────────────────────────────────────────────────────────────
# 진짜 AI(OpenAI)를 부르면 돈이 들고 매번 답이 조금씩 달라서,
# _get_llm()을 "정해진 답만 하는 가짜 AI"로 바꿔치기(patch)해서 테스트해요.
# 그래서 이 테스트는 API 키 없이도 돌아가요.
# ─────────────────────────────────────────────────────────────

import unittest
from unittest.mock import MagicMock, patch  # MagicMock: 아무 모양이나 흉내 내는 가짜 객체

from app.reports.mock_data import MOCK_COLLECTION, MOCK_REQUEST
from app.reports.models.report_models import (
    Chunk, CollectionResult, ReportTemplate, Section, SectionType,
)
from app.reports.services import report_generator
from app.reports.services.prompts import COMMON_RULES, NO_EVIDENCE_TEXT

# 바꿔치기할 함수의 "주소"
GET_LLM = "app.reports.services.report_generator._get_llm"


def make_fake_llm(answer: str) -> MagicMock:
    """invoke()를 부르면 항상 answer를 돌려주는 가짜 AI를 만든다."""
    fake_llm = MagicMock()
    # 진짜 AI 답은 response.content에 글자가 들어 있어요. 그 모양을 흉내 내요.
    fake_llm.invoke.return_value = MagicMock(content=answer)
    return fake_llm


class GetTemplateSectionsTest(unittest.TestCase):

    def test_comprehensive_has_four_sections_in_order(self):
        sections = report_generator.get_template_sections(ReportTemplate.COMPREHENSIVE)
        self.assertEqual(
            sections,
            [SectionType.OVERVIEW, SectionType.STATUS, SectionType.SYNERGY, SectionType.ADVICE],
        )

    def test_returns_copy(self):
        # 돌려받은 목록을 고쳐도 원래 순서표는 그대로여야 해요.
        sections = report_generator.get_template_sections(ReportTemplate.COMPREHENSIVE)
        sections.clear()
        self.assertEqual(len(report_generator.get_template_sections(ReportTemplate.COMPREHENSIVE)), 4)

    def test_unknown_template_raises(self):
        # assertRaises: 이 블록 안에서 ValueError가 나야 통과예요.
        with self.assertRaises(ValueError):
            report_generator.get_template_sections("weekly")


class BuildSectionPromptTest(unittest.TestCase):

    def test_prompt_has_numbered_evidence_and_rules(self):
        prompt = report_generator.build_section_prompt(
            SectionType.STATUS, MOCK_COLLECTION.chunks, MOCK_REQUEST,
        )
        # 근거 번호, 공통 규칙, 주제, 기간, 섹션 제목이 모두 들어 있어야 해요.
        self.assertIn("[1] [현대엘리베이터", prompt)
        self.assertIn("[3] [현대경제연구원", prompt)
        self.assertIn(COMMON_RULES, prompt)
        self.assertIn("스마트 물류", prompt)
        self.assertIn("2025-01-01 ~ 2025-12-31", prompt)
        self.assertIn("[작성할 섹션] 현황", prompt)

    def test_previous_sections_without_citation_numbers(self):
        previous = [
            Section(SectionType.OVERVIEW, "개요", "물류 자동화 수요가 늘고 있음.[1][2]"),
            Section(SectionType.SYNERGY, "시너지", NO_EVIDENCE_TEXT, has_evidence=False),
        ]
        prompt = report_generator.build_section_prompt(
            SectionType.ADVICE, MOCK_COLLECTION.chunks, MOCK_REQUEST, previous,
        )
        # 앞 섹션 본문은 들어가되, 그 섹션의 [1][2] 번호는 지워져야 해요.
        self.assertIn("물류 자동화 수요가 늘고 있음.", prompt)
        self.assertNotIn("있음.[1][2]", prompt)
        # 근거 없는 섹션은 참고 자료로 넣지 않아요.
        self.assertNotIn("## 시너지", prompt)


class GenerateSectionTest(unittest.TestCase):

    def test_no_chunks_skips_llm(self):
        with patch(GET_LLM) as get_llm:
            section = report_generator.generate_section(SectionType.STATUS, [], MOCK_REQUEST)

        # 근거가 없으면 AI를 한 번도 부르지 않아야 해요.
        get_llm.assert_not_called()
        self.assertEqual(section.body, NO_EVIDENCE_TEXT)
        self.assertFalse(section.has_evidence)

    def test_section_keeps_evidence_order(self):
        with patch(GET_LLM, return_value=make_fake_llm("물류 수요가 늘고 있음.[1]")):
            section = report_generator.generate_section(
                SectionType.STATUS, MOCK_COLLECTION.chunks, MOCK_REQUEST,
            )
        self.assertEqual(section.title, "현황")
        self.assertEqual(section.body, "물류 수요가 늘고 있음.[1]")
        # [1]이 가리키는 청크 = evidence[0] 이어야 R-03 각주가 맞게 붙어요.
        self.assertEqual(section.evidence, MOCK_COLLECTION.chunks)

    def test_llm_says_no_evidence(self):
        with patch(GET_LLM, return_value=make_fake_llm(NO_EVIDENCE_TEXT)):
            section = report_generator.generate_section(
                SectionType.SYNERGY, MOCK_COLLECTION.chunks, MOCK_REQUEST,
            )
        self.assertFalse(section.has_evidence)
        self.assertEqual(section.evidence, [])
        self.assertEqual(section.sources, [])

    def test_no_evidence_with_period(self):
        # AI가 마침표를 붙여 "근거 자료 없음." 이라고 답해도 근거 없는 섹션이어야 해요.
        with patch(GET_LLM, return_value=make_fake_llm(f" {NO_EVIDENCE_TEXT}. ")):
            section = report_generator.generate_section(
                SectionType.SYNERGY, MOCK_COLLECTION.chunks, MOCK_REQUEST,
            )
        self.assertFalse(section.has_evidence)
        self.assertEqual(section.body, NO_EVIDENCE_TEXT)  # 정해진 문구 하나로 맞춰져요

    def test_empty_answer_is_no_evidence(self):
        # AI가 빈 답(빈칸·줄바꿈만)을 주면 근거 없는 섹션이어야 하고, 근거·출처를 붙이면 안 돼요.
        with patch(GET_LLM, return_value=make_fake_llm("  \n ")):
            section = report_generator.generate_section(
                SectionType.STATUS, MOCK_COLLECTION.chunks, MOCK_REQUEST,
            )
        self.assertFalse(section.has_evidence)
        self.assertEqual(section.body, NO_EVIDENCE_TEXT)
        self.assertEqual(section.evidence, [])
        self.assertEqual(section.sources, [])

    def test_sources_match_s04_format(self):
        with patch(GET_LLM, return_value=make_fake_llm("물류 수요가 늘고 있음.[1][2]")):
            section = report_generator.generate_section(
                SectionType.STATUS, MOCK_COLLECTION.chunks, MOCK_REQUEST,
            )
        # 근거 3개 → 출처도 3개, 번호는 1부터 차례대로
        self.assertEqual([s["citation_number"] for s in section.sources], [1, 2, 3])
        first = section.sources[0]
        # S-04 출처 패널·S-05 원문 뷰어가 쓰는 칸이 모두 있어야 해요.
        self.assertEqual(first["company"], "현대엘리베이터")
        self.assertEqual(first["company_id"], "ELV")
        self.assertEqual(first["filename"], "elv_2025_report.pdf")
        self.assertEqual(first["location"], "p.12")
        self.assertEqual(first["doc_id"], "doc-elv")
        self.assertEqual(first["chunk_id"], "doc-elv#0003")

    def test_empty_chunk_does_not_shift_numbers(self):
        # 본문이 빈 청크가 끼어 있으면 미리 빼서, [2]가 두 번째 진짜 근거를 가리켜야 해요.
        empty = Chunk(chunk_id="doc-x#0001", text="  ", metadata={})
        chunks = [MOCK_COLLECTION.chunks[0], empty, MOCK_COLLECTION.chunks[1]]
        with patch(GET_LLM, return_value=make_fake_llm("내용임.[2]")) as get_llm:
            section = report_generator.generate_section(SectionType.STATUS, chunks, MOCK_REQUEST)

        prompt = get_llm.return_value.invoke.call_args[0][0]
        self.assertIn("[2] [현대무벡스", prompt)
        self.assertEqual(len(section.evidence), 2)
        self.assertEqual(section.sources[1]["company_id"], "MVX")


class IsNoEvidenceTest(unittest.TestCase):

    def test_variants(self):
        self.assertTrue(report_generator.is_no_evidence(NO_EVIDENCE_TEXT))
        self.assertTrue(report_generator.is_no_evidence(f"  {NO_EVIDENCE_TEXT}.\n"))
        # 문장 안에 들어 있기만 한 경우는 근거 없음이 아니에요.
        self.assertFalse(report_generator.is_no_evidence(f"일부 회사는 {NO_EVIDENCE_TEXT}임.[1]"))


class GenerateDraftTest(unittest.TestCase):

    def test_draft_follows_template_order(self):
        fake_llm = make_fake_llm("내용임.[1]")
        with patch(GET_LLM, return_value=fake_llm):
            sections = report_generator.generate_draft(MOCK_REQUEST, MOCK_COLLECTION)

        self.assertEqual([s.title for s in sections], ["개요", "현황", "시너지", "제언"])
        # 섹션 4개 → AI도 4번 불려야 해요.
        self.assertEqual(fake_llm.invoke.call_count, 4)

        # 마지막(제언) 프롬프트에는 앞 섹션 내용이 들어 있어야 해요.
        # call_args_list[-1] = 마지막 호출, [0][0] = 그때 넘긴 첫 번째 값(프롬프트)
        advice_prompt = fake_llm.invoke.call_args_list[-1][0][0]
        self.assertIn("## 개요", advice_prompt)
        self.assertIn("## 시너지", advice_prompt)

    def test_draft_without_evidence_never_calls_llm(self):
        empty = CollectionResult(chunks=[])
        with patch(GET_LLM) as get_llm:
            sections = report_generator.generate_draft(MOCK_REQUEST, empty)

        get_llm.assert_not_called()
        self.assertTrue(all(s.body == NO_EVIDENCE_TEXT for s in sections))

    def test_llm_error_is_raised(self):
        # AI 호출이 실패하면 오류를 잡지 않고 그대로 올려 보내야 해요.
        # 그래야 보고서 생성 흐름이 "중간 실패 시 저장하지 않고 오류 반환"을 할 수 있어요.
        fake_llm = MagicMock()
        fake_llm.invoke.side_effect = RuntimeError("API 오류")  # side_effect: 부르면 이 오류를 내요
        with patch(GET_LLM, return_value=fake_llm):
            with self.assertRaises(RuntimeError):
                report_generator.generate_draft(MOCK_REQUEST, MOCK_COLLECTION)


if __name__ == "__main__":
    unittest.main()
