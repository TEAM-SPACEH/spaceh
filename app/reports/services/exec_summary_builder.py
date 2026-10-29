"""R-04 의사결정용 1페이지 요약: 요약 생성(build_exec_summary)과 1페이지 분량 조정(fit_one_page)."""

# ─────────────────────────────────────────────────────────────
# 흐름
#   summarize_report(report)        상세보고서(섹션 본문 + 각주) → 1페이지 요약 (AI 1번, 필요하면 재시도 1번)
#     ├─ _code_notes()              근거 없는 섹션·일부 제외 섹션·근거 없는 회사 → 유의사항 (코드가 씀)
#     ├─ build_summary_prompt()     AI에게 줄 지시문 조립
#     └─ check_sentences() 재사용   R-02와 같은 검사 (근거 번호 범위·단위 붙은 수치)
#   fit_one_page(summary)           1,500자·단락 500자를 넘으면 1번 압축 → 그래도 넘치면 "상세보고서 ○○ 참고"
#
# R-02와 같은 3단계로 처리해요: 재시도 1번 → 틀린 문장만 제거 → (항목에 남은 문장이 없으면) 항목 제외
# services 파일이라 화면 코드(st.*)는 쓰지 않아요. (팀 규칙)
# ─────────────────────────────────────────────────────────────

import json
import logging
import re
from dataclasses import replace

from langchain_openai import ChatOpenAI

from core import config
from app.reports.models.report_models import (
    Chunk, ExecSummary, Report, SectionType, SummaryItem,
)
from app.reports.services.prompts import (
    DETAIL_REFERENCE_TEXT, NOTE_COMPANY_NO_EVIDENCE, NOTE_ITEM_DROPPED, NOTE_SECTION_NO_EVIDENCE,
    NOTE_SECTION_PARTIAL, NOTE_SUMMARY_FAILED, PROBLEM_BAD_JSON, PROBLEM_NO_CITATION,
    PROBLEM_TRUNCATED, SECTION_TITLES, SUMMARY_KIND_TITLES, SUMMARY_MAX_CHARS,
    SUMMARY_MAX_PARAGRAPH_CHARS, SUMMARY_PROMPT_TEMPLATE, SUMMARY_RETRY_PROMPT_TEMPLATE,
    SUMMARY_RULES, SUMMARY_SHORTEN_PROMPT_TEMPLATE,
)
# R-02에서 만든 검사 도구를 그대로 써요. 같은 규칙으로 검사해야 상세보고서와 요약의 기준이 같아져요.
from app.reports.services.report_generator import (
    CITATION_PATTERN, SECTION_MAX_TOKENS, UNIT_NUMBER_PATTERN, check_sentences,
    get_company_names, split_sentences,
)

logger = logging.getLogger(__name__)

# 항목 종류별 기본 이동 섹션. AI가 section을 잘못 주면 이걸 써요.
DEFAULT_SECTION_BY_KIND = {
    "key": SectionType.OVERVIEW,
    "company": SectionType.STATUS,
    "advice": SectionType.ADVICE,
}


# ─────────────────────────────────────────────────────────────
# AI 호출 (R-02와 같은 설정)
# ─────────────────────────────────────────────────────────────
def _get_llm() -> ChatOpenAI:
    """요약용 LLM을 만든다. 테스트에서는 이 함수만 가짜로 바꿔요."""
    return ChatOpenAI(
        model=config.LLM_MODEL,
        api_key=config.OPENAI_API_KEY,
        temperature=0,                  # 요약도 지어내지 않고 일관되게
        max_tokens=SECTION_MAX_TOKENS,  # 비정상적으로 긴 답을 막는 안전장치 (명세서: 안전장치로만 쓴다)
    )


def _ask_llm(prompt: str) -> tuple[str, bool]:
    """AI에게 보내고 (답 글자, 길이 한도에 걸려 끊겼는지)를 돌려준다. API 오류는 위로 올려 보낸다."""
    response = _get_llm().invoke(prompt)
    metadata = getattr(response, "response_metadata", None)
    truncated = isinstance(metadata, dict) and metadata.get("finish_reason") == "length"
    return response.content.strip(), truncated


# ─────────────────────────────────────────────────────────────
# 프롬프트 재료 만들기
# ─────────────────────────────────────────────────────────────
def _footnote_chunks(report: Report) -> list[Chunk]:
    """각주를 번호 순서대로 Chunk 모양으로 바꾼다. [n] = 목록의 n-1번째."""
    # check_sentences()는 Chunk 목록을 받아요. 각주 본문(text)과 회사 코드를 그대로 옮겨 담아요.
    return [
        Chunk(chunk_id=note.chunk_id, text=note.text,
              metadata={"company_id": note.company_id, "company_name": note.company})
        for note in sorted(report.footnotes, key=lambda note: note.number)
    ]


def build_summary_prompt(report: Report) -> str:
    """R-04 상세보고서 본문·각주 목록·요약 지침을 하나의 프롬프트로 조립한다."""
    sections = [section for section in report.sections if section.has_evidence]
    # 상세보고서 본문: "## 현황 (status)" 아래에 본문. [n]은 이미 보고서 전체 번호예요.
    report_body = "\n\n".join(
        f"## {section.title} ({section.section_type.value})\n{section.body}" for section in sections
    )
    # 각주 목록: 번호와 출처만 줘요. AI는 상세보고서 문장의 번호를 그대로 옮겨 쓰면 돼요.
    footnote_list = "\n".join(
        f"[{note.number}] {note.company} · {note.filename} · {note.location}"
        for note in sorted(report.footnotes, key=lambda note: note.number)
    )
    company_ids = report.request.company_ids
    companies = ", ".join(
        f"{company_id}={name}" for company_id, name in zip(company_ids, get_company_names(company_ids))
    )
    return SUMMARY_PROMPT_TEMPLATE.format(
        rules=SUMMARY_RULES,
        max_chars=SUMMARY_MAX_CHARS,
        max_paragraph_chars=SUMMARY_MAX_PARAGRAPH_CHARS,
        section_values=", ".join(f"{s.section_type.value}({s.title})" for s in sections),
        companies=companies,
        report_body=report_body,
        footnote_list=footnote_list,
    )


# ─────────────────────────────────────────────────────────────
# AI 답 읽기·검사
# ─────────────────────────────────────────────────────────────
def _load_json(answer: str) -> dict | None:
    """AI 답에서 JSON을 읽는다. ```json … ``` 처럼 감싸 와도 읽고, 못 읽으면 None."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", answer.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _parse_items(answer: str, report: Report) -> list[SummaryItem] | None:
    """AI 답(JSON)을 SummaryItem 목록으로 바꾼다. 형식이 틀렸으면 None."""
    data = _load_json(answer)
    if data is None or not isinstance(data.get("items"), list):
        return None

    # 근거가 있는 섹션으로만 이동할 수 있어요. ("근거 자료 없음" 섹션으로 보내면 볼 게 없어서)
    available = {section.section_type for section in report.sections if section.has_evidence}
    items: list[SummaryItem] = []
    for raw in data["items"]:
        if not isinstance(raw, dict):
            continue
        kind = raw.get("kind")
        text = raw.get("text")
        if kind not in SUMMARY_KIND_TITLES or not isinstance(text, str) or not text.strip():
            continue  # 모르는 종류이거나 글이 없는 항목은 버려요

        # section: 값이 이상하거나 근거 없는 섹션이면 종류별 기본 섹션으로 바꿔요.
        try:
            section_ref = SectionType(raw.get("section"))
        except ValueError:
            section_ref = DEFAULT_SECTION_BY_KIND[kind]
        if section_ref not in available:
            section_ref = DEFAULT_SECTION_BY_KIND[kind]
        # 분기 실적 양식에는 현황이 없고 실적 비교가 있어요.
        if section_ref == SectionType.STATUS and SectionType.STATUS not in available:
            section_ref = SectionType.PERFORMANCE

        # company_id: 계열사별 시사점에서만 쓰고, 고른 회사 목록에 있는 코드만 받아요.
        company_id = raw.get("company_id") if kind == "company" else None
        if company_id not in report.request.company_ids:
            company_id = None

        items.append(SummaryItem(kind=kind, text=text.strip(), section_ref=section_ref, company_id=company_id))
    return items


def _check_item(item: SummaryItem, chunks: list[Chunk]) -> list[tuple[str, str | None]]:
    """요약 항목 하나를 문장마다 검사한다. (근거 번호 범위·단위 붙은 수치)"""
    # 섹션 종류로 OVERVIEW를 넘기는 이유: "시너지는 회사 2곳 근거" 검사는 시너지 섹션 본문용이라
    # 요약 문장에는 적용하지 않으려고요. (OVERVIEW에는 그 검사가 없어요)
    checks = check_sentences(item.text, chunks, SectionType.OVERVIEW)
    # 글자가 있는 문장이 하나도 없으면 쓸 수 없는 항목이에요.
    return checks or [(item.text, PROBLEM_NO_CITATION)]


def _problem_lines(items: list[SummaryItem], all_checks: list[list[tuple[str, str | None]]]) -> list[str]:
    """재시도 프롬프트에 넣을 '고칠 점'. 예: '- 권고안 2번 항목, 1번째 문장: 근거 번호 없음'"""
    lines = []
    counters: dict[str, int] = {}  # 종류별 몇 번째 항목인지
    for item, checks in zip(items, all_checks):
        counters[item.kind] = counters.get(item.kind, 0) + 1
        for number, (_, problem) in enumerate(checks, start=1):
            if problem is not None:
                lines.append(
                    f"- {SUMMARY_KIND_TITLES[item.kind]} {counters[item.kind]}번 항목, "
                    f"{number}번째 문장: {problem}"
                )
    return lines


def _code_notes(report: Report) -> list[str]:
    """AI가 아니라 코드가 쓰는 유의사항 목록."""
    notes = []
    for section in report.sections:
        if not section.has_evidence:
            notes.append(NOTE_SECTION_NO_EVIDENCE.format(title=section.title))
        elif section.partial:
            notes.append(NOTE_SECTION_PARTIAL.format(title=section.title))
    # 각주가 하나도 없는 회사 = 보고서 어디에도 근거가 없는 회사
    cited = {note.company_id for note in report.footnotes}
    missing = [company_id for company_id in report.request.company_ids if company_id not in cited]
    if missing:
        notes += [NOTE_COMPANY_NO_EVIDENCE.format(company=name) for name in get_company_names(missing)]
    return notes


# ─────────────────────────────────────────────────────────────
# 1페이지 요약 생성
# ─────────────────────────────────────────────────────────────
def summarize_report(report: Report) -> ExecSummary:
    """R-04 상세보고서를 핵심 내용·계열사별 시사점·권고안으로 요약한다. 항목마다 section_ref를 남긴다."""
    notes = _code_notes(report)

    # 근거 있는 섹션이나 각주가 없으면 요약할 게 없어서 AI를 부르지 않아요.
    if not any(section.has_evidence for section in report.sections) or not report.footnotes:
        return ExecSummary(items=[], notes=notes)

    chunks = _footnote_chunks(report)
    prompt = build_summary_prompt(report)
    logger.info("R-04 요약 생성 sections=%d footnotes=%d", len(report.sections), len(report.footnotes))
    answer, truncated = _ask_llm(prompt)

    def inspect(answer: str, truncated: bool):
        """답을 읽고 검사해 (항목, 문장별 검사 결과, 고칠 점)을 돌려준다."""
        items = _parse_items(answer, report)
        if items is None:
            return None, [], [f"- {PROBLEM_BAD_JSON}"]
        all_checks = [_check_item(item, chunks) for item in items]
        problems = _problem_lines(items, all_checks)
        if truncated:
            problems.append(f"- {PROBLEM_TRUNCATED}")
        return items, all_checks, problems

    items, all_checks, problems = inspect(answer, truncated)

    # ── 1단계: 재시도 1번 ──
    if problems:
        logger.warning("R-04 요약 검증 재시도 problems=%d", len(problems))
        retry_prompt = SUMMARY_RETRY_PROMPT_TEMPLATE.format(
            prompt=prompt, answer=answer, problems="\n".join(problems),
        )
        retry = inspect(*_ask_llm(retry_prompt))
        # 다시 쓴 답을 읽을 수 있으면 그걸 써요. 못 읽으면 첫 답으로 2단계를 해요.
        if retry[0] is not None:
            items, all_checks, problems = retry

    if items is None:  # 두 번 다 JSON을 못 읽음
        logger.warning("R-04 요약 생성 실패: 답 형식 오류")
        return ExecSummary(items=[], notes=notes + [NOTE_SUMMARY_FAILED])

    # ── 2단계: 틀린 문장만 빼기 / 3단계: 남은 문장이 없으면 항목 제외 ──
    # 요약 항목은 1~2문장이라 R-02의 "60%·2문장" 기준 대신 "1문장이라도 남으면 살림"으로 해요.
    final_items: list[SummaryItem] = []
    removed_any = False
    for item, checks in zip(items, all_checks):
        kept = [sentence.strip() for sentence, problem in checks if problem is None]
        if len(kept) < len(checks):
            removed_any = True
        if kept:
            final_items.append(item if len(kept) == len(checks) else replace(item, text=" ".join(kept)))
    if removed_any:
        logger.warning("R-04 요약 문장 제외 items=%d→%d", len(items), len(final_items))
        notes.append(NOTE_ITEM_DROPPED)

    return ExecSummary(items=final_items, notes=notes)


def build_exec_summary(user: dict, report_id: int) -> ExecSummary:
    """R-04 상세보고서 본문을 입력으로 1페이지 요약을 만든다. (명세서 모양)"""
    # 📌 명세서는 report_id를 받지만, 보고서 저장·조회(report_repository, get_report)가 아직 없어요.
    #    저장 기능이 생기면 아래처럼 연결해요:
    #      report = get_report(user, report_id)   # 본인 보고서만 조회 (없으면 None)
    #      summary = fit_one_page(summarize_report(report))
    #      save_exec_summary(report_id, user["id"], summary)
    #    그 전까지 화면은 Report를 직접 받는 summarize_report()를 써요.
    raise NotImplementedError("보고서 저장 기능(report_repository) 준비 후 연결합니다.")


# ─────────────────────────────────────────────────────────────
# 1페이지 분량 조정
# ─────────────────────────────────────────────────────────────
def _lengths(items: list[SummaryItem]) -> tuple[int, dict[str, int]]:
    """(전체 글자 수, 종류별 글자 수)"""
    by_kind: dict[str, int] = {}
    for item in items:
        by_kind[item.kind] = by_kind.get(item.kind, 0) + len(item.text)
    return sum(by_kind.values()), by_kind


def _fits(items: list[SummaryItem], max_chars: int, max_paragraph_chars: int) -> bool:
    total, by_kind = _lengths(items)
    return total <= max_chars and all(length <= max_paragraph_chars for length in by_kind.values())


def _is_safe_shortening(original: str, shortened: str) -> bool:
    """압축한 글이 원래 항목에 없던 번호·수치를 만들지 않았는지 본다."""
    # 원래 요약은 이미 검사를 통과했으니, 압축본은 "원래 항목 안에서만" 번호·수치를 가져오면 안전해요.
    sentences = split_sentences(shortened)
    if not sentences or any(not CITATION_PATTERN.search(sentence) for sentence in sentences):
        return False  # 문장이 없거나, 번호 없는 문장이 생겼어요
    if not set(CITATION_PATTERN.findall(shortened)) <= set(CITATION_PATTERN.findall(original)):
        return False  # 원래 없던 번호가 생겼어요 (<= 는 "부분집합"이라는 뜻)
    normalized = re.sub(r"[,\s]", "", original)
    for match in UNIT_NUMBER_PATTERN.finditer(CITATION_PATTERN.sub("", shortened)):
        core = re.sub(r"[,\s]", "", match.group(0)).removesuffix("원").removesuffix("p")
        if core not in normalized:
            return False  # 원래 없던 수치가 생겼어요
    return True


def fit_one_page(
    summary: ExecSummary,
    max_chars: int = SUMMARY_MAX_CHARS,
    max_paragraph_chars: int = SUMMARY_MAX_PARAGRAPH_CHARS,
) -> ExecSummary:
    """R-04 단락별 500자, 전체 1,500자를 넘으면 1회 재요약하고, 그래도 넘치면 '상세보고서 ○○ 섹션 참고'로 바꾼다."""
    items = list(summary.items)
    if _fits(items, max_chars, max_paragraph_chars):
        return summary

    # ── 1단계: 문장 압축 1회 ──
    summary_json = json.dumps(
        {"items": [
            {"kind": item.kind, "section": item.section_ref.value, "company_id": item.company_id, "text": item.text}
            for item in items
        ]},
        ensure_ascii=False,  # 한글을 \uXXXX로 바꾸지 않고 그대로 둬요
    )
    logger.info("R-04 요약 분량 초과 → 압축 요청 items=%d", len(items))
    answer, _ = _ask_llm(SUMMARY_SHORTEN_PROMPT_TEMPLATE.format(
        summary_json=summary_json, max_chars=max_chars, max_paragraph_chars=max_paragraph_chars,
    ))
    data = _load_json(answer)
    shortened = data.get("items") if data else None
    # 항목 수가 같을 때만 순서대로 맞춰 봐요. 항목마다 안전하게 줄었을 때만 바꿔요.
    if isinstance(shortened, list) and len(shortened) == len(items):
        for index, (item, raw) in enumerate(zip(items, shortened)):
            text = raw.get("text") if isinstance(raw, dict) else None
            if isinstance(text, str) and _is_safe_shortening(item.text, text.strip()):
                items[index] = replace(item, text=text.strip())

    # ── 2단계: 그래도 넘치면 "첫 문장 + (상세보고서 ○○ 섹션 참고)" ──
    # 결론·권고안 항목 수는 줄이지 않아요. 가장 긴 항목부터 하나씩 줄여요.
    referenced: set[int] = set()  # 이미 줄인 항목 (같은 항목을 두 번 줄이지 않게)
    while not _fits(items, max_chars, max_paragraph_chars):
        total, by_kind = _lengths(items)
        over_kinds = {kind for kind, length in by_kind.items() if length > max_paragraph_chars}
        if not over_kinds and total > max_chars:
            over_kinds = set(by_kind)  # 단락은 괜찮은데 전체가 넘치면 모든 종류에서 골라요
        candidates = [
            index for index, item in enumerate(items)
            if index not in referenced and item.kind in over_kinds and len(split_sentences(item.text)) > 1
        ]
        if not candidates:
            break  # 더 줄일 항목이 없으면 그대로 둬요 (항목을 지우지는 않아요)
        index = max(candidates, key=lambda i: len(items[i].text))
        item = items[index]
        first = split_sentences(item.text)[0].strip()
        title = SECTION_TITLES[item.section_ref.value]
        items[index] = replace(item, text=f"{first} {DETAIL_REFERENCE_TEXT.format(title=title)}")
        referenced.add(index)

    return ExecSummary(items=items, notes=summary.notes)
