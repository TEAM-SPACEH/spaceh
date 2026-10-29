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

# 섹션별 근거 선별에 사용할 키워드
MAX_SECTION_CHUNKS = 12
SECTION_KEYWORDS = {
    SectionType.OVERVIEW: (
        "개요", "배경", "시장", "산업", "동향",
        "전망", "환경", "연구", "기술",
    ),
    SectionType.STATUS: (
        "현황", "사업", "제품", "공급", "생산",
        "운영", "수주", "도입", "설비",
        "투자", "구축", "개발", "확대",
    ),
    SectionType.PERFORMANCE: (
        "매출", "영업이익", "순이익", "실적",
        "매출액", "영업수익", "재무",
        "분기", "전년 대비",
    ),
}


def _get_chunk_body(chunk: Chunk) -> str:
    """출처 접두어를 제외하고 근거 본문을 가져온다."""
    text = chunk.text.strip()

    # '[회사 · 문서 · 위치] 본문' 형식에서 본문만 추출
    if text.startswith("[") and "] " in text:
        text = text.split("] ", 1)[1]

    section = chunk.metadata.get("section", "")
    return f"{section} {text}".lower()


def select_section_evidence(
    section_type: SectionType,
    collection: CollectionResult,
) -> list[Chunk]:
    """R-01 섹션 목적에 맞는 근거 청크를 선별한다."""

    chunks = [
        chunk for chunk in collection.chunks
        if chunk.text and chunk.text.strip()
    ]

    if not chunks:
        return []

    # 1. 시너지: 2개 이상 기업의 관련 근거가 필요
    if section_type == SectionType.SYNERGY:
        companies = {
            chunk.metadata.get("company_id")
            for chunk in chunks
            if chunk.metadata.get("company_id")
        }

        if len(companies) < 2:
            return []

        # 기존 회사별 균형 순서를 유지
        return chunks[:MAX_SECTION_CHUNKS]

    # 2. 제언: 수집된 근거를 활용해 제안 작성
    if section_type == SectionType.ADVICE:
        return chunks[:MAX_SECTION_CHUNKS]

    # 3. 나머지 섹션: 관련 키워드 기반 선별
    keywords = SECTION_KEYWORDS.get(section_type)
    if not keywords:
        return []

    selected = []

    for chunk in chunks:
        body = _get_chunk_body(chunk)

        if not any(keyword in body for keyword in keywords):
            continue

        # 실적 비교는 공시 수치 근거만 사용
        if section_type == SectionType.PERFORMANCE:
            metadata = chunk.metadata

            if (
                metadata.get("source_type") != "dart"
                and metadata.get("doc_type") != "disclosure"
            ):
                continue

            # 연도만 있는 자료가 아니라 실제 수치가 있는지 확인
            if not re.search(
                r"\d[\d,.]*\s*(?:%|조|억|만|원)",
                body,
            ):
                continue

        selected.append(chunk)

    # 적합한 근거가 없으면 빈 목록 반환
    # R-02가 AI 호출 없이 '근거 자료 없음' 처리
    return selected[:MAX_SECTION_CHUNKS]
