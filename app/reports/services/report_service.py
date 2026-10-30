"""R-01 보고서 생성 요청 조건 검증, R-01~R-04 보고서 생성 흐름(create_report)."""

import logging
from datetime import date

from app.admin.services.audit_service import record_audit_log
from app.admin.services.company_service import get_company_options
from app.reports.models.report_models import CollectionResult, Report, ReportRequest, ReportTemplate, Section
from app.reports.repositories import report_repository
from app.reports.services.citation_mapper import map_footnotes, renumber_footnotes
from app.reports.services.exec_summary_builder import fit_one_page, summarize_report
from app.reports.services.report_collector import balance_by_company, collect_documents
from app.reports.services.report_generator import generate_draft
from core.constants import ACCESS_LEVELS, ACCESS_PUBLIC

logger = logging.getLogger(__name__)

# 감사 로그(A-04) 행위 코드. 보고서 1건을 만들 때 1번만 남긴다 (회사별 검색마다 남기지 않는다).
AUDIT_REPORT_CREATE = "report_create"


def validate_request(request: ReportRequest) -> list[str]:
    """보고서 생성 조건을 검사하고 오류 메시지 목록을 반환한다."""

    errors = []

    # 1. 보고서 양식 검증
    try:
        ReportTemplate(request.template)
    except (ValueError, TypeError):
        errors.append("올바른 보고서 양식을 선택해 주세요.")

    # 2. 주제 입력 여부 검증
    if not isinstance(request.topic, str) or not request.topic.strip():
        errors.append("보고서 주제를 입력해 주세요.")

    # 3. 선택 기업 검증
    if not request.company_ids:
        errors.append("보고서 대상 기업을 하나 이상 선택해 주세요.")
    else:
        # DB에서 현재 활성화된 계열사 목록 조회
        company_options = get_company_options()
        valid_company_ids = {company["id"] for company in company_options}

        invalid_companies = [
            company_id
            for company_id in request.company_ids
            if company_id not in valid_company_ids
        ]

        if invalid_companies:
            errors.append(
                f"등록되지 않았거나 비활성화된 기업입니다: {', '.join(map(str, invalid_companies))}"
            )

    # 4. 보고서 기간 검증
    if type(request.start_date) is not date or type(request.end_date) is not date:
        errors.append("올바른 보고서 기간을 선택해 주세요.")
    elif request.start_date > request.end_date:
        errors.append("시작일은 종료일보다 늦을 수 없습니다.")

    return errors


def assemble_report(
    request: ReportRequest,
    collection: CollectionResult,
    sections: list[Section],
) -> Report:
    """R-02 보고서 초안에 R-03 각주를 매핑하여 Report 객체를 구성한다."""

    # 1. 섹션별 인용 번호를 실제 근거 청크와 매핑
    mapped_sections, footnotes = map_footnotes(
        sections,
        collection.chunks,
    )

    # 2. 보고서 전체 기준으로 각주 번호 재정렬
    mapped_sections, footnotes = renumber_footnotes(
        mapped_sections,
        footnotes,
    )

    # 3. 매핑된 섹션과 각주로 Report 객체 생성
    return Report(
        request=request,
        sections=mapped_sections,
        footnotes=footnotes,
    )


def create_report(user: dict, request: ReportRequest) -> Report:
    """R-01~R-04 보고서를 만든다: 검증 → 수집 → 섹션 작성 → 각주 → 1페이지 요약 → 저장 → 감사 로그.

    user: 로그인 사용자. {"id": 3, "role": "employee", "company_id": "MVX"} 모양
    반환: report_id가 채워진 Report. 화면은 이 번호로 결과 화면을 연다.
    오류: 조건이 틀리면 ValueError(메시지는 줄바꿈으로 이어 붙임), 사용자 정보가 이상하면 PermissionError.
    근거가 하나도 없어도 오류가 아니다. 섹션이 "근거 자료 없음"인 보고서가 만들어진다 (report.md §6).
    """
    # 1. 조건 확인. 화면에서 이미 확인했어도 서비스에서 한 번 더 본다 (화면을 거치지 않는 호출 대비).
    errors = validate_request(request)
    if errors:
        raise ValueError("\n".join(errors))

    # 2. 근거 수집 (R-01). S-03 권한 필터는 hybrid_search() 안에서 검색 전에 걸린다.
    try:
        chunks = collect_documents(user, request)
    except PermissionError as error:
        # 권한으로 막힌 시도도 감사 로그에 남긴다 (A-04 공통 규칙).
        _record_audit(user, request, None, None, blocked=True, reason=str(error))
        raise
    collection = balance_by_company(chunks, request.company_ids)

    # 3. 섹션 작성 (R-02) → 4. 보고서 전체 각주 번호 (R-03) → 5. 1페이지 요약 (R-04)
    sections = generate_draft(request, collection)
    report = assemble_report(request, collection, sections)
    report.exec_summary = fit_one_page(summarize_report(report))

    # 6. 저장. 작성자와 근거 문서의 최고 보안 등급(A-06이 쓴다)을 채운 뒤 저장한다.
    report.user_id = user["id"]
    report.max_access_level = _max_access_level(report, collection)
    report_repository.save(report)

    # 7. 감사 로그 (A-04). 저장이 끝난 뒤 1건만 남긴다.
    _record_audit(user, request, report, collection, blocked=False)
    return report


def _max_access_level(report: Report, collection: CollectionResult) -> str:
    """각주에 쓰인 근거 청크 중 가장 높은 보안 등급. 근거가 없으면 public."""
    # 보안 등급은 청크 metadata에 있다. Footnote에는 없어서 수집 결과에서 chunk_id로 찾는다.
    cited = {note.chunk_id for note in report.footnotes}
    levels = [
        chunk.metadata.get("access_level", ACCESS_PUBLIC)
        for chunk in collection.chunks
        if chunk.chunk_id in cited
    ]
    # ACCESS_LEVELS는 public < internal < confidential 순서다. 모르는 값은 가장 높은 등급으로 본다(안전한 쪽).
    ranks = [ACCESS_LEVELS.index(level) if level in ACCESS_LEVELS else len(ACCESS_LEVELS) - 1 for level in levels]
    return ACCESS_LEVELS[max(ranks)] if ranks else ACCESS_PUBLIC


def _record_audit(
    user: dict,
    request: ReportRequest,
    report: Report | None,
    collection: CollectionResult | None,
    blocked: bool,
    reason: str | None = None,
) -> None:
    """보고서 생성을 감사 로그(A-04)에 1건 남긴다. 기록이 실패해도 보고서 생성은 막지 않는다."""
    footnotes = report.footnotes if report else []
    try:
        record_audit_log(
            user.get("id") if user else None,
            AUDIT_REPORT_CREATE,
            str(report.report_id) if report and report.report_id is not None else None,
            None,                    # ip_address: 저장하지 않는 칸 (A-04 규칙)
            blocked,
            reason,
            target_type="report",
            query=request.topic,
            filters={"company_ids": request.company_ids,
                     "start_date": request.start_date.isoformat(),
                     "end_date": request.end_date.isoformat()},
            doc_ids=list(dict.fromkeys(note.doc_id for note in footnotes)),
            doc_companies=list(dict.fromkeys(note.company_id for note in footnotes)),
            result_count=len(footnotes),
            context_detail={
                "template": ReportTemplate(request.template).value,
                "empty_companies": collection.empty_companies if collection else [],
            },
        )
    except Exception:
        logger.exception("보고서 생성 감사 로그 기록 실패")
