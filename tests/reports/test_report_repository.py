"""R-02 보고서 저장소(report_repository) 테스트. 저장소 루트에서 `python -m unittest`."""

# ─────────────────────────────────────────────────────────────
# 진짜 MySQL 없이 테스트하려고 get_connection()을 "가짜 연결"로 바꿔 끼워요.
# 가짜 커서는 실행한 SQL과 값을 기록해 두고, fetchone()에는 미리 정한 답을 돌려줘요.
# 저장(INSERT)한 값으로 DB 한 줄을 만들어 다시 꺼내 보면(find_by_id),
# "저장한 보고서를 그대로 되살릴 수 있는지"를 DB 없이 확인할 수 있어요.
# ─────────────────────────────────────────────────────────────

import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from app.reports.mock_data import MOCK_COLLECTION, MOCK_REQUEST, make_quote
from app.reports.models.report_models import (
    ExecSummary, Footnote, Report, Section, SectionType, SummaryItem,
)
from app.reports.repositories import report_repository
from app.reports.services.prompts import NO_EVIDENCE_TEXT

GET_CONNECTION = "app.reports.repositories.report_repository.get_connection"
INSERT_COLUMNS = (
    "user_id", "template", "title", "params", "content_md", "sections", "footnotes",
    "exec_summary", "doc_ids", "max_access_level",
)


class FakeCursor:
    """실행한 SQL·값을 기록하고, fetchone()에는 answers를 차례대로 돌려주는 가짜 커서."""

    def __init__(self, answers):
        self.executed = []          # [(sql, params), ...]
        self.answers = list(answers)
        self.lastrowid = 42         # INSERT하면 DB가 매긴 id라고 가정

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.answers.pop(0) if self.answers else None

    # with conn.cursor() as cur: 로 쓸 수 있게 해 주는 두 함수
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_connection(cursor: FakeCursor):
    """get_connection() 대신 쓸 함수. with 블록에서 가짜 커서를 돌려준다."""
    class FakeConnection:
        def cursor(self):
            return cursor

    @contextmanager
    def connect():
        yield FakeConnection()

    return connect


def make_report(**overrides) -> Report:
    """보고서 전체 번호가 매겨진 가짜 보고서. 각주 [1]=ELV, [2]=MVX, [3]=HRI(같은 문서 2번)."""
    chunks = list(MOCK_COLLECTION.chunks)
    footnotes = [
        Footnote(
            number=number, company=chunk.metadata["company_name"], company_id=chunk.metadata["company_id"],
            filename=chunk.metadata["file_name"], location=chunk.metadata["location"],
            quote=make_quote(chunk.text), text=chunk.text, doc_id=chunk.metadata["doc_id"],
            chunk_id=chunk.chunk_id,
        )
        for number, chunk in enumerate(chunks + chunks[:1], start=1)  # 4번째 각주는 ELV 문서 한 번 더
    ]
    values = dict(
        request=MOCK_REQUEST,
        sections=[
            Section(SectionType.OVERVIEW, "개요", "물류 자동화 수요가 늘고 있음.[1][3]"),
            Section(SectionType.STATUS, "현황", "현대무벡스는 설비 공급을 늘림.[2]", partial=True),
            Section(SectionType.SYNERGY, "시너지", NO_EVIDENCE_TEXT, has_evidence=False),
        ],
        footnotes=footnotes,
        exec_summary=ExecSummary(
            items=[
                SummaryItem("key", "수요가 늘고 있음.[1]", SectionType.OVERVIEW),
                SummaryItem("company", "설비 공급을 늘림.[2]", SectionType.STATUS, company_id="MVX"),
            ],
            notes=["시너지 섹션은 근거 자료가 없어 요약에서 제외됨"],
        ),
        user_id=7,
        max_access_level="internal",
    )
    values.update(overrides)
    return Report(**values)


def inserted_row(cursor: FakeCursor) -> dict:
    """가짜 커서에 기록된 INSERT 값을 reports 한 줄(dict) 모양으로 바꾼다."""
    _sql, params = cursor.executed[0]
    return dict(zip(INSERT_COLUMNS, params))


class SaveTest(unittest.TestCase):

    def save(self, report: Report) -> tuple[int, FakeCursor]:
        cursor = FakeCursor([])
        with patch(GET_CONNECTION, fake_connection(cursor)):
            return report_repository.save(report), cursor

    def test_saves_columns(self):
        report = make_report()
        report_id, cursor = self.save(report)

        self.assertEqual(report_id, 42)
        self.assertEqual(report.report_id, 42)  # 들고 있던 Report에도 번호가 채워져요
        sql, _params = cursor.executed[0]
        self.assertIn("INSERT INTO reports", sql)
        self.assertNotIn("물류", sql)  # 값은 SQL에 붙이지 않고 %s로만 넘겨요 (SQL 인젝션 방지)

        row = inserted_row(cursor)
        self.assertEqual(row["user_id"], 7)
        self.assertEqual(row["template"], "comprehensive")
        self.assertEqual(row["title"], "스마트 물류 보고서")
        self.assertEqual(row["max_access_level"], "internal")
        self.assertEqual(json.loads(row["params"])["start_date"], "2025-01-01")
        # 같은 문서(doc-elv)가 각주에 두 번 나와도 근거 문서 목록에는 한 번만
        self.assertEqual(json.loads(row["doc_ids"]), ["doc-elv", "doc-mvx", "doc-hri"])
        self.assertIn("## 현황\n\n현대무벡스는 설비 공급을 늘림.[2]", row["content_md"])
        self.assertIn("현황", row["sections"])  # 한글이 현 같은 글자로 바뀌지 않아요

    def test_section_flags_saved(self):
        _report_id, cursor = self.save(make_report())
        sections = json.loads(inserted_row(cursor)["sections"])
        self.assertEqual(sections[1], {
            "section_type": "status", "title": "현황", "body": "현대무벡스는 설비 공급을 늘림.[2]",
            "has_evidence": True, "partial": True,
        })
        self.assertFalse(sections[2]["has_evidence"])

    def test_no_summary_saved_as_null(self):
        _report_id, cursor = self.save(make_report(exec_summary=None))
        self.assertIsNone(inserted_row(cursor)["exec_summary"])

    def test_long_title_cut(self):
        request = type(MOCK_REQUEST)(**{**MOCK_REQUEST.__dict__, "topic": "가" * 400})
        _report_id, cursor = self.save(make_report(request=request))
        self.assertEqual(len(inserted_row(cursor)["title"]), report_repository.TITLE_MAX_LENGTH)

    def test_no_user_raises(self):
        with patch(GET_CONNECTION) as get_connection, self.assertRaises(ValueError):
            report_repository.save(make_report(user_id=None))
        get_connection.assert_not_called()  # DB에 가기 전에 막아요


class FindByIdTest(unittest.TestCase):

    def find(self, row: dict | None, report_id=42, user_id=7) -> tuple[Report | None, FakeCursor]:
        cursor = FakeCursor([row])
        with patch(GET_CONNECTION, fake_connection(cursor)):
            return report_repository.find_by_id(report_id, user_id), cursor

    def saved_row(self, report: Report) -> dict:
        """report를 저장했을 때 DB에 들어갈 한 줄 (id 포함)."""
        cursor = FakeCursor([])
        with patch(GET_CONNECTION, fake_connection(cursor)):
            report_repository.save(report)
        return {"id": 42, **inserted_row(cursor)}

    def test_round_trip(self):
        # 저장한 보고서를 다시 꺼내면 원래와 똑같아야 해요. (섹션 표시·각주·요약의 이동 섹션까지)
        original = make_report()
        restored, _cursor = self.find(self.saved_row(original))
        self.assertEqual(restored, original)
        self.assertEqual(restored.report_id, 42)
        self.assertIs(restored.exec_summary.items[1].section_ref, SectionType.STATUS)

    def test_round_trip_without_summary(self):
        original = make_report(exec_summary=None)
        restored, _cursor = self.find(self.saved_row(original))
        self.assertIsNone(restored.exec_summary)

    def test_only_own_report(self):
        # 보고서 ID와 작성자 ID를 함께 조건으로 걸어요.
        _report, cursor = self.find(None, report_id=5, user_id=7)
        sql, params = cursor.executed[0]
        self.assertIn("WHERE id = %s AND user_id = %s", sql)
        self.assertIn("max_access_level FROM reports", sql)  # 두 줄로 나눈 SQL이 띄어쓰기로 잘 붙었는지
        self.assertEqual(params, (5, 7))

    def test_not_found(self):
        report, _cursor = self.find(None)
        self.assertIsNone(report)


class SaveExecSummaryTest(unittest.TestCase):

    SUMMARY = ExecSummary(items=[SummaryItem("advice", "묶음 제안을 검토함.[1]", SectionType.ADVICE)])

    def save_summary(self, found_row) -> tuple[bool, FakeCursor]:
        cursor = FakeCursor([found_row])
        with patch(GET_CONNECTION, fake_connection(cursor)):
            return report_repository.save_exec_summary(42, 7, self.SUMMARY), cursor

    def test_own_report(self):
        saved, cursor = self.save_summary({"id": 42})
        self.assertTrue(saved)
        sql, params = cursor.executed[1]
        self.assertIn("UPDATE reports SET exec_summary = %s WHERE id = %s AND user_id = %s", sql)
        self.assertEqual(json.loads(params[0])["items"][0]["section_ref"], "advice")
        self.assertEqual(params[1:], (42, 7))

    def test_not_own_report(self):
        # 남의 보고서거나 없는 보고서면 UPDATE 하지 않고 False
        saved, cursor = self.save_summary(None)
        self.assertFalse(saved)
        self.assertEqual(len(cursor.executed), 1)


if __name__ == "__main__":
    unittest.main()
