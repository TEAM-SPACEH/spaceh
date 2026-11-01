"""R-04 섹션 앵커, [임시 R-03] 각주 번호 정리·원문 인용 테스트. 저장소 루트에서 `python -m unittest`."""

# ─────────────────────────────────────────────────────────────
# build_mock_report()·make_quote()는 R-03(김소은)이 오기 전까지 쓰는 임시 함수예요.
# 진짜 R-03 함수도 같은 규칙(처음 나온 순서·같은 청크 같은 번호·없는 번호 제거)을 지켜야 해서,
# 그 규칙을 여기서 테스트로 적어 둬요.
# ─────────────────────────────────────────────────────────────

import unittest
from unittest.mock import patch
from dataclasses import replace

from app.reports.mock_data import MOCK_COLLECTION, MOCK_REQUEST, build_mock_report, make_quote
from app.reports.models.report_models import Chunk, Section, SectionType
from app.reports.services.citation_mapper import build_section_anchor, build_source_link
from app.reports.services.prompts import NO_EVIDENCE_TEXT
from app.reports.services.report_generator import build_section_sources
from app.reports.services.citation_mapper import build_section_anchor, map_footnotes, renumber_footnotes
from app.reports.services.report_service import assemble_report

# build_section_sources()가 쓰는 S-04 prepare_context()는 DB를 안 써요. 회사 목록만 가짜로 바꿔요.
COMPANY_OPTIONS = "app.reports.services.report_generator.get_company_options"
ELV, MVX, HRI = MOCK_COLLECTION.chunks  # [현대엘리베이터, 현대무벡스, 현대경제연구원] 가짜 청크


def setUpModule():
    global _company_patcher
    _company_patcher = patch(COMPANY_OPTIONS, return_value=[{"id": "ELV", "name": "현대엘리베이터"}])
    _company_patcher.start()


def tearDownModule():
    _company_patcher.stop()


def make_section(section_type: SectionType, body: str, chunks: list[Chunk]) -> Section:
    """R-02 generate_section()이 만드는 것과 같은 모양의 섹션 (섹션마다 [1]부터)."""
    return Section(
        section_type=section_type, title=section_type.value, body=body,
        evidence=chunks, has_evidence=True, sources=build_section_sources(chunks),
    )


class SectionAnchorTest(unittest.TestCase):

    def test_anchor_id(self):
        self.assertEqual(build_section_anchor(SectionType.STATUS), "sec-status")
        self.assertEqual(build_section_anchor(SectionType.ADVICE), "sec-advice")
        # 글자 값("overview")을 넘겨도 같은 ID가 나와요.
        self.assertEqual(build_section_anchor("overview"), "sec-overview")

    def test_unknown_section_raises(self):
        with self.assertRaises(ValueError):
            build_section_anchor("weekly")


class MakeQuoteTest(unittest.TestCase):

    def test_header_removed(self):
        # 앞머리 [회사 · 제목 · 위치]를 떼고 본문만 남겨요.
        self.assertTrue(make_quote(ELV.text).startswith("물류센터용 고속 화물 승강기"))
        self.assertNotIn("[현대엘리베이터", make_quote(ELV.text))

    def test_cut_at_150_chars(self):
        quote = make_quote("[A · B · p.1] " + "가" * 200)
        self.assertEqual(len(quote), 151)  # 150자 + "…"
        self.assertTrue(quote.endswith("…"))

    def test_spaces_collapsed(self):
        self.assertEqual(make_quote("[A · B · p.1]  첫 줄\n\n  둘째   줄"), "첫 줄 둘째 줄")


class BuildMockReportTest(unittest.TestCase):

    def setUp(self):
        sections = [
            # 개요: [1]=ELV, [2]=HRI
            make_section(SectionType.OVERVIEW, "가 사실임.[1] 나 사실임.[2]", [ELV, HRI]),
            # 현황: [1]=MVX, [2]=ELV(개요와 같은 청크), [9]=없는 번호
            make_section(SectionType.STATUS, "다 사실임.[1] 라 사실임.[2][9]", [MVX, ELV]),
            Section(SectionType.SYNERGY, "synergy", NO_EVIDENCE_TEXT, has_evidence=False),
        ]
        self.report = build_mock_report(MOCK_REQUEST, sections)

    def test_bodies_renumbered(self):
        # 처음 나온 순서대로: ELV=1, HRI=2, MVX=3. 같은 청크(ELV)는 같은 번호, 없는 번호 [9]는 지워요.
        self.assertEqual(self.report.sections[0].body, "가 사실임.[1] 나 사실임.[2]")
        self.assertEqual(self.report.sections[1].body, "다 사실임.[3] 라 사실임.[1]")

    def test_footnotes(self):
        footnotes = self.report.footnotes
        self.assertEqual([note.number for note in footnotes], [1, 2, 3])
        self.assertEqual([note.company_id for note in footnotes], ["ELV", "HRI", "MVX"])
        first = footnotes[0]
        self.assertEqual(first.filename, "elv_2025_report.pdf")
        self.assertEqual(first.location, "p.12")
        self.assertEqual(first.doc_id, "doc-elv")
        self.assertEqual(first.text, ELV.text)               # 수치 확인·하이라이트용 본문 전체
        self.assertTrue(first.quote.startswith("물류센터용"))  # 앞머리를 뗀 인용

    def test_no_evidence_section_kept(self):
        self.assertEqual(self.report.sections[2].body, NO_EVIDENCE_TEXT)
        self.assertEqual(len(self.report.sections), 3)


if __name__ == "__main__":
    unittest.main()


class MapFootnotesTest(unittest.TestCase):

    def test_map_footnotes(self):
        sections = [
            make_section(
                SectionType.OVERVIEW,
                "가 사실임.[1] 나 사실임.[2]",
                [ELV, HRI],
            ),
            make_section(
                SectionType.STATUS,
                "다 사실임.[1] 라 사실임.[2][9]",
                [MVX, ELV],
            ),
        ]

        mapped_sections, footnotes = map_footnotes(
            sections,
            MOCK_COLLECTION.chunks,
        )

        # 섹션별 번호가 보고서 전체 번호로 변경되는지
        self.assertEqual(
            mapped_sections[0].body,
            "가 사실임.[1] 나 사실임.[2]",
        )
        self.assertEqual(
            mapped_sections[1].body,
            "다 사실임.[3] 라 사실임.[1]",
        )

        # 같은 청크는 하나의 각주로 통합되는지
        self.assertEqual(len(footnotes), 3)
        self.assertEqual(
            [note.chunk_id for note in footnotes],
            [ELV.chunk_id, HRI.chunk_id, MVX.chunk_id],
        )

        # 출처 패널 번호도 변경되는지
        self.assertEqual(
            [s["citation_number"] for s in mapped_sections[1].sources],
            [3, 1],
        )


class RenumberFootnotesTest(unittest.TestCase):

    def test_renumber_footnotes(self):
        # 기존 함수로 기본 섹션과 각주 준비
        sections, footnotes = map_footnotes(
            [
                make_section(
                    SectionType.OVERVIEW,
                    "가.[1] 나.[2]",
                    [ELV, HRI],
                ),
            ],
            MOCK_COLLECTION.chunks,
        )

        # 번호가 뒤섞이고 동일 청크가 중복된 상황
        old_footnotes = [
            replace(footnotes[0], number=7),
            replace(footnotes[1], number=4),
            replace(footnotes[0], number=9),
        ]

        first_section = replace(
            sections[0],
            body="가.[9] 나.[4][99]",
            sources=[
                {**sections[0].sources[0], "citation_number":9},
                {**sections[0].sources[1], "citation_number":4},
            ],
        )

        second_section = replace(
            sections[0],
            section_type=SectionType.STATUS,
            body="다.[7]",
            sources=[
                {**sections[0].sources[0], "citation_number":7},
            ],
        )

        new_sections, new_footnotes = renumber_footnotes(
            [first_section, second_section],
            old_footnotes,
        )

        # 본문 등장 순서대로 번호 재정렬
        self.assertEqual(new_sections[0].body, "가.[1] 나.[2]")
        self.assertEqual(new_sections[1].body, "다.[1]")

        # 동일한 청크는 같은 번호 사용
        self.assertEqual(len(new_footnotes), 2)
        self.assertEqual(
            [note.number for note in new_footnotes],
            [1, 2],
        )
        self.assertEqual(
            [note.chunk_id for note in new_footnotes],
            [ELV.chunk_id, HRI.chunk_id],
        )

        # 출처 패널의 번호도 일치
        self.assertEqual(
            [s["citation_number"] for s in new_sections[0].sources],
            [1, 2],
        )
        self.assertEqual(
            [s["citation_number"] for s in new_sections[1].sources],
            [1],
        )

class BuildSourceLinkTest(unittest.TestCase):

    def test_build_source_link(self):
        section = make_section(
            SectionType.OVERVIEW,
            "가 사실임.[1]",
            [ELV],
        )

        _, footnotes = map_footnotes(
            [section],
            MOCK_COLLECTION.chunks,
        )

        note = footnotes[0]
        source = build_source_link(note)

        self.assertEqual(source["doc_id"], "doc-elv")
        self.assertEqual(source["location"], "p.12")
        self.assertEqual(source["text"], ELV.text)
        self.assertEqual(source["citation_number"], 1)


class AssembleReportTest(unittest.TestCase):

    def test_assemble_report(self):
        sections = [
            make_section(
                SectionType.OVERVIEW,
                "가 사실임.[1] 나 사실임.[2]",
                [ELV, HRI],
            ),
            make_section(
                SectionType.STATUS,
                "다 사실임.[1] 라 사실임.[2]",
                [MVX, ELV],
            ),
            Section(
                SectionType.SYNERGY,
                "시너지",
                NO_EVIDENCE_TEXT,
                has_evidence=False,
            ),
        ]

        report = assemble_report(
            MOCK_REQUEST,
            MOCK_COLLECTION,
            sections,
        )

        # 보고서 생성 조건 유지
        self.assertEqual(report.request, MOCK_REQUEST)

        # 보고서 전체 인용 번호 확인
        self.assertEqual(
            report.sections[0].body,
            "가 사실임.[1] 나 사실임.[2]",
        )
        self.assertEqual(
            report.sections[1].body,
            "다 사실임.[3] 라 사실임.[1]",
        )

        # 중복 청크는 각주 하나로 통합
        self.assertEqual(len(report.footnotes), 3)
        self.assertEqual(
            [note.chunk_id for note in report.footnotes],
            [ELV.chunk_id, HRI.chunk_id, MVX.chunk_id],
        )

        # 출처 패널 번호도 동일하게 반영
        self.assertEqual(
            [s["citation_number"] for s in report.sections[1].sources],
            [3, 1],
        )

        # 근거 없는 섹션도 유지
        self.assertFalse(report.sections[2].has_evidence)
        self.assertEqual(
            report.sections[2].body,
            NO_EVIDENCE_TEXT,
        )
