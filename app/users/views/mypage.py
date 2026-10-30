"""M-02·M-03·M-04 내 정보 화면 (Figma UI v4 06): 프로필·통계, 열람 권한 요청, 사용 기록.

이 화면은 services만 부른다(계층 규칙). 내 정보·비밀번호는 users.user_service, 열람 권한 요청과 사용 기록은
history.history_service(M-04)를 거친다. 날짜 묶음·통계 계산은 mypage_data.py의 순수 함수가 한다.
메뉴 연결(main.py)과 사이드바 배지(layout.py)는 이 파일이 하지 않는다.
"""

import html
import logging
from datetime import datetime

import streamlit as st

from app.auth.session import get_current_user_id
from app.common.ui import card, company_tag_html, empty_state
from app.history.services.history_service import get_access_request_history, get_user_history
from app.users.services.user_service import change_password, get_user_info, validate_password
from app.users.views import mypage_data

logger = logging.getLogger(__name__)

# 역할 코드 → 화면 이름 (DB에는 영어 코드만 저장, 화면에서 한글로 바꾼다)
_ROLE_LABELS = {
    "employee": "일반 사원",
    "company_admin": "계열사 관리자",
    "super_admin": "최종 어드민",
}

# 요청 상태 코드 → (화면 이름, 태그 색 클래스). 색은 공통 테마(.sh-tag)의 보안 등급 색을 다시 쓴다.
_STATUS_TAGS = {
    "pending": ("대기", "sh-int"),   # 노랑
    "approved": ("승인", "sh-pub"),  # 초록 (체크 아이콘 포함)
    "rejected": ("반려", "sh-con"),  # 빨강
}

# 사용 기록 종류 → 아이콘 (static/icons, Figma 사용 기록 아이콘)
_KIND_ICONS = {
    "ask": "history-ask.svg",
    "search": "history-ask.svg",
    "report_create": "history-report.svg",
    "view_document": "history-view.svg",
    mypage_data.KIND_ACCESS_REQUEST: "history-key.svg",
}
_ICON_BASE = "app/static/icons/"

# 사용 기록 카드가 처음에 보여 주는 항목 수. [전체 보기]를 누르면 서비스가 준 전체를 스크롤로 보여 준다.
HISTORY_PREVIEW_COUNT = 5

HISTORY_ALL_KEY = "mypage_history_all"
PASSWORD_FLASH_KEY = "password_changed_flash"


def render_mypage() -> None:
    """내 정보: 프로필 카드, 열람 권한 요청 목록, 사용 기록."""
    user_id = get_current_user_id()
    if user_id is None:
        st.warning("로그인 후 이용할 수 있습니다.")
        return

    try:
        info = get_user_info(user_id)
    except Exception:
        # DB 오류 등은 화면 밖으로 터뜨리지 않고, 쉬운 말로 안내하고 자세한 내용은 로그에만 남긴다.
        logger.exception("내 정보 조회 실패")
        st.error("내 정보를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return
    if info is None:
        st.error("내 정보를 불러오지 못했습니다.")
        return

    requests = _load(get_access_request_history, user_id, "열람 권한 요청 목록 조회 실패")
    history = _load(lambda uid: get_user_history(uid, None), user_id, "사용 기록 조회 실패")
    now = datetime.now()

    # 비밀번호 변경 성공 안내는 대화상자를 닫고 재실행한 '다음 화면'에서 한 번만 보여 준다.
    if st.session_state.pop(PASSWORD_FLASH_KEY, False):
        st.success("비밀번호를 변경했습니다.")

    with st.container(key="mp_root"):
        _render_profile(info, requests, history, now)
        request_col, history_col = st.columns([670, 460], gap="medium")
        with request_col:
            _render_access_requests(requests, now)
        with history_col:
            _render_history(requests, history, now)


def _load(fetch, user_id: int, log_message: str) -> list[dict] | None:
    """서비스에서 목록을 읽는다. 실패하면 None (화면이 그 카드에만 안내를 보여 준다)."""
    try:
        return fetch(user_id)
    except Exception:
        logger.exception(log_message)
        return None


# ─────────────────────────────────────────────────────────────
# 프로필 카드 (M-02)
# ─────────────────────────────────────────────────────────────
def _render_profile(info: dict, requests: list[dict] | None, history: list[dict] | None, now: datetime) -> None:
    """이름·태그·사원번호 줄, 통계 3개, [내 정보 수정] 버튼."""
    with card("mp_profile"):
        with st.container(horizontal=True, vertical_alignment="center", key="mp_profile_row"):
            st.html(_profile_html(info))
            if requests is not None and history is not None:
                st.html(_stats_html(mypage_data.usage_counts(history, requests, now.date())))
            if st.button("내 정보 수정", key="mp_edit"):
                _edit_dialog(info)


def _profile_html(info: dict) -> str:
    """이름 + 회사 코드·역할 태그, 아래에 사원번호·소속 줄. 이름·소속은 DB 값이라 escape한다."""
    role_label = _ROLE_LABELS.get(info["role"], info["role"])
    company_tag = company_tag_html(info["company_id"]) if info["company_id"] else ""
    parts = [f"사원번호 {info['employee_no']}"]
    if info.get("email"):
        parts.append(info["email"])
    parts.append(info["company_name"] or "소속 없음")
    return (
        '<div class="sh-mp-who">'
        f'<div class="sh-mp-name"><b>{html.escape(info["name"] or info["employee_no"])}</b>'
        f'{company_tag}<span class="sh-tag sh-co">{html.escape(role_label)}</span></div>'
        f'<div class="sh-mp-meta">{html.escape(" · ".join(parts))}</div></div>'
    )


def _stats_html(counts: dict[str, int]) -> str:
    """이번 달 질문·만든 보고서·열람 승인 숫자."""
    cells = (("이번 달 질문", counts["asked"]), ("만든 보고서", counts["reports"]), ("열람 승인", counts["approved"]))
    body = "".join(
        f'<div class="sh-mp-stat"><div class="sh-mp-stat-label">{label}</div><div class="sh-mp-stat-num">{number}</div></div>'
        for label, number in cells
    )
    return f'<div class="sh-mp-stats">{body}</div>'


@st.dialog("내 정보")
def _edit_dialog(info: dict) -> None:
    """[내 정보 수정] 대화상자 (Figma 16): 위에 바꿀 수 없는 내 정보, 아래에 비밀번호 변경."""
    # 팝업 안 글자 크기·입력칸 모양은 공통 CSS가 key(sh-dlg-…)로 맞춘다.
    with st.container(key="sh-dlg-profile"):
        st.caption("비밀번호만 직접 바꿀 수 있습니다.")
        st.html(_info_grid_html(info))
        _render_password_form(info["user_id"])


def _info_grid_html(info: dict) -> str:
    """바꿀 수 없는 내 정보 (이름·사원번호·역할·소속). 이름·소속은 DB 값이라 escape한다."""
    rows = (
        ("이름", info["name"] or "-"),
        ("사원번호", info["employee_no"]),
        ("역할", _ROLE_LABELS.get(info["role"], info["role"])),
        ("소속", info["company_name"] or "소속 없음"),
    )
    cells = "".join(f"<div><dt>{label}</dt><dd>{html.escape(str(value))}</dd></div>" for label, value in rows)
    return f'<dl class="sh-dlg-info">{cells}<p>역할·소속은 관리자만 바꿀 수 있습니다.</p></dl>'


def _render_password_form(user_id: int) -> None:
    """M-02 현재 비밀번호 확인 → 새 비밀번호 검증 → 변경. user_service에 맡기고 결과만 안내한다."""
    # clear_on_submit=True: 제출하면 입력칸을 비운다(비밀번호를 화면에 남기지 않는다. 기본값은 False).
    with st.form("change_password_form", clear_on_submit=True, border=False):
        st.html('<div class="sh-dlg-section">비밀번호 변경</div>')
        current = st.text_input("현재 비밀번호", type="password")
        new_col, confirm_col = st.columns(2)
        new = new_col.text_input("새 비밀번호", type="password", placeholder="8~20자, 영문·숫자 포함")
        confirm = confirm_col.text_input("새 비밀번호 확인", type="password", placeholder="한 번 더 입력")
        # 왼쪽 안내, 오른쪽 [취소] [저장] (Figma 16)
        with st.container(horizontal=True, vertical_alignment="center", key="sh-dlg-footer-profile"):
            st.caption("비밀번호를 바꾸려면 현재 비밀번호가 맞아야 합니다.")
            cancelled = st.form_submit_button("취소")
            submitted = st.form_submit_button("저장", type="primary")

    if cancelled:
        st.rerun()
    if not submitted:
        return

    # 서비스를 부르기 전에 화면에서 먼저 거른다. 실패 원인마다 메시지를 나눠 안내한다.
    # 1) 새 비밀번호와 확인이 다름
    if new != confirm:
        st.error("새 비밀번호와 확인이 일치하지 않습니다.")
        return
    # 2) 새 비밀번호 규칙 위반. 먼저 여기서 걸러야 아래 서비스 False를 '현재 비밀번호 불일치'로 좁힐 수 있다.
    if not validate_password(new):
        st.error("새 비밀번호가 규칙(8~20자, 영문·숫자 포함, 공백 없음)에 맞지 않습니다.")
        return

    try:
        # 서비스도 같은 검증을 다시 한다(화면 검사를 통과해도 서비스가 최종 판단 — 검증은 유지한다).
        changed = change_password(user_id, current, new)
    except Exception:
        # DB 오류 등은 화면 밖으로 터뜨리지 않고 쉬운 말로 안내한다(스택 트레이스는 로그에만).
        logger.exception("비밀번호 변경 실패")
        st.error("비밀번호 변경 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.")
        return

    if changed:
        # 대화상자를 닫고(전체 재실행) 성공 안내는 다음 화면에서 한 번 보여 준다.
        st.session_state[PASSWORD_FLASH_KEY] = True
        st.rerun()
    else:
        # 위에서 규칙 위반은 이미 걸렀으므로, 서비스가 False면 현재 비밀번호 불일치다.
        st.error("현재 비밀번호가 올바르지 않습니다.")


# ─────────────────────────────────────────────────────────────
# 열람 권한 요청 카드 (M-03)
# ─────────────────────────────────────────────────────────────
def _render_access_requests(requests: list[dict] | None, now: datetime) -> None:
    """최근 30일 열람 권한 요청: 문서·회사·요청 시각·상태 표."""
    with card("mp_requests"):
        st.html(_card_head_html("열람 권한 요청", "최근 30일"))
        if requests is None:
            st.error("열람 권한 요청 목록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
            return
        recent = mypage_data.recent_requests(requests, now)
        if not recent:
            empty_state("최근 30일 안에 열람 권한을 요청한 문서가 없습니다.")
            return
        st.html(_requests_table_html(recent))


def _card_head_html(title: str, note: str = "") -> str:
    """카드 머리: 제목과 오른쪽 작은 글자."""
    note_html = f'<span class="sh-mp-note">{html.escape(note)}</span>' if note else ""
    return f'<div class="sh-mp-head"><span class="sh-mp-h">{html.escape(title)}</span>{note_html}</div>'


def _requests_table_html(requests: list[dict]) -> str:
    """요청 표 HTML. 문서 제목·사유·반려 사유는 사용자가 쓴 글이라 모두 escape한다."""
    rows = ['<div class="sh-mp-row sh-mp-row-head"><span>문서</span><span>회사</span><span>요청</span><span>상태</span></div>']
    for request in requests:
        rows.append(
            '<div class="sh-mp-row">'
            f'<div class="sh-mp-doc"><b>{html.escape(request["title"])}</b>{_request_sub_html(request)}</div>'
            f'<div>{company_tag_html(request["owner_company_code"])}</div>'
            f'<div class="sh-mp-when">{html.escape(_short_time(request["created_at"]))}</div>'
            f'<div>{_status_tag_html(request["status"])}</div></div>'
        )
    return '<div class="sh-mp-table">' + "".join(rows) + "</div>"


def _request_sub_html(request: dict) -> str:
    """제목 아래 줄: 대기는 요청 사유, 승인은 승인일, 반려는 관리자가 남긴 반려 사유(빨강)."""
    status = request["status"]
    if status == "approved":
        day = _short_time(request.get("reviewed_at"))[:5]
        return f'<span class="sh-mp-sub">{html.escape(f"{day} 승인" if day else "승인")}</span>'
    if status == "rejected":
        if not request.get("review_comment"):
            return ""
        return f'<span class="sh-mp-sub sh-mp-sub-bad">{html.escape("반려 사유: " + request["review_comment"])}</span>'
    if request.get("reason"):
        return f'<span class="sh-mp-sub">{html.escape("사유: " + request["reason"])}</span>'
    return ""


def _status_tag_html(status: str) -> str:
    """상태 태그. 승인에는 체크 아이콘을 붙인다. 모르는 값은 회색으로 코드 그대로 보여 준다."""
    label, css = _STATUS_TAGS.get(status, (status, "sh-co"))
    icon = f'<img src="{_ICON_BASE}check-green.svg" width="12" height="12" alt="">' if status == "approved" else ""
    return f'<span class="sh-tag {css}">{icon}{html.escape(label)}</span>'


def _short_time(value: str | None) -> str:
    """"YYYY-MM-DD HH:MM" → "MM.DD HH:MM" (읽을 수 없으면 빈 문자열)."""
    when = mypage_data.parse_time(value)
    return when.strftime("%m.%d %H:%M") if when else ""


# ─────────────────────────────────────────────────────────────
# 사용 기록 카드 (M-04)
# ─────────────────────────────────────────────────────────────
def _render_history(requests: list[dict] | None, history: list[dict] | None, now: datetime) -> None:
    """날짜별 사용 기록. [전체 보기]를 누르면 서비스가 준 전체를 같은 카드에서 스크롤로 보여 준다."""
    with card("mp_history"):
        st.html(_card_head_html("사용 기록"))
        if history is None:
            st.error("사용 기록을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
            return
        # 열람 권한 요청 목록을 못 읽었더라도 나머지 기록은 보여 준다.
        timeline = mypage_data.build_timeline(history, requests or [])
        if not timeline:
            empty_state("아직 사용 기록이 없습니다. 통합 검색에서 문서를 찾아보세요.")
            return

        expanded = st.session_state.get(HISTORY_ALL_KEY, False)
        if len(timeline) > HISTORY_PREVIEW_COUNT:
            # 링크처럼 보이는 버튼을 카드 머리 오른쪽 끝에 겹쳐 둔다 (CSS는 _CSS_MYPAGE).
            st.button("접기" if expanded else "전체 보기", key="mp_all", type="tertiary",
                      on_click=_toggle_history_all)
        shown = timeline if expanded else timeline[:HISTORY_PREVIEW_COUNT]
        st.html(_history_html(shown, now.date(), scroll=expanded))


def _toggle_history_all() -> None:
    """[전체 보기]/[접기] 콜백. 화면을 다시 그리기 전에 실행된다."""
    st.session_state[HISTORY_ALL_KEY] = not st.session_state.get(HISTORY_ALL_KEY, False)


def _history_html(entries: list[dict], today, scroll: bool) -> str:
    """날짜 묶음별 사용 기록 HTML. 제목(검색어·문서 제목·보고서 제목)은 사용자가 정한 글이라 escape한다."""
    parts = []
    for label, group in mypage_data.group_by_day(entries, today):
        parts.append(f'<div class="sh-mp-day">{html.escape(label)}</div>')
        for entry in group:
            icon = _KIND_ICONS.get(entry["kind"], "history-ask.svg")
            parts.append(
                '<div class="sh-mp-item">'
                f'<img src="{_ICON_BASE}{icon}" width="16" height="16" alt="">'
                f'<div class="sh-mp-item-text"><div class="sh-mp-item-title">{html.escape(entry["title"])}</div>'
                f'<div class="sh-mp-item-sub">{html.escape(_entry_sub(entry))}</div></div>'
                f'<span class="sh-mp-item-time">{entry["when"].strftime("%H:%M")}</span></div>'
            )
    css = "sh-mp-list sh-mp-scroll" if scroll else "sh-mp-list"
    return f'<div class="{css}">' + "".join(parts) + "</div>"


def _entry_sub(entry: dict) -> str:
    """제목 아래 줄: 종류와, 서비스가 알려 준 건수(있을 때만)."""
    kind, count = entry["kind"], entry["result_count"]
    if kind == "ask":
        text = f"질문, 근거 {count}건" if count is not None else "질문"
    elif kind == "search":
        text = f"검색, 결과 {count}건" if count is not None else "검색"
    elif kind == "view_document":
        text = "원문 보기"
    elif kind == "report_create":
        text = "보고서"
    elif kind == mypage_data.KIND_ACCESS_REQUEST:
        text = "열람 권한 요청"
    else:
        text = ""
    return f"{text} · 차단됨" if entry["is_blocked"] else text
