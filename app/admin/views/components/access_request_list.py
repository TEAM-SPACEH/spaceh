"""A-05 자사 소유 문서 열람 요청 목록 UI (Figma 09 왼쪽 카드): 대기·승인·반려 탭과 요청 행."""

import html
import logging
from datetime import datetime

import streamlit as st

from app.admin.services.access_service import get_access_request_counts, get_access_request_list
from app.common.ui import card, company_tag_html, empty_state, security_badge_html

logger = logging.getLogger(__name__)

PAGE_SIZE = 20

STATUS_KEY = "ar_status"          # 탭에서 고른 상태 코드
SELECTED_KEY = "ar_selected"      # 목록에서 고른 요청 번호
STATUS_LABELS = {"pending": "대기", "approved": "승인", "rejected": "반려"}

# 요청자 역할 코드 → 화면 이름 (DB에는 영어 코드만 저장)
ROLE_LABELS = {"employee": "일반 사원", "company_admin": "계열사 관리자", "super_admin": "최종 어드민"}

# 목록 행 앞에 붙는 문서 아이콘
FILE_ICON_URL = "app/static/icons/file-dark.svg"


def format_ago(created_at: datetime | None, now: datetime | None = None) -> str:
    """요청 시각을 "방금 전·N분 전·N시간 전·어제·N일 전"으로 바꾼다. 30일이 넘으면 날짜(MM.DD)로 보여 준다."""
    if not isinstance(created_at, datetime):
        return ""
    now = now or datetime.now()
    seconds = (now - created_at).total_seconds()
    if seconds < 60:
        return "방금 전"
    if seconds < 3600:
        return f"{int(seconds // 60)}분 전"
    if seconds < 86400 and created_at.date() == now.date():
        return f"{int(seconds // 3600)}시간 전"
    days = (now.date() - created_at.date()).days
    if days <= 1:
        return "어제"
    return f"{days}일 전" if days <= 30 else created_at.strftime("%m.%d")


def _select_request(request_id: int) -> None:
    """목록 행을 누르면 그 요청을 오른쪽 상세에 연다. 콜백이라 화면을 다시 그리기 전에 실행된다."""
    st.session_state[SELECTED_KEY] = request_id


def _count_css(counts: dict[str, int]) -> str:
    """탭 이름 옆 숫자 칩. 숫자는 코드가 센 정수라 CSS에 그대로 넣어도 안전하다."""
    rules = "".join(
        f'.st-key-{STATUS_KEY} [data-testid="stRadioGroup"]>div:nth-child({index}) [data-testid="stRadioOption"]>div::after'
        f'{{content:"{int(counts.get(code, 0))}"}}'
        for index, code in enumerate(STATUS_LABELS, start=1)
    )
    return f"<style>{rules}</style>"


def _item_html(request: dict) -> str:
    """요청 한 줄: 요청자·소속·시각, 역할, 문서와 보안 등급. 모두 DB 값이라 escape한다."""
    role = ROLE_LABELS.get(request["requester_role"], request["requester_role"])
    return (
        '<div class="sh-ar-item">'
        '<div class="sh-ar-top">'
        f'<span class="sh-ar-name">{html.escape(request["requester_name"])}</span>'
        f'{company_tag_html(request["requester_company_id"] or "")}'
        f'<span class="sh-ar-ago">{html.escape(format_ago(request["created_at"]))}</span></div>'
        f'<div class="sh-ar-role">{html.escape(role)}</div>'
        '<div class="sh-ar-doc">'
        f'<img src="{FILE_ICON_URL}" width="13" height="13" alt="">'
        f'<span class="sh-ar-doc-title">{html.escape(request["title"])}</span>'
        f'{security_badge_html(request["access_level"])}</div></div>'
    )


def render_access_request_list(user: dict) -> dict | None:
    """A-05 관리자 범위의 요청을 상태 탭별로 보여 주고, 오른쪽 상세에 열 요청 1건을 돌려준다. 요청이 없으면 None."""
    page_key = f"access_request_page_{user['id']}"
    with card("ar_list"):
        try:
            counts = get_access_request_counts(user)
        except PermissionError as exc:
            st.error(str(exc))
            return None
        except Exception:
            logger.exception("A-05 열람 요청 개수 조회 실패")
            st.error("열람 요청을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
            return None

        st.html(_count_css(counts))
        status = st.radio(
            "요청 상태", list(STATUS_LABELS), format_func=STATUS_LABELS.get, horizontal=True,
            key=STATUS_KEY, label_visibility="collapsed",
        )
        # 상태 탭을 바꾸면 1페이지부터 다시 본다.
        if st.session_state.get("ar_status_seen") != status:
            st.session_state["ar_status_seen"] = status
            st.session_state[page_key] = 1
        page = st.session_state.get(page_key, 1)
        try:
            result = get_access_request_list(user, {"status": status}, page, PAGE_SIZE)
        except PermissionError as exc:
            st.error(str(exc))
            return None
        except Exception:
            logger.exception("A-05 열람 요청 목록 조회 실패")
            st.error("열람 요청을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
            return None

        requests = result["requests"]
        if not requests:
            with st.container(key="ar_list_empty"):
                empty_state(f"{STATUS_LABELS[status]} 상태의 열람 요청이 없습니다.")
            return None

        # 고른 요청이 이 목록에 없으면(탭을 바꿨거나 방금 처리했으면) 첫 요청을 연다.
        selected = next((r for r in requests if r["id"] == st.session_state.get(SELECTED_KEY)), requests[0])
        with st.container(key="ar_items"):
            for request in requests:
                is_on = request["id"] == selected["id"]
                with st.container(key=f"ar_item_{'on' if is_on else 'off'}_{request['id']}"):
                    st.html(_item_html(request))
                    st.button(
                        f"{request['requester_name']}의 요청 선택", key=f"ar_pick_{request['id']}",
                        on_click=_select_request, args=(request["id"],),
                    )
        _render_pager(page_key, result["page"], result["total_pages"])
        st.session_state[page_key] = result["page"]
    return selected


def _render_pager(page_key: str, page: int, total_pages: int) -> None:
    """요청이 한 페이지를 넘을 때만 이전·다음 버튼을 보여 준다. 누르면 페이지만 바꾸고 다시 그린다."""
    if total_pages <= 1:
        return
    with st.container(horizontal=True, key="ar_pager"):
        if st.button("이전", key="access_request_previous", disabled=page <= 1, type="tertiary"):
            st.session_state[page_key] = page - 1
            st.rerun()
        st.html(f'<span class="sh-ar-page">{page} / {total_pages}</span>')
        if st.button("다음", key="access_request_next", disabled=page >= total_pages, type="tertiary"):
            st.session_state[page_key] = page + 1
            st.rerun()
