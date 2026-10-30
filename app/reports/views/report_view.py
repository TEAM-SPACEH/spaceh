"""R-02~R-05 보고서 결과 화면: 내보내기 버튼, [1페이지 요약]/[상세보고서] 탭, 요약, 상세보고서, 각주."""

# ─────────────────────────────────────────────────────────────
# views 파일 = "홀 직원"이에요. 화면에 보여 주고 클릭을 받기만 하고,
# 요약 만들기·검사·권한 판단은 services와 documents 패키지에 맡겨요.
#
# 담당 (명세서 기준)
#   - render_result_tabs(), render_exec_summary(), go_to_detail() ... R-04 (박예원)
#   - render_report() ................................................ R-02 (박예원)
#   - render_footnotes() ............................................. R-03 (김소은) ← 합의 후 박예원이 먼저 만듦
#   - render_export_buttons() ........................................ R-05 (박예원)
#
# 화면 흐름
#   맨 위 [Markdown 다운로드] / [DOCX 다운로드] 버튼 (R-05)
#   [1페이지 요약] 탭 (처음 열리는 탭)
#      항목마다 [상세 보기] → go_to_detail() → [상세보고서] 탭으로 바꾸고 그 섹션으로 스크롤
#   [상세보고서] 탭
#      섹션마다 [요약으로 돌아가기] / 맨 아래 각주 → [원문 보기] → S-05 원문 뷰어
# ─────────────────────────────────────────────────────────────

import html
import re

import streamlit as st

from app.common.ui import citation_html, company_tag_html, empty_state, show_text
from app.documents.views.components.document_viewer import render_selected_source
from app.documents.views.components.source_badge import SELECTED_SOURCE_KEY
from app.reports.models.report_models import Footnote, Report, SectionType
from app.reports.services import report_exporter
from app.reports.services.citation_mapper import build_section_anchor
from app.reports.services.prompts import NO_EVIDENCE_TEXT, SUMMARY_KIND_TITLES

# 탭 이름. st.tabs의 key로 지금 열린 탭 이름이 세션에 저장돼요.
TAB_SUMMARY = "1페이지 요약"
TAB_DETAIL = "상세보고서"
TAB_KEY = "r04_result_tab"           # 지금 열린 탭 (화면을 다시 그려도 보던 탭 유지)
FOCUS_KEY = "r04_focus_section"      # [상세 보기]로 이동할 섹션 (스크롤한 뒤 지워요)

# [n] 근거 번호를 찾는 패턴
CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def _cited_html(text: str) -> str:
    """본문을 안전하게 바꾸고 [n]만 공통 번호 배지로 바꾼 HTML. (#61 답변 카드와 같은 방식)"""
    # ① html.escape: 본문의 <, > 같은 글자를 무력화해요. AI·문서 글이 HTML로 실행되지 않게요.
    # ② [n] → citation_html(n): 공통 UI의 번호 배지
    # sh-rag-body는 공통 CSS(#61)에 있는 본문 스타일이에요. 줄바꿈(문단)을 그대로 보여 줘요.
    body = CITATION_PATTERN.sub(lambda match: citation_html(int(match.group(1))), html.escape(text))
    return f'<div class="sh-rag-body">{body}</div>'


# ─────────────────────────────────────────────────────────────
# 탭 이동 (버튼 콜백)
# ─────────────────────────────────────────────────────────────
def go_to_detail(section_ref: SectionType) -> None:
    """R-04 [상세 보기]: 이동할 섹션을 세션에 저장하고 [상세보고서] 탭으로 바꾼다."""
    # 버튼의 on_click(콜백)으로 불러요. 콜백은 화면을 다시 그리기 "전"에 실행돼서,
    # 여기서 탭 값을 바꾸면 다시 그릴 때 [상세보고서] 탭이 열린 채로 그려져요.
    st.session_state[TAB_KEY] = TAB_DETAIL
    st.session_state[FOCUS_KEY] = SectionType(section_ref).value


def _back_to_summary() -> None:
    """[요약으로 돌아가기]: [1페이지 요약] 탭으로 바꾼다."""
    st.session_state[TAB_KEY] = TAB_SUMMARY
    st.session_state.pop(FOCUS_KEY, None)


def _open_source(note: Footnote) -> None:
    """각주 [원문 보기]: S-05 원문 뷰어가 읽는 세션 칸에 출처를 넣는다."""
    # S-05 render_selected_source()는 S-04 출처 모양(dict)을 읽어요. 각주를 그 모양으로 바꿔 넣어요.
    st.session_state[SELECTED_SOURCE_KEY] = {
        "text": note.text, "company": note.company, "company_id": note.company_id,
        "filename": note.filename, "location": note.location,
        "doc_id": note.doc_id, "chunk_id": note.chunk_id, "citation_number": note.number,
    }


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
def render_result_tabs(user: dict, report: Report) -> None:
    """R-04 보고서 결과를 [1페이지 요약] / [상세보고서] 두 탭으로 보여 준다. 처음에는 요약 탭을 연다."""
    # 📌 명세서 입력은 report인데 그대로예요. 지금 열린 탭과 이동할 섹션은 세션에 저장해요.
    # st.tabs에 key와 on_change="rerun"을 주면, 지금 탭이 세션(TAB_KEY)에 저장되고
    # 콜백(go_to_detail)에서 세션 값을 바꿔 탭을 코드로 바꿀 수 있어요. (Streamlit 1.66)
    render_export_buttons(user, report)  # R-05: 어느 탭을 보든 맨 위에서 내려받을 수 있게
    summary_tab, detail_tab = st.tabs(
        [TAB_SUMMARY, TAB_DETAIL], key=TAB_KEY, default=TAB_SUMMARY, on_change="rerun",
    )
    # .open = 이 탭이 열려 있는지. 안 보이는 탭은 그리지 않아서 화면이 가벼워져요.
    with summary_tab:
        if summary_tab.open:
            render_exec_summary(user, report)
    with detail_tab:
        if detail_tab.open:
            focus = st.session_state.get(FOCUS_KEY)
            render_report(report, SectionType(focus) if focus else None)
            # 각주의 [원문 보기]를 눌렀으면 맨 아래에 S-05 원문 뷰어를 보여 줘요.
            # (원문을 열 때의 권한 재확인은 S-05가 해요)
            if st.session_state.get(SELECTED_SOURCE_KEY):
                with st.container(border=True):
                    render_selected_source(user)


def render_exec_summary(user: dict, report: Report) -> None:
    """R-04 [1페이지 요약] 탭에 핵심 내용·계열사별 시사점·권고안과 [상세 보기] 버튼을 보여 준다."""
    # 📌 명세서 입력은 report_id인데, 보고서 저장·조회가 아직 없어 Report를 직접 받아요.
    summary = report.exec_summary
    if summary is None:
        empty_state("1페이지 요약이 아직 없습니다. 보고서를 생성하면 함께 만들어집니다.")
        return

    for kind, title in SUMMARY_KIND_TITLES.items():  # 핵심 내용 → 계열사별 시사점 → 권고안 순서
        st.subheader(title)
        items = [item for item in summary.items if item.kind == kind]
        if not items:
            show_text("해당하는 요약 항목이 없습니다.", muted=True)
        for index, item in enumerate(items):
            with st.container(border=True):
                if item.company_id:  # 계열사별 시사점이면 회사 코드 태그
                    st.html(company_tag_html(item.company_id))
                st.html(_cited_html(item.text))
                # 콜백(on_click)으로 탭을 바꿔요. args로 이동할 섹션을 넘겨요.
                st.button(
                    "상세 보기", key=f"r04_detail_{kind}_{index}",
                    on_click=go_to_detail, args=(item.section_ref,),
                )

    if summary.notes:  # 코드가 쓴 유의사항 (근거 없는 섹션·회사 등)
        st.subheader("유의사항")
        for note in summary.notes:
            show_text(f"· {note}", muted=True)


def render_report(report: Report, focus_section: SectionType | None = None) -> None:
    """R-02 [상세보고서] 탭에 섹션별 제목·본문을 보여 주고, 섹션 제목마다 이동용 앵커를 단다."""
    for section in report.sections:
        # 앵커: 빈 div에 id를 달아 두면 _scroll_to()가 이 위치로 스크롤해요.
        st.html(f'<div id="{build_section_anchor(section.section_type)}"></div>')
        st.subheader(section.title)
        if not section.has_evidence:
            show_text(NO_EVIDENCE_TEXT, muted=True)
        else:
            if section.partial:
                st.warning("일부 문장이 근거 검증에 실패해 제외되었습니다.")
            st.html(_cited_html(section.body))
        st.button(
            "요약으로 돌아가기", key=f"r04_back_{section.section_type.value}", on_click=_back_to_summary,
        )

    render_footnotes(report.footnotes)

    # [상세 보기]로 들어왔으면 그 섹션으로 스크롤하고, 한 번 했으면 지워요(다시 그릴 때마다 튀지 않게).
    if focus_section is not None:
        _scroll_to(build_section_anchor(focus_section))
        st.session_state.pop(FOCUS_KEY, None)


def render_footnotes(footnotes: list[Footnote]) -> None:
    """R-03 본문 아래에 각주를 [번호] 회사명 · 파일명 · 위치 형식으로 나열하고 원문 보기로 연결한다."""
    st.subheader("각주")
    if not footnotes:
        empty_state("표시할 각주가 없습니다.")
        return
    for note in footnotes:
        with st.container(border=True):
            # 회사명·파일명·위치·인용은 데이터에서 온 글자라 escape해서 보여 줘요. (팀 규칙)
            st.html(
                f"{citation_html(note.number)} "
                f"{html.escape(f'{note.company} · {note.filename} · {note.location}')}"
            )
            if note.quote:
                show_text(f"“{note.quote}”", muted=True)  # 원문 인용 (150자)
            # 내부 문서는 원문 뷰어, DART 공시는 DART 링크 — S-05 뷰어가 DB를 보고 알아서 나눠요.
            st.button(
                "원문 보기", key=f"r04_footnote_{note.number}", on_click=_open_source, args=(note,),
            )


def render_export_buttons(user: dict, report: Report) -> None:
    """R-05 Markdown·DOCX 다운로드 버튼. 누르는 순간 A-06 판정을 거쳐 파일을 만든다."""
    # 📌 명세서 입력은 report_id인데, 보고서 결과 화면이 이미 Report를 들고 있어 그대로 받아요.
    # 📌 명세서는 "차단이면 버튼을 끄고 사유 안내"인데, 지금은 버튼을 누를 때만 판정해요.
    #    A-06 판정이 부를 때마다 차단을 감사 로그에 남겨서, 화면을 그릴 때(재실행마다) 부르면
    #    누르지도 않은 "다운로드 차단" 기록이 쌓이기 때문이에요. (A-06에 audit 인자가 생기면 미리 판정)
    md_col, docx_col = st.columns(2)
    for column, file_format, label in (
        (md_col, report_exporter.FORMAT_MARKDOWN, "Markdown 다운로드"),
        (docx_col, report_exporter.FORMAT_DOCX, "DOCX 다운로드"),
    ):
        # data에 "함수"를 넘기면 버튼을 눌렀을 때만 이 함수가 실행돼요.
        #   → 화면을 그릴 때마다 Word 파일을 만들지 않아 가볍고,
        #   → 누르는 순간의 권한으로 판정하고, 실제로 받은 경우만 감사 로그에 남아요.
        # 기본값 인자(fmt=file_format): for 반복 안에서 만든 함수가 마지막 형식만 기억하는 실수를 막아요.
        def make_file(fmt: str = file_format) -> bytes:
            # 차단이면 export_report_file()이 PermissionError를 내요.
            # 그러면 Streamlit이 다운로드를 멈추고 브라우저에 실패를 알려요(빈 파일이 받아지지 않아요).
            # 이 함수 안에서는 st.* 화면 명령이 무시돼서 안내 문구 대신 오류로 알려요.
            return report_exporter.export_report_file(user, report, fmt)

        with column:
            st.download_button(
                label,
                data=make_file,  # 괄호 없이 함수 자체를 넘겨요. 괄호를 붙이면 지금 바로 실행돼 버려요.
                file_name=report_exporter.build_file_name(report, file_format),
                mime=report_exporter.MIME_TYPES[file_format],
                key=f"r05_download_{file_format}",
                # "ignore": 내려받아도 화면을 다시 그리지 않아요. 보던 탭·스크롤이 그대로예요.
                on_click="ignore",
                width="stretch",
            )

    show_text(
        "내려받을 때 근거 문서 열람 권한을 다시 확인합니다. 볼 수 없는 근거 문서가 있으면 내려받을 수 없고, "
        "파일에는 받은 사람·일시가 워터마크로 표시됩니다.",
        muted=True,
    )
