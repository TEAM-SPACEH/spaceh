"""A-05 선택한 열람 요청의 상세 UI (Figma 09 오른쪽 카드): 요청 문서·요청한 사람·이전 요청·요청 사유와 처리."""

import html
import logging
from datetime import datetime

import streamlit as st

from app.admin.services.access_service import get_requester_summary
from app.admin.views.components.access_request_actions import render_access_request_actions
from app.admin.views.components.access_request_list import ROLE_LABELS
from app.common.ui import ACCESS_LABELS, card, security_badge_html
from app.documents.views.components.document_viewer import FORMAT_LABELS
from app.documents.views.components.source_badge import SELECTED_SOURCE_KEY
from core.constants import ACCESS_CONFIDENTIAL

logger = logging.getLogger(__name__)

# [문서 보기]로 원문 뷰어를 연 상태 표시 (화면이 직접 남긴다. access_requests.py가 읽는다)
VIEWER_FLAG_KEY = "ar_viewing_document"

LOCK_ICON_URL = "app/static/icons/lock-red.svg"
EYE_ICON_URL = "app/static/icons/eye.svg"


def _level_badge_html(access_level: str) -> str:
    """보안 등급 배지. 기밀은 자물쇠를 붙인다 (Figma 상세 카드)."""
    badge = security_badge_html(access_level)
    if access_level != ACCESS_CONFIDENTIAL:
        return badge
    label = html.escape(ACCESS_LABELS.get(access_level, access_level))
    return f'<span class="sh-tag sh-con sh-ar-lock"><img src="{LOCK_ICON_URL}" width="11" height="11" alt="">{label}</span>'


def _date_text(value, fmt: str) -> str:
    """날짜·시각 값을 글자로 바꾼다. 값이 없으면 빈 글자."""
    return value.strftime(fmt) if hasattr(value, "strftime") else ""


def previous_request_text(summary: dict) -> tuple[str, str]:
    """"이전 요청" 카드의 큰 글자와 작은 글자를 만든다. 처리 결과가 모두 같으면 "N건 모두 승인"처럼 줄여 쓴다."""
    total = summary["total"]
    if total == 0:
        return "처음 요청", "이 회사 문서에 낸 이전 요청이 없습니다."
    decided = summary["approved"] + summary["rejected"]
    if summary["approved"] == total:
        head = f"{total}건 모두 승인"
    elif summary["rejected"] == total:
        head = f"{total}건 모두 반려"
    else:
        parts = [f"승인 {summary['approved']}건", f"반려 {summary['rejected']}건"]
        if summary["pending"]:
            parts.append(f"대기 {summary['pending']}건")
        head = " · ".join(parts)
    last = _date_text(summary["last_approved_at"], "마지막 승인 %m.%d")
    return head, last or ("처리 대기 중인 요청만 있습니다." if decided == 0 else "")


def _info_cards_html(request: dict, summary: dict | None) -> str:
    """요청한 사람·이전 요청 카드 두 장."""
    role = ROLE_LABELS.get(request["requester_role"], request["requester_role"])
    company = request["requester_company_name"] or request["requester_company_id"] or ""
    who = (
        '<div class="sh-ar-card"><div class="sh-ar-label">요청한 사람</div>'
        f'<div class="sh-ar-value">{html.escape(request["requester_name"])}</div>'
        f'<div class="sh-ar-subtext">{html.escape(f"{company} {role}".strip())}</div></div>'
    )
    if summary is None:
        previous = ('<div class="sh-ar-card"><div class="sh-ar-label">이전 요청</div>'
                    '<div class="sh-ar-subtext">불러오지 못했습니다.</div></div>')
    else:
        head, sub = previous_request_text(summary)
        previous = (
            '<div class="sh-ar-card"><div class="sh-ar-label">이전 요청</div>'
            f'<div class="sh-ar-value">{html.escape(head)}</div>'
            f'<div class="sh-ar-subtext">{html.escape(sub)}</div></div>'
        )
    return f'<div class="sh-ar-cards">{who}{previous}</div>'


def _open_document(request: dict) -> None:
    """[문서 보기]: S-05 원문 뷰어가 읽는 세션 칸에 문서를 넣는다. 열람 권한은 뷰어가 다시 확인한다."""
    st.session_state[SELECTED_SOURCE_KEY] = {
        "text": "", "company": request["company_name"] or request["company_id"], "company_id": request["company_id"],
        "filename": request["title"], "location": "", "doc_id": request["doc_id"], "chunk_id": "", "citation_number": 0,
    }
    st.session_state[VIEWER_FLAG_KEY] = True


def render_access_request_detail(user: dict, request: dict) -> None:
    """A-05 요청 1건의 문서·요청자·사유를 보여 주고, 대기 중이면 승인·반려 입력을 붙인다."""
    try:
        summary = get_requester_summary(user, request["id"])
    except Exception:
        logger.exception("A-05 요청자 이전 요청 요약 조회 실패")
        summary = None

    published = _date_text(request["published_date"], "%Y.%m.%d")
    meta = ", ".join(part for part in (
        request["company_name"] or request["company_id"],
        FORMAT_LABELS.get(request["file_format"], str(request["file_format"]).upper()),
        published,
    ) if part)
    with card("ar_detail"):
        with st.container(horizontal=True, key="ar_doc_head"):
            st.html(
                '<div><div class="sh-ar-label">요청 문서</div>'
                f'<div class="sh-ar-title">{html.escape(request["title"])}{_level_badge_html(request["access_level"])}</div>'
                f'<div class="sh-ar-label sh-ar-meta">{html.escape(meta)}</div></div>'
            )
            st.button("문서 보기", key=f"ar_open_{request['id']}", on_click=_open_document, args=(request,))
        st.html(_info_cards_html(request, summary))
        st.html(
            '<div class="sh-ar-section"><div class="sh-ar-section-title">요청 사유</div>'
            f'<div class="sh-ar-reason">{html.escape(request["reason"] or "")}</div></div>'
        )
        render_access_request_actions(request, user)
