"""A-04 감사 로그 필터 UI: render_audit_log_filters()."""

import streamlit as st

# 선택지 맨 앞의 "전체" 항목. 고르면 그 조건을 걸지 않는다.
_ALL = "전체"


def render_audit_log_filters(options: dict) -> dict:
    """A-04 사원번호·행위·기간·차단 여부 필터 입력칸을 그리고 입력값을 돌려준다.

    options: get_audit_filter_options() 결과. {"users": [...], "action_types": [...]}
    반환: search_audit_logs() 의 filters 인자 모양 dict.
        고르지 않은 조건은 키가 없다 (None 을 넣지 않는다).
    """
    filters: dict = {}
    col_user, col_action = st.columns(2)

    employee_no = col_user.selectbox("사원번호", [_ALL, *options.get("users", [])])
    if employee_no != _ALL:
        filters["employee_no"] = employee_no

    action_type = col_action.selectbox("행위", [_ALL, *options.get("action_types", [])])
    if action_type != _ALL:
        filters["action_type"] = action_type

    # 기간은 비워 둘 수 있게 빈 튜플로 시작한다. 시작일만 고른 중간 상태(길이 1)는 무시한다.
    period = st.date_input("기간", value=(), help="시작일과 종료일을 모두 고르면 적용됩니다. 종료일 당일도 포함합니다.")
    if isinstance(period, (tuple, list)) and len(period) == 2:
        filters["start_date"], filters["end_date"] = period

    if st.checkbox("차단된 기록만 보기"):
        filters["blocked_only"] = True
    return filters
