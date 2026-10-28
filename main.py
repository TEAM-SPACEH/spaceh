"""spaceH Streamlit 진입점. 저장소 루트에서 `streamlit run main.py`로 실행한다."""

import streamlit as st

from app.auth import session
from app.auth.views.login_page import render_login
from app.common.layout import company_label, render_header, render_sidebar
from app.common.ui import apply_theme, empty_state, page_header
from app.history.views.history_page import render_history
from app.search.views.search_page import render_search
from core.constants import ROLE_COMPANY_ADMIN, ROLE_EMPLOYEE, ROLE_SUPER_ADMIN

st.set_page_config(page_title="spaceH", layout="wide")
apply_theme()


def coming_soon_page(title: str, url_path: str, icon: str) -> st.Page:
    """아직 구현 전인 화면의 메뉴 자리. 각 기능을 구현할 때 실제 render 함수로 바꾼다."""

    def render() -> None:
        page_header(title)
        empty_state("준비 중인 화면입니다.")

    return st.Page(render, title=title, url_path=url_path, icon=icon)


def build_pages(user: dict) -> dict:
    """역할별 사이드바 메뉴 (Figma UI v4). 섹션 이름이 키이고, 빈 문자열은 제목 없는 맨 위 묶음이다."""
    pages = {
        "": [
            st.Page(render_search, title="통합 검색", icon=":material/search:", default=True),
            coming_soon_page("보고서", "reports", ":material/show_chart:"),
            st.Page(render_history, title="내 사용 히스토리", url_path="history", icon=":material/history:"),
        ],
    }
    # UI v4는 일반 사원에게만 내 정보 메뉴를 두고, 관리자는 위쪽 헤더의 계정 메뉴를 쓴다.
    if user["role"] == ROLE_EMPLOYEE:
        pages[""].append(coming_soon_page("내 정보", "mypage", ":material/person:"))

    manage = [
        coming_soon_page("문서", "admin-documents", ":material/description:"),
        coming_soon_page("열람 권한 요청", "admin-access-requests", ":material/inbox:"),
        coming_soon_page("감사 로그", "admin-audit-logs", ":material/format_list_bulleted:"),
    ]
    if user["role"] == ROLE_SUPER_ADMIN:
        pages["전체 관리"] = [
            coming_soon_page("계열사", "admin-companies", ":material/apartment:"),
            *manage,
            coming_soon_page("DART 수집", "admin-dart", ":material/cloud_download:"),
        ]
    elif user["role"] == ROLE_COMPANY_ADMIN:
        pages[f"{company_label(user)} 관리"] = manage
    return pages


# 로그인 전에는 로그인 화면만, 로그인 후에는 역할에 맞는 메뉴만 노출한다 (overview.md §4).
if not session.is_authenticated():
    st.navigation([st.Page(render_login, title="로그인")], position="hidden").run()
else:
    user = session.get_current_user()
    page = st.navigation(build_pages(user))
    # 헤더(로그아웃 포함)·사이드바 안내는 모든 화면 공통이라 여기서 한 번 그리고, 각 화면은 본문만 그린다.
    render_sidebar(user)
    render_header(user)
    page.run()
