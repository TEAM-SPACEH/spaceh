"""I-02 본문·표 청킹의 내용 보존·출처·권한·설정 경계값을 검증한다."""

import copy
import unittest

from app.ingestion.preprocessing.chunker import split_into_chunks


def block(text, page=1, section="", kind="text", location=None):
    """마스킹 이후 I-01 공통 블록 형식의 테스트 입력을 만든다."""
    return {"text": text, "page": page, "section": section,
            "block_type": kind, "location": location or f"p.{page}"}


def body(chunk):
    """출처 접두어를 제외한 청크 본문을 반환한다."""
    return chunk["text"].split("\n", 1)[1]


class ChunkerTest(unittest.TestCase):
    """외부 API·DB 없이 청킹 규칙과 입력 불변을 확인한다."""

    def setUp(self):
        """검증된 공통 메타데이터와 기본 청킹 설정을 준비한다."""
        self.metadata = {
            "doc_id": "a" * 32, "company_id": "MVX",
            "company_name": "현대무벡스", "title": "점검 문서",
            "doc_type": "report", "file_name": "sample.pdf",
            "file_format": "pdf", "source_type": "internal",
            "access_level": "internal", "is_group_shared": False,
            "published_date": 0,
        }

    def test_short_text_and_exact_limit_are_not_split(self):
        """800자 이하 본문은 그대로 두고 순번·출처 접두어를 붙인다."""
        for length in (1, 799, 800):
            with self.subTest(length=length):
                chunks = split_into_chunks([block("가" * length)],
                                           self.metadata, {})
                self.assertEqual(len(chunks), 1)
                self.assertEqual(body(chunks[0]), "가" * length)
                self.assertEqual(chunks[0]["chunk_id"], "a" * 32 + "#0001")
                self.assertTrue(chunks[0]["text"].startswith(
                    "[현대무벡스 · 점검 문서 · p.1]\n"))

    def test_long_text_preserves_all_characters_and_overlap(self):
        """긴 본문을 800자로 나누고 150자 겹침 제거 후 원문을 복원한다."""
        original = "".join(chr(0xAC00 + i) for i in range(2100))
        chunks = split_into_chunks([block(original)], self.metadata, {})
        pieces = [body(chunk) for chunk in chunks]
        self.assertEqual([len(p) for p in pieces], [800, 800, 800])
        self.assertEqual(pieces[0][-150:], pieces[1][:150])
        self.assertEqual(pieces[1][-150:], pieces[2][:150])
        self.assertEqual(pieces[0] + "".join(p[150:] for p in pieces[1:]),
                         original)

    def test_sections_can_span_pages_and_new_sections_do_not_merge(self):
        """절은 페이지 경계를 넘어 묶되 다른 절과 제목 경계를 넘지 않는다."""
        blocks = [block("절 A", section="A", kind="title"),
                  block("본문 A", page=2, section="A"),
                  block("절 B", page=2, section="B", kind="title"),
                  block("본문 B", page=3, section="B")]
        chunks = split_into_chunks(blocks, self.metadata, {})
        self.assertEqual([body(c) for c in chunks],
                         ["절 A\n본문 A", "절 B\n본문 B"])
        self.assertEqual(chunks[0]["metadata"]["location"], "p.1 ~ p.2")
        self.assertEqual(chunks[1]["metadata"]["section"], "B")

    def test_split_chunks_use_their_actual_page(self):
        """같은 절의 긴 본문을 나눌 때 모든 청크가 첫 페이지를 가리키지 않는다."""
        blocks = [block("가" * 800, section="A"),
                  block("나" * 800, page=2, section="A")]
        chunks = split_into_chunks(blocks, self.metadata, {})
        self.assertEqual([c["metadata"]["page"] for c in chunks], [1, 1, 2])
        self.assertEqual(chunks[1]["metadata"]["location"], "p.1 ~ p.2")
        self.assertEqual(chunks[-1]["metadata"]["location"], "p.2")

    def test_intro_and_missing_sections_group_by_page(self):
        """소개서는 절이 같아도 페이지별로, 제목 없는 본문도 페이지별로 묶는다."""
        for doc_type, section in [("intro", "공통 제목"), ("report", "")]:
            chunks = split_into_chunks(
                [block("첫째", section=section),
                 block("둘째", section=section),
                 block("다음", page=2, section=section)],
                {**self.metadata, "doc_type": doc_type}, {},
            )
            self.assertEqual([body(c) for c in chunks], ["첫째\n둘째", "다음"])

    def test_large_table_is_whole_with_caption_unit_and_section(self):
        """800자를 넘는 표도 제목·단위를 붙여 분할 없이 보존한다."""
        table = "| 항목 | 값 |\n| --- | --- |\n" + "| 자산 | 123 |\n" * 100
        blocks = [block("재무 요약", section="재무", kind="title"),
                  block("(단위: 천원)", section="재무"),
                  block(table, section="재무", kind="table")]
        chunks = split_into_chunks(blocks, self.metadata, {})
        tables = [c for c in chunks if c["metadata"]["block_type"] == "table"]
        self.assertEqual(len(tables), 1)
        self.assertGreater(len(body(tables[0])), 800)
        self.assertIn(table, body(tables[0]))
        for text in ("재무", "재무 요약", "(단위: 천원)"):
            self.assertIn(text, body(tables[0]))

    def test_table_context_does_not_leak_from_previous_page(self):
        """이전 페이지의 표 제목·단위를 다음 페이지 표에 임의로 붙이지 않는다."""
        chunks = split_into_chunks(
            [block("이전 표"), block("(단위: 원)"),
             block("| 새 표 |", page=2, kind="table")], self.metadata, {},
        )
        self.assertEqual(body(chunks[-1]), "| 새 표 |")

    def test_adjacent_tables_keep_same_page_unit_without_copying_table(self):
        """연속 표에는 같은 페이지의 단위만 유지하고 이전 표는 복사하지 않는다."""
        chunks = split_into_chunks(
            [block("(단위: 원)"), block("| 표 A |", kind="table"),
             block("| 표 B |", kind="table")], self.metadata, {},
        )
        self.assertIn("(단위: 원)", body(chunks[-1]))
        self.assertNotIn("| 표 A |", body(chunks[-1]))

    def test_same_page_new_section_does_not_inherit_previous_unit(self):
        """페이지가 같아도 절이 달라지면 앞 절의 단위 문맥을 사용하지 않는다."""
        chunks = split_into_chunks(
            [block("(단위: 원)", section="A"),
             block("새 절 본문", section="B"),
             block("| 새 절 표 |", section="B", kind="table")],
            self.metadata, {},
        )
        self.assertNotIn("(단위: 원)", body(chunks[-1]))
        self.assertIn("새 절 본문", body(chunks[-1]))

    def test_tables_do_not_discard_surrounding_text_and_ids_are_sequential(self):
        """표 앞뒤 본문을 모두 반환하며 청크 ID·순번을 연속으로 부여한다."""
        chunks = split_into_chunks(
            [block("앞 본문"), block("| 표 |", kind="table"),
             block("뒤 본문")], self.metadata, {},
        )
        self.assertEqual([c["metadata"]["block_type"] for c in chunks],
                         ["text", "table", "text"])
        self.assertEqual(body(chunks[0]), "앞 본문")
        self.assertEqual(body(chunks[-1]), "뒤 본문")
        self.assertEqual([c["metadata"]["chunk_index"] for c in chunks], [1, 2, 3])
        self.assertEqual([c["chunk_id"] for c in chunks],
                         ["a" * 32 + f"#{i:04d}" for i in range(1, 4)])

    def test_empty_input_and_blank_blocks_produce_no_chunks(self):
        """빈 입력·공백뿐인 블록은 검색할 빈 청크를 만들지 않는다."""
        self.assertEqual(split_into_chunks([], self.metadata, {}), [])
        self.assertEqual(split_into_chunks([block(" \n")], self.metadata, {}), [])

    def test_input_and_permission_metadata_are_preserved(self):
        """추출 블록이 권한을 덮어쓰지 못하며 입력과 청크 간 dict를 분리한다."""
        blocks = [{**block("비공개 내용"), "access_level": "public",
                   "company_id": "OTHER"}, block("다음", page=2)]
        before = copy.deepcopy((blocks, self.metadata))
        chunks = split_into_chunks(blocks, self.metadata, {})
        self.assertEqual((blocks, self.metadata), before)
        for chunk in chunks:
            self.assertEqual(chunk["metadata"]["company_id"], "MVX")
            self.assertEqual(chunk["metadata"]["access_level"], "internal")
            self.assertIs(chunk["metadata"]["is_group_shared"], False)
        chunks[0]["metadata"]["title"] = "변경"
        self.assertEqual(chunks[1]["metadata"]["title"], "점검 문서")

    def test_custom_size_and_zero_overlap(self):
        """외부에서 전달한 크기와 겹침 0을 적용해 누락 없이 나눈다."""
        chunks = split_into_chunks([block("abcdefg")], self.metadata,
                                   {"chunk_size": 3, "chunk_overlap": 0})
        self.assertEqual([body(c) for c in chunks], ["abc", "def", "g"])

    def test_invalid_settings_blocks_and_permissions_are_rejected(self):
        """무한 반복 설정·잘못된 위치·불완전 권한으로 청크를 만들지 않는다."""
        for settings in ({"chunk_size": 0}, {"chunk_size": True},
                         {"chunk_overlap": -1}, {"chunk_overlap": 800},
                         {"chunk_overlap": True}):
            with self.subTest(settings=settings):
                with self.assertRaises(ValueError):
                    split_into_chunks([], self.metadata, settings)
        for invalid in [None, {**block("x"), "page": 0},
                        {**block("x"), "page": True},
                        {**block("x"), "location": ""},
                        {**block("x"), "block_type": "image"},
                        {**block("x"), "section": None}]:
            with self.assertRaises(ValueError):
                split_into_chunks([invalid], self.metadata, {})
        for updates in ({"doc_id": ""}, {"company_id": None},
                        {"access_level": "unknown"},
                        {"is_group_shared": "false"},
                        {"access_level": "confidential", "is_group_shared": True},
                        {"extra": []}):
            with self.assertRaises(ValueError):
                split_into_chunks([], {**self.metadata, **updates}, {})


if __name__ == "__main__":
    unittest.main()
