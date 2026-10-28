"""A-03 그룹사 공유 ON/OFF 화면: render_admin_sharing()."""

import logging

import streamlit as st

from app.admin.services.access_service import (
    DEFAULT_PAGE_SIZE,
    get_company_filter_options,
    get_manageable_documents,
)
from app.admin.views.components.group_share_toggle import render_group_share_toggle
from app.common.ui import company_tag_html, empty_state, page_header, security_badge_html, show_text
from core.constants import ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN

logger = logging.getLogger(__name__)

_ALL = "전체"
_SHARE_OPTIONS = {_ALL: None, "공유 ON": True, "공유 OFF": False}
_PAGE_KEY = "admin-sharing-page"
_FILTER_KEY = "admin-sharing-filter-signature"

# 목록 표의 열 너비 비율: 제목, 계열사, 보안 등급, 파일 형식, 업로드일, 공유
_COLUMN_WIDTHS = [4, 1.5, 1.5, 1.5, 2, 2.5]


def render_admin_sharing(user: dict) -> None:
    """A-03 관리자 확인 후 필터·문서 목록·그룹사 공유 토글을 보여 준다.

    user: 로그인 사용자. 관리자(계열사 관리자·최종 어드민)만 볼 수 있다.
    """
    # 1차 가드(화면 단계). st.stop() 은 이 줄 아래의 화면을 그리지 않고 실행을 멈춘다.
    # 이 가드가 뚫려도 서비스(get_manageable_documents·set_group_share)가 권한을 다시 확인한다.
    if user.get("role") not in (ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN):
        st.error("관리자만 접근할 수 있는 페이지입니다.")
        st.stop()

    page_header("그룹사 공유 설정", "사내(internal) 문서를 다른 계열사에도 보여 줄지 정합니다. 대외비 문서는 공유할 수 없습니다.")

    try:
        companies = get_company_filter_options(user)
    except Exception:
        logger.exception("A-03 계열사 선택지 조회 실패")
        st.error("화면을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return

    company_filter, keyword, share_label = _render_filters(companies)

    # st.session_state: 화면을 다시 그려도(버튼·입력 때마다 스크립트가 처음부터 다시 실행된다) 유지되는 저장 공간.
    # 현재 페이지 번호를 여기에 두고, 필터 조합(signature)이 바뀌면 1페이지부터 다시 본다.
    # 그러지 않으면 3페이지를 보다가 검색하면 "3페이지째"의 결과가 비어 보인다.
    signature = (company_filter, keyword, share_label)
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

    st.caption(f"총 {result['total_count']}건 · {page} / {result['total_pages']} 페이지")
    if not result["documents"]:
        empty_state("조건에 맞는 문서가 없습니다. 검색어나 필터를 바꿔 보세요.")
        return

    _render_table(result["documents"], user)
    _render_pager(page, result["total_pages"])


def _render_filters(companies: list[str]) -> tuple[str, str, str]:
    """계열사(최종 어드민만)·제목 검색·공유 상태 필터를 그리고 입력값을 돌려준다."""
    if companies:
        col_company, col_keyword, col_share = st.columns([1, 2, 1])
        company_label = col_company.selectbox("계열사", [_ALL, *companies])
        company_filter = "" if company_label == _ALL else company_label
    else:
        col_keyword, col_share = st.columns([2, 1])
        company_filter = ""
    keyword = col_keyword.text_input("문서 제목 검색", placeholder="예: 현대무벡스 3분기 실적 보고서").strip()
    share_label = col_share.selectbox("공유 상태", list(_SHARE_OPTIONS))
    return company_filter, keyword, share_label


def _render_table(documents: list[dict], user: dict) -> None:
    """문서 목록을 머리글 + 행으로 그리고, 행마다 공유 토글을 둔다."""
    header = st.columns(_COLUMN_WIDTHS)
    for cell, label in zip(header, ["제목", "계열사", "보안 등급", "파일 형식", "업로드일자", "그룹사 공유"]):
        cell.markdown(f"**{label}**")

    for doc in documents:
        cols = st.columns(_COLUMN_WIDTHS, vertical_alignment="center")
        # 제목·파일 형식은 업로드한 사람이 정한 값이라 Markdown 해석 없이 보여 준다.
        with cols[0]:
            show_text(doc["title"])
        cols[1].html(company_tag_html(doc["company_id"]))
        cols[2].html(security_badge_html(doc["access_level"]))
        with cols[3]:
            show_text(doc["file_format"])
        cols[4].write(doc["created_at"])
        with cols[5]:
            render_group_share_toggle(doc, user)


def _render_pager(page: int, total_pages: int) -> None:
    """이전·다음 버튼. 첫·마지막 페이지에서는 해당 버튼을 끈다."""
    prev_col, _, next_col = st.columns([1, 6, 1])
    # 버튼을 누르면 페이지 번호만 바꾸고 st.rerun() 으로 처음부터 다시 그려서 새 페이지를 읽는다.
    # (목록은 이 버튼보다 위에서 이미 그려졌으므로 rerun 없이는 이전 페이지가 한 번 더 보인다.)
    if prev_col.button("이전", disabled=page <= 1, key="admin-sharing-prev"):
        st.session_state[_PAGE_KEY] = page - 1
        st.rerun()
    if next_col.button("다음", disabled=page >= total_pages, key="admin-sharing-next"):
        st.session_state[_PAGE_KEY] = page + 1
        st.rerun()
