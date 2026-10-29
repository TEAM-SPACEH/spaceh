"""R-01 새 보고서 화면 (Figma 04): 주제·범위·양식을 고르고 오른쪽에서 모일 근거 문서를 확인한다."""

# views 파일 = "홀 직원"이에요. 입력을 받아 보여 주고, 문서 수 세기·권한 판단은 services에 맡겨요.
# 이 화면은 입력만 받아 ReportRequest를 돌려줘요. 근거 수집(R-01)과 보고서 생성(R-02)을 부르는 일은 이 파일이 하지 않아요.

import html
import logging
from datetime import date

import streamlit as st

from app.admin.services.company_service import get_company_options
from app.common.ui import card, company_tag_html
from app.reports.models.report_models import ReportRequest, ReportTemplate, SectionType
from app.reports.services.evidence_preview import count_visible_documents
from app.reports.services.report_generator import get_template_sections
from app.reports.views.report_form_state import (
    COMPANIES_KEY, DEFAULT_END, DEFAULT_START, END_KEY, REPORT_ID_PARAM, REQUEST_KEY, START_KEY, TEMPLATE_KEY, TOPIC_KEY,
)
from app.reports.views.report_view import render_report_view

logger = logging.getLogger(__name__)

TOPIC_PLACEHOLDER = "예) 2025년 하반기 스마트 물류 사업 동향과 계열사 협력 기회"
QUICK_TOPICS = ("분기 실적 요약", "신사업 검토", "시장 전망")

# 양식 카드: (양식, 이름, 설명). 이름·설명은 Figma 문구예요.
TEMPLATE_CARDS = (
    (ReportTemplate.COMPREHENSIVE, "종합 보고서", "개요, 현황, 계열사 시너지, 제언"),
    (ReportTemplate.QUARTERLY, "분기 실적 보고서", "공시 수치와 전년 대비 변화"),
)

# "만들어질 목차"에 보일 이름. 순서는 R-02 양식 순서표(get_template_sections)를 그대로 따라가요.
OUTLINE_TITLES = {
    SectionType.OVERVIEW: "개요",
    SectionType.STATUS: "계열사별 현황",
    SectionType.SYNERGY: "협력 기회와 시너지",
    SectionType.ADVICE: "제언",
    SectionType.PERFORMANCE: "실적 비교",
}
OUTLINE_TAIL = "각주, 근거 문서 목록"


def render_report_page(user: dict) -> None:
    """보고서 화면. 주소에 report_id가 있으면 저장된 보고서를 보여 주고(R-03~R-05), 없으면 새 보고서 폼(R-01)을 보여 준다."""
    report_id = _requested_report_id()
    if report_id is not None:
        render_report_view(user, report_id)
        return

    st.html(
        '<div class="sh-r-crumb">보고서</div>'
        '<div class="sh-r-title">새 보고서</div>'
        '<div class="sh-r-desc">주제와 범위를 정하면 권한 안의 문서만 모아 출처가 달린 보고서를 만듭니다.</div>'
    )
    request = render_report_form(user)
    if request is not None:
        st.session_state[REQUEST_KEY] = request
        # 근거 수집(R-01)·보고서 생성(R-02)을 이 요청으로 부르는 연결은 아직 없어요.
        st.info("보고서 조건을 받았습니다. 근거 수집·보고서 생성 기능이 연결되면 이 조건으로 보고서가 만들어집니다.")


def _requested_report_id() -> int | None:
    """주소의 ?report_id= 값. 숫자가 아니거나 0 이하이면 없는 것으로 본다."""
    raw = st.query_params.get(REPORT_ID_PARAM)
    return int(raw) if raw and raw.isdecimal() and int(raw) > 0 else None


def render_report_form(user: dict) -> ReportRequest | None:
    """R-01 양식·주제·회사·기간을 입력받는다. [보고서 만들기]를 눌러 조건이 맞으면 ReportRequest, 아니면 None."""
    options = get_company_options()
    if not options:
        st.warning("보고서를 만들 수 있는 계열사가 없습니다. 관리자에게 계열사 등록을 요청해 주세요.")
        return None
    names = {option["id"]: option["name"] for option in options}
    st.session_state.setdefault(TEMPLATE_KEY, ReportTemplate.COMPREHENSIVE.value)
    # 기본값은 세션에 미리 넣는다. [다시 만들기]가 같은 칸을 채워도 Streamlit의 "기본값과 세션 값이 함께 있음" 경고가 뜨지 않는다.
    st.session_state.setdefault(COMPANIES_KEY, [option["id"] for option in options])
    st.session_state.setdefault(START_KEY, DEFAULT_START)
    st.session_state.setdefault(END_KEY, DEFAULT_END)

    form_col, side_col = st.columns([694, 380], gap="medium")
    with form_col, card("r01_form"):
        topic = _render_topic_step()
        company_ids, start, end = _render_scope_step(options, names)
        template = ReportTemplate(_render_template_step())

    request = None
    with side_col, st.container(key="r01_side"):
        counts = _load_counts(user, company_ids, start, end)
        with card("r01_evidence"):
            st.html(_evidence_html(company_ids, names, counts))
        with card("r01_outline"):
            st.html(_outline_html(template))

        submitted = st.button("보고서 만들기", key="r01_submit", type="primary", width="stretch")
        st.html(f'<div class="sh-r-note">{html.escape(_note_text(counts))}</div>')

        if submitted:
            errors = _validate(topic, company_ids, start, end)
            for message in errors:
                st.error(message)
            if not errors:
                request = ReportRequest(
                    template=template, topic=topic.strip(), company_ids=list(company_ids),
                    start_date=start, end_date=end,
                )
    return request


# ─────────────────────────────────────────────────────────────
# 왼쪽: 세 단계 입력
# ─────────────────────────────────────────────────────────────
def _step_head(number: int, question: str) -> None:
    """단계 번호 상자와 질문."""
    st.html(f'<div class="sh-r-step-head"><span class="sh-r-no">{number}</span>{html.escape(question)}</div>')


def _render_topic_step() -> str:
    """1단계 주제. 자주 쓰는 주제를 누르면 입력칸이 채워진다."""
    with st.container(key="r01_step1"):
        _step_head(1, "무엇에 대한 보고서인가요?")
        topic = st.text_input(
            "보고서 주제", key=TOPIC_KEY, placeholder=TOPIC_PLACEHOLDER, label_visibility="collapsed",
        )
        with st.container(horizontal=True, key="r01_quick"):
            st.html('<span class="sh-r-quick-label">자주 쓰는 주제</span>')
            for quick in QUICK_TOPICS:
                st.button(quick, key=f"r01_quick_{quick}", on_click=_set_topic, args=(quick,))
    st.html('<div class="sh-r-sep"></div>')
    return topic


def _render_scope_step(options: list[dict], names: dict[str, str]) -> tuple[list[str], date, date]:
    """2단계 범위: 계열사(여러 개 선택)와 기간."""
    with st.container(key="r01_step2"):
        _step_head(2, "어느 범위에서 찾을까요?")
        st.html('<div class="sh-r-label">계열사</div>')
        company_ids = st.pills(
            "계열사", [option["id"] for option in options], selection_mode="multi",
            format_func=lambda company_id: names.get(company_id, company_id),
            key=COMPANIES_KEY, label_visibility="collapsed",
        ) or []
        start_col, end_col = st.columns(2, gap="small")
        start = start_col.date_input("시작", format="YYYY.MM.DD", key=START_KEY)
        end = end_col.date_input("끝", format="YYYY.MM.DD", key=END_KEY)
        if start > end:
            st.error("시작일이 끝 날짜보다 늦을 수 없습니다.")
    st.html('<div class="sh-r-sep"></div>')
    return company_ids, start, end


def _render_template_step() -> str:
    """3단계 양식. 카드를 누르면 고른 양식이 바뀐다. 고른 양식 값(ReportTemplate 값)을 돌려준다."""
    selected = st.session_state[TEMPLATE_KEY]
    with st.container(key="r01_step3"):
        _step_head(3, "어떤 양식으로 만들까요?")
        columns = st.columns(2, gap="small")
        for column, (template, title, description) in zip(columns, TEMPLATE_CARDS):
            # 고른 카드와 아닌 카드의 모양이 달라서, 상태를 key에 넣어 CSS가 구분하게 해요 (버튼은 값을 갖지 않아서 괜찮아요).
            state = "on" if template.value == selected else "off"
            column.button(
                f"**{title}**\n\n{description}", key=f"r01_tpl_{template.value}_{state}",
                on_click=_pick_template, args=(template.value,), width="stretch",
            )
    return selected


def _set_topic(topic: str) -> None:
    """[자주 쓰는 주제]를 입력칸에 채운다. 콜백이라 화면을 다시 그리기 전에 실행돼요."""
    st.session_state[TOPIC_KEY] = topic


def _pick_template(template_value: str) -> None:
    """양식 카드를 고른다."""
    st.session_state[TEMPLATE_KEY] = template_value


# ─────────────────────────────────────────────────────────────
# 오른쪽: 모일 근거 문서·목차·만들기
# ─────────────────────────────────────────────────────────────
def _load_counts(user: dict, company_ids: list[str], start: date, end: date) -> dict[str, int] | None:
    """회사별로 내가 볼 수 있는 문서 수. 조건이 잘못됐거나 세지 못하면 None (화면은 숫자 대신 안내를 보여 줘요)."""
    if not company_ids or start > end:
        return None
    try:
        return count_visible_documents(user, company_ids, start, end)
    except Exception:
        logger.exception("R-01 근거 문서 수 미리보기 실패")
        return None


def _evidence_html(company_ids: list[str], names: dict[str, str], counts: dict[str, int] | None) -> str:
    """"모일 근거 문서" 카드: 전체 건수, 회사별 막대, 근거가 없는 회사 안내."""
    total = sum(counts.values()) if counts is not None else None
    parts = [
        '<div class="sh-r-ev-head"><span class="sh-r-h">모일 근거 문서</span>'
        f'<span class="sh-r-total">{"-" if total is None else total}건</span></div>'
        '<div class="sh-r-ev-desc">내부 문서와 DART 공시 중 지금 조건에서 내가 볼 수 있는 문서입니다.</div>'
    ]
    if counts is None:
        message = "회사를 고르고 기간을 확인해 주세요." if not company_ids else "근거 문서 수를 불러오지 못했습니다."
        parts.append(f'<div class="sh-r-ev-desc sh-r-ev-empty">{message}</div>')
        return "".join(parts)

    parts.append('<div class="sh-r-rows">')
    for company_id in company_ids:
        count = counts.get(company_id, 0)
        percent = count / total * 100 if total else 0
        zero = " sh-r-zero" if count == 0 else ""
        parts.append(
            '<div class="sh-r-co-row"><div class="sh-r-co-top">'
            f'<span class="sh-r-co-name">{company_tag_html(company_id)}{html.escape(names.get(company_id, company_id))}</span>'
            f'<b class="sh-r-co-count{zero}">{count}건</b></div>'
            f'<div class="sh-r-bar"><i style="width:{percent:.1f}%"></i></div></div>'
        )
    parts.append("</div>")

    empty_names = [names.get(company_id, company_id) for company_id in company_ids if counts.get(company_id, 0) == 0]
    if empty_names:
        parts.append(
            '<div class="sh-r-warn"><img src="app/static/icons/warning.svg" width="14" height="14" alt="">'
            f'<span>{html.escape(", ".join(empty_names))}는 이 기간에 볼 수 있는 문서가 없어 보고서에 "근거 없음"으로 표시됩니다.</span></div>'
        )
    return "".join(parts)


def _outline_html(template: ReportTemplate) -> str:
    """"만들어질 목차" 카드. 고른 양식의 섹션 순서대로 번호를 붙인다."""
    titles = [OUTLINE_TITLES.get(section, section.value) for section in get_template_sections(template)]
    lines = [f"{number}. {title}" for number, title in enumerate(titles, start=1)] + [OUTLINE_TAIL]
    body = "".join(f"<div>{html.escape(line)}</div>" for line in lines)
    return f'<div class="sh-r-h">만들어질 목차</div><div class="sh-r-outline">{body}</div>'


def _note_text(counts: dict[str, int] | None) -> str:
    """만들기 버튼 아래 안내. 문서 수를 모르면 숫자를 말하지 않는다."""
    if counts is None:
        return "근거 문서 수를 확인하지 못했습니다."
    return f"문서 {sum(counts.values())}건을 읽고 섹션별로 작성합니다."


def _validate(topic: str, company_ids: list[str], start: date, end: date) -> list[str]:
    """[보고서 만들기]를 누를 때 입력을 확인한다. 고칠 곳을 문장으로 돌려준다 (없으면 빈 목록)."""
    errors = []
    if not topic.strip():
        errors.append("주제를 입력해 주세요.")
    if not company_ids:
        errors.append("계열사를 하나 이상 선택해 주세요.")
    if start > end:
        errors.append("시작일이 끝 날짜보다 늦을 수 없습니다.")
    return errors
