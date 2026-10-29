"""R-01 보고서 생성 요청 조건 검증."""

from datetime import date

from app.admin.services.company_service import get_company_options
from app.reports.models.report_models import CollectionResult, Report, ReportRequest, ReportTemplate, Section
from app.reports.services.citation_mapper import map_footnotes, renumber_footnotes

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
