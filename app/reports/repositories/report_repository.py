"""R-02 보고서 저장·본인 보고서 조회, R-04 1페이지 요약 저장."""

# ─────────────────────────────────────────────────────────────
# repositories 파일 = DB에서 읽고 쓰기만 하는 곳이에요. 권한·업무 판단은 하지 않아요. (팀 규칙)
#
# 담당 (명세서 기준)
#   - save(), find_by_id() ........ R-02 (박예원)
#   - save_exec_summary() ......... R-04 (박예원)
#
# 파이썬 객체(Report)는 DB 칸에 그대로 못 넣어요. 그래서
#   저장할 때:  Report → 칸마다 글자·숫자·JSON 글자로 바꿔서 INSERT
#   꺼낼 때:   DB 한 줄 → JSON 글자를 다시 객체로 바꿔서 Report로 되살려요
#
# reports 칸과 Report의 짝
#   template·params ...... request (양식 / 주제·회사·기간)
#   content_md ........... 사람이 읽는 Markdown 본문 (검색·히스토리에서 보기 좋게)
#   sections ............. 섹션 목록 JSON (다시 열 때 화면을 그대로 그리는 용도)
#   footnotes ............ 각주 목록 JSON
#   exec_summary ......... 1페이지 요약 JSON
#   doc_ids .............. 근거 문서 ID 목록 (각주에서 모아요)
#   max_access_level ..... 근거 문서 중 가장 높은 보안 등급 (A-06이 써요)
# ─────────────────────────────────────────────────────────────

import json
from dataclasses import asdict
from datetime import date

from app.reports.models.report_models import (
    ExecSummary, Footnote, Report, ReportRequest, ReportTemplate, Section, SectionType, SummaryItem,
)
from core.database import get_connection  # 팀 규칙: DB 연결은 반드시 이 함수로만 열어요

# reports.title 칸 길이 (VARCHAR(300)). 넘으면 INSERT가 실패해서 잘라서 넣어요.
TITLE_MAX_LENGTH = 300


# ─────────────────────────────────────────────────────────────
# 저장·조회 (명세서 함수)
# ─────────────────────────────────────────────────────────────
def save(report: Report) -> int:
    """R-02 보고서의 작성자·양식·조건·본문·섹션·각주·요약·근거 문서·최고 보안 등급을 저장하고 report_id를 반환한다."""
    if report.user_id is None:  # 작성자 없는 보고서는 저장하지 않아요 (reports.user_id NOT NULL)
        raise ValueError("작성자(user_id)가 없는 보고서는 저장할 수 없습니다.")

    request = report.request
    # 값은 반드시 %s 자리로 넘겨요. 문자열을 이어 붙여 SQL을 만들면 SQL 인젝션에 뚫려요. (팀 규칙)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO reports (user_id, template, title, params, content_md, sections, footnotes, "
            "exec_summary, doc_ids, max_access_level) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                report.user_id,
                request.template.value,                      # "comprehensive" 같은 영어 값
                _report_title(report)[:TITLE_MAX_LENGTH],
                _to_json(_request_to_dict(request)),
                _to_markdown(report),
                _to_json([_section_to_dict(section) for section in report.sections]),
                _to_json([asdict(note) for note in report.footnotes]),
                _summary_json(report.exec_summary),
                _to_json(_doc_ids(report)),
                report.max_access_level,
            ),
        )
        # lastrowid: 방금 INSERT한 줄에 DB가 매긴 id(AUTO_INCREMENT)
        report_id = cur.lastrowid
    report.report_id = report_id  # 들고 있던 Report에도 번호를 채워 줘요
    return report_id


def find_by_id(report_id: int, user_id: int) -> Report | None:
    """R-02 보고서 ID와 작성자 ID를 함께 조건으로 걸어 본인 보고서 1건만 조회한다. 없으면 None."""
    # user_id까지 WHERE에 거는 이유: 남의 보고서 번호를 넣어도 꺼내지 못하게요.
    # 📌 다시 열 때 근거 문서 권한을 다시 확인하는 일(팀 규칙)은 services에서 해요. 여기는 읽기만 해요.
    with get_connection() as conn, conn.cursor() as cur:
        # SELECT * 대신 필요한 칸만 적어요. SQL은 f-string·문자열 연결 없이 고정 글자로만 써요. (팀 규칙)
        # 따옴표 글자 두 개를 나란히 쓰면 파이썬이 하나로 붙여 줘요. 줄 끝 공백이 없으면 "levelFROM"이 돼요.
        cur.execute(
            "SELECT id, user_id, template, params, sections, footnotes, exec_summary, max_access_level "
            "FROM reports WHERE id = %s AND user_id = %s",
            (report_id, user_id),
        )
        row = cur.fetchone()  # 결과 1줄(딕셔너리). 없으면 None
    return _row_to_report(row) if row else None


def save_exec_summary(report_id: int, user_id: int, summary: ExecSummary) -> bool:
    """R-04 1페이지 요약을 본인 보고서에 저장한다. 본인 보고서가 아니거나 없으면 False."""
    with get_connection() as conn, conn.cursor() as cur:
        # 먼저 본인 보고서인지 확인해요.
        # UPDATE의 rowcount만 보면, 같은 요약을 다시 저장할 때(값이 안 바뀜) 0이 나와서
        # "실패"로 착각할 수 있어서예요.
        cur.execute("SELECT id FROM reports WHERE id = %s AND user_id = %s", (report_id, user_id))
        if cur.fetchone() is None:
            return False
        cur.execute(
            "UPDATE reports SET exec_summary = %s WHERE id = %s AND user_id = %s",
            (_summary_json(summary), report_id, user_id),
        )
    return True


# ─────────────────────────────────────────────────────────────
# Report → DB 칸 (저장할 때)
# ─────────────────────────────────────────────────────────────
def _to_json(value) -> str:
    """파이썬 값(dict·list)을 JSON 글자로 바꾼다."""
    # ensure_ascii=False: 한글을 "스" 같은 암호처럼 바꾸지 않고 그대로 저장해요.
    return json.dumps(value, ensure_ascii=False)


def _request_to_dict(request: ReportRequest) -> dict:
    """생성 조건 → params 칸. 양식은 template 칸에 따로 있어서 빼요."""
    return {
        "topic": request.topic,
        "company_ids": request.company_ids,
        # 날짜는 JSON에 그대로 못 넣어서 "2025-01-01" 글자로 바꿔요.
        "start_date": request.start_date.isoformat(),
        "end_date": request.end_date.isoformat(),
    }


def _section_to_dict(section: Section) -> dict:
    """섹션 → JSON에 넣을 dict. 다시 열 때 화면을 그리는 데 필요한 칸만 저장한다."""
    # evidence(근거 청크)·sources(섹션 번호 출처)는 저장하지 않아요.
    # 보고서가 완성되면 [n] 번호가 보고서 전체 번호로 바뀌고, 근거 정보는 footnotes에 다 들어 있어서예요.
    return {
        "section_type": section.section_type.value,
        "title": section.title,
        "body": section.body,
        "has_evidence": section.has_evidence,
        "partial": section.partial,
    }


def _summary_json(summary: ExecSummary | None) -> str | None:
    """1페이지 요약 → exec_summary 칸 JSON. 요약이 없으면 None(NULL)."""
    if summary is None:
        return None
    return _to_json({
        "items": [
            {
                "kind": item.kind,
                "text": item.text,
                "section_ref": SectionType(item.section_ref).value,
                "company_id": item.company_id,
            }
            for item in summary.items
        ],
        "notes": summary.notes,
    })


def _doc_ids(report: Report) -> list[str]:
    """각주의 근거 문서 ID 목록 (순서 유지, 중복 제거)."""
    # dict.fromkeys: 순서를 지키면서 같은 값을 한 번만 남기는 방법이에요.
    return list(dict.fromkeys(note.doc_id for note in report.footnotes))


def _report_title(report: Report) -> str:
    """title 칸에 넣을 보고서 제목. 예: 스마트 물류 보고서"""
    return f"{report.request.topic} 보고서"


def _to_markdown(report: Report) -> str:
    """content_md 칸에 넣을 사람이 읽는 Markdown 본문 (섹션 제목 + 본문)."""
    # 📌 R-05 to_markdown()이 머지되면 그걸로 바꿔도 돼요(요약·각주까지 들어간 전체 문서).
    blocks = [f"## {section.title}\n\n{section.body}" for section in report.sections]
    return "\n\n".join(blocks)


# ─────────────────────────────────────────────────────────────
# DB 한 줄 → Report (꺼낼 때)
# ─────────────────────────────────────────────────────────────
def _from_json(value):
    """DB에서 꺼낸 JSON 칸을 파이썬 값으로 바꾼다."""
    # PyMySQL은 JSON 칸을 글자(str)로 돌려줘요. 혹시 이미 바뀐 값이면 그대로 써요.
    if value is None or isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _row_to_report(row: dict) -> Report:
    """reports 한 줄을 Report 객체로 되살린다."""
    params = _from_json(row["params"])
    request = ReportRequest(
        template=ReportTemplate(row["template"]),
        topic=params["topic"],
        company_ids=params["company_ids"],
        start_date=date.fromisoformat(params["start_date"]),  # "2025-01-01" → 날짜
        end_date=date.fromisoformat(params["end_date"]),
    )
    sections = [
        Section(
            section_type=SectionType(data["section_type"]),
            title=data["title"],
            body=data["body"],
            has_evidence=data["has_evidence"],
            partial=data["partial"],
        )
        for data in _from_json(row["sections"])
    ]
    # Footnote 칸 이름과 JSON 이름이 같아서 **data로 한 번에 넣어요. (asdict로 저장했기 때문)
    footnotes = [Footnote(**data) for data in (_from_json(row["footnotes"]) or [])]
    return Report(
        request=request,
        sections=sections,
        footnotes=footnotes,
        exec_summary=_summary_from_json(_from_json(row["exec_summary"])),
        report_id=row["id"],
        user_id=row["user_id"],
        max_access_level=row["max_access_level"],
    )


def _summary_from_json(data: dict | None) -> ExecSummary | None:
    """exec_summary 칸 → ExecSummary. 저장된 요약이 없으면 None."""
    if data is None:
        return None
    items = [
        SummaryItem(
            kind=item["kind"],
            text=item["text"],
            section_ref=SectionType(item["section_ref"]),
            company_id=item.get("company_id"),
        )
        for item in data["items"]
    ]
    return ExecSummary(items=items, notes=data.get("notes", []))
