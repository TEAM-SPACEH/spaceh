"""spaceH Streamlit 진입점. 저장소 루트에서 `streamlit run main.py`로 실행한다.

로그인 전에는 로그인 화면만, 로그인 후에는 역할별 메뉴를 보여 준다 (Figma "UI v4 디테일 수정", overview §2.2).
메뉴의 각 페이지는 메소드 명세서의 페이지 함수(render_search 등)를 부른다. 담당자가 그 함수를
아직 만들지 않았으면 "준비 중" 화면이 대신 나온다. 함수를 만들면 이 파일을 고치지 않아도 연결된다.
"""

import importlib

import streamlit as st

from app.auth.services.auth_service import login, logout
from app.auth.session import get_current_user
from app.common.ui import apply_theme, empty_state, page_header, show_text, text_html
from core.constants import ROLE_COMPANY_ADMIN, ROLE_EMPLOYEE, ROLE_SUPER_ADMIN

st.set_page_config(page_title="spaceH", layout="wide")
apply_theme()

ROLE_LABELS = {
    ROLE_EMPLOYEE: "일반 사원",
    ROLE_COMPANY_ADMIN: "계열사 관리자",
    ROLE_SUPER_ADMIN: "최종 어드민",
}

# (메뉴 이름, 주소, 모듈, 메소드 명세서의 페이지 함수)
# 모든 사용자 메뉴. UI v4는 관리자의 내 정보를 오른쪽 위 아바타에 두지만 Streamlit에는 그 자리가 없어 메뉴에 둔다.
USER_MENU = [
    ("통합 검색", "search", "app.search.views.search_page", "render_search"),
    ("보고서", "report", "app.reports.views.report_page", "render_report_page"),
    # 내 정보(M-02·M-03·M-04) 화면 함수는 명세서에 없다. 이름이 정해지면 여기만 바꾼다.
    ("내 정보", "mypage", "app.users.views.mypage", "render_mypage"),
]
# 관리 메뉴. 그룹사 공유(A-03)·현황(A-09)은 UI v4에서 별도 메뉴 없이 문서 화면 안에 들어간다.
COMPANY_ADMIN_MENU = [
    ("문서", "admin-documents", "app.admin.views.documents", "render_admin_documents"),
    ("열람 권한 요청", "admin-access-requests", "app.admin.views.access_requests", "render_admin_permissions"),
    ("감사 로그", "admin-audit-logs", "app.admin.views.audit_logs", "render_admin_audit_logs"),
]
SUPER_ADMIN_MENU = [
    ("계열사", "admin-companies", "app.admin.views.companies", "render_admin_companies"),
    *COMPANY_ADMIN_MENU,
    ("DART 수집", "admin-dart", "app.admin.views.dart_collection", "render_admin_dart_collect"),
]


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


def _company_label(user: dict) -> str:
    """화면에 보여 줄 소속 이름. 세션에 회사 이름이 없으면 회사 코드를 쓴다."""
    return user.get("company_name") or user.get("company_id") or "전 계열사"


def _scope_lines(user: dict) -> tuple[str, list[str]]:
    """사이드바 아래 안내 상자의 제목과 줄 (UI v4: 내 열람 범위 / 관리 범위)."""
    company = _company_label(user)
    if user["role"] == ROLE_SUPER_ADMIN:
        return "관리 범위", ["모든 계열사 문서와 사용자"]
    if user["role"] == ROLE_COMPANY_ADMIN:
        return "관리 범위", [f"{company} 문서와 사용자", "다른 계열사 문서는 볼 수만 있음"]
    return "내 열람 범위", ["공개 문서 전체", f"{company} 사내 문서", "다른 계열사가 공유한 사내 문서", "열람 승인받은 문서"]


def _render_sidebar(user: dict) -> None:
    """사이드바: 사용자 정보(이름·역할·소속), 로그아웃(계정 전환), 열람·관리 범위."""
    with st.sidebar:
        # 이름·소속은 DB에서 온 값이라 Markdown으로 해석하지 않는 공통 함수로 보여 준다.
        show_text(user["name"], bold=True)
        show_text(f"{ROLE_LABELS.get(user['role'], user['role'])} · {_company_label(user)}", muted=True)
        if st.button("로그아웃 · 계정 전환", key="m01_logout"):
            logout()
            st.rerun()

        title, lines = _scope_lines(user)
        with st.container(border=True):
            # 줄마다 st.html을 따로 부르면 요소 사이 간격이 벌어져 한 번에 그린다.
            st.html(text_html(title, bold=True) + "".join(text_html(line, muted=True) for line in lines))


def _build_pages(user: dict) -> dict:
    """로그인 사용자의 역할로 볼 수 있는 메뉴만 st.Page로 만든다. 섹션 이름이 키다."""

    def to_pages(items: list) -> list:
        return [
            st.Page(
                _make_page(title, module_name, function_name),
                title=title,
                url_path=url_path,
                default=url_path == "search",
            )
            for title, url_path, module_name, function_name in items
        ]

    pages = {"": to_pages(USER_MENU)}
    if user["role"] == ROLE_SUPER_ADMIN:
        pages["전체 관리"] = to_pages(SUPER_ADMIN_MENU)
    elif user["role"] == ROLE_COMPANY_ADMIN:
        pages[f"{_company_label(user)} 관리"] = to_pages(COMPANY_ADMIN_MENU)
    return pages


user = get_current_user()
if user is None:
    st.navigation([st.Page(_login_page, title="로그인", url_path="login")], position="hidden").run()
else:
    _render_sidebar(user)
    st.navigation(_build_pages(user)).run()
