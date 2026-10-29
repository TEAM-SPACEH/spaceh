"""R-02 양식별 섹션 구성, 섹션 프롬프트 조립, AI 섹션 작성, 보고서 초안 생성."""

# ─────────────────────────────────────────────────────────────
# 함수 4개가 이렇게 이어져요.
#
#   generate_draft()                ④ 전체 지휘: 섹션 순서대로 ③을 부름
#     ├─ get_template_sections()    ① 양식 → 섹션 순서
#     └─ generate_section()         ③ 섹션 하나를 AI로 작성
#          └─ build_section_prompt() ② AI에게 줄 지시문 조립
#
# services 파일이라 화면 코드(st.*)는 쓰지 않아요. (팀 규칙)
# ─────────────────────────────────────────────────────────────

import logging
import re  # 정규식: 글자 속에서 "[숫자]" 같은 패턴을 찾을 때 써요

from langchain_openai import ChatOpenAI  # OpenAI 모델을 부르는 LangChain 도구 (requirements.txt에 있음)

from core import config  # 모델 이름·API 키는 반드시 여기서 읽어요 (팀 규칙)
# A-07 계열사 목록 {"id": 코드, "name": 회사명}. "보고서 대상 선택지용"으로 만들어진 공통 함수예요.
# 회사 목록을 코드에 직접 적지 말고 이 함수를 쓰는 게 팀 규칙이에요.
from app.admin.services.company_service import get_company_options
# S-04(김소은)가 청크를 출처 모양으로 바꿀 때 쓰는 함수예요.
# 같은 함수를 써야 답변 출처와 보고서 출처의 회사·파일·위치 표기가 똑같아져요.
from app.search.services.rag_service import prepare_context
from app.reports.models.report_models import (
    Chunk, CollectionResult, ReportRequest, ReportTemplate, Section, SectionType,
)
from app.reports.services.prompts import (
    COMMON_RULES, NO_EVIDENCE_TEXT, SECTION_GUIDES, SECTION_PROMPT_TEMPLATE, SECTION_TITLES,
)
# 지금은 가짜예요. 김소은의 R-01이 완성되면 이 줄만 아래처럼 바꿔요.
#   from app.reports.services.report_collector import select_section_evidence
from app.reports.mock_data import select_section_evidence

logger = logging.getLogger(__name__)

# 본문 속 근거 번호 [1], [12] ... 를 찾는 패턴. (\d+) 부분이 숫자만 따로 꺼내 줘요.
CITATION_PATTERN = re.compile(r"\[(\d+)\]")

# 본문을 "문장 + 뒤에 붙은 근거 번호" 단위로 자르는 패턴.
#   (?:\.(?=\d)|[^.!?。\n])+  문장 내용. 마침표는 "3.5%"처럼 뒤에 숫자가 올 때만 내용으로 봐요.
#   [.!?。]*                 문장 끝 기호
#   (?:\s*\[\d+\])*          문장 끝에 붙은 근거 번호들 ("있음.[1][3]")
# 예: "증가함.[1] 확대 중임.[2]" → ["증가함.[1]", " 확대 중임.[2]"]
SENTENCE_PATTERN = re.compile(r"(?:\.(?=\d)|[^.!?。\n])+[.!?。]*(?:\s*\[\d+\])*")

# 섹션 하나의 프롬프트에 넣을 근거 글자 수 한도.
# 청크가 너무 많으면 AI 모델이 한 번에 받을 수 있는 양을 넘어 요청이 실패해요.
# S-04 후속 질문(#60)처럼 토큰 대신 글자 수로 어림잡아요. (토큰 계산 패키지를 따로 들이지 않으려고)
# 보고서는 여러 회사 근거를 함께 보므로 #60(8000자)보다 넉넉하게 잡았어요.
EVIDENCE_CHAR_BUDGET = 12000

# 양식별 섹션 순서표. 이 순서대로 보고서를 써요.
TEMPLATE_SECTIONS = {
    # 종합 보고서: 명세서에 정해진 4단 (개요 · 현황 · 시너지 · 제언)
    ReportTemplate.COMPREHENSIVE: [
        SectionType.OVERVIEW, SectionType.STATUS, SectionType.SYNERGY, SectionType.ADVICE,
    ],
    # 분기 실적 보고서: 📌 명세서에 구성이 없어서 임시로 정했어요. 팀 확인이 필요해요.
    ReportTemplate.QUARTERLY: [
        SectionType.OVERVIEW, SectionType.PERFORMANCE, SectionType.ADVICE,
    ],
}


# ─────────────────────────────────────────────────────────────
# ① 양식별 섹션 구성
# ─────────────────────────────────────────────────────────────
def get_template_sections(template: ReportTemplate) -> list[SectionType]:
    """R-02 선택한 양식에 맞는 섹션 목록과 작성 순서를 돌려준다."""
    # 순서표에 없는 양식이 들어오면 잘못된 요청이니 오류를 내요.
    if template not in TEMPLATE_SECTIONS:
        raise ValueError(f"알 수 없는 보고서 양식: {template}")

    # list(...)로 복사본을 돌려줘요.
    # 원본을 그대로 주면, 받은 쪽에서 실수로 목록을 고쳤을 때 순서표 자체가 망가져요.
    return list(TEMPLATE_SECTIONS[template])


def get_company_names(company_ids: list[str]) -> list[str]:
    """R-02 회사 코드 목록을 회사 이름 목록으로 바꾼다. 이름을 모르는 코드는 코드 그대로 둔다."""
    # {"ELV": "현대엘리베이터", ...} 처럼 코드 → 이름 사전을 만들어요.
    names = {option["id"]: option["name"] for option in get_company_options()}
    # names.get(코드, 코드): 사전에 있으면 이름, 없으면(사용 중지된 회사 등) 코드를 그대로 써요.
    # 이름을 못 찾았다고 보고서 전체를 멈추는 것보다, 코드라도 보여 주는 게 나아요.
    return [names.get(company_id, company_id) for company_id in company_ids]


# ─────────────────────────────────────────────────────────────
# ② 섹션 프롬프트 구성
# ─────────────────────────────────────────────────────────────
def build_section_prompt(
    section_type: SectionType,
    chunks: list[Chunk],
    request: ReportRequest,
    previous_sections: list[Section] | None = None,
) -> str:
    """R-02 섹션 지침·보고서 조건·번호 붙인 근거 청크를 하나의 프롬프트로 조립한다."""
    # 📌 previous_sections는 명세서에 없는 입력이에요.
    #    "제언은 앞 섹션 내용을 참고한다"는 명세를 지키려면 앞 섹션을 받을 자리가 필요해서 추가했어요.
    #    기본값이 None이라, 명세서대로 3개만 넣어서 불러도 그대로 동작해요.

    # ── 근거에 번호 붙이기 ──
    # enumerate(chunks, start=1) → (1, 첫 청크), (2, 두 번째 청크) ...
    # 결과 예:
    #   [1] [현대엘리베이터 · 사업보고서 · p.12] 물류센터용 ...
    #   [2] [현대무벡스 · 반기보고서 · II. 사업의 내용] 스마트 물류 ...
    # "\n\n".join(...)은 목록 사이사이에 빈 줄을 넣어 하나의 글로 이어 붙여요.
    evidence = "\n\n".join(
        f"[{number}] {chunk.text}" for number, chunk in enumerate(chunks, start=1)
    )

    # ── 앞 섹션 내용 (제언 섹션에서만 들어와요) ──
    previous = ""
    if previous_sections:
        parts = []
        for section in previous_sections:
            # "근거 자료 없음" 섹션은 참고할 내용이 없어서 건너뛰어요.
            if not section.has_evidence:
                continue
            # ⚠️ 앞 섹션 본문의 [1], [2]는 "그 섹션의" 근거 번호예요.
            #    그대로 넘기면 AI가 제언에 엉뚱한 번호를 따라 쓸 수 있어서 번호를 지우고 넘겨요.
            #    r"\[\d+\]" = "[ + 숫자 1개 이상 + ]" 패턴. re.sub로 찾은 부분을 ""(빈 글자)로 바꿔요.
            clean_body = re.sub(r"\[\d+\]", "", section.body)
            parts.append(f"## {section.title}\n{clean_body}")
        if parts:
            previous = (
                "\n[앞 섹션 내용 — 참고만 하고, 이와 어긋나지 않는 결론을 낸다. "
                "근거 번호는 아래 [근거]의 번호만 쓴다]\n"
                + "\n\n".join(parts)
                + "\n"
            )

    # ── 틀에 값 채워 넣기 ──
    # .format(이름=값)은 틀 안의 {이름} 자리를 값으로 바꿔요.
    return SECTION_PROMPT_TEMPLATE.format(
        rules=COMMON_RULES,
        topic=request.topic,
        # AI는 "ELV"보다 "현대엘리베이터"를 더 잘 알아들어서, 프롬프트에는 회사 이름을 넣어요.
        companies=", ".join(get_company_names(request.company_ids)),  # ["ELV", "MVX"] → "현대엘리베이터, 현대무벡스"
        start_date=request.start_date.isoformat(),  # date(2025, 1, 1) → "2025-01-01"
        end_date=request.end_date.isoformat(),
        title=SECTION_TITLES[section_type.value],   # "status" → "현황"
        guide=SECTION_GUIDES[section_type.value],
        previous=previous,
        evidence=evidence,
    )


# ─────────────────────────────────────────────────────────────
# 근거 없음 판정 · 출처 만들기 (generate_section이 쓰는 도우미)
# ─────────────────────────────────────────────────────────────
def is_no_evidence(body: str) -> bool:
    """R-02 섹션 본문이 '근거 자료 없음' 상태인지 판정한다."""
    # S-04의 is_no_answer()와 같은 방식이에요.
    # AI가 "근거 자료 없음." 처럼 마침표를 붙이거나 앞뒤에 빈칸을 넣어도 같은 뜻으로 봐요.
    # (예전에는 글자가 완전히 같을 때만 알아봐서, 마침표 하나로 "근거 있음"이 돼 버렸어요.)
    # 화면에서도 이 함수로 판정하도록 밖에서 쓸 수 있게 공개 함수로 뒀어요.
    normalized = body.strip().rstrip(".!。").strip()
    return normalized == NO_EVIDENCE_TEXT


def has_valid_citations(body: str, evidence_count: int) -> bool:
    """R-02 본문의 모든 문장에 근거 번호가 있고, 번호가 1 ~ 근거 개수 안에 있는지 검사한다."""
    # S-04 validate_answer()처럼 AI 답을 그대로 믿지 않고 한 번 더 확인해요.
    # 막는 경우:
    #   "문장 하나.[99]"                  → 근거가 3개뿐인데 99번 → 연결할 출처가 없음
    #   "인용 없는 문장. 다음 문장.[1]"     → 첫 문장에 번호가 없음 → 근거 없는 내용일 수 있음
    sentences = SENTENCE_PATTERN.findall(body)
    checked = 0  # 실제로 검사한 문장 수

    for sentence in sentences:
        # 글자(한글·영어)가 하나도 없는 조각은 문장이 아니라서 건너뛰어요.
        # 예: 빈칸, 목록 번호 "1." → 이걸 문장으로 보면 번호가 없다고 잘못 막아요.
        # [^\W\d_] = "글자이면서 숫자·밑줄이 아닌 것" = 한글·영어 같은 문자
        if not re.search(r"[^\W\d_]", sentence):
            continue
        checked += 1

        numbers = [int(number) for number in CITATION_PATTERN.findall(sentence)]
        if not numbers:  # 이 문장에 근거 번호가 하나도 없어요
            return False
        # any(...)는 하나라도 조건에 맞으면 True예요. 범위 밖 번호가 하나라도 있으면 실패.
        if any(number < 1 or number > evidence_count for number in numbers):
            return False

    # 검사할 문장이 하나도 없었다면 쓸 만한 본문이 아니에요.
    return checked > 0


def select_chunks_within_budget(chunks: list[Chunk], budget_chars: int = EVIDENCE_CHAR_BUDGET) -> list[Chunk]:
    """R-02 글자 예산 안에 드는 앞쪽 근거 청크만 고른다. 첫 청크는 예산을 넘어도 넣는다."""
    # S-04 _select_chunks_within_budget()(#60)과 같은 방식이에요.
    # 앞쪽 청크부터 담아요. R-01이 중요한 근거를 앞에 두도록 순서를 정해 줘야 해요.
    # 📌 회사별로 몰아서(A사 전부 → B사 전부) 주면 뒤쪽 회사가 잘릴 수 있어서 R-01과 순서를 맞춰야 해요.
    selected: list[Chunk] = []
    used = 0  # 지금까지 담은 글자 수

    for chunk in chunks:
        length = len(chunk.text)
        # 이미 하나 이상 담았고, 이번 청크까지 넣으면 한도를 넘으면 멈춰요.
        # (첫 청크는 길어도 넣어요. 안 그러면 근거가 통째로 비어 버려요.)
        if selected and used + length > budget_chars:
            break
        selected.append(chunk)
        used += length

    if len(selected) < len(chunks):
        # 팀 규칙: 본문은 로그에 남기지 않아요. 개수만 남겨요.
        logger.warning("R-02 근거 글자 예산 초과 used=%d/%d chunks", len(selected), len(chunks))
    return selected


def build_section_sources(chunks: list[Chunk]) -> list[dict]:
    """R-02 섹션 근거 청크를 S-04 답변 출처와 같은 모양의 목록으로 바꾼다."""
    # prepare_context()는 (AI용 글, 출처 목록)을 돌려줘요. 여기서는 출처 목록만 써요.
    # 앞의 _ 는 "이 값은 안 쓴다"는 파이썬 관습이에요.
    _, sources = prepare_context(chunks)

    # 본문의 [1]이 sources의 첫 번째와 이어지도록 번호를 1부터 붙여요.
    # S-04 출처도 citation_number 칸에 번호를 담아서, 같은 이름을 써요.
    for number, source in enumerate(sources, start=1):
        source["citation_number"] = number
    return sources


# ─────────────────────────────────────────────────────────────
# ③ 섹션 본문 생성 (여기서 AI를 불러요)
# ─────────────────────────────────────────────────────────────
def _get_llm() -> ChatOpenAI:
    """보고서 작성용 LLM을 만든다."""
    # 이름 앞 _(밑줄) = 이 파일 안에서만 쓰는 도우미라는 표시예요.
    # 함수로 따로 빼 둔 이유: 테스트할 때 이 함수만 가짜로 바꾸면
    # API 비용 없이 테스트할 수 있어요.
    return ChatOpenAI(
        model=config.LLM_MODEL,         # 개발: gpt-4o-mini / 시연: gpt-4o (.env에서 바꿔요)
        api_key=config.OPENAI_API_KEY,  # 키는 코드에 직접 쓰지 않고 .env에서만 읽어요
        temperature=0,                  # 0 = 지어내지 않고 일관되게. 보고서는 창의성보다 정확성이 중요해요.
    )


def generate_section(
    section_type: SectionType,
    chunks: list[Chunk],
    request: ReportRequest,
    previous_sections: list[Section] | None = None,
) -> Section:
    """R-02 근거 청크만으로 섹션 본문을 생성하고 문장마다 근거 번호 [n]을 단다."""
    title = SECTION_TITLES[section_type.value]

    # ── 본문이 빈 청크는 미리 빼요 ──
    # prepare_context()는 본문 없는 청크를 출처에서 빼요.
    # 프롬프트에는 남기고 출처에서만 빠지면 [2]가 엉뚱한 출처를 가리켜서, 처음부터 같이 빼요.
    chunks = [chunk for chunk in chunks if chunk.text and chunk.text.strip()]

    # ── 글자 예산 안의 청크만 남겨요 ──
    # 여기서 잘라야 프롬프트 번호 [n], evidence, sources가 모두 같은 청크 목록을 써요.
    chunks = select_chunks_within_budget(chunks)

    # ── 근거가 0개면 AI를 부르지 않아요 ──
    # 근거 없이 쓰라고 하면 AI가 지어낼 위험이 크고, 비용도 아까워요.
    if not chunks:
        return Section(
            section_type=section_type,
            title=title,
            body=NO_EVIDENCE_TEXT,
            evidence=[],
            has_evidence=False,
        )

    # ── 프롬프트 만들기 → AI에게 보내기 ──
    prompt = build_section_prompt(section_type, chunks, request, previous_sections)
    # 팀 규칙: 문서 본문은 로그에 남기지 않아요. 그래서 섹션 이름과 개수만 남겨요.
    logger.info("R-02 섹션 생성 section=%s chunks=%d", section_type.value, len(chunks))

    # invoke(글자)는 AI에게 글자를 보내고 답을 받아요. 답의 글자는 .content에 들어 있어요.
    # API 오류가 나면 여기서 예외가 발생해요. 일부러 잡지 않고 위로 올려 보내요.
    # → 보고서 전체 흐름(create_report)이 "중간에 실패하면 저장하지 않고 오류 반환"하도록 명세되어 있어서예요.
    response = _get_llm().invoke(prompt)
    body = response.content.strip()  # strip(): 앞뒤 빈칸·빈 줄 제거

    # AI가 "근거 자료 없음"이라고 답했거나, 아무것도 쓰지 않았으면(빈 답) 근거 없는 섹션으로 표시해요.
    # 빈 답을 그냥 두면 본문은 비었는데 근거·출처만 붙은 이상한 섹션이 돼요.
    has_evidence = bool(body) and not is_no_evidence(body)

    # 근거 번호 검사: 번호 없는 문장이나 범위 밖 번호가 있으면 섹션 전체를 "근거 자료 없음"으로 바꿔요.
    # S-04도 검증에 실패한 답변은 통째로 "찾을 수 없음"으로 바꿔요.
    # 일부 문장만 지우면 남은 글의 앞뒤가 안 맞을 수 있어서, 섹션 단위로 처리해요.
    if has_evidence and not has_valid_citations(body, len(chunks)):
        # 팀 규칙: 본문은 로그에 남기지 않아요. 섹션 이름만 남겨요.
        logger.warning("R-02 근거 번호 검증 실패 section=%s", section_type.value)
        has_evidence = False

    if not has_evidence:
        body = NO_EVIDENCE_TEXT  # "근거 자료 없음." 같은 변형을 정해진 문구 하나로 맞춰요

    return Section(
        section_type=section_type,
        title=title,
        body=body,
        evidence=chunks if has_evidence else [],  # [1]=chunks[0], [2]=chunks[1] ...
        has_evidence=has_evidence,
        sources=build_section_sources(chunks) if has_evidence else [],
    )


# ─────────────────────────────────────────────────────────────
# ④ 보고서 초안 생성 (전체 지휘)
# ─────────────────────────────────────────────────────────────
def generate_draft(request: ReportRequest, collection: CollectionResult) -> list[Section]:
    """R-02 양식의 섹션 순서대로 generate_section()을 호출해 보고서 초안을 만든다."""
    sections: list[Section] = []  # 완성된 섹션을 차곡차곡 담을 빈 목록

    # 양식에 맞는 섹션 순서대로 하나씩 처리해요.
    # 종합 보고서면 AI를 최대 4번 불러요. 팀 규칙의 "반복문 안 LLM 호출 금지"는
    # 청크마다 부르는 것을 막는 뜻이고, 섹션마다 부르는 건 명세서가 정한 방식이에요.
    for section_type in get_template_sections(request.template):

        # 이 섹션 목적에 맞는 근거만 골라요. (김소은의 R-01 함수, 지금은 가짜)
        chunks = select_section_evidence(section_type, collection)

        # 제언 섹션일 때만 지금까지 완성된 섹션을 참고 자료로 넘겨요.
        # 제언이 맨 마지막 순서라, 이때 sections에는 앞 섹션들이 모두 들어 있어요.
        previous = sections if section_type == SectionType.ADVICE else None

        section = generate_section(section_type, chunks, request, previous_sections=previous)
        sections.append(section)  # 완성된 섹션을 목록 끝에 추가

    return sections
