"""R-03·R-04·R-05 보고서 보기 (Figma 05): 목차 사이드바, 제목·내려받기, 세 탭(1페이지 요약·전체 보고서·근거 문서), 각주."""

# ─────────────────────────────────────────────────────────────
# views 파일 = "홀 직원"이에요. 화면에 보여 주고 클릭을 받기만 하고,
# 열어도 되는지(권한 재확인)·문구 만들기는 services(report_view_service)에 맡겨요.
#
# 담당 (명세서 기준)
#   - render_result_tabs(), render_exec_summary(), go_to_detail() ... R-04 (박예원)
#   - render_report() ................................................ R-02 (박예원)
#   - render_footnotes() ............................................. R-03 (김소은)
#   - render_export_buttons() ........................................ R-05 (박예원)
#
# 화면 흐름
#   주소 /reports?report_id=N → render_report_view()
#   [1페이지 요약] 탭 (처음 열리는 탭): 항목마다 [상세 보기 ›] → go_to_detail() → [전체 보고서] 탭의 그 섹션으로 이동
#   [전체 보고서] 탭: 섹션마다 [요약으로 돌아가기]
#   [근거 문서] 탭: 근거 문서 목록. 각주·근거 문서의 [원문]/[DART] → S-05 원문 뷰어 (보고서로 돌아가기)
# ─────────────────────────────────────────────────────────────

import html
import logging
import re

import streamlit as st

from app.common.ui import card, citation_html, company_tag_html, empty_state, show_text
from app.documents.views.components.document_viewer import render_selected_source
from app.documents.views.components.source_badge import SELECTED_SOURCE_KEY
from app.reports.models.report_models import Footnote, Report, SectionType, SummaryItem
from app.reports.services import report_exporter
from app.reports.services.citation_mapper import build_section_anchor
from app.reports.services.prompts import NO_EVIDENCE_TEXT
from app.reports.services.report_view_service import (
    OPEN_BLOCKED,
    OPEN_OK,
    download_notice,
    format_created,
    format_period,
    group_sources,
    link_label,
    open_report,
    split_summary,
    template_title,
)
from app.reports.views.report_form_state import prefill_form

logger = logging.getLogger(__name__)

# 탭 이름. st.tabs의 key로 지금 열린 탭 이름이 세션에 저장돼요.
TAB_SUMMARY = "1페이지 요약"
TAB_FULL = "전체 보고서"
TAB_EVIDENCE = "근거 문서"
TAB_KEY = "r04_result_tab"           # 지금 열린 탭 (화면을 다시 그려도 보던 탭 유지)
FOCUS_KEY = "r04_focus_section"      # [상세 보기]로 이동할 섹션 (스크롤한 뒤 지워요)
CURRENT_KEY = "rv_toc_current"       # 목차에서 강조할 항목: "summary" | 섹션 값 | "footnotes"
OPEN_SOURCE_KEY = "rv_open_source"   # 이 화면에서 연 원문 (다른 화면이 고른 출처와 구분해요)

# [n] 근거 번호를 찾는 패턴
CITATION_PATTERN = re.compile(r"\[(\d+)\]")

# 각주 카드는 5줄까지 보이고 나머지는 스크롤해요 (Figma 각주 카드 높이)
FOOTNOTE_VISIBLE_HEIGHT = 316
FOOTNOTE_VISIBLE_ROWS = 5


# ─────────────────────────────────────────────────────────────
# HTML 조각 (데이터에서 온 글자는 모두 escape)
# ─────────────────────────────────────────────────────────────
def _cited_html(text: str) -> str:
    """본문을 안전하게 바꾸고 [n]만 공통 번호 배지로 바꾼 HTML."""
    # ① html.escape: 본문의 <, > 같은 글자를 무력화해요. AI·문서 글이 HTML로 실행되지 않게요.
    # ② [n] → citation_html(n): 공통 UI의 번호 배지
    return CITATION_PATTERN.sub(lambda match: citation_html(int(match.group(1))), html.escape(text))


def _head_html(report: Report, created_at) -> str:
    """제목 영역: 양식 태그, 기간·근거 건수·만든 시각, 큰 제목."""
    meta = f"{format_period(report)}, 근거 {len(report.footnotes)}건, {format_created(created_at)}"
    return (
        '<div class="sh-rv-meta-row">'
        f'<span class="sh-rv-kind">{html.escape(template_title(report))}</span>'
        f'<span class="sh-rv-meta">{html.escape(meta)}</span></div>'
        f'<div class="sh-rv-title">{html.escape(report.request.topic)}</div>'
    )


def _list_item_html(item_html: str, marker: str) -> str:
    """요약 한 줄. 점·번호는 글자 왼쪽 바깥에 걸려요."""
    return f'<div class="sh-rv-li"><span class="sh-rv-mark">{marker}</span>{item_html}</div>'


def _footnote_row_html(note: Footnote) -> str:
    """각주 한 줄의 왼쪽: 번호, 파일명, 회사 태그와 위치. 오른쪽 [원문] 버튼은 따로 그려요."""
    return (
        f'<div class="sh-rv-fn">{citation_html(note.number)}'
        f'<div class="sh-rv-fn-body"><div class="sh-rv-fn-name">{html.escape(note.filename)}</div>'
        f'<div class="sh-rv-fn-meta">{_plain_tag_html(note.company)}'
        f'<span>{html.escape(note.location)}</span></div></div></div>'
    )


def _plain_tag_html(name: str) -> str:
    """회사 이름 태그 (Figma 각주·근거 문서 목록은 코드가 아니라 회사 이름을 보여 줘요)."""
    return f'<span class="sh-tag sh-co">{html.escape(name)}</span>'


# ─────────────────────────────────────────────────────────────
# 이동 (버튼 콜백) — 콜백은 화면을 다시 그리기 "전"에 실행돼서, 여기서 탭 값을 바꾸면 바뀐 탭이 열린 채로 그려져요.
# ─────────────────────────────────────────────────────────────
def go_to_summary() -> None:
    """목차 [핵심 요약]: [1페이지 요약] 탭으로 바꾼다."""
    st.session_state[TAB_KEY] = TAB_SUMMARY
    st.session_state[CURRENT_KEY] = "summary"
    st.session_state.pop(FOCUS_KEY, None)


def go_to_detail(section_ref: SectionType) -> None:
    """R-04 [상세 보기]·목차 섹션: 이동할 섹션을 세션에 저장하고 [전체 보고서] 탭으로 바꾼다."""
    value = SectionType(section_ref).value
    st.session_state[TAB_KEY] = TAB_FULL
    st.session_state[FOCUS_KEY] = value
    st.session_state[CURRENT_KEY] = value


def go_to_evidence(label: str) -> None:
    """목차 [각주 N]: [근거 문서] 탭으로 바꾼다. label은 개수가 붙은 탭 이름이다."""
    st.session_state[TAB_KEY] = label
    st.session_state[CURRENT_KEY] = "footnotes"
    st.session_state.pop(FOCUS_KEY, None)


def _back_to_list() -> None:
    """[보고서 목록]: 주소의 report_id를 지워 새 보고서 화면으로 돌아간다."""
    _reset_view_state()
    st.query_params.clear()


def _rebuild(report: Report) -> None:
    """[다시 만들기]: 폼을 이 보고서의 조건으로 채우고 새 보고서 화면으로 돌아간다."""
    prefill_form(report.request)
    _back_to_list()


def _reset_view_state() -> None:
    """보고서 하나를 보는 동안만 쓰는 세션 값을 지운다 (다른 보고서를 열 때 이전 탭·원문이 남지 않게)."""
    for key in (TAB_KEY, FOCUS_KEY, CURRENT_KEY, OPEN_SOURCE_KEY, SELECTED_SOURCE_KEY):
        st.session_state.pop(key, None)


def _open_source(note: Footnote) -> None:
    """각주 [원문]: S-05 원문 뷰어가 읽는 세션 칸에 출처를 넣는다."""
    # S-05 render_selected_source()는 S-04 출처 모양(dict)을 읽어요. 각주를 그 모양으로 바꿔 넣어요.
    source = {
        "text": note.text, "company": note.company, "company_id": note.company_id,
        "filename": note.filename, "location": note.location,
        "doc_id": note.doc_id, "chunk_id": note.chunk_id, "citation_number": note.number,
    }
    st.session_state[SELECTED_SOURCE_KEY] = source
    st.session_state[OPEN_SOURCE_KEY] = source


def _scroll_to(anchor: str) -> None:
    """브라우저에서 앵커 위치로 스크롤한다."""
    # 탭이 바뀐 화면이 다 그려질 시간을 조금(300ms) 기다렸다가 스크롤해요.
    # anchor는 build_section_anchor()가 만든 "sec-status" 같은 고정 글자라 스크립트에 넣어도 안전해요.
    st.html(
        "<script>setTimeout(() => {"
        f"const target = document.getElementById({anchor!r});"
        "if (target) target.scrollIntoView({behavior: 'smooth', block: 'start'});"
        "}, 300);</script>",
        unsafe_allow_javascript=True,
    )


# ─────────────────────────────────────────────────────────────
# 화면
# ─────────────────────────────────────────────────────────────
def render_report_view(user: dict, report_id: int) -> None:
    """R-03 저장된 보고서를 열고(근거 문서 권한 재확인) Figma 05 모양으로 보여 준다."""
    # 이 화면에서 연 원문이 있으면 보고서 대신 원문 뷰어(S-05)를 보여 줘요. 돌아가기를 누르면 세션에서 지워져요.
    source = st.session_state.get(SELECTED_SOURCE_KEY)
    if source is not None and source == st.session_state.get(OPEN_SOURCE_KEY):
        render_selected_source(user, back_label="보고서로 돌아가기")
        return

    try:
        opened = open_report(user, report_id)
    except Exception:
        # DB 오류 등은 화면 밖으로 터뜨리지 않고, 쉬운 말로 안내하고 자세한 내용은 로그에만 남긴다.
        logger.exception("R-03 보고서 열기 실패 report_id=%s", report_id)
        st.error("보고서를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    if opened["status"] == OPEN_BLOCKED:
        st.warning("이 보고서의 근거 문서 중 지금은 열람할 수 없는 문서가 있어 보고서를 열 수 없습니다. "
                   "열람 권한을 요청하거나 같은 주제로 새 보고서를 만들어 주세요.")
        st.button("보고서 목록", key="rv_blocked_back", type="tertiary", on_click=_back_to_list)
        return
    if opened["status"] != OPEN_OK:
        empty_state("보고서를 찾을 수 없습니다. 내가 만든 보고서만 열 수 있습니다.")
        st.button("보고서 목록", key="rv_missing_back", type="tertiary", on_click=_back_to_list)
        return

    report: Report = opened["report"]
    evidence_label = f"{TAB_EVIDENCE} :gray-badge[{len(report.footnotes)}]"
    # 다른 보고서를 보다 온 탭 이름(개수가 다른 근거 문서 탭 등)이 남아 있으면 처음 탭으로 돌려요.
    if st.session_state.get(TAB_KEY) not in (None, TAB_SUMMARY, TAB_FULL, evidence_label):
        st.session_state.pop(TAB_KEY, None)

    _render_toc(report, evidence_label)
    with st.container(key="rv_root"):
        _render_head(user, report, opened["created_at"])
        summary_tab, full_tab, evidence_tab = st.tabs(
            [TAB_SUMMARY, TAB_FULL, evidence_label], key=TAB_KEY, default=TAB_SUMMARY, on_change="rerun",
        )
        # .open = 이 탭이 열려 있는지. 안 보이는 탭은 그리지 않아서 화면이 가벼워져요.
        notice = download_notice(report.max_access_level)
        with summary_tab:
            if summary_tab.open:
                _render_with_side(report, opened["source_types"], notice, lambda: render_exec_summary(report))
        with full_tab:
            if full_tab.open:
                focus = st.session_state.get(FOCUS_KEY)
                _render_with_side(
                    report, opened["source_types"], notice,
                    lambda: render_report(report, SectionType(focus) if focus else None),
                )
        with evidence_tab:
            if evidence_tab.open:
                render_evidence_documents(report, opened["source_types"])


def _render_toc(report: Report, evidence_label: str) -> None:
    """왼쪽 사이드바를 목차로 바꾼다 (일반 메뉴는 CSS로 숨겨요). ← 보고서 목록 / 핵심 요약 / 1~N. 섹션 / 각주 N."""
    current = _current_toc_item(report)
    with st.sidebar, st.container(key="rv_toc"):
        st.button("보고서 목록", key="rv_back", type="tertiary", on_click=_back_to_list)
        st.html('<div class="sh-rv-toc-label">목차</div>')
        _toc_button("핵심 요약", "summary", current, go_to_summary)
        for number, section in enumerate(report.sections, start=1):
            value = section.section_type.value
            _toc_button(f"{number}. {section.title}", value, current, go_to_detail, (section.section_type,))
        _toc_button(f"각주 {len(report.footnotes)}", "footnotes", current, go_to_evidence, (evidence_label,))


def _current_toc_item(report: Report) -> str:
    """목차에서 강조할 항목. 열린 탭이 정하고, [전체 보고서] 탭에서는 마지막으로 고른 섹션을 따른다."""
    tab = st.session_state.get(TAB_KEY, TAB_SUMMARY)
    if tab == TAB_SUMMARY:
        return "summary"
    if tab == TAB_FULL:
        chosen = st.session_state.get(CURRENT_KEY)
        return chosen if chosen in {section.section_type.value for section in report.sections} else ""
    return "footnotes"


def _toc_button(label: str, value: str, current: str, on_click, args: tuple = ()) -> None:
    """목차 한 줄. 지금 보는 항목이면 key에 on이 붙어 CSS가 강조해요."""
    state = "on" if value == current else "off"
    with st.container(key=f"rv_toc_{state}_{value}"):
        st.button(label, key=f"rv_toc_btn_{value}", type="tertiary", on_click=on_click, args=args)


def _render_head(user: dict, report: Report, created_at) -> None:
    """제목 영역: 왼쪽에 종류·기간·제목, 오른쪽에 Markdown·DOCX 내려받기와 다시 만들기."""
    with st.container(horizontal=True, vertical_alignment="bottom", key="rv_head"):
        st.html(_head_html(report, created_at))
        render_export_buttons(user, report)


def render_export_buttons(user: dict, report: Report) -> None:
    """R-05 Markdown·DOCX 다운로드 버튼과 [다시 만들기]. 기밀 문서가 있으면 내려받기 버튼을 끈다."""
    # 허용·차단 판단은 화면이 하지 않고 services(report_view_service·report_exporter)에 맡겨요.
    blocked = download_notice(report.max_access_level)["blocked"]
    with st.container(horizontal=True, key="rv_actions"):
        for file_format, label in ((report_exporter.FORMAT_MARKDOWN, "Markdown"), (report_exporter.FORMAT_DOCX, "DOCX")):
            st.download_button(
                label,
                # data에 "함수"를 넘기면 버튼을 눌렀을 때만 파일을 만들어요(눌러야 감사 로그에 다운로드가 남아요).
                # 기본값 인자(fmt=file_format): for 반복 안에서 만든 함수가 마지막 형식만 기억하는 실수를 막아요.
                data=lambda fmt=file_format: report_exporter.export_report_file(user, report, fmt) or b"",
                file_name=report_exporter.build_file_name(report, file_format),
                mime=report_exporter.MIME_TYPES[file_format],
                key=f"rv_dl_{file_format}",
                on_click="ignore",  # 내려받아도 화면을 다시 그리지 않아요. 보던 탭·스크롤이 그대로예요.
                disabled=blocked,
            )
        st.button("다시 만들기", key="rv_rebuild", type="primary", on_click=_rebuild, args=(report,))


def _render_with_side(report: Report, source_types: dict, notice: dict, render_main) -> None:
    """왼쪽에 본문 카드, 오른쪽(330)에 각주 카드와 다운로드 안내 카드를 놓는다."""
    main_col, side_col = st.columns([720, 330], gap="medium")
    with main_col:
        render_main()
    with side_col, st.container(key="rv_side"):
        render_footnotes(report.footnotes, source_types)
        with card("rv_notice"):
            st.html(
                '<div class="sh-rv-notice"><img src="app/static/icons/inbox.svg" width="14" height="14" alt="">'
                f'<span>{html.escape(notice["text"])}</span></div>'
            )


def render_exec_summary(report: Report) -> None:
    """R-04 [1페이지 요약] 탭: 핵심 요약과 제언, 항목마다 [상세 보기 ›]."""
    summary = report.exec_summary
    with card("rv_summary"):
        if summary is None:
            empty_state("1페이지 요약이 아직 없습니다. 보고서를 생성하면 함께 만들어집니다.")
            return
        key_items, advice_items, notes = split_summary(summary)
        _render_summary_group("key", "핵심 요약", key_items, notes, ordered=False)
        _render_summary_group("advice", "제언", advice_items, [], ordered=True)
        st.html('<div class="sh-rv-foot"><img src="app/static/icons/file-muted.svg" width="13" height="13" alt="">'
                "<span>1,500자 이내 요약입니다. 수치와 근거 문단은 전체 보고서에서 확인하세요.</span></div>")


def _render_summary_group(prefix: str, title: str, items: list[SummaryItem], notes: list[str], ordered: bool) -> None:
    """요약 묶음 하나(제목 + 항목들). 항목이 없고 유의사항도 없으면 아무것도 그리지 않는다."""
    if not items and not notes:
        return
    with st.container(key=f"rv_group_{prefix}"):
        st.html(f'<div class="sh-rv-h">{html.escape(title)}</div>')
        with st.container(key=f"rv_list_{prefix}"):
            for number, item in enumerate(items, start=1):
                with st.container(key=f"rv_item_{prefix}_{number}"):
                    company = f"{company_tag_html(item.company_id)} " if item.company_id else ""
                    marker = f"{number}." if ordered else "•"
                    st.html(_list_item_html(f"{company}{_cited_html(item.text)}", marker))
                    # 콜백(on_click)으로 탭을 바꿔요. args로 이동할 섹션을 넘겨요.
                    st.button("상세 보기 ›", key=f"rv_detail_{prefix}_{number}", type="tertiary",
                              on_click=go_to_detail, args=(item.section_ref,))
            for note in notes:  # 코드가 쓴 유의사항 (근거 없는 섹션·회사 등)
                st.html(_list_item_html(html.escape(note), "•"))


def render_report(report: Report, focus_section: SectionType | None = None) -> None:
    """R-02 [전체 보고서] 탭: 섹션별 제목·본문, 섹션 제목마다 이동용 앵커."""
    with card("rv_full"):
        for section in report.sections:
            with st.container(key=f"rv_section_{section.section_type.value}"):
                # 앵커: 제목에 id를 달아 두면 _scroll_to()가 이 위치로 스크롤해요.
                st.html(f'<div class="sh-rv-h" id="{build_section_anchor(section.section_type)}">{html.escape(section.title)}</div>')
                if not section.has_evidence:
                    show_text(NO_EVIDENCE_TEXT, muted=True)
                else:
                    if section.partial:
                        st.warning("일부 문장이 근거 검증에 실패해 제외되었습니다.")
                    st.html(f'<div class="sh-rv-body">{_cited_html(section.body)}</div>')
                st.button("요약으로 돌아가기", key=f"rv_back_{section.section_type.value}", type="tertiary",
                          on_click=go_to_summary)

    # [상세 보기]로 들어왔으면 그 섹션으로 스크롤하고, 한 번 했으면 지워요(다시 그릴 때마다 튀지 않게).
    if focus_section is not None:
        _scroll_to(build_section_anchor(focus_section))
        st.session_state.pop(FOCUS_KEY, None)


def render_footnotes(footnotes: list[Footnote], source_types: dict | None = None) -> None:
    """R-03 각주 카드: [번호] 파일명, 회사 태그·위치, 오른쪽 [원문]/[DART] 링크. 5줄을 넘으면 스크롤한다."""
    source_types = source_types or {}
    with card("rv_footnotes"):
        st.html('<div class="sh-rv-card-head"><b>각주</b><span>같은 출처는 한 번호</span></div>')
        if not footnotes:
            empty_state("표시할 각주가 없습니다.")
            return
        height = FOOTNOTE_VISIBLE_HEIGHT if len(footnotes) > FOOTNOTE_VISIBLE_ROWS else "content"
        with st.container(height=height, border=False, key="rv_fn_list"):
            for note in footnotes:
                _footnote_row(note, source_types.get(note.doc_id))


def _footnote_row(note: Footnote, source_type: str | None) -> None:
    """각주 한 줄 (왼쪽 설명 + 오른쪽 원문 링크 버튼)."""
    with st.container(horizontal=True, vertical_alignment="top", key=f"rv_fn_{note.number}"):
        st.html(_footnote_row_html(note))
        # 내부 문서는 원문 뷰어, DART 공시는 DART 링크 — S-05 뷰어가 DB를 보고 알아서 나눠요.
        st.button(link_label(source_type), key=f"rv_fn_open_{note.number}", type="tertiary",
                  on_click=_open_source, args=(note,))


def render_evidence_documents(report: Report, source_types: dict) -> None:
    """[근거 문서] 탭: 보고서가 인용한 문서를 문서별로 묶어 보여 준다. 위치마다 각주 번호를 붙인다."""
    groups = group_sources(report.footnotes)
    with card("rv_evidence"):
        st.html(f'<div class="sh-rv-card-head"><b>근거 문서</b><span>{len(groups)}건</span></div>')
        if not groups:
            empty_state("표시할 근거 문서가 없습니다.")
            return
        for group in groups:
            first = group["notes"][0]
            with st.container(horizontal=True, vertical_alignment="top", key=f"rv_doc_{group['doc_id']}"):
                where = "".join(
                    f'<span class="sh-rv-doc-at">{citation_html(note.number)}{html.escape(note.location)}</span>'
                    for note in group["notes"]
                )
                st.html(
                    '<div class="sh-rv-fn"><div class="sh-rv-fn-body">'
                    f'<div class="sh-rv-fn-name">{html.escape(group["filename"])}</div>'
                    f'<div class="sh-rv-fn-meta">{_plain_tag_html(group["company"])}{where}</div></div></div>'
                )
                st.button(link_label(source_types.get(group["doc_id"])), key=f"rv_doc_open_{group['doc_id']}",
                          type="tertiary", on_click=_open_source, args=(first,))
