"""A-04 감사 로그 목록 UI: render_audit_log_list()."""

import html

import streamlit as st

from app.common.ui import company_tag_html, empty_state, show_text

# 열 너비 비율: 시각, 사용자, 행동, 대상, 결과
_COLUMN_WIDTHS = [1.6, 2.4, 1.6, 4, 2.6]
_HEADERS = ["시각", "사용자", "행동", "대상", "결과"]

# 결과 배지는 공통 CSS 클래스(app/common/ui.py)를 쓴다. 차단은 빨강(기밀 배지와 같은 색), 허용은 초록.
_BLOCKED_CLASS = "sh-tag sh-con"
_ALLOWED_CLASS = "sh-tag sh-pub"


def render_audit_log_list(logs: list[dict]) -> int | None:
    """A-04 감사 로그 목록을 표로 보여 주고, 상세를 볼 로그를 고르게 한다.

    logs: search_audit_logs() 결과의 logs. 비어 있으면 안내 문구만 보여 준다
    반환: 상세를 볼 로그의 log_id. 로그가 없으면 None
    """
    if not logs:
        empty_state("조건에 맞는 감사 로그가 없습니다. 기간이나 필터를 바꿔 보세요.")
        return None

    header = st.columns(_COLUMN_WIDTHS)
    for cell, label in zip(header, _HEADERS):
        with cell:
            show_text(label, bold=True, muted=True)

    for log in logs:
        cells = st.columns(_COLUMN_WIDTHS, vertical_alignment="center")
        with cells[0]:
            # 날짜는 앞의 연도를 떼고 월-일 시:분:초만 보여 준다 (예: 10-28 14:22:08).
            show_text(log["created_at"][5:])
        # 이름·소속·사유는 사용자나 다른 기능이 적은 글자라 html.escape 한 뒤 HTML 로 그린다.
        cells[1].html(_user_html(log))
        with cells[2]:
            show_text(log["action_label"])
        with cells[3]:
            show_text(log["target_label"])
        cells[4].html(_result_html(log))

    by_id = {log["log_id"]: log for log in logs}
    return st.selectbox(
        "상세를 볼 기록",
        list(by_id),
        format_func=lambda log_id: _label(by_id[log_id]),
    )


def _user_html(log: dict) -> str:
    """사용자 칸: 이름(없으면 사원번호) + 소속 태그. 사용자를 알 수 없으면 "알 수 없음"."""
    name = log.get("user_name") or log.get("employee_no") or "알 수 없음"
    tag = f" {company_tag_html(log['company_code'])}" if log.get("company_code") else ""
    return f"<div>{html.escape(name)}{tag}</div>"


def _result_html(log: dict) -> str:
    """결과 칸: 차단/허용 배지 + 차단 사유."""
    if not log["blocked"]:
        return f'<span class="{_ALLOWED_CLASS}">허용</span>'
    reason = f' <span class="sh-muted">{html.escape(log["block_reason"])}</span>' if log.get("block_reason") else ""
    return f'<span class="{_BLOCKED_CLASS}">차단</span>{reason}'


def _label(log: dict) -> str:
    """선택 목록에 보여 줄 한 줄 설명. 예) 2026-10-27 09:30:05 · 홍길동 · 검색"""
    # 사용자를 알 수 없는 기록(로그인 실패 등)은 사원번호가 비어 있을 수 있다.
    who = log.get("user_name") or log.get("employee_no") or "(알 수 없음)"
    return f"{log['created_at']} · {who} · {log['action_label']}"
