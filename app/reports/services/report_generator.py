"""R-02 양식별 섹션 구성, 섹션 프롬프트 조립, AI 섹션 작성, 보고서 초안 생성."""

# ─────────────────────────────────────────────────────────────
# 함수 4개가 이렇게 이어져요.
#
#   generate_draft()                ④ 전체 지휘: 섹션 순서대로 ③을 부름
#     ├─ get_template_sections()    ① 양식 → 섹션 순서
#     └─ generate_section()         ③ 섹션 하나를 AI로 작성
#          ├─ build_section_prompt() ② AI에게 줄 지시문 조립
#          └─ check_sentences()      문장마다 근거 번호·수치·회사 수 검사
#
# 근거 검사에 걸렸을 때 3단계로 처리해요. (섹션을 통째로 버리는 일을 줄이려고)
#   1. 재시도 1번: 무엇이 틀렸는지 알려 주고 다시 쓰게 해요.
#   2. 문장 단위 제거: 그래도 틀리면 틀린 문장만 빼요. 남은 문장이 60% 이상·2문장 이상이면 살려요(partial).
#   3. 포기: 그보다 적게 남으면 "근거 자료 없음"으로 바꿔요.
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
    COMMON_RULES, NO_COMPANY_EVIDENCE_TEMPLATE, NO_EVIDENCE_TEXT, PROBLEM_NO_CITATION,
    PROBLEM_NUMBER_NOT_FOUND, PROBLEM_OUT_OF_RANGE, PROBLEM_SYNERGY_ONE_COMPANY,
    PROBLEM_TRUNCATED, RETRY_PROMPT_TEMPLATE, SCOPE_SENTENCE_TEMPLATE, SECTION_GUIDES,
    SECTION_PROMPT_TEMPLATE, SECTION_TITLES,
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

# 섹션 하나에 넣을 근거 청크 개수 한도.
# 번호가 [14], [15]처럼 커질수록 AI가 범위 밖 번호를 쓰는 실수가 늘어서 12개로 막아요.
# 📌 회사별 할당량·번갈아 담기는 R-01(김소은)이 해요. 여기 한도는 R-01이 놓쳤을 때만 걸리는 안전장치예요.
MAX_SECTION_CHUNKS = 12

# AI 답 길이 한도(토큰). 한국어 약 1,500~2,000자라 섹션 분량 지침(최대 약 1,050자)보다 넉넉해요.
# 이 한도에 걸려 끊긴 답은 마지막 문장에 번호가 없어서, "끊김"으로 보고 재시도해요.
SECTION_MAX_TOKENS = 1200

# 문장 단위 제거 기준: 남은 문장이 원래 문장 수의 60% 이상이고, 2문장 이상이면 섹션을 살려요.
# 글자 수가 아니라 "문장 개수"로 세요. 문장 길이에 따라 결과가 들쭉날쭉하지 않게 하려고요.
KEEP_RATIO = 0.6
MIN_KEPT_SENTENCES = 2

# 수치 확인에 쓸 "단위가 붙은 숫자" 패턴. 금액·비율처럼 틀리면 위험한 숫자만 검사해요.
#   \d[\d,]*(?:\.\d+)?          숫자 (1,234 / 12.5)
#   \s*(?: ... )                뒤에 붙은 단위:
#     %p | % | 배                비율·배수
#     (?:조|억)\s*원?             조·억 (뒤에 원이 붙어도 되고 안 붙어도 돼요)
#     (?:천만|백만|만|천)?\s*원    원·천원·백만원 …
# "2개 사업부문", "2025년", "3곳"처럼 단위가 없는 숫자는 검사하지 않아요(멀쩡한 문장을 잘못 잡지 않게).
UNIT_NUMBER_PATTERN = re.compile(
    r"\d[\d,]*(?:\.\d+)?\s*(?:%p|%|배|(?:조|억)\s*원?|(?:천만|백만|만|천)?\s*원)"
)

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


def _is_heading_line(line: str) -> bool:
    """번호 없는 머리글 줄인지 본다. 예: '## 현황', '현대엘리베이터:'"""
    # 프롬프트 규칙 7번으로 머리글을 쓰지 말라고 했지만, AI가 가끔 어길 수 있어요(2차 방어).
    # 머리글은 "문장"이 아니라 "제목"이라서, 근거 번호가 없어도 검사에서 빼 줘요.
    line = line.strip()
    # 빈 줄이거나, 근거 번호가 붙어 있으면 머리글로 보지 않아요. (번호가 있으면 문장으로 검사해요)
    if not line or CITATION_PATTERN.search(line):
        return False
    # "#"으로 시작("## 현황")하거나 ":" / "："(전각 콜론)으로 끝나는("현대엘리베이터:") 줄
    # ⚠️ "현대엘리베이터"처럼 기호가 없는 줄은 머리글인지 문장인지 알 수 없어서 그대로 검사해요.
    return line.startswith("#") or line.endswith((":", "："))


def split_sentences(body: str) -> list[str]:
    """R-02 본문을 검사할 문장 목록으로 자른다. 머리글 줄과 글자 없는 조각은 뺀다."""
    # 머리글 줄을 뺀 나머지만 문장으로 봐요.
    # splitlines()는 글을 줄마다 잘라 목록으로 만들고, "\n".join(...)은 다시 이어 붙여요.
    # ⚠️ 검사에서만 빼고, 화면에 보일 본문(body)에서는 지우지 않아요.
    body = "\n".join(line for line in body.splitlines() if not _is_heading_line(line))

    # 글자(한글·영어)가 하나도 없는 조각은 문장이 아니라서 빼요.
    # 예: 빈칸, 목록 번호 "1." → 이걸 문장으로 보면 번호가 없다고 잘못 막아요.
    # [^\W\d_] = "글자이면서 숫자·밑줄이 아닌 것" = 한글·영어 같은 문자
    return [
        sentence for sentence in SENTENCE_PATTERN.findall(body)
        if re.search(r"[^\W\d_]", sentence)
    ]


def _citation_problem(sentence: str, evidence_count: int) -> str | None:
    """문장의 근거 번호 문제를 돌려준다. 문제가 없으면 None."""
    numbers = [int(number) for number in CITATION_PATTERN.findall(sentence)]
    if not numbers:  # 이 문장에 근거 번호가 하나도 없어요
        return PROBLEM_NO_CITATION
    for number in numbers:
        if number < 1 or number > evidence_count:  # 근거 개수를 넘는 번호 (예: 근거 3개인데 [99])
            return PROBLEM_OUT_OF_RANGE.format(number=number, count=evidence_count)
    return None


def _normalize_number_text(text: str) -> str:
    """수치 비교용으로 쉼표·띄어쓰기를 지운다. 예: '1,234 억 원' → '1234억원'"""
    return re.sub(r"[,\s]", "", text)


def _number_problem(sentence: str, cited_chunks: list[Chunk]) -> str | None:
    """문장의 '단위 붙은 숫자'가 인용한 근거 글자에 그대로 있는지 본다. 없으면 문제 문구."""
    # 계산 금지 규칙("근거에 적힌 그대로")을 코드로 가볍게 확인하는 거예요.
    # [n] 근거 번호를 먼저 지워요. 안 그러면 [12]의 12를 숫자로 착각할 수 있어요.
    text = CITATION_PATTERN.sub("", sentence)
    # 인용한 근거들을 하나로 이어 붙이고, 같은 방식으로 쉼표·띄어쓰기를 지워요.
    evidence = _normalize_number_text(" ".join(chunk.text for chunk in cited_chunks))

    for match in UNIT_NUMBER_PATTERN.finditer(text):
        value = match.group(0).strip()  # 문제 문구에 보여 줄 원래 모양 (예: "1,234억 원")
        # 비교할 핵심: 쉼표·띄어쓰기를 지우고, 끝의 "원"·"p"는 떼요.
        # 근거에 "1,234억"만 있고 문장에 "1,234억 원"이라고 써도 같은 숫자로 보려고요. ("12.5%p" → "12.5%")
        core = _normalize_number_text(value).removesuffix("원").removesuffix("p")
        # (?<![\d.]) = 바로 앞이 숫자·소수점이 아니어야 해요. "1.5%"가 "11.5%" 안에서 잘못 찾아지지 않게요.
        if not re.search(r"(?<![\d.])" + re.escape(core), evidence):
            return PROBLEM_NUMBER_NOT_FOUND.format(value=value)
    return None


def _company_of(chunk: Chunk) -> str:
    """청크의 회사 코드 (없으면 회사 이름)."""
    return str(chunk.metadata.get("company_id") or chunk.metadata.get("company_name") or "")


def check_sentences(
    body: str, chunks: list[Chunk], section_type: SectionType,
) -> list[tuple[str, str | None]]:
    """R-02 본문을 문장마다 검사해 (문장, 문제 또는 None) 목록을 돌려준다."""
    # S-04 validate_answer()처럼 AI 답을 그대로 믿지 않고 한 번 더 확인해요.
    # 참/거짓만 돌려주지 않고 "어느 문장이 왜 틀렸는지"를 돌려줘요.
    # → 재시도 때 AI에게 고칠 점을 알려 주고, 문장 단위로 뺄 때도 이 결과를 써요.
    # 검사 순서 (앞에서 걸리면 뒤는 보지 않아요):
    #   1. 근거 번호: 없거나 범위 밖이면 문제
    #   2. 수치: 단위 붙은 숫자가 인용한 근거에 없으면 문제
    #   3. 시너지만: 인용한 근거의 회사가 2곳 미만이면 문제
    results: list[tuple[str, str | None]] = []
    for sentence in split_sentences(body):
        problem = _citation_problem(sentence, len(chunks))
        if problem is None:
            # [1]은 chunks[0]이라 1을 빼서 꺼내요. set(...)으로 같은 번호 중복을 없애요.
            numbers = {int(number) for number in CITATION_PATTERN.findall(sentence)}
            cited = [chunks[number - 1] for number in sorted(numbers)]
            problem = _number_problem(sentence, cited)
            if problem is None and section_type == SectionType.SYNERGY:
                companies = {_company_of(chunk) for chunk in cited}
                if len(companies) < 2:
                    problem = PROBLEM_SYNERGY_ONE_COMPANY
        results.append((sentence, problem))
    return results


def has_valid_citations(body: str, evidence_count: int) -> bool:
    """R-02 본문의 모든 문장에 근거 번호가 있고, 번호가 1 ~ 근거 개수 안에 있는지 검사한다."""
    # 근거 번호만 보는 간단한 검사예요. (수치·시너지 검사까지 하려면 check_sentences()를 써요)
    # 막는 경우:
    #   "문장 하나.[99]"                  → 근거가 3개뿐인데 99번 → 연결할 출처가 없음
    #   "인용 없는 문장. 다음 문장.[1]"     → 첫 문장에 번호가 없음 → 근거 없는 내용일 수 있음
    sentences = split_sentences(body)
    # 검사할 문장이 하나도 없으면 쓸 만한 본문이 아니에요.
    # all(...)은 모두 조건에 맞아야 True예요.
    return bool(sentences) and all(
        _citation_problem(sentence, evidence_count) is None for sentence in sentences
    )


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
        max_tokens=SECTION_MAX_TOKENS,  # 비정상적으로 긴 답을 막는 한도
    )


def _ask_llm(prompt: str) -> tuple[str, bool]:
    """AI에게 프롬프트를 보내고 (답 글자, 길이 한도에 걸려 끊겼는지)를 돌려준다."""
    # invoke(글자)는 AI에게 글자를 보내고 답을 받아요. 답의 글자는 .content에 들어 있어요.
    # API 오류가 나면 여기서 예외가 발생해요. 일부러 잡지 않고 위로 올려 보내요.
    # → 보고서 전체 흐름(create_report)이 "중간에 실패하면 저장하지 않고 오류 반환"하도록 명세되어 있어서예요.
    response = _get_llm().invoke(prompt)

    # response_metadata["finish_reason"]: AI가 답을 멈춘 이유.
    #   "stop"   = 스스로 다 쓰고 멈춤 (정상)
    #   "length" = 길이 한도(max_tokens)에 걸려 문장 중간에 끊김
    metadata = getattr(response, "response_metadata", None)
    truncated = isinstance(metadata, dict) and metadata.get("finish_reason") == "length"
    return response.content.strip(), truncated  # strip(): 앞뒤 빈칸·빈 줄 제거


def _problem_lines(checks: list[tuple[str, str | None]], truncated: bool) -> list[str]:
    """재시도 프롬프트에 넣을 '고칠 점' 목록을 만든다. 예: '- 3번째 문장: 근거 번호 없음'"""
    lines = [
        f"- {number}번째 문장: {problem}"
        for number, (_, problem) in enumerate(checks, start=1)
        if problem is not None
    ]
    if truncated:
        lines.append(f"- {PROBLEM_TRUNCATED}")
    return lines


def _remove_sentences(body: str, bad_sentences: list[str]) -> str:
    """본문에서 잘못된 문장만 지우고, 남은 빈칸·빈 줄을 정리한다."""
    # 문장을 다시 이어 붙이지 않고 원래 본문에서 "빼기"만 해요. 그래야 문단(빈 줄) 모양이 그대로 남아요.
    for sentence in bad_sentences:
        body = body.replace(sentence, "", 1)  # 1 = 맨 처음 찾은 한 곳만 지워요
    # 줄마다 앞뒤 빈칸을 정리하고, 빈 줄이 3줄 이상 이어지면 1줄(문단 나눔)로 줄여요.
    body = "\n".join(line.strip() for line in body.splitlines())
    return re.sub(r"\n{3,}", "\n\n", body).strip()


def _missing_company_lines(
    section_type: SectionType, chunks: list[Chunk], request: ReportRequest,
) -> list[str]:
    """현황·실적 비교 섹션에서 근거가 0건인 회사의 '근거 자료 없음' 줄을 만든다."""
    # 회사마다 문단을 쓰는 섹션만 해당돼요.
    if section_type not in (SectionType.STATUS, SectionType.PERFORMANCE):
        return []
    # 📌 R-01의 empty_companies는 "보고서 전체"에서 0건인 회사예요.
    #    여기서는 "이 섹션 근거"에 없는 회사를 직접 세요. 전체에는 있어도 이 섹션 근거에는 없을 수 있어서예요.
    present = {_company_of(chunk) for chunk in chunks}
    missing = [company_id for company_id in request.company_ids if company_id not in present]
    if not missing:
        return []
    return [NO_COMPANY_EVIDENCE_TEMPLATE.format(company=name) for name in get_company_names(missing)]


def build_scope_sentence(request: ReportRequest, collection: CollectionResult) -> str:
    """R-02 개요 맨 앞에 붙일 범위 문장(대상 회사·기간·근거 문서 수)을 코드로 만든다."""
    # 이 문장에는 붙일 근거 번호가 없어서 AI에게 시키면 검사에 무조건 걸려요. 그래서 코드가 써요.
    # 근거가 1건 이상 있는 회사만 세요. 순서는 사용자가 고른 회사 순서를 따라요.
    present = {_company_of(chunk) for chunk in collection.chunks}
    company_ids = [company_id for company_id in request.company_ids if company_id in present]
    # 문서 수: 같은 문서의 청크가 여러 개여도 1건으로 세요.
    # doc_id가 없으면 chunk_id의 "#" 앞부분(예: "doc-elv#0003" → "doc-elv")을 문서 번호로 봐요.
    doc_ids = {
        str(chunk.metadata.get("doc_id") or chunk.chunk_id.split("#")[0])
        for chunk in collection.chunks
    }
    if not company_ids or not doc_ids:
        return ""  # 근거가 하나도 없으면 범위 문장을 쓰지 않아요
    return SCOPE_SENTENCE_TEMPLATE.format(
        companies="·".join(get_company_names(company_ids)),  # "현대엘리베이터·현대무벡스"
        company_count=len(company_ids),
        start_date=request.start_date.isoformat(),
        end_date=request.end_date.isoformat(),
        doc_count=len(doc_ids),
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

    # ── 청크 개수·글자 예산 안의 청크만 남겨요 (R-01이 놓쳤을 때를 위한 안전장치) ──
    # 여기서 잘라야 프롬프트 번호 [n], evidence, sources가 모두 같은 청크 목록을 써요.
    if len(chunks) > MAX_SECTION_CHUNKS:
        logger.warning("R-02 근거 청크 개수 초과 used=%d/%d", MAX_SECTION_CHUNKS, len(chunks))
        chunks = chunks[:MAX_SECTION_CHUNKS]
    chunks = select_chunks_within_budget(chunks)

    # 근거 없는 섹션을 만드는 짧은 도우미. 아래에서 여러 번 써서 함수로 묶었어요.
    def no_evidence_section() -> Section:
        return Section(
            section_type=section_type, title=title, body=NO_EVIDENCE_TEXT,
            evidence=[], has_evidence=False,
        )

    # ── 근거가 0개면 AI를 부르지 않아요 ──
    # 근거 없이 쓰라고 하면 AI가 지어낼 위험이 크고, 비용도 아까워요.
    if not chunks:
        return no_evidence_section()

    # ── 프롬프트 만들기 → AI에게 보내기 ──
    prompt = build_section_prompt(section_type, chunks, request, previous_sections)
    # 팀 규칙: 문서 본문은 로그에 남기지 않아요. 그래서 섹션 이름과 개수만 남겨요.
    logger.info("R-02 섹션 생성 section=%s chunks=%d", section_type.value, len(chunks))
    body, truncated = _ask_llm(prompt)

    # AI가 "근거 자료 없음"이라고 답했거나, 아무것도 쓰지 않았으면(빈 답) 근거 없는 섹션이에요.
    # 빈 답을 그냥 두면 본문은 비었는데 근거·출처만 붙은 이상한 섹션이 돼요.
    if not body or is_no_evidence(body):
        return no_evidence_section()

    # ── 문장마다 검사 ──
    checks = check_sentences(body, chunks, section_type)
    problems = _problem_lines(checks, truncated)

    # ── 1단계: 재시도 1번 ──
    # 무엇이 틀렸는지 알려 주고 섹션 전체를 다시 쓰게 해요. 실패한 섹션만 다시 불러서 비용이 작아요.
    if problems:
        logger.warning("R-02 근거 검증 재시도 section=%s problems=%d", section_type.value, len(problems))
        retry_prompt = RETRY_PROMPT_TEMPLATE.format(
            prompt=prompt, answer=body, problems="\n".join(problems),
        )
        retry_body, retry_truncated = _ask_llm(retry_prompt)
        # 다시 쓴 답이 비었거나 "근거 자료 없음"이면, 첫 답을 가지고 2단계로 가요.
        if retry_body and not is_no_evidence(retry_body):
            body, truncated = retry_body, retry_truncated
            checks = check_sentences(body, chunks, section_type)
            problems = _problem_lines(checks, truncated)

    # ── 2단계: 문장 단위 제거 / 3단계: 포기 ──
    partial = False
    if problems:
        total = len(checks)
        bad = [sentence for sentence, problem in checks if problem is not None]
        kept = total - len(bad)
        # 남은 문장 수 ÷ 원래 문장 수 ≥ 60% 이고, 2문장 이상 남으면 섹션을 살려요.
        if total and kept / total >= KEEP_RATIO and kept >= MIN_KEPT_SENTENCES:
            logger.warning("R-02 문장 제외 section=%s removed=%d/%d", section_type.value, len(bad), total)
            # 끊긴 답이라도, 끊긴 마지막 문장은 번호가 없어서 bad에 들어가 함께 빠져요.
            body = _remove_sentences(body, bad)
            partial = True
        else:
            logger.warning("R-02 근거 검증 실패로 섹션 제외 section=%s", section_type.value)
            return no_evidence_section()

    # ── 코드가 쓰는 줄: 근거가 0건인 회사 표시 (현황·실적 비교) ──
    # 검사가 끝난 뒤에 붙여요. 이 줄은 근거 번호가 없어서 검사 대상이 아니에요.
    missing_lines = _missing_company_lines(section_type, chunks, request)
    if missing_lines:
        body = body + "\n\n" + "\n".join(missing_lines)

    return Section(
        section_type=section_type,
        title=title,
        body=body,
        evidence=chunks,  # [1]=chunks[0], [2]=chunks[1] ...
        has_evidence=True,
        sources=build_section_sources(chunks),
        partial=partial,
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

        # 개요 맨 앞에 범위 문장(대상 회사·기간·근거 문서 수)을 코드로 붙여요.
        # 수집 결과 전체(collection)를 알아야 해서 generate_section()이 아니라 여기서 붙여요.
        if section_type == SectionType.OVERVIEW and section.has_evidence:
            scope = build_scope_sentence(request, collection)
            if scope:
                section.body = scope + "\n\n" + section.body

        sections.append(section)  # 완성된 섹션을 목록 끝에 추가

    return sections
