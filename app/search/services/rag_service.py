from collections.abc import Mapping, Sequence
from typing import Any

def _get_field(chunk: Any, name: str, default=None) :
    """딕셔너리 또는 객체에서 필드 값을 가져옵니다"""
    if isinstance(chunk, Mapping):
        return chunk.get(name, default)

    return getattr(chunk, name, default)

def _normalize_chunk(chunk: Any) -> dict | None:
    """검색 결과 청크를 공통 형식으로 변환합니다."""

    # 1. 문서 내용 추출
    text = (
        _get_field(chunk, "page_content")
        or _get_field(chunk, "content")
        or _get_field(chunk, "text")
    )

    if not isinstance(text, str) or not text.strip():
        return None

    # 2. 메타데이터 추출
    metadata = _get_field(chunk, "metadata", {})

    if not isinstance(metadata, Mapping):
        metadata = {}

    def field(*names):
        for name in names:
            value = metadata.get(name)

            if value is None or value == "":
                value = _get_field(chunk, name)

            if value is not None and value != "":
                return value

        return None

    # 3. 회사 및 파일 정보
    company = (
        field("company_name", "company", "company_id")
        or "회사 정보 없음"
    )

    filename = (
        field("filename", "file_name", "document_name", "source")
        or "파일 정보 없음"
    )

    filename = str(filename).replace("\\", "/").split("/")[-1]

    # 4. 문서 위치 정보
    location = field("location")

    if location is None:
        for name, label in [
            ("page", "페이지"),
            ("slide", "슬라이드"),
            ("paragraph", "문단"),
        ]:
            value = field(name)

            if value is not None:
                location = f"{label} {value}"
                break

    # 5. 공통 형식 반환
    return {
        "text": text.strip(),
        "company": str(company),
        "filename": filename,
        "location": str(location) if location is not None else "위치 정보 없음",
        "doc_id": field("doc_id", "document_id"),
        "chunk_id": field("chunk_id", "id"),
    }

def prepare_context(chunks: Sequence[Any]) -> tuple[str, list[dict]]:
    """검색 청크를 LLM 입력용 컨텍스트롤 변환합니다."""

    sections = []
    sources = []

    for chunk in chunks:
        normalized = _normalize_chunk(chunk)

        # 내용이 없는 청크 제외
        if normalized is None:
            continue

        # 유효한 청크에만 출처 번호 부여
        number = len(sources) + 1

        section = (
            f"[문서 {number}]\n"
            f"회사: {normalized['company']}\n"
            f"파일: {normalized['filename']}\n"
            f"위치: {normalized['location']}\n"
            f"내용:\n{normalized['text']}"
        )

        sections.append(section)
        sources.append(normalized)

    context = "\n\n".join(sections)

    return context, sources