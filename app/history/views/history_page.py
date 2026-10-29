"""M-04 내 사용 히스토리 화면: render_history()."""

import html
import logging

import streamlit as st

from app.auth.session import get_current_user
from app.common.ui import company_tag_html, empty_state, page_header, show_text
from app.history.services.history_service import (
    HISTORY_TYPES,
    get_access_request_history,
    get_history_detail,
    get_history_report,
    get_user_history,
    rerun_search,
)

logger = logging.getLogger(__name__)

# 목록에서 고른 항목을 다시 그릴 때(rerun)까지 기억하는 session_state 키. 값은 (동작, id).
_SELECTED_KEY = "history-selected"

_ALL = "전체"

# 권한 요청 상태 배지 색. 공통 테마의 보안 등급 색을 다시 쓴다 (M-03 마이페이지와 같은 색).
_STATUS_CLASS = {"pending": "sh-int", "approved": "sh-pub", "rejected": "sh-con"}


def render_history(user: dict | None = None) -> None:
    """M-04 내 사용 이력(최신순)과 열람 권한 요청 상태를 보여 준다.

    user: 로그인 사용자. 없으면 세션의 현재 사용자를 쓴다
    """
    user = user or get_current_user()
    if not user:
        st.warning("로그인 후 볼 수 있습니다.")
        return

    page_header("내 사용 히스토리", "내 검색·질문·원문 열람·보고서 생성 이력과 열람 권한 요청 상태를 확인합니다.")
    history_tab, request_tab = st.tabs(["사용 이력", "권한 요청"])
    with history_tab:
        _render_usage(user["id"])
    with request_tab:
        _render_requests(user["id"])


def _render_usage(user_id: int) -> None:
    labels = {_ALL: None, **{label: code for code, label in HISTORY_TYPES.items()}}
    choice = st.selectbox("이력 유형", list(labels), key="history-type")

    _render_selected(user_id)

    try:
        items = get_user_history(user_id, labels[choice])
    except Exception:
        logger.exception("M-04 사용 이력 조회 실패")
        st.error("이력을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return
    if not items:
        empty_state("아직 이력이 없습니다. 통합 검색에서 문서를 찾아보세요.")
        return

    for item in items:
        with st.container(border=True):
            info, actions = st.columns([5, 1])
            with info:
                blocked = " · 차단됨" if item["is_blocked"] else ""
                show_text(f"[{item['type_label']}] {item['summary']}", bold=True)
                show_text(f"{item['created_at']}{blocked}", muted=True)
            with actions:
                history_id = item["history_id"]
                if item["can_rerun"] and st.button("다시 검색", key=f"rerun-{history_id}"):
                    st.session_state[_SELECTED_KEY] = ("rerun", history_id)
                    st.rerun()
                # 보고서 항목은 감사 로그가 아니라 reports 에서 온 것이라 history_id 가 없다.
                if item["report_id"] is not None and st.button("보고서 열기", key=f"report-{item['report_id']}"):
                    st.session_state[_SELECTED_KEY] = ("report", item["report_id"])
                    st.rerun()
                if history_id is not None and st.button("상세", key=f"detail-{history_id}"):
                    st.session_state[_SELECTED_KEY] = ("detail", history_id)
                    st.rerun()


def _render_selected(user_id: int) -> None:
    """목록에서 고른 항목(상세·다시 검색·보고서)을 목록 위에 펼친다."""
    selected = st.session_state.get(_SELECTED_KEY)
    if not selected:
        return
    kind, target_id = selected
    with st.container(border=True):
        if st.button("닫기", key="history-close"):
            st.session_state.pop(_SELECTED_KEY, None)
            st.rerun()
        try:
            if kind == "rerun":
                _render_rerun(user_id, target_id)
            elif kind == "report":
                _render_report(user_id, target_id)
            else:
                _render_detail(user_id, target_id)
        except Exception:
            logger.exception("M-04 이력 항목 처리 실패 kind=%s", kind)
            st.error("처리 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.")


def _render_detail(user_id: int, history_id: int) -> None:
    detail = get_history_detail(user_id, history_id)
    if detail is None:
        st.error("이력을 찾을 수 없습니다.")
        return
    st.subheader(f"{detail['type_label']} 상세")
    if detail["query"]:
        show_text(f"내용: {detail['query']}")
    show_text(f"실행 시각: {detail['created_at']}", muted=True)
    if detail["result_count"] is not None:
        show_text(f"결과 {detail['result_count']}건", muted=True)
    if detail["is_blocked"]:
        show_text(f"차단됨: {detail['block_reason'] or '권한 없음'}", muted=True)
    if detail["documents"]:
        show_text("관련 문서", bold=True)
        for document in detail["documents"]:
            show_text(f"· {document['title']}")


def _render_rerun(user_id: int, history_id: int) -> None:
    result = rerun_search(user_id, history_id)
    if not result:
        st.error("다시 실행할 검색 이력을 찾을 수 없습니다.")
        return
    st.subheader("다시 검색한 결과")
    show_text(f"검색어: {result['query']}", muted=True)
    if not result["results"]:
        empty_state("지금 권한으로 볼 수 있는 결과가 없습니다. 다른 검색어로 찾아보세요.")
        return
    # 같은 문서의 청크는 한 줄로 묶는다. 결과가 관련도 순이라 처음 만난 청크가 그 문서의 최고 점수다.
    documents: dict[str, dict] = {}
    for chunk in result["results"]:
        documents.setdefault(chunk["doc_id"], {"metadata": chunk["metadata"], "score": chunk["score"]})
    for document in documents.values():
        meta = document["metadata"]
        show_text(meta.get("title") or meta.get("file_name", ""), bold=True)
        show_text(f"{meta.get('company_name', '')} · {meta.get('file_name', '')} · 관련도 {document['score']:.2f}", muted=True)


def _render_report(user_id: int, report_id: int) -> None:
    report = get_history_report(user_id, report_id)
    if report is None:
        st.error("보고서를 열 수 없습니다. 근거 문서 중 지금 권한으로 볼 수 없는 문서가 있거나 보고서가 없습니다.")
        return
    show_text(report["title"], bold=True)
    show_text(f"생성 시각: {report['created_at']}", muted=True)
    if report["exec_summary_md"]:
        show_text("1페이지 요약", bold=True)
        show_text(report["exec_summary_md"])
    # 보고서 본문은 문서 내용을 바탕으로 만든 글이라 Markdown 으로 해석하지 않는다 (ui.py 규칙).
    show_text(report["content_md"])


def _render_requests(user_id: int) -> None:
    try:
        requests = get_access_request_history(user_id)
    except Exception:
        logger.exception("M-04 권한 요청 조회 실패")
        st.error("권한 요청 내역을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")
        return
    if not requests:
        empty_state("신청한 열람 권한 요청이 없습니다. 권한이 없는 문서에서 '열람 권한 요청'을 누르면 여기에 나타납니다.")
        return

    for request in requests:
        with st.container(border=True):
            css = _STATUS_CLASS.get(request["status"], "sh-co")
            st.html(
                f'<div><span class="sh-tag {css}">{html.escape(request["status_label"])}</span> '
                f"{company_tag_html(request['owner_company_code'])} <b>{html.escape(request['title'])}</b></div>"
            )
            dates = f"신청 {request['created_at']}"
            if request["reviewed_at"]:
                dates += f" · 처리 {request['reviewed_at']}"
            show_text(dates, muted=True)
            show_text(f"요청 사유: {request['reason']}", muted=True)
            if request["status"] == "rejected":
                show_text(f"반려 사유: {request['review_comment'] or '사유 없음'}")
