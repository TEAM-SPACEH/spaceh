"""A-04 감사 로그 필터 UI: render_audit_log_filters()."""

from datetime import date, timedelta

import streamlit as st

from app.admin.services.audit_service import ACTION_LABELS
from app.common.ui import show_text

# 선택지 맨 앞의 "전체" 항목. 고르면 그 조건을 걸지 않는다.
_ALL = "전체"

# 기간 선택지. 첫 번째가 처음 화면의 기본값이다 (Figma 시안의 "오늘").
PERIOD_TODAY = "오늘"
_PERIODS = (PERIOD_TODAY, "최근 7일", "최근 30일", "전체 기간", "직접 선택")
_PERIOD_CUSTOM = "직접 선택"

# session_state 키. 값이 바뀌면 화면이 다시 그려져도 선택이 유지된다.
PERIOD_KEY = "admin-audit-period"
USER_KEY = "admin-audit-user"
ACTION_KEY = "admin-audit-action"
BLOCKED_KEY = "admin-audit-blocked"
_RANGE_KEY = "admin-audit-range"


def render_audit_log_filters(options: dict, today: date) -> tuple[dict, object]:
    """A-04 기간·사용자·행동·차단 여부 필터를 한 줄 칩으로 그리고 입력값을 돌려준다.

    options: get_audit_filter_options() 결과. {"users": [...], "action_types": [...]}
    today: 오늘 날짜(KST). "오늘"·"최근 7일" 같은 기간을 날짜로 바꾸는 기준이다
    반환: (filters, count_slot)
        filters: search_audit_logs() 의 filters 인자 모양 dict. 고르지 않은 조건은 키가 없다
        count_slot: 줄 오른쪽 빈칸. 조회가 끝난 뒤 "N건"을 채워 넣는다
    """
    filters: dict = {}
    period_col, user_col, action_col, blocked_col, _, count_col = st.columns([1, 1.2, 1.2, 1, 2, 1])

    # 칩 이름은 위젯이 만들어지기 전에 정해야 하므로 session_state 에서 직전 선택을 읽는다.
    period = st.session_state.get(PERIOD_KEY, PERIOD_TODAY)
    with period_col.popover(period, icon=":material/calendar_today:"):
        period = st.selectbox("기간", _PERIODS, key=PERIOD_KEY)
        custom = ()
        if period == _PERIOD_CUSTOM:
            # 시작일만 고른 중간 상태(길이 1)는 무시한다. 시작일과 종료일을 모두 골라야 적용된다.
            custom = st.date_input("시작일과 종료일", value=(), key=_RANGE_KEY, help="종료일 당일도 포함합니다.")
    start, end = _period_dates(period, today, custom)
    if start is not None:
        filters["start_date"], filters["end_date"] = start, end

    user_label = st.session_state.get(USER_KEY, _ALL)
    with user_col.popover("사용자 전체" if user_label == _ALL else user_label, icon=":material/person:"):
        employee_no = st.selectbox("사원번호", [_ALL, *options.get("users", [])], key=USER_KEY)
    if employee_no != _ALL:
        filters["employee_no"] = employee_no

    action_code = st.session_state.get(ACTION_KEY, _ALL)
    with action_col.popover(
        "행동 전체" if action_code == _ALL else _action_label(action_code), icon=":material/filter_alt:"
    ):
        action_type = st.selectbox(
            "행동", [_ALL, *options.get("action_types", [])], key=ACTION_KEY, format_func=_action_label
        )
    if action_type != _ALL:
        filters["action_type"] = action_type

    with blocked_col:
        if st.toggle(":material/warning: 차단만", key=BLOCKED_KEY):
            filters["blocked_only"] = True

    return filters, count_col.empty()


def show_result_count(slot, total_count: int) -> None:
    """필터 줄 오른쪽 빈칸(render_audit_log_filters 가 돌려준 count_slot)에 조건에 맞는 전체 건수를 채운다."""
    with slot:
        show_text(f"{total_count:,}건", muted=True)


def _action_label(code: str) -> str:
    """행위 코드의 화면 이름. 선택지의 "전체"와 모르는 코드는 그대로 보여 준다."""
    return ACTION_LABELS.get(code, code)


def _period_dates(period: str, today: date, custom) -> tuple[date | None, date | None]:
    """기간 선택을 (시작일, 종료일)로 바꾼다. 기간을 걸지 않으면 (None, None). 종료일은 그날 끝까지 포함된다."""
    if period == PERIOD_TODAY:
        return today, today
    if period == "최근 7일":
        return today - timedelta(days=6), today
    if period == "최근 30일":
        return today - timedelta(days=29), today
    if period == _PERIOD_CUSTOM and isinstance(custom, (tuple, list)) and len(custom) == 2:
        return custom[0], custom[1]
    return None, None
