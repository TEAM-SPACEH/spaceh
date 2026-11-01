"""A-05 승인·반려 처리 UI (Figma 09 오른쪽 카드 아래): 반려 사유 입력과 [반려]·[승인] 버튼."""

import html
import logging

import streamlit as st

from app.admin.services.access_service import process_access_request

logger = logging.getLogger(__name__)

NOTICE_KEY = "access_review_notice"
REJECT_PLACEHOLDER = "예: 계약 단가가 들어 있어 공유할 수 없습니다."


def _footer_text(request: dict) -> str:
    """버튼 줄 왼쪽 안내. 승인하면 어떤 일이 생기는지 알려 준다. 이름은 DB 값이라 escape해서 쓴다."""
    return f"승인하면 {request['requester_name']}님의 검색 결과와 답변 근거에 이 문서가 들어갑니다. 결정은 감사 로그에 남습니다."


def render_access_request_actions(request: dict, user: dict) -> None:
    """A-05 대기 요청이면 반려 사유 입력과 승인·반려 버튼을, 처리된 요청이면 처리 결과를 표시한다."""
    request_id = request["id"]
    if request["status"] != "pending":
        _render_result(request)
        return

    # 반려 사유는 서비스가 반려할 때 필수로 확인한다(A-05 규칙). 화면 라벨도 그대로 알린다.
    reason = st.text_area(
        "반려할 때 남길 말 (반려 시 필수)", key=f"access_review_reason_{request_id}", max_chars=4000, height=76,
        placeholder=REJECT_PLACEHOLDER,
    )
    with st.container(horizontal=True, key="ar_footer"):
        st.html(f'<div class="sh-ar-footnote">{html.escape(_footer_text(request))}</div>')
        with st.container(horizontal=True, key="ar_actions"):
            rejected = st.button("반려", key=f"access_review_reject_{request_id}", icon=":material/close:")
            approved = st.button("승인", key=f"access_review_approve_{request_id}", type="primary",
                                 icon=":material/check:")
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
    st.session_state[NOTICE_KEY] = (
        "열람 요청을 승인했습니다." if result["status"] == "approved" else "열람 요청을 반려했습니다."
    )
    st.rerun()


def _render_result(request: dict) -> None:
    """처리된 요청의 결과: 처리 시각과 (반려면) 남긴 사유. 버튼은 없다."""
    approved = request["status"] == "approved"
    reviewed = request["reviewed_at"].strftime("%m.%d %H:%M") if hasattr(request["reviewed_at"], "strftime") else ""
    parts = []
    if not approved and request["review_comment"]:
        parts.append(
            '<div class="sh-ar-section"><div class="sh-ar-section-title">반려 사유</div>'
            f'<div class="sh-ar-reason">{html.escape(request["review_comment"])}</div></div>'
        )
    verdict = "승인" if approved else "반려"
    parts.append(f'<div class="sh-ar-footnote sh-ar-done">{verdict}한 요청입니다. {html.escape(reviewed)}</div>')
    st.html("".join(parts))
