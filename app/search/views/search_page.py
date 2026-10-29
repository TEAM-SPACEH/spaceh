"""S-01 통합 검색 화면: render_search(). S-02 필터(기업·문서 유형·기간)를 함께 건다."""

import html
import logging
import re
from datetime import date

import streamlit as st

from app.auth.session import get_current_user
from app.common.ui import DOC_TYPE_LABELS, card, company_tag_html, no_permission_notice
from app.documents.views.components.document_viewer import render_selected_source
from app.documents.views.components.source_badge import SELECTED_SOURCE_KEY
from app.permissions.services.permission_service import request_document_access
from app.search.services.rag_service import (
    RAGServiceError,
    generate_answer_with_audit,
    is_no_answer,
    record_blocked_ask,
)
from app.search.services.search_service import (
    apply_metadata_filters,
    hybrid_search,
    search_requestable_documents,
)
from app.search.views.components.followup_questions import render_followup_questions
from app.search.views.components.rag_answer_card import render_rag_answer_card
from app.search.views.components.rag_source_panel import render_rag_source_panel
from app.search.views.components.search_filters import render_search_filters
from app.search.views.components.search_result_list import render_search_result_list

logger = logging.getLogger(__name__)

# S-02 필터 선택지. 회사는 관문 시연용 임시값이다.
# TODO: 회사는 A-07 companies 테이블에서 읽는다
_COMPANIES = [
    {"id": "HRI", "name": "현대경제연구원"},
    {"id": "MVX", "name": "현대무벡스"},
    {"id": "ELV", "name": "현대엘리베이터"},
]

# 문서 유형은 공통 상수(DOC_TYPE_LABELS)에서 만든다.
_DOC_TYPES = [{"code": code, "label": label} for code, label in DOC_TYPE_LABELS.items()]

# 오래된 문서도 검색할 수 있도록 기간 하한은 2000년으로 지정한다.
# 종료일은 프로그램 실행 시 고정하지 않고 화면 렌더링 시점마다 오늘 날짜로 계산한다.
_EARLIEST_DOC_DATE = date(2000, 1, 1)

# 검색창 위젯 key. 후속 질문(followup_questions)도 이 key로 검색어를 바꾼다.
_QUERY_KEY = "s61_query_input"

# 초기 화면(Figma 02-0)의 인사말·검색 상자 폭
_START_WIDTH = 760

# 사이드바 최근 질문 (이번 로그인 동안만 세션에 둔다)
_RECENT_KEY = "s61_recent_queries"
_RECENT_PENDING_KEY = "s61_recent_pending"
_RECENT_LIMIT = 5

# M-03 요청을 보낸 뒤 화면에 한 번 보여 줄 안내
_REQUEST_FLASH_KEY = "s61_request_flash"


def render_search(query: str | None = None, user: dict | None = None) -> None:
    """S-01 통합 검색 및 S-04 근거 기반 AI 답변 화면.

    query: 미리 입력할 검색어
    user: 로그인 사용자. 없으면 세션의 현재 사용자 사용
    """

    user = user or get_current_user()

    if not user:
        st.warning("로그인 후 검색할 수 있습니다.")
        return

    date_range = (_EARLIEST_DOC_DATE, date.today())

    # 미리 채울 검색어는 세션 값으로만 넣는다. text_input에 value=를 같이 주면
    # 후속 질문이 세션 값을 바꿀 때 Streamlit이 "기본값과 세션 값이 함께 지정됨" 경고를 낸다.
    if query and _QUERY_KEY not in st.session_state:
        st.session_state[_QUERY_KEY] = query

    # 사용자별 검색 상태 관리
    user_key = (
        user.get("id"),
        user.get("company_id"),
        user.get("role"),
    )

    state_key = "s61_search_results"

    # 후속 질문 자동 검색 여부
    pending = st.session_state.pop("s61_followup_pending", False)
    # 사이드바 최근 질문을 누르면 그 질문으로 새로 검색한다 (후속 질문과 달리 최초 질문도 바뀐다).
    recent = st.session_state.pop(_RECENT_PENDING_KEY, False)
    _render_recent_questions()

    # 아직 검색 결과가 없으면 초기 화면(Figma 02-0): 인사말 아래 가운데에 검색 상자와 필터를 둔다.
    # 검색 결과가 있으면 검색 화면(Figma 02): 맨 위 검색 상자, 그 아래 필터와 결과.
    saved_before = st.session_state.get(state_key)
    is_start = not (pending or recent) and not (saved_before and saved_before.get("user_key") == user_key)

    with st.container(key="search-hero" if is_start else "search-top", horizontal_alignment="center"):
        with st.container(width=_START_WIDTH if is_start else "stretch"):
            if is_start:
                st.html(
                    f'<div class="sh-hero-title">안녕하세요, <b>{html.escape(user.get("name") or "")}</b>님</div>'
                    '<div class="sh-hero-sub">무엇을 찾아볼까요?</div>'
                    '<div class="sh-hero-desc">현대경제연구원 · 현대무벡스 · 현대엘리베이터 문서 중 '
                    "내 권한 안의 문서에서 찾아, 근거와 함께 답합니다.</div>"
                )

            # 1. 검색창
            with card("search-box"):
                with st.form("s61_search_form", border=False):
                    search_col, button_col = st.columns(
                        [10, 1],
                        vertical_alignment="center",
                        gap="small",
                    )

                    with search_col:
                        search_query = st.text_input(
                            "검색어",
                            placeholder="예: 현대무벡스 3분기 스마트팩토리 수주 현황과 위험 요인은?",
                            label_visibility="collapsed",
                            key=_QUERY_KEY,
                        )

                    with button_col:
                        submitted = st.form_submit_button(
                            "검색",
                            type="primary",
                        )

                # 2. 검색 필터 (초기 화면은 검색 상자 안)
                # 폼 밖에 배치하여 후속 질문에서도 최신 필터 상태를 사용한다.
                if is_start:
                    selection = _render_filters(date_range)

            # 2. 검색 필터 (검색 화면은 검색 상자 아래)
            if not is_start:
                selection = _render_filters(date_range)

    # 최초 질문을 유지하기 위해 이전 결과를 보관
    previous_saved = st.session_state.get(state_key)

    # 4. 검색 실행
    if submitted or pending or recent:
        current_query = search_query.strip()
        base_query = current_query

        # 후속 질문일 때 최초 검색어 유지
        if (
            pending
            and not submitted
            and previous_saved
            and previous_saved.get("user_key") == user_key
        ):
            base_query = (
                previous_saved.get("base_query")
                or previous_saved.get("query")
                or current_query
            )

        # 이전 검색 결과 및 원문 선택 초기화
        st.session_state.pop(state_key, None)
        st.session_state.pop(SELECTED_SOURCE_KEY, None)

        if not current_query:
            st.warning("검색어를 입력해 주세요.")
            return

        # 권한 오류 발생 시 감사 로그에 검색 조건을 전달하기 위한 초기값
        where = None

        try:
            # S-02 필터 변환
            where = apply_metadata_filters(selection)

            # S-06 하이브리드 검색 (S-03 권한 필터는 검색 전에 적용된다)
            # search 감사 로그는 기본값(audit=True)을 유지한다.
            with st.spinner("문서를 검색하고 있습니다..."):
                chunks = hybrid_search(
                    current_query,
                    where,
                    user,
                )

            rag_result = None
            rag_error = None

            # S-04 검색된 청크를 활용한 AI 답변 생성 및 ask 감사 로그 기록
            # 결과가 0건이어도 일반 무결과 질의로 기록한다.
            try:
                with st.spinner("AI 답변을 생성하고 있습니다..."):
                    rag_result = generate_answer_with_audit(
                        current_query,
                        chunks,
                        user,
                        filters=where,
                    )

            except PermissionError as exc:
                record_blocked_ask(user, current_query, where, str(exc))
                logger.exception("S-04 답변 생성 권한 오류")
                rag_error = (
                    "AI 답변에 사용할 문서의 접근 권한을 "
                    "확인할 수 없습니다."
                )

            except RAGServiceError:
                logger.exception("S-04 AI 서비스 오류")
                rag_error = (
                    "AI 답변 서비스에 문제가 발생했습니다. "
                    "잠시 후 다시 시도해 주세요."
                )

            except Exception:
                logger.exception("S-04 답변 생성 실패")
                rag_error = "AI 답변 생성 중 문제가 발생했습니다."

            # M-03 요청 가능 문서(제목만)도 '검색할 때 한 번만' 찾아 결과와 함께 저장한다.
            # 요청 버튼 클릭 등으로 화면이 재실행될 때마다 DB를 다시 호출하지 않게 캐시한다.
            # 요청 후보는 본문(Chroma)이 아니라 제목·메타데이터(MySQL)로 찾으므로, Chroma where가
            # 아니라 S-02 선택값(selection) 그대로 넘긴다(권한 사전 필터 원칙 — overview.md §2.3).
            try:
                requestable = search_requestable_documents(current_query, selection, user)
            except Exception:
                logger.exception("요청 가능 문서 검색 실패")
                requestable = []

            # 검색 결과 및 최초 질문 저장.
            st.session_state[state_key] = {
                "user_key": user_key,
                "query": current_query,
                "base_query": base_query,
                "where": where,
                "chunks": chunks,
                "rag_result": rag_result,
                "rag_error": rag_error,
                "requestable": requestable,
            }

        except ValueError:
            st.error("검색 기간을 다시 확인해 주세요.")
            return

        except PermissionError as exc:
            record_blocked_ask(user, current_query, where, str(exc))
            logger.exception("S-06 검색 권한 확인 실패")
            st.error("검색 권한을 확인할 수 없습니다.")
            return

        except Exception:
            logger.exception("S-06 하이브리드 검색 실패")
            st.error("검색 중 문제가 발생했습니다.")
            return

        # 최근 질문 목록을 갱신하고, 초기 화면이었으면 검색 화면 배치로 바꾸도록 다시 그린다.
        # (사이드바 최근 질문은 이번 실행에서 이미 그려졌으므로 다시 그려야 새 질문이 보인다.)
        _remember_query(current_query)
        st.rerun()

    # 5. 저장된 결과 표시
    saved = st.session_state.get(state_key)

    if not saved:
        return

    # 로그인 사용자 변경 시 기존 검색 결과 폐기
    if saved.get("user_key") != user_key:
        st.session_state.pop(state_key, None)
        st.session_state.pop(SELECTED_SOURCE_KEY, None)
        return

    chunks = saved["chunks"]

    if not chunks:
        st.info("검색 결과가 없습니다. 다른 검색어로 찾아보세요.")
        # 결과가 없어도, 권한 때문에 가려졌을 수 있는 문서는 제목만 보여 주고 요청을 받는다 (M-03).
        _render_requestable_documents(saved, user)
        return

    # 6. AI 답변 및 출처 2열 레이아웃
    content_col, source_col = st.columns(
        [2.2, 1],
        gap="medium",
        vertical_alignment="top",
    )

    # 왼쪽: AI 답변, 이어서 묻기, 검색 결과
    with content_col:
        if saved.get("rag_error"):
            st.error(saved["rag_error"])

        elif saved.get("rag_result") is not None:
            render_rag_answer_card(saved["rag_result"])

        # 후속 질문은 최초 질문을 기준으로 생성
        if (
            saved.get("rag_result") is not None
            and not is_no_answer(saved["rag_result"].get("answer") or "")
        ):
            render_followup_questions(
                saved.get("base_query") or saved["query"]
            )

        render_search_result_list(chunks)

    # 오른쪽: AI 인용 출처 및 원문 뷰어
    with source_col:
        rag_result = saved.get("rag_result")

        render_rag_source_panel(
            rag_result.get("sources") or []
            if rag_result is not None
            else []
        )

        # 7. 권한이 없어 본문은 못 보지만 '요청하면 볼 수 있는' 문서는 제목만 보여 주고 요청을 받는다 (M-03).
        # Figma 02처럼 출처 칸에 회사 카드로 둔다.
        _render_requestable_documents(saved, user)

        if st.session_state.get(SELECTED_SOURCE_KEY):
            with st.expander(
                "선택한 문서 원문",
                expanded=True,
            ):
                # 원문 뷰어(S-05)가 열기 전에 문서 접근 권한을 다시 확인한다.
                render_selected_source(user)


def _render_filters(date_range: tuple[date, date]) -> dict:
    """S-02 기업·문서 유형·기간 필터. 초기 화면과 검색 화면에서 놓이는 자리만 다르다."""
    return render_search_filters(
        _COMPANIES,
        _DOC_TYPES,
        date_range,
        key="search",
        compact=True,
    )


def _render_requestable_documents(saved: dict, user: dict) -> None:
    """권한 없는 문서를 '제목만' 보여 주고, 사유 입력 → 열람 권한 요청까지 연결한다.

    목록은 검색할 때 한 번 구해 saved["requestable"]에 저장해 둔 것을 쓴다(재실행마다 재조회하지
    않는다). 그래서 요청 버튼을 눌러 화면이 재실행돼도 목록·요청 양식이 그대로 유지된다.
    본문·청크는 쓰지 않는다(제목·회사명만). overview.md §2.3-6 규칙.
    """
    # 요청을 보낸 뒤 팝업이 닫히고 다시 그려진 화면에서 한 번만 안내한다.
    flash = st.session_state.pop(_REQUEST_FLASH_KEY, None)
    if flash:
        st.success(flash)

    documents = saved.get("requestable") or []
    for document in documents:
        company = document["company_name"] or document["company_id"]
        # 제목만 보여 주는 안내 + [내 권한 요청] 버튼 (공통 컴포넌트). 버튼을 누르면 사유 입력 팝업을 연다.
        if no_permission_notice(document["title"], company, key=document["doc_id"]):
            _request_dialog(saved, user, document)


@st.dialog("내 권한 요청")
def _request_dialog(saved: dict, user: dict, document: dict) -> None:
    """M-03 사유를 적어 열람 권한 요청을 등록하는 팝업 (Figma 15). 성공하면 캐시 목록에서 그 문서를 뺀다."""
    company = document["company_name"] or document["company_id"]
    st.caption("문서를 가진 회사의 관리자에게 열람 승인을 요청합니다.")
    # 제목·회사명은 데이터에서 온 글자라 escape해서 st.html로 보여 준다.
    st.html(
        f'<div class="sh-req-doc">{company_tag_html(company)}'
        f'<div class="sh-req-title">{html.escape(document["title"])}</div>'
        '<div class="sh-req-note">승인 전에는 제목만 보이고 내용은 볼 수 없습니다.</div></div>'
    )
    st.text_input("받는 사람", value=f"{company} 관리자", disabled=True, key=f"to-{document['doc_id']}")
    reason = st.text_area(
        "요청 사유",
        placeholder="예: 승강기 부품 물류 공동 운영 방안을 보고서로 정리하려고 합니다.",
        max_chars=500,
        key=f"reason-{document['doc_id']}",
    )
    st.caption("필수 · 5~500자")
    st.info("요청 상태(대기·승인·반려)와 반려 사유는 내 정보에서 확인할 수 있습니다.")

    cancel_col, send_col = st.columns(2)
    if cancel_col.button("취소", key=f"cancel-{document['doc_id']}", width="stretch"):
        st.rerun()
    if not send_col.button("요청 보내기", key=f"send-{document['doc_id']}", type="primary", width="stretch"):
        return

    try:
        registered = request_document_access(user["id"], document["doc_id"], reason)
    except Exception:
        # 동시 요청 시 DB 데드락(1213) 등으로 예외가 올라올 수 있다. 앱을 멈추지 않고 안내한다.
        logger.exception("열람 권한 요청 등록 실패")
        st.error("요청 처리 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.")
        return

    if registered:
        st.session_state[_REQUEST_FLASH_KEY] = "열람 권한을 요청했습니다. 소유 회사 관리자의 승인 후 볼 수 있습니다."
        # 이미 요청했으니 캐시 목록에서 빼서 다시 안 보이게 한다(재조회 없이).
        saved["requestable"] = [
            item for item in saved.get("requestable", []) if item["doc_id"] != document["doc_id"]
        ]
        st.rerun()
    else:
        st.error("요청을 등록하지 못했습니다. 사유(5~500자)를 확인하거나, 이미 요청한 문서인지 확인해 주세요.")


def _remember_query(query: str) -> None:
    """사이드바 최근 질문에 이번 검색어를 맨 앞으로 넣는다 (이번 로그인 동안만, 최대 5개)."""
    queries = [item for item in st.session_state.get(_RECENT_KEY, []) if item != query]
    st.session_state[_RECENT_KEY] = [query, *queries][:_RECENT_LIMIT]


def _set_recent_query(query: str) -> None:
    """최근 질문을 검색창에 넣고 새 검색을 요청한다."""
    st.session_state[_QUERY_KEY] = query
    st.session_state[_RECENT_PENDING_KEY] = True


def _render_recent_questions() -> None:
    """사이드바 메뉴 아래 최근 질문 (Figma 02). 누르면 같은 질문으로 다시 검색한다."""
    queries = st.session_state.get(_RECENT_KEY) or []
    if not queries:
        return

    with st.sidebar, st.container(key="s61_recent"):
        st.html('<div class="sh-recent-title">최근 질문</div>')
        for index, query in enumerate(queries):
            # 버튼 글자는 Markdown으로 해석되므로 특수문자를 escape한다.
            label = re.sub(r"([\\`*_\[\]()#+\-.!~>|{}:$])", r"\\\1", query)
            st.button(
                label,
                key=f"s61_recent_{index}",
                type="tertiary",
                on_click=_set_recent_query,
                args=(query,),
                width="stretch",
            )
