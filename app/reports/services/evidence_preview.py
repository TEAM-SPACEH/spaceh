"""R-01 새 보고서 화면의 "모일 근거 문서 N건" 미리보기: count_visible_documents().

보고서를 만들기 전에 지금 조건(회사·기간)에서 내가 볼 수 있는 문서가 회사마다 몇 건인지 센다.
검색 전에 권한 필터(S-03)를 where 조건에 넣어 센다. 센 뒤에 거르지 않으므로, 못 보는 문서는 숫자에도 들어오지 않는다.

이 파일은 문서 수만 센다. 근거 청크를 모으는 R-01 본 기능(hybrid_search 호출)과 보고서 생성(R-02)은 하지 않는다.
"""

from datetime import date

from app.permissions.services.permission_service import apply_rbac_filter
from app.reports.repositories.evidence_repository import get_chunk_metadatas
from app.search.services.search_service import apply_metadata_filters


def count_visible_documents(
    user: dict,
    company_ids: list[str],
    start_date: date,
    end_date: date,
) -> dict[str, int]:
    """R-01 이 사용자가 볼 수 있는 문서 수를 회사 코드별로 센다. 같은 문서의 청크는 한 건으로 센다.

    user: 로그인 사용자. {"id": 3, "role": "employee", "company_id": "MVX"} 모양
    company_ids: 대상 회사 코드. 문서가 없는 회사도 0건으로 돌려준다
    start_date, end_date: 문서 작성·공시일(published_date) 범위. 양 끝날을 포함한다
    반환: {"HRI": 5, "MVX": 7, "ELV": 0}  company_ids 순서를 지킨다
    ValueError: 시작일이 종료일보다 늦을 때
    PermissionError: 로그인 정보가 없거나 모르는 역할일 때 (권한 필터가 낸다)
    """
    counts = {company_id: 0 for company_id in dict.fromkeys(company_ids)}
    if not counts:
        return counts

    filters = {
        "companies": list(counts),
        "date_from": _to_yyyymmdd(start_date),
        "date_to": _to_yyyymmdd(end_date),
    }
    # 권한 조건이 맨 먼저 들어간다. 시작일 > 종료일 검사는 apply_metadata_filters 가 한다.
    where = apply_rbac_filter(user, apply_metadata_filters(filters))

    seen: dict[str, set[str]] = {company_id: set() for company_id in counts}
    for metadata in get_chunk_metadatas(where):
        company_id = metadata.get("company_id")
        doc_id = metadata.get("doc_id")
        if company_id in seen and doc_id:
            seen[company_id].add(doc_id)

    return {company_id: len(doc_ids) for company_id, doc_ids in seen.items()}


def _to_yyyymmdd(value: date) -> int:
    """Chroma published_date 비교용 정수 (2025-07-01 → 20250701)."""
    return value.year * 10000 + value.month * 100 + value.day
