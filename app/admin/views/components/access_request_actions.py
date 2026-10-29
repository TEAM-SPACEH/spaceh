"""A-05 승인·반려 처리 UI."""

import logging

import streamlit as st

from app.admin.services.access_service import process_access_request

logger = logging.getLogger(__name__)


def render_access_request_actions(request_id: int, user: dict) -> None:
    """A-05 요청별 승인·반려 버튼과 반려 사유 입력란을 표시한다."""
    with st.form(f"access_review_{request_id}"):
        reason = st.text_area("반려 사유", max_chars=4000, key=f"access_review_reason_{request_id}")
        approve, reject = st.columns(2)
        approved = approve.form_submit_button("승인", type="primary")
        rejected = reject.form_submit_button("반려")
    if not (approved or rejected):
        return
    try:
        result = process_access_request(request_id, "approved" if approved else "rejected", user, reason)
    except (PermissionError, ValueError, LookupError) as exc:
        st.error(str(exc))
        return
    except Exception:
        logger.exception("A-05 열람 요청 처리 실패")
        st.error("처리 결과를 확인하지 못했습니다. 목록을 새로 확인한 뒤 다시 시도해 주세요.")
        return
    st.session_state["access_review_notice"] = (
        "열람 요청을 승인했습니다." if result["status"] == "approved" else "열람 요청을 반려했습니다."
    )
    st.rerun()
