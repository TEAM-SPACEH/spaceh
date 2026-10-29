"""R-01 주제 기반 연관 문서 수집 및 회사별 균형 수집."""

from app.reports.models.report_models import (
    Chunk,
    CollectionResult,
    ReportRequest,
)
from app.search.services.search_service import (
    apply_metadata_filters,
    hybrid_search,
)


def collect_documents(user: dict, request: ReportRequest) -> list[Chunk]:
    """주제·기업·기간에 맞는 문서를 권한에 따라 검색한다."""

    # 1. 보고서 주제 확인
    topic = (request.topic or "").strip()
    if not topic:
        raise ValueError("보고서 주제를 입력해 주세요.")

    # 2. 선택한 기업 확인 (중복 기업 제거)
    company_ids = list(dict.fromkeys(request.company_ids))
    if not company_ids:
        raise ValueError("보고서 대상 기업을 선택해 주세요.")

    # 3. 날짜를 Chroma 메타데이터 형식(YYYYMMDD)으로 변환
    date_from = int(request.start_date.strftime("%Y%m%d"))
    date_to = int(request.end_date.strftime("%Y%m%d"))

    # 4. 수집 결과 및 중복 확인용 변수
    collected = []
    seen_ids = set()

    # 5. 기업별로 검색
    for company_id in company_ids:

        # 회사와 기간 조건 생성
        filters = apply_metadata_filters({
            "companies": [company_id],
            "date_from": date_from,
            "date_to": date_to,
        })

        # 기존 하이브리드 검색 사용
        # 내부에서 S-03 권한 사전 필터가 적용됨
        results = hybrid_search(
            topic,
            filters,
            user,
            audit=False,
        )

        # 6. 검색 결과를 Chunk 객체로 변환
        for result in results:
            metadata = result.get("metadata") or {}
            chunk_id = result.get("chunk_id")
            text = result.get("text")

            # 다른 기업의 청크 또는 불완전한 결과 제외
            if metadata.get("company_id") != company_id:
                continue

            if not chunk_id or not text or not text.strip():
                continue

            # 동일 청크 중복 제거
            if chunk_id in seen_ids:
                continue

            seen_ids.add(chunk_id)

            collected.append(
                Chunk(
                    chunk_id=chunk_id,
                    text=text,
                    metadata=metadata,
                )
            )

    return collected


def balance_by_company(
    chunks: list[Chunk],
    companies: list[str],
) -> CollectionResult:
    """회사별 관련 청크를 같은 개수씩 선정하고 근거 없는 회사를 기록한다."""

    # 1. 선택한 기업 목록 (중복 제거)
    company_ids = list(dict.fromkeys(companies))

    # 2. 기업별 청크 분류
    by_company = {company_id: [] for company_id in company_ids}
    seen_ids = set()

    for chunk in chunks:
        company_id = chunk.metadata.get("company_id")

        # 선택하지 않은 기업의 청크 제외
        if company_id not in by_company:
            continue

        # 동일 청크 중복 제거
        if chunk.chunk_id in seen_ids:
            continue

        seen_ids.add(chunk.chunk_id)
        by_company[company_id].append(chunk)

    # 3. 근거가 없는 기업 기록
    empty_companies = [
        company_id
        for company_id in company_ids
        if not by_company[company_id]
    ]

    # 4. 근거가 있는 기업만 추출
    available = [
        by_company[company_id]
        for company_id in company_ids
        if by_company[company_id]
    ]

    # 모든 기업의 검색 결과가 없는 경우
    if not available:
        return CollectionResult(
            chunks=[],
            empty_companies=empty_companies,
        )

    # 5. 기업별 동일 개수 선정
    # collect_documents()가 관련도 순으로 가져온 상태를 유지
    limit = min(len(company_chunks) for company_chunks in available)

    # 6. 기업별로 번갈아 배치
    balanced_chunks = []

    for index in range(limit):
        for company_chunks in available:
            balanced_chunks.append(company_chunks[index])

    return CollectionResult(
        chunks=balanced_chunks,
        empty_companies=empty_companies,
    )
