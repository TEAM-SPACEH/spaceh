"""R-01 보고서 생성 요청 조건 검증."""

from datetime import date

from app.admin.services.company_service import get_company_options
from app.reports.models.report_models import ReportRequest, ReportTemplate


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
    if not isinstance(request.start_date, date) or not isinstance(request.end_date, date):
        errors.append("올바른 보고서 기간을 선택해 주세요.")
    elif request.start_date > request.end_date:
        errors.append("시작일은 종료일보다 늦을 수 없습니다.")

    return errors
