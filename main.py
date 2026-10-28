"""spaceH Streamlit 진입점. 저장소 루트에서 `streamlit run main.py`로 실행한다.

로그인 전에는 로그인 화면만, 로그인 후에는 역할별 메뉴를 보여 준다 (overview §2.2, 플로우 차트).
메뉴의 각 페이지는 메소드 명세서의 페이지 함수(render_search 등)를 부른다. 담당자가 그 함수를
아직 만들지 않았으면 "준비 중" 화면이 대신 나온다. 함수를 만들면 이 파일을 고치지 않아도 연결된다.
"""

import importlib

import streamlit as st

from app.auth.services.auth_service import login, logout
from app.auth.session import get_current_user
from app.common.ui import apply_theme, empty_state, page_header, show_text
from core.constants import ROLE_COMPANY_ADMIN, ROLE_EMPLOYEE, ROLE_SUPER_ADMIN

st.set_page_config(page_title="spaceH", layout="wide")
apply_theme()

ROLE_LABELS = {
    ROLE_EMPLOYEE: "일반 사원",
    ROLE_COMPANY_ADMIN: "계열사 관리자",
    ROLE_SUPER_ADMIN: "최종 어드민",
}
ADMIN_ROLES = (ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN)

# (메뉴 이름, 주소, 모듈, 메소드 명세서의 페이지 함수, 볼 수 있는 역할)
# 메뉴 순서는 플로우 차트의 사이드바 순서를 따른다.
MENU = {
    "": [
        ("통합 검색", "search", "app.search.views.search_page", "render_search", None),
        ("보고서", "report", "app.reports.views.report_page", "render_report_page", None),
        # 마이페이지(M-02·M-04) 화면 함수는 명세서에 없다. 이름이 정해지면 여기만 바꾼다.
        ("마이페이지", "mypage", "app.users.views.mypage", "render_mypage", None),
    ],
    "관리자": [
        ("대시보드", "admin-dashboard", "app.admin.views.dashboard", "render_admin_dashboard", ADMIN_ROLES),
        ("문서 관리", "admin-documents", "app.admin.views.documents", "render_admin_documents", ADMIN_ROLES),
        ("그룹사 공유", "admin-sharing", "app.admin.views.sharing", "render_admin_sharing", ADMIN_ROLES),
        ("권한 승인", "admin-permissions", "app.admin.views.access_requests", "render_admin_permissions", ADMIN_ROLES),
        ("감사 로그", "admin-audit-logs", "app.admin.views.audit_logs", "render_admin_audit_logs", ADMIN_ROLES),
        ("DART 수집", "admin-dart", "app.admin.views.dart_collection", "render_admin_dart_collect", (ROLE_SUPER_ADMIN,)),
        ("계열사 관리", "admin-companies", "app.admin.views.companies", "render_admin_companies", (ROLE_SUPER_ADMIN,)),
    ],
}


def _find_page_function(module_name: str, function_name: str):
    """페이지 함수를 찾는다. 모듈 파일이나 함수가 아직 없을 때만 None을 돌려준다."""
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        # 페이지 파일 안에서 다른 모듈을 못 찾은 오류(오타 등)는 "준비 중"으로 숨기지 않는다.
        if error.name != module_name:
            raise
        return None
    return getattr(module, function_name, None)


def _make_page(title: str, module_name: str, function_name: str):
    """메뉴 하나를 그리는 함수를 만든다. 페이지 함수가 없으면 준비 중 안내를 보여 준다."""

    def render() -> None:
        page_function = _find_page_function(module_name, function_name)
        if page_function is None:
            page_header(title)
            empty_state(f"준비 중인 화면입니다. ({module_name}.{function_name})")
            return
        page_function(user=get_current_user())

    return render


def _login_page() -> None:
    """M-01 사원번호·비밀번호 로그인 화면. 실패하면 오류를 보여 주고 다시 입력받는다."""
    page_header("spaceH 로그인", "배정받은 사원번호와 비밀번호로 로그인합니다.")
    with st.form("m01_login"):
        employee_no = st.text_input("사원번호", placeholder="MVX-0001")
        password = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인", type="primary")
    if not submitted:
        return
    # TODO(A-04): audit_service.record_audit_log가 머지되면 로그인 성공·실패를 기록한다.
    if login(employee_no, password):
        st.rerun()
    st.error("사원번호 또는 비밀번호가 맞지 않습니다.")


def _render_sidebar_user(user: dict) -> None:
    """사이드바 맨 위 사용자 정보(이름·역할·소속)와 로그아웃(계정 전환)."""
    with st.sidebar:
        # 이름은 DB에서 온 값이라 Markdown으로 해석하지 않는 공통 함수로 보여 준다.
        show_text(user["name"], bold=True)
        role = ROLE_LABELS.get(user["role"], user["role"])
        show_text(f"{role} · {user['company_id'] or '전 계열사'}", muted=True)
        if st.button("로그아웃 · 계정 전환", key="m01_logout"):
            logout()
            st.rerun()


def _build_pages(user: dict) -> dict:
    """로그인 사용자의 역할로 볼 수 있는 메뉴만 st.Page로 만든다."""
    pages = {}
    for section, items in MENU.items():
        section_pages = [
            st.Page(
                _make_page(title, module_name, function_name),
                title=title,
                url_path=url_path,
                default=url_path == "search",
            )
            for title, url_path, module_name, function_name, roles in items
            if roles is None or user["role"] in roles
        ]
        if section_pages:
            pages[section] = section_pages
    return pages


user = get_current_user()
if user is None:
    st.navigation([st.Page(_login_page, title="로그인", url_path="login")], position="hidden").run()
else:
    _render_sidebar_user(user)
    st.navigation(_build_pages(user)).run()
