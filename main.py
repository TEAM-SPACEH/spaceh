"""spaceH Streamlit 진입점. 저장소 루트에서 `streamlit run main.py`로 실행한다."""

import streamlit as st

from app.auth import session
from app.auth.services import auth_service
from app.auth.views.login_page import render_login
from app.common.ui import apply_theme, empty_state, page_header
from app.search.views.search_page import render_search
from core.constants import ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN

st.set_page_config(page_title="spaceH", layout="wide")
apply_theme()

ADMIN_ROLES = (ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN)


def coming_soon_page(title: str, url_path: str) -> st.Page:
    """아직 구현 전인 화면의 메뉴 자리. 각 기능을 구현할 때 실제 render 함수로 바꾼다."""

    def render() -> None:
        page_header(title)
        empty_state("준비 중인 화면입니다.")

    return st.Page(render, title=title, url_path=url_path)


# 로그인 전에는 로그인 화면만, 로그인 후에는 역할에 맞는 메뉴만 노출한다 (overview.md §4).
if not session.is_authenticated():
    st.navigation([st.Page(render_login, title="로그인")], position="hidden").run()
else:
    pages = {
        "": [
            st.Page(render_search, title="통합 검색", default=True),
            coming_soon_page("보고서", "reports"),
            coming_soon_page("마이페이지", "mypage"),
        ],
    }
    if session.get_current_user()["role"] in ADMIN_ROLES:
        pages["관리자"] = [
            coming_soon_page("대시보드", "admin-dashboard"),
            coming_soon_page("문서·권한 관리", "admin-manage"),
        ]
    # 마이페이지(M-02) 전까지 로그아웃은 사이드바 버튼으로 둔다.
    st.sidebar.button("로그아웃", on_click=auth_service.logout)
    st.navigation(pages).run()
