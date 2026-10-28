"""S-01 통합 검색 화면: render_search(). S-02 필터(기업·문서 유형·기간)를 함께 건다."""

import logging
from datetime import date

import streamlit as st

from app.auth.session import get_current_user
from app.common.ui import no_permission_notice, page_header
from app.documents.views.components.document_viewer import render_selected_source
from app.documents.views.components.source_badge import SELECTED_SOURCE_KEY
from app.permissions.services.permission_service import request_document_access
from app.search.services.rag_service import RAGServiceError, generate_answer, is_no_answer
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

# S-02 필터 선택지 (관문 시연용 임시값).
# TODO: 회사는 A-07 companies 테이블에서 읽고, 문서 유형 라벨은 공통 상수로 이동
_COMPANIES = [
    {"id": "HRI", "name": "현대경제연구원"},
    {"id": "MVX", "name": "현대무벡스"},
    {"id": "ELV", "name": "현대엘리베이터"},
]

_DOC_TYPES = [
    {"code": "report", "label": "연구 보고서"},
    {"code": "disclosure", "label": "공시"},
    {"code": "manual", "label": "매뉴얼"},
    {"code": "spec", "label": "사양서"},
    {"code": "intro", "label": "회사·제품 소개"},
    {"code": "memo", "label": "내부 메모"},
]

# 오래된 문서도 검색할 수 있도록 기간 하한은 2000년으로 지정한다.
# 종료일은 프로그램 실행 시 고정하지 않고 화면 렌더링 시점마다 오늘 날짜로 계산한다.
_EARLIEST_DOC_DATE = date(2000, 1, 1)

# 검색창 위젯 key. 후속 질문(followup_questions)도 이 key로 검색어를 바꾼다.
_QUERY_KEY = "s61_query_input"


def render_search(query: str | None = None, user: dict | None = None) -> None:
    """S-01 통합 검색 및 S-04 근거 기반 AI 답변 화면.

    query: 미리 입력할 검색어
    user: 로그인 사용자. 없으면 세션의 현재 사용자 사용
    """

    user = user or get_current_user()

    if not user:
        st.warning("로그인 후 검색할 수 있습니다.")
        return

    # 공통 UI 헤더 사용
    page_header("통합 검색")

    date_range = (_EARLIEST_DOC_DATE, date.today())

    # 미리 채울 검색어는 세션 값으로만 넣는다. text_input에 value=를 같이 주면
    # 후속 질문이 세션 값을 바꿀 때 Streamlit이 "기본값과 세션 값이 함께 지정됨" 경고를 낸다.
    if query and _QUERY_KEY not in st.session_state:
        st.session_state[_QUERY_KEY] = query

    # 1. 검색창
    with st.form("s61_search_form", border=False):
        search_col, button_col = st.columns(
            [10, 1],
            vertical_alignment="bottom",
            gap="small",
        )

        with search_col:
            search_query = st.text_input(
                "검색어",
                placeholder="궁금한 내용을 검색해 보세요.",
                label_visibility="collapsed",
                key=_QUERY_KEY,
            )

        with button_col:
            submitted = st.form_submit_button(
                "검색",
                type="primary",
            )

    # 2. 검색 필터
    # 폼 밖에 배치하여 후속 질문에서도 최신 필터 상태를 사용한다.
    selection = render_search_filters(
        _COMPANIES,
        _DOC_TYPES,
        date_range,
        key="search",
        compact=True,
    )

    # 3. 사용자별 검색 상태 관리
    user_key = (
        user.get("id"),
        user.get("company_id"),
        user.get("role"),
    )

    state_key = "s61_search_results"

    # 후속 질문 자동 검색 여부
    pending = st.session_state.pop("s61_followup_pending", False)

    # 최초 질문을 유지하기 위해 이전 결과를 보관
    previous_saved = st.session_state.get(state_key)

    # 4. 검색 실행
    if submitted or pending:
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

        try:
            # S-02 필터 변환
            where = apply_metadata_filters(selection)

            # S-06 하이브리드 검색 (S-03 권한 필터는 검색 전에 적용된다)
            with st.spinner("문서를 검색하고 있습니다..."):
                chunks = hybrid_search(
                    current_query,
                    where,
                    user,
                )

            rag_result = None
            rag_error = None

            # S-04 검색된 청크를 활용한 AI 답변 생성
            if chunks:
                try:
                    with st.spinner("AI 답변을 생성하고 있습니다..."):
                        rag_result = generate_answer(
                            current_query,
                            chunks,
                        )

                except PermissionError:
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

            # 검색 결과 및 최초 질문 저장
            st.session_state[state_key] = {
                "user_key": user_key,
                "query": current_query,
                "base_query": base_query,
                "chunks": chunks,
                "rag_result": rag_result,
                "rag_error": rag_error,
            }

        except ValueError:
            st.error("검색 기간을 다시 확인해 주세요.")
            return

        except PermissionError:
            st.error("검색 권한을 확인할 수 없습니다.")
            return

        except Exception:
            logger.exception("S-06 하이브리드 검색 실패")
            st.error("검색 중 문제가 발생했습니다.")
            return

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
        _render_requestable_documents(saved["query"], user)
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

        # 7. 권한이 없어 본문은 못 보지만 '요청하면 볼 수 있는' 문서는 제목만 보여 주고 요청을 받는다 (M-03).
        _render_requestable_documents(saved["query"], user)

    # 오른쪽: AI 인용 출처 및 원문 뷰어
    with source_col:
        rag_result = saved.get("rag_result")

        render_rag_source_panel(
            rag_result.get("sources") or []
            if rag_result is not None
            else []
        )

        if st.session_state.get(SELECTED_SOURCE_KEY):
            with st.expander(
                "선택한 문서 원문",
                expanded=True,
            ):
                # 원문 뷰어(S-05)가 열기 전에 문서 접근 권한을 다시 확인한다.
                render_selected_source(user)


def _render_requestable_documents(query: str, user: dict) -> None:
    """검색어에 맞지만 권한 없는 문서를 '제목만' 보여 주고, 사유 입력 → 열람 권한 요청까지 연결한다.

    본문·청크는 쓰지 않는다(제목·회사명만). overview.md §2.3-6 규칙.
    """
    try:
        documents = search_requestable_documents(query, user)
    except Exception:
        logger.exception("요청 가능 문서 검색 실패")
        return

    if not documents:
        return

    st.divider()
    st.subheader("열람 권한을 요청할 수 있는 문서")
    for document in documents:
        company = document["company_name"] or document["company_id"]
        # 제목만 보여 주는 안내 + [열람 권한 요청] 버튼 (공통 컴포넌트). 버튼을 누르면 사유 입력을 연다.
        if no_permission_notice(document["title"], company, key=document["doc_id"]):
            st.session_state["request_open_doc"] = document["doc_id"]

        if st.session_state.get("request_open_doc") == document["doc_id"]:
            _render_request_form(user, document)


def _render_request_form(user: dict, document: dict) -> None:
    """선택한 문서에 사유를 적어 열람 권한 요청을 등록한다."""
    reason = st.text_area("요청 사유 (5~500자)", key=f"reason-{document['doc_id']}")
    if not st.button("요청 보내기", key=f"send-{document['doc_id']}"):
        return

    try:
        registered = request_document_access(user["id"], document["doc_id"], reason)
    except Exception:
        # 동시 요청 시 DB 데드락(1213) 등으로 예외가 올라올 수 있다. 앱을 멈추지 않고 안내한다.
        logger.exception("열람 권한 요청 등록 실패")
        st.error("요청 처리 중 문제가 생겼습니다. 잠시 후 다시 시도해 주세요.")
        return

    if registered:
        st.success("열람 권한을 요청했습니다. 소유 회사 관리자의 승인 후 볼 수 있습니다.")
        st.session_state.pop("request_open_doc", None)
    else:
        st.error("요청을 등록하지 못했습니다. 사유(5~500자)를 확인하거나, 이미 요청한 문서인지 확인해 주세요.")
