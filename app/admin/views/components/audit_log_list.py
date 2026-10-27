"""A-04 감사 로그 목록 UI: render_audit_log_list()."""

import streamlit as st

# 목록 표에 보여 줄 컬럼과 머리글. 상세 정보(필터·문서 목록 등)는 상세 화면에서 보여 준다.
_COLUMNS = {
    "created_at": "시각",
    "employee_no": "사원번호",
    "company_code": "소속",
    "action_type": "행위",
    "target_id": "대상",
    "result_count": "결과 수",
    "blocked": "차단",
    "block_reason": "차단 사유",
}


def render_audit_log_list(logs: list[dict]) -> int | None:
    """A-04 감사 로그 목록을 표로 보여 주고, 상세를 볼 로그를 고르게 한다.

    logs: search_audit_logs() 결과의 logs. 비어 있으면 안내 문구만 보여 준다
    반환: 상세를 볼 로그의 log_id. 로그가 없으면 None
    """
    if not logs:
        st.info("조건에 맞는 감사 로그가 없습니다.")
        return None

    st.dataframe(
        [{label: log.get(key) for key, label in _COLUMNS.items()} for log in logs],
        width="stretch",
        hide_index=True,
    )
    by_id = {log["log_id"]: log for log in logs}
    return st.selectbox(
        "상세를 볼 기록",
        list(by_id),
        format_func=lambda log_id: _label(by_id[log_id]),
    )


def _label(log: dict) -> str:
    """선택 목록에 보여 줄 한 줄 설명. 예) 2026-10-27 09:30:05 · MVX-0001 · search"""
    # 사용자를 알 수 없는 기록(로그인 실패 등)은 사원번호가 비어 있을 수 있다.
    return f"{log['created_at']} · {log.get('employee_no') or '(알 수 없음)'} · {log['action_type']}"
