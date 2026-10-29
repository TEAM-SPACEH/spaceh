"""S-01 통합 검색 화면: render_search(). S-02 필터(기업·문서 유형·기간)를 함께 건다."""

import logging
from datetime import date

import streamlit as st

from app.auth.session import get_current_user
from app.common.ui import DOC_TYPE_LABELS, page_header
from app.documents.views.components.document_viewer import render_selected_source
from app.documents.views.components.source_badge import SELECTED_SOURCE_KEY
from app.search.services.rag_service import RAGServiceError, generate_answer_with_audit, is_no_answer
from app.search.services.search_service import apply_metadata_filters, hybrid_search
from app.search.services.search_access_service import get_fresh_search_user, inspect_search_access
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
_DOC_TYPES = [
    {"code": code, "label": label}
    for code, label in DOC_TYPE_LABELS.items()
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

    # 권한 변경으로 검색 결과를 다시 생성해야 하는 경우
    refresh_request = st.session_state.pop(
        "s61_refresh_request",
        None,
    )

    # text_input이 생성되기 전에 검색어를 복원한다.
    if refresh_request is not None:
        st.session_state[_QUERY_KEY] = refresh_request["query"]

    # 공통 UI 헤더 사용
    page_header("통합 검색")

    date_range = (_EARLIEST_DOC_DATE, date.today())

    # 미리 채울 검색어는 세션 값으로만 넣는다.
    # text_input에 value=를 같이 주면 Streamlit 경고가 발생할 수 있다.
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
    pending = st.session_state.pop(
        "s61_followup_pending",
        False,
    )

    # 최초 질문을 유지하기 위해 이전 결과를 보관
    previous_saved = st.session_state.get(state_key)

    # 4. 검색 실행
    if submitted or pending or refresh_request is not None:

        # 권한 변경에 의한 재검색이면 이전 검색어를 복원한다.
        current_query = (
            refresh_request["query"]
            if refresh_request is not None
            else search_query.strip()
        )

        base_query = (
            refresh_request["base_query"]
            if refresh_request is not None
            else current_query
        )

        # 후속 질문일 때 최초 검색어 유지
        if (
            pending
            and not submitted
            and refresh_request is None
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
            # 권한 변경 재검색 시에는 기존 질문에 사용한 필터를 유지한다.
            where = (
                refresh_request["where"]
                if refresh_request is not None
                else apply_metadata_filters(selection)
            )

            # 최신 DB 사용자 정보 조회
            # 세션의 역할·소속 회사가 오래되었을 가능성을 차단한다.
            fresh_user = get_fresh_search_user(user)

            # S-06 하이브리드 검색
            # S-03 권한 필터는 검색 전에 적용된다.
            with st.spinner("문서를 검색하고 있습니다..."):
                chunks = hybrid_search(
                    current_query,
                    where,
                    fresh_user,
                    audit=False,
                )

                # 검색 결과를 최신 MySQL 문서 권한으로 재검증
                chunks, access_snapshot = inspect_search_access(
                    fresh_user,
                    chunks,
                )

            rag_result = None
            rag_error = None

            # S-04 AI 답변 생성 및 ask 감사 로그 기록
            # 검색 결과가 없어도 "찾을 수 없음"과 ask 로그를 생성한다.
            try:
                with st.spinner("AI 답변을 생성하고 있습니다..."):
                    rag_result = generate_answer_with_audit(
                        current_query,
                        chunks,
                        fresh_user,
                        filters=where,
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
                "where": where,
                "access_snapshot": access_snapshot,
            }

        except ValueError:
            st.error("검색 기간을 다시 확인해 주세요.")
            return

        except PermissionError:
            logger.exception("S-06 검색 권한 확인 실패")
            st.error("검색 권한을 확인할 수 없습니다.")
            return

        except Exception:
            logger.exception("S-06 하이브리드 검색 실패")
            st.error("검색 중 문제가 발생했습니다.")
            return

    # 5. 저장된 검색 결과 표시
    saved = st.session_state.get(state_key)

    if not saved:
        return

    # 로그인 사용자 변경 시 기존 검색 결과 폐기
    if saved.get("user_key") != user_key:
        st.session_state.pop(state_key, None)
        st.session_state.pop(SELECTED_SOURCE_KEY, None)
        return

    # 기존 검색 결과를 화면에 표시하기 전에 최신 권한을 재검증한다.
    try:
        fresh_user = get_fresh_search_user(user)

        authorized_chunks, current_snapshot = inspect_search_access(
            fresh_user,
            saved["chunks"],
        )

    except Exception:
        logger.exception("검색 결과 권한 재검증 실패")

        # DB 조회 실패 시 기존 답변·출처를 보여주지 않는다.
        st.session_state.pop(state_key, None)
        st.session_state.pop(SELECTED_SOURCE_KEY, None)

        st.error("문서 접근 권한을 확인할 수 없습니다.")
        return

    # 사용자 역할, 승인 내역, 문서 권한 변경 감지
    access_changed = (
        current_snapshot != saved.get("access_snapshot")
        or len(authorized_chunks) != len(saved["chunks"])
    )

    if access_changed:
        # 권한 변경 전의 검색 결과·AI 답변·출처 폐기
        st.session_state.pop(state_key, None)
        st.session_state.pop(SELECTED_SOURCE_KEY, None)

        # 기존 질문 및 필터를 유지하면서 최신 권한으로 재검색
        st.session_state["s61_refresh_request"] = {
            "query": saved["query"],
            "base_query": (
                saved.get("base_query")
                or saved["query"]
            ),
            "where": saved.get("where") or {},
        }

        st.rerun()
        return

    # 재검증된 청크만 화면에서 사용한다.
    chunks = authorized_chunks

    if not chunks:
        st.info("검색 결과가 없습니다. 다른 검색어로 찾아보세요.")
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
            and not is_no_answer(
                saved["rag_result"].get("answer") or ""
            )
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

        if st.session_state.get(SELECTED_SOURCE_KEY):
            with st.expander(
                "선택한 문서 원문",
                expanded=True,
            ):
                # 원문 뷰어(S-05)도 최신 사용자 정보로 권한 확인
                render_selected_source(fresh_user)
