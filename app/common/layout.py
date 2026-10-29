"""모든 화면에 공통으로 붙는 헤더와 사이드바 (Figma "UI v4 디테일 수정", 02 통합 검색 화면 기준).

main.py가 로그인 후 모든 페이지에 그린다. 각 화면(views)은 이 함수를 부르지 않고 본문만 만든다.
- 헤더: 화면 맨 위에 고정된 56px 바. 로고(Space H 아이콘·글자)와 소속만 둔다.
- 사이드바: 메뉴는 main.py의 st.navigation이 그리고, 여기서는 메뉴 모양과 맨 아래 열람·관리 범위 안내,
  사용자 정보(아바타·이름·역할)와 계정 메뉴(로그아웃)를 맞춘다. M-02 명세의 "사이드바 사용자 정보"다.

Streamlit 기본 화면 위에 덧씌우는 CSS라 이 파일에만 둔다 (views에서는 CSS를 넣지 않는다).
Streamlit 기본 헤더는 숨기지 않고 투명하게만 한다. 숨기면 사이드바 열기 버튼까지 사라진다.
"""

import html

import streamlit as st

from app.auth.services.auth_service import logout
from app.common.ui import show_text
from core.constants import ROLE_COMPANY_ADMIN, ROLE_EMPLOYEE, ROLE_SUPER_ADMIN

# 사이드바 사용자 정보의 역할 이름 (UI v4: 사원 / 현대무벡스 관리자 / 최종 어드민)
HEADER_ROLE_LABELS = {
    ROLE_EMPLOYEE: "사원",
    ROLE_COMPANY_ADMIN: "관리자",
    ROLE_SUPER_ADMIN: "최종 어드민",
}

# config.toml의 enableStaticServing으로 static/ 폴더가 app/static/ 주소로 나간다.
# 로고는 Figma 「Space H · Logo Components」의 Space H / Icon, Space H / Text 컴포넌트를 내보낸 SVG다.
LOGO_ICON_URL = "app/static/logo-icon.svg"
LOGO_TEXT_URL = "app/static/logo-text.svg"
SCOPE_ICON_URL = "app/static/icons/shield-check.svg"

_LAYOUT_CSS = """
<style>
/* 헤더: 화면 맨 위 고정 바 (높이 56, 아래 테두리) */
.sh-topbar{position:fixed;top:0;left:0;right:0;height:56px;z-index:999980;background:#FFFFFF;
  border-bottom:1px solid #E9ECEF;display:flex;align-items:center;gap:20px;padding:0 20px;box-sizing:border-box}
.sh-brand{display:flex;align-items:center;gap:8px}
.sh-brand span{border-left:1px solid #E9ECEF;padding-left:9px;margin-left:4px;font-size:12px;color:#495057}
/* Streamlit 기본 헤더는 투명하게 두어 아래 고정 바가 보이게 한다 (사이드바 열기 버튼은 그대로 쓴다) */
header[data-testid="stHeader"]{background:transparent}
/* 본문은 헤더 아래에서 시작 (v4 본문 여백 22px 28px) */
.stMainBlockContainer{padding-top:78px;padding-left:28px;padding-right:28px}
/* 화면에 안 보이는 요소(테마 CSS·헤더 바)가 요소 사이 간격(1rem)만 차지하지 않게 한다 */
.stMainBlockContainer .stElementContainer:has(style){margin-bottom:-1rem}
/* 사이드바 사용자 정보: 칩 위를 계정 메뉴 버튼이 통째로 덮어, 칩 어디를 눌러도 메뉴가 열린다 */
.st-key-sh_account{position:relative;gap:0}
.sh-account{display:flex;align-items:center;gap:9px;padding:8px 36px 8px 8px;background:#FFFFFF;
  border:1px solid #E5E8EB;border-radius:10px}
.sh-avatar{flex:none;width:30px;height:30px;border-radius:15px;background:#E6F4EA;color:#007A36;font-size:12px;font-weight:700;
  display:flex;align-items:center;justify-content:center}
.sh-user-name{font-size:13px;font-weight:600;line-height:16.25px;color:#111111}
.sh-user-role{font-size:11px;line-height:13.75px;color:#6B7280}
.st-key-sh_account [data-testid="stLayoutWrapper"]:has(>[data-testid="stPopover"]){position:absolute;inset:0;width:100%}
.st-key-sh_account [data-testid="stPopover"],.st-key-sh_account [data-testid="stPopover"]>div,
.st-key-sh_account [data-testid="stPopover"] button{width:100%;height:100%}
.st-key-sh_account [data-testid="stPopover"] button{border:none;background:transparent;justify-content:flex-end;padding:0 10px}
/* 버튼 글자 "계정 메뉴"는 눈에는 숨기고 화면 읽기 프로그램에는 남긴다 (v4는 화살표만 보인다) */
.st-key-sh_account button [data-testid="stMarkdownContainer"]{position:absolute;width:1px;height:1px;
  overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
/* 사이드바: 폭 232, 흰 바탕, 오른쪽 테두리, 헤더 아래부터 */
section[data-testid="stSidebar"]{width:232px !important;min-width:232px !important;top:56px !important;
  height:calc(100vh - 56px) !important;background:#FFFFFF;border-right:1px solid #E9ECEF}
/* 넓은 화면에서는 사이드바 닫기 버튼을 두지 않는다 (UI v4, 팀장 결정). 사이드바 머리에는 닫기 버튼만 있어 머리째 숨긴다.
   좁은 화면에서는 Streamlit이 사이드바를 접고 열기 버튼을 주는데, 열린 사이드바가 본문을 덮으므로 닫기 버튼을 남긴다. */
@media (min-width: 768px){[data-testid="stSidebarHeader"]{display:none}}
@media (max-width: 767px){[data-testid="stSidebarHeader"]{position:absolute;top:2px;right:2px;height:auto;padding:0;z-index:1}}
[data-testid="stSidebarContent"]{display:flex;flex-direction:column;padding:14px 10px}
[data-testid="stSidebarNav"]{padding:0}
[data-testid="stSidebarNavItems"]{padding:0}
[data-testid="stSidebarNavLink"]{height:36px;padding:0 10px;margin:0;border-radius:8px;gap:10px}
[data-testid="stSidebarNavLink"] span{font-size:14px;font-weight:500;color:#495057;letter-spacing:-0.1px}
[data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"]{font-size:17px;color:#495057}
[data-testid="stSidebarNavLink"][aria-current="page"]{background:#EAF6EF}
[data-testid="stSidebarNavLink"][aria-current="page"] span,
[data-testid="stSidebarNavLink"][aria-current="page"] [data-testid="stIconMaterial"]{color:#007A36;font-weight:600}
[data-testid="stNavSectionHeader"]{padding:14px 10px 6px;margin:0;font-size:11px;font-weight:600;color:#6B7280}
[data-testid="stSidebarNavSeparator"]{display:none}
/* 범위 안내 상자와 사용자 정보는 사이드바 맨 아래에 붙인다 */
[data-testid="stSidebarUserContent"]{margin-top:auto;padding:0}
.sh-scope{background:#F3FAF6;border:1px solid #D3EEDD;border-radius:10px;padding:12px}
.sh-scope-title{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:600;line-height:18.6px;color:#111111}
.sh-scope-lines{display:flex;flex-direction:column;gap:3px;padding-top:6px;font-size:12px;line-height:18.6px;color:#495057}
</style>
"""


def company_label(user: dict) -> str:
    """화면에 보여 줄 소속 이름. 세션에 회사 이름이 없으면 회사 코드를 쓴다."""
    return user.get("company_name") or user.get("company_id") or "전 계열사"


def _header_context(user: dict) -> str:
    """로고 옆 작은 글자 (UI v4: 사원은 소속 회사, 관리자는 "관리자", 최종 어드민은 "최종 어드민")."""
    if user["role"] == ROLE_SUPER_ADMIN:
        return "최종 어드민"
    if user["role"] == ROLE_COMPANY_ADMIN:
        return "관리자"
    return company_label(user)


def _header_role(user: dict) -> str:
    """이름 아래 역할 글자. 계열사 관리자는 소속을 붙인다 (현대무벡스 관리자)."""
    role = HEADER_ROLE_LABELS.get(user["role"], user["role"])
    if user["role"] == ROLE_COMPANY_ADMIN:
        return f"{company_label(user)} {role}"
    return role


def header_html(user: dict) -> str:
    """헤더 바 HTML. 소속은 DB 값이라 escape한다."""
    return (
        '<div class="sh-topbar"><div class="sh-brand">'
        f'<img src="{LOGO_ICON_URL}" width="24" height="24" alt="">'
        f'<img src="{LOGO_TEXT_URL}" height="15" alt="Space H">'
        f"<span>{html.escape(_header_context(user))}</span></div></div>"
    )


def account_html(user: dict) -> str:
    """사이드바 맨 아래 사용자 정보 칩 HTML. 이름·소속은 DB 값이라 escape한다."""
    name = user.get("name") or ""
    return (
        f'<div class="sh-account"><div class="sh-avatar">{html.escape(name[:1])}</div>'
        f'<div><div class="sh-user-name">{html.escape(name)}</div>'
        f'<div class="sh-user-role">{html.escape(_header_role(user))}</div></div></div>'
    )


def render_header(user: dict) -> None:
    """모든 페이지 맨 위 공통 헤더 (로고·소속)."""
    st.html(_LAYOUT_CSS + header_html(user))


def scope_lines(user: dict) -> tuple[str, list[str]]:
    """사이드바 아래 안내 상자의 제목과 줄 (UI v4: 내 열람 범위 / 관리 범위)."""
    company = company_label(user)
    if user["role"] == ROLE_SUPER_ADMIN:
        return "관리 범위", ["모든 계열사 문서와 사용자"]
    if user["role"] == ROLE_COMPANY_ADMIN:
        return "관리 범위", [f"{company} 문서와 사용자", "다른 계열사 문서는 볼 수만 있음"]
    return "내 열람 범위", ["공개 문서 전체", f"{company} 사내 문서", "다른 계열사가 공유한 사내 문서"]


def scope_html(user: dict) -> str:
    """사이드바 맨 아래 열람·관리 범위 안내 상자 HTML."""
    title, lines = scope_lines(user)
    body = "".join(f"<div>{html.escape(line)}</div>" for line in lines)
    return (
        '<div class="sh-scope">'
        f'<div class="sh-scope-title"><img src="{SCOPE_ICON_URL}" width="14" height="14" alt="">{html.escape(title)}</div>'
        f'<div class="sh-scope-lines">{body}</div></div>'
    )


def render_sidebar(user: dict) -> None:
    """사이드바 맨 아래 열람·관리 범위 안내와 사용자 정보. 메뉴 자체는 main.py의 st.navigation이 그린다.

    사용자 정보 칩을 누르면 계정 메뉴가 열리고, 여기서 로그아웃(계정 전환)한다.
    """
    with st.sidebar:
        st.html(scope_html(user))
        with st.container(key="sh_account"):
            st.html(account_html(user))
            # 제목은 대화상자 이름(aria-label)으로도 쓰여 비우지 않는다. 화면에는 CSS로 화살표만 보인다.
            # Markdown으로 해석되므로 사용자 이름 대신 고정 문구를 쓴다.
            with st.popover("계정 메뉴"):
                show_text(f"사원번호 {user.get('employee_no') or '-'}", muted=True)
                if st.button("로그아웃 · 계정 전환", key="m01_logout", width="stretch"):
                    logout()
                    st.rerun()
