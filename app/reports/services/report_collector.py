"""R-01 주제 기반 연관 문서 수집 및 회사별 균형 수집."""
import re

from app.reports.models.report_models import (
    Chunk,
    CollectionResult,
    ReportRequest,
    SectionType,
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
    """회사별 청크를 번갈아 배치하고 근거 없는 회사를 기록한다."""

    # 1. 선택 기업 중복 제거
    company_ids = list(dict.fromkeys(companies))

    # 2. 회사별 청크 분류
    by_company = {company_id: [] for company_id in company_ids}
    seen_ids = set()

    for chunk in chunks:
        company_id = chunk.metadata.get("company_id")

        if company_id not in by_company:
            continue

        if chunk.chunk_id in seen_ids:
            continue

        seen_ids.add(chunk.chunk_id)
        by_company[company_id].append(chunk)

    # 3. 근거 없는 회사 기록
    empty_companies = [
        company_id
        for company_id in company_ids
        if not by_company[company_id]
    ]

    available = [
        by_company[company_id]
        for company_id in company_ids
        if by_company[company_id]
    ]

    if not available:
        return CollectionResult(
            chunks=[],
            empty_companies=empty_companies,
        )

    # 4. 회사별 청크를 번갈아 배치
    # 청크가 부족한 회사는 건너뛰고 나머지는 계속 수집
    balanced_chunks = []

    max_count = max(len(company_chunks) for company_chunks in available)

    for index in range(max_count):
        for company_chunks in available:
            if index < len(company_chunks):
                balanced_chunks.append(company_chunks[index])

    return CollectionResult(
        chunks=balanced_chunks,
        empty_companies=empty_companies,
    )

def select_section_evidence(
    section_type: SectionType,
    collection: CollectionResult,
) -> list[Chunk]:
    """R-01 회사별 균형 수집 결과에서 섹션 근거를 선택한다."""

    # 1. 본문이 없는 청크 제외
    chunks = [
        chunk
        for chunk in collection.chunks
        if chunk.text and chunk.text.strip()
    ]

    if not chunks:
        return []

    # 2. 시너지: 최소 2개 기업의 근거가 필요
    if section_type == SectionType.SYNERGY:
        companies = {
            chunk.metadata.get("company_id")
            for chunk in chunks
            if chunk.metadata.get("company_id")
        }

        if len(companies) < 2:
            return []

        return chunks.copy()

    # 3. 실적 비교: 내부 문서와 DART 모두 허용
    # 실제 수치가 포함된 청크만 선별
    if section_type == SectionType.PERFORMANCE:
        return [
            chunk
            for chunk in chunks
            if re.search(
                r"\d[\d,.]*\s*(?:%|조|억|만|원)",
                chunk.text,
            )
        ]

    # 4. 나머지 섹션은 키워드로 추가 필터링하지 않음
    if section_type in (
        SectionType.OVERVIEW,
        SectionType.STATUS,
        SectionType.ADVICE,
    ):
        return chunks.copy()

    return []
