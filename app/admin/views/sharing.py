"""A-03 그룹사 공유 ON/OFF 화면: render_admin_sharing()."""

import html
import logging

import streamlit as st

from app.admin.services.access_service import (
    DEFAULT_PAGE_SIZE,
    get_company_filter_options,
    get_manageable_documents,
    get_share_scope_name,
    get_share_summary,
)
from app.admin.views.components.group_share_toggle import render_group_share_toggle
from app.admin.views.components.share_document_panel import render_share_document_panel
from app.admin.views.components.share_summary import render_share_summary
from app.common.ui import company_tag_html, empty_state, page_header, security_badge_html, show_text
from core.constants import ACCESS_CONFIDENTIAL, ACCESS_INTERNAL, ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN

logger = logging.getLogger(__name__)

_ALL = "전체"
_SHARE_OPTIONS = {_ALL: None, "공유 ON": True, "공유 OFF": False}
_LEVEL_OPTIONS = {_ALL: "", "사내": ACCESS_INTERNAL, "기밀": ACCESS_CONFIDENTIAL}

# session_state 키. 값이 바뀌면 화면이 다시 그려져도 선택이 유지된다.
_PAGE_KEY = "admin-sharing-page"
_FILTER_KEY = "admin-sharing-filter-signature"
_KEYWORD_KEY = "admin-sharing-keyword"
_COMPANY_KEY = "admin-sharing-company"
_LEVEL_KEY = "admin-sharing-level"
_SHARE_KEY = "admin-sharing-share"

# 목록 표의 열 너비 비율: 문서, 보안 등급, 공유, 올린 날
_COLUMN_WIDTHS = [5, 1.6, 1.6, 1.4]
# 표(왼쪽)와 선택 문서 패널(오른쪽)의 너비 비율
_TABLE_PANEL_WIDTHS = [8, 3.4]


def render_admin_sharing(user: dict) -> None:
    """A-03 관리자 확인 후 요약 카드·필터·문서 표·선택 문서 패널을 보여 준다.

    user: 로그인 사용자. 관리자(계열사 관리자·최종 어드민)만 볼 수 있다.
    """
    # 1차 가드(화면 단계). st.stop() 은 이 줄 아래의 화면을 그리지 않고 실행을 멈춘다.
    # 이 가드가 뚫려도 서비스(get_manageable_documents·set_group_share)가 권한을 다시 확인한다.
    if user.get("role") not in (ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN):
        st.error("관리자만 접근할 수 있는 페이지입니다.")
        st.stop()

    try:
        companies = get_company_filter_options(user)
        scope_name = get_share_scope_name(user)
    except Exception:
        logger.exception("A-03 화면 준비 실패")
        st.error("화면을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    # 회사명은 관리자가 입력한 글자일 수 있어 Markdown 해석 없이 보여 준다.
    show_text(f"{scope_name} 관리", muted=True)
    page_header("그룹사 공유", "사내(internal) 문서를 다른 계열사에도 보여 줄지 정합니다. 기밀 문서는 공유할 수 없습니다.")

    # 요약 카드는 화면 위쪽에 놓되, 계열사 필터 값을 알아야 숫자를 셀 수 있다. 그래서 자리(container)만 먼저
    # 만들어 두고, 아래에서 필터를 읽은 뒤 이 자리를 채운다.
    summary_box = st.container()

    table_col, panel_col = st.columns(_TABLE_PANEL_WIDTHS)
    with table_col, st.container(border=True):
        company_filter, keyword, level_label, share_label = _render_filters(companies)

        # 필터가 바뀌면 1페이지부터 다시 본다.
        # st.session_state: 화면을 다시 그려도(버튼·입력 때마다 스크립트가 처음부터 다시 실행된다) 유지되는 저장 공간.
        # 그러지 않으면 3페이지를 보다가 검색하면 "3페이지째"의 결과가 비어 보인다.
        signature = (company_filter, keyword, level_label, share_label)
        if st.session_state.get(_FILTER_KEY) != signature:
            st.session_state[_FILTER_KEY] = signature
            st.session_state[_PAGE_KEY] = 1
        page = int(st.session_state.get(_PAGE_KEY, 1))

        try:
            result = get_manageable_documents(
                user,
                keyword=keyword,
                company_filter=company_filter,
                page=page,
                size=DEFAULT_PAGE_SIZE,
                share_filter=_SHARE_OPTIONS[share_label],
                access_level=_LEVEL_OPTIONS[level_label],
            )
        except PermissionError:
            st.error("관리자만 접근할 수 있는 페이지입니다.")
            return
        except Exception:
            logger.exception("A-03 문서 목록 조회 실패")
            st.error("문서 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
            return

        # 서비스가 범위를 벗어난 페이지를 마지막 페이지로 보정했을 수 있다.
        page = result["page"]
        st.session_state[_PAGE_KEY] = page

        documents = result["documents"]
        if documents:
            _render_table(documents, user)
            _render_pager(page, result["total_count"], len(documents))
        else:
            empty_state("조건에 맞는 문서가 없습니다. 검색어나 필터를 바꿔 보세요.")

    with panel_col:
        render_share_document_panel(_select_document(documents), user)

    # 토글을 바꾸면 on_change 가 화면 전체를 다시 그리기 전에 먼저 실행되므로, 여기서 읽는 숫자는 바뀐 값이다.
    with summary_box:
        try:
            render_share_summary(get_share_summary(user, company_filter))
        except Exception:
            logger.exception("A-03 요약 집계 실패")
            st.error("요약을 불러오지 못했습니다.")


def _render_filters(companies: list[str]) -> tuple[str, str, str, str]:
    """검색창과 계열사(최종 어드민만)·보안 등급·공유 상태 필터 칩을 그리고 입력값을 돌려준다."""
    keyword = st.text_input(
        "문서 검색",
        key=_KEYWORD_KEY,
        placeholder="제목이나 파일명으로 찾기 (예: 스마트팩토리 사양서)",
        label_visibility="collapsed",
        icon=":material/search:",
    ).strip()

    company_col, level_col, share_col, _ = st.columns([1.2, 1.2, 1.2, 3])
    company_filter = ""
    # 칩 이름은 위젯이 만들어지기 전에 정해야 하므로 session_state 에서 직전 선택을 읽는다.
    if companies:
        current = st.session_state.get(_COMPANY_KEY, _ALL)
        with company_col.popover(current if current != _ALL else "계열사 전체", icon=":material/apartment:"):
            choice = st.selectbox("계열사", [_ALL, *companies], key=_COMPANY_KEY)
        company_filter = "" if choice == _ALL else choice

    level_current = st.session_state.get(_LEVEL_KEY, _ALL)
    with level_col.popover(f"보안 등급: {level_current}" if level_current != _ALL else "보안 등급", icon=":material/lock:"):
        level_label = st.selectbox("보안 등급", list(_LEVEL_OPTIONS), key=_LEVEL_KEY)

    share_current = st.session_state.get(_SHARE_KEY, _ALL)
    with share_col.popover(share_current if share_current != _ALL else "공유 상태", icon=":material/share:"):
        share_label = st.selectbox("공유 상태", list(_SHARE_OPTIONS), key=_SHARE_KEY)
    return company_filter, keyword, level_label, share_label


def _render_table(documents: list[dict], user: dict) -> None:
    """문서 목록을 머리글 + 행으로 그리고, 사내 문서 행마다 공유 토글을 둔다."""
    header = st.columns(_COLUMN_WIDTHS)
    for cell, label in zip(header, ["문서", "보안 등급", "공유", "올린 날"]):
        with cell:
            show_text(label, bold=True, muted=True)

    for doc in documents:
        cols = st.columns(_COLUMN_WIDTHS, vertical_alignment="center")
        # 제목·파일 형식·회사 코드는 올린 사람이 정한 값이라 html.escape 한 뒤 HTML 로 그린다 (Markdown 해석 방지).
        cols[0].html(_document_html(doc))
        cols[1].html(security_badge_html(doc["access_level"]))
        with cols[2]:
            if doc["access_level"] == ACCESS_INTERNAL:
                render_group_share_toggle(doc, user)
            else:
                # 기밀은 공유할 수 없다. 잠긴 토글은 오른쪽 패널에서 보여 주고, 표에서는 시안처럼 글자로만 알린다.
                show_text("불가", muted=True)
        # 올린 날은 "10-28" 대신 시안처럼 "10.28" 로 보여 준다.
        with cols[3]:
            show_text(doc["created_at"][5:].replace("-", "."), muted=True)


def _document_html(doc: dict) -> str:
    """문서 칸: 파일 형식 태그 + 제목 + 계열사 태그, 아래 줄에 청크 수(없으면 파일명)."""
    sub = f"{doc['chunk_count']:,}청크" if doc.get("chunk_count") else doc["file_name"]
    return (
        f'<div><span class="sh-tag sh-co">{html.escape(doc["file_format"].upper())}</span> '
        f'<b>{html.escape(doc["title"])}</b> {company_tag_html(doc["company_id"])}</div>'
        f'<div class="sh-muted">{html.escape(sub)}</div>'
    )


def _select_document(documents: list[dict]) -> dict | None:
    """오른쪽 패널에 보여 줄 문서를 고른다. 문서가 없으면 None.

    제목은 업로드한 사람이 정한 글자라, 목록 대신 선택 상자의 글자(Markdown 해석 없음)로 보여 준다.
    key 를 주지 않아서 필터·페이지가 바뀌어 선택지가 달라지면 첫 문서로 돌아간다.
    """
    if not documents:
        return None
    by_id = {doc["doc_id"]: doc for doc in documents}
    doc_id = st.selectbox("설정할 문서", list(by_id), format_func=lambda value: by_id[value]["title"])
    return by_id[doc_id]


def _render_pager(page: int, total_count: int, shown: int) -> None:
    """"N건 중 a–b" 와 이전·다음 버튼. 첫·마지막 페이지에서는 해당 버튼을 끈다."""
    first = (page - 1) * DEFAULT_PAGE_SIZE + 1
    last_page = (total_count + DEFAULT_PAGE_SIZE - 1) // DEFAULT_PAGE_SIZE
    info_col, prev_col, next_col = st.columns([6, 1, 1])
    with info_col:
        show_text(f"{total_count:,}건 중 {first:,}–{first + shown - 1:,}", muted=True)
    # 버튼을 누르면 페이지 번호만 바꾸고 st.rerun() 으로 처음부터 다시 그려서 새 페이지를 읽는다.
    # (목록은 이 버튼보다 위에서 이미 그려졌으므로 rerun 없이는 이전 페이지가 한 번 더 보인다.)
    if prev_col.button("이전", disabled=page <= 1, key="admin-sharing-prev"):
        st.session_state[_PAGE_KEY] = page - 1
        st.rerun()
    if next_col.button("다음", disabled=page >= last_page, key="admin-sharing-next"):
        st.session_state[_PAGE_KEY] = page + 1
        st.rerun()
