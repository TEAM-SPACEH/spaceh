from collections.abc import Mapping, Sequence
from typing import Any

from dotenv import load_dotenv

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI

from .rag_prompt import SYSTEM_PROMPT, USER_PROMPT

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

def _generate_with_openai(query: str, context: str) -> str:
    """OpenAI LLM을 활용해 문서 기반 답변을 생성합니다."""

    # 1. 환경변수 불러오기
    load_dotenv()

    # 2. 프롬프트 구성
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", USER_PROMPT),
    ])

    # 3. OpenAI 모델 설정
    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0,
    )

    # 4. LCEL 체인 구성
    chain = prompt | llm | StrOutputParser()

    # 5. 답변 생성
    answer = chain.invoke({
        "query": query,
        "context": context,
    })

    return answer

def generate_answer(query: str, chunks: Sequence[Any]) -> dict[str, Any]:
    """검색된 문서 청크를 기반으로 AI 답변을 생성합니다."""

    # 1. 질문 유효성 검사
    if not isinstance(query, str) or not query.strip():
        raise ValueError("질문을 입력해 주세요.")

    # 2. 문서 청크를 컨텍스트로 변환
    context, sources = prepare_context(chunks)

    # 3. 검색 결과가 없는 경우
    if not sources:
        return {
            "answer": "찾을 수 없음",
            "sources": [],
        }

    # 4. OpenAI를 통한 답변 생성
    answer = _generate_with_openai(query.strip(), context)

    # 5. 답변 및 출처 후보 반환
    return {
        "answer": answer.strip(),
        "sources": sources,
    }