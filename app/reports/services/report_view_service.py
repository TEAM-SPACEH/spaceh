"""R-03·R-04·R-05 보고서 보기: 저장된 보고서를 다시 열 때의 권한 재확인과 화면에 쓸 값 만들기.

화면(views)은 st.*만 쓰고, 열어도 되는지·어떻게 보여 줄지의 판단은 이 파일이 한다.
"""

import logging
from datetime import datetime

from app.permissions.services.permission_service import check_document_access
from app.reports.models.report_models import ExecSummary, Footnote, Report, SummaryItem
from app.reports.repositories import report_repository, report_view_repository
from app.reports.services.report_exporter import TEMPLATE_TITLES
from core.constants import ACCESS_CONFIDENTIAL, ACCESS_INTERNAL, ACCESS_PUBLIC

logger = logging.getLogger(__name__)

# open_report()의 결과 상태
OPEN_OK = "ok"
OPEN_NOT_FOUND = "not_found"
OPEN_BLOCKED = "blocked"

# 보안 등급 화면 이름 (보고서 안내 문구용)
_LEVEL_LABELS = {ACCESS_PUBLIC: "공개", ACCESS_INTERNAL: "사내", ACCESS_CONFIDENTIAL: "기밀"}

# 요약 항목 중 「핵심 요약」에 묶는 종류와 「제언」에 묶는 종류
_KEY_KINDS = ("key", "company")
_ADVICE_KINDS = ("advice",)


def open_report(user: dict | None, report_id: int) -> dict:
    """R-03 본인 보고서를 열고, 근거 문서를 지금도 볼 수 있는지 DB 기준으로 다시 확인한다.

    근거 문서를 하나라도 볼 수 없으면 보고서 본문에 그 내용이 들어 있으므로 내용을 돌려주지 않는다.
    반환: {"status": OPEN_OK | OPEN_NOT_FOUND | OPEN_BLOCKED, "report", "created_at", "source_types", "blocked_count"}
    """
    empty = {"status": OPEN_NOT_FOUND, "report": None, "created_at": None, "source_types": {}, "blocked_count": 0}
    user_id = user.get("id") if user else None
    if user_id is None:
        return empty

    report = report_repository.find_by_id(report_id, user_id)
    if report is None:
        return empty

    doc_ids = list(dict.fromkeys(note.doc_id for note in report.footnotes if note.doc_id))
    blocked = [doc_id for doc_id in doc_ids if not check_document_access(user_id, doc_id)]
    if blocked:
        logger.info("R-03 보고서 열기 차단 report_id=%s user_id=%s blocked=%s", report_id, user_id, len(blocked))
        return {**empty, "status": OPEN_BLOCKED, "blocked_count": len(blocked)}

    return {
        "status": OPEN_OK,
        "report": report,
        "created_at": report_view_repository.find_created_at(report_id, user_id),
        "source_types": report_view_repository.find_source_types(doc_ids),
        "blocked_count": 0,
    }


def template_title(report: Report) -> str:
    """양식의 화면 이름 (종합 보고서 / 분기 실적 보고서)."""
    return TEMPLATE_TITLES.get(report.request.template, "보고서")


def format_period(report: Report) -> str:
    """보고서 기간 "2025.07 – 2025.10"."""
    request = report.request
    return f"{request.start_date:%Y.%m} – {request.end_date:%Y.%m}"


def format_created(created_at: datetime | None, now: datetime | None = None) -> str:
    """만든 시각을 "오늘 13:40" / "어제 17:55" / "10.27 10:12"로. 모르면 빈 글자."""
    if created_at is None:
        return ""
    now = now or datetime.now()
    days = (now.date() - created_at.date()).days
    clock = f"{created_at:%H:%M}"
    if days == 0:
        return f"오늘 {clock}"
    if days == 1:
        return f"어제 {clock}"
    return f"{created_at:%m.%d} {clock}"


def split_summary(summary: ExecSummary | None) -> tuple[list[SummaryItem], list[SummaryItem], list[str]]:
    """1페이지 요약을 (핵심 요약 항목, 제언 항목, 유의사항)으로 나눈다. 요약이 없으면 모두 비어 있다."""
    if summary is None:
        return [], [], []
    key_items = [item for item in summary.items if item.kind in _KEY_KINDS]
    advice_items = [item for item in summary.items if item.kind in _ADVICE_KINDS]
    return key_items, advice_items, list(summary.notes)


def group_sources(footnotes: list[Footnote]) -> list[dict]:
    """각주를 문서(doc_id)별로 묶는다. 순서는 처음 인용된 순서. 한 문서의 여러 위치는 notes에 모은다."""
    groups: dict[str, dict] = {}
    for note in footnotes:
        group = groups.setdefault(
            note.doc_id,
            {"doc_id": note.doc_id, "filename": note.filename, "company": note.company,
             "company_id": note.company_id, "notes": []},
        )
        group["notes"].append(note)
    return list(groups.values())


def link_label(source_type: str | None) -> str:
    """원문 링크 글자. DART 공시는 "DART", 내부 문서는 "원문"."""
    return "DART" if source_type == "dart" else "원문"


def download_notice(max_access_level: str) -> dict:
    """다운로드 안내 카드 문구와 차단 여부. 근거 문서 중 최고 보안 등급으로 정한다.

    반환: {"text": 안내 문구, "blocked": 기밀 문서가 있어 내려받기가 막혔는지}
    """
    if max_access_level == ACCESS_CONFIDENTIAL:
        return {"text": "포함된 문서의 최고 보안 등급이 '기밀'이라 내려받기가 막힙니다.", "blocked": True}
    label = _LEVEL_LABELS.get(max_access_level, _LEVEL_LABELS[ACCESS_INTERNAL])
    return {
        "text": f"포함된 문서의 최고 보안 등급이 '{label}'라 내려받은 파일에 워터마크가 들어갑니다. "
                "'기밀' 문서가 있으면 내려받기가 막힙니다.",
        "blocked": False,
    }
