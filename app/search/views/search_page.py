"""S-01 통합 검색 화면: render_search(). S-02 필터(기업·문서 유형·기간)를 함께 건다."""

import logging
from datetime import date

import streamlit as st

from app.auth.session import get_current_user
from app.search.services.search_service import apply_metadata_filters, search_documents
from app.search.services.rag_service import RAGServiceError, generate_answer
from app.search.views.components.search_filters import render_search_filters
from app.search.views.components.rag_answer_card import render_rag_answer_card
from app.search.views.components.rag_source_panel import render_rag_source_panel
from app.search.views.components.search_result_list import render_search_result_list
from app.search.views.components.followup_questions import render_followup_questions
from app.documents.views.components.source_badge import SELECTED_SOURCE_KEY
from app.documents.views.components.document_viewer import render_selected_source

logger = logging.getLogger(__name__)

# 청크 목록에서 본문을 미리 보여 줄 글자 수
PREVIEW_CHARS = 200

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

# 검색 기간 하한
_EARLIEST_DOC_DATE = date(2000, 1, 1)

def render_search(query: str | None = None, user: dict | None = None) -> None:
    """S-01 통합 검색 및 S-04 근거 기반 AI 답변 화면.

    query: 미리 입력할 검색어
    user: 로그인 사용자. 없으면 세션의 현재 사용자 사용
    """

    user = user or get_current_user()

    if not user:
        st.warning("로그인 후 검색할 수 있습니다.")
        return

    st.caption("02 · 통합 검색 / 근거 답변")
    st.markdown("#### 통합 검색")

    date_range = (_EARLIEST_DOC_DATE, date.today())

    with st.form("s61_search_form", border=False):
        search_col, button_col = st.columns(
            [10, 1],
            vertical_alignment="bottom",
            gap="small",
        )

        with search_col:
            search_query = st.text_input(
                "검색어",
                value=query or "",
                placeholder="궁금한 내용을 검색해 보세요.",
                label_visibility="collapsed",
                key="s61_query_input",
            )

        with button_col:
            submitted = st.form_submit_button(
                "검색",
                type="primary",
            )

    selection = render_search_filters(
        _COMPANIES,
        _DOC_TYPES,
        date_range,
        key="search",
        compact=True,
    )

    user_key = (
        user.get("id"),
        user.get("company_id"),
        user.get("role"),
    )

    state_key = "s61_search_results"

    # 후속 질문 자동 검색 여부 확인
    pending = st.session_state.pop("s61_followup_pending", False)

    # 이전 검색 정보 보관 (초기 질문을 유지하기 위함)
    previous_saved = st.session_state.get(state_key)

    if submitted or pending:

        # 현재 입력된 질문
        current_query = search_query.strip()

        # 기본값은 현재 질문
        base_query = current_query

        # 후속 질문이면 이전 최초 질문 유지
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
            # 필터 조건 생성
            where = apply_metadata_filters(selection)

            # S-01 문서 검색
            with st.spinner("문서를 검색하고 있습니다..."):
                chunks = search_documents(
                    current_query,
                    where,
                    user,
                )

            # S-04 AI 답변 생성
            rag_result = None
            rag_error = None

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
            logger.exception("S-01 검색 실패")
            st.error("검색 중 문제가 발생했습니다.")
            return

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
        return

    content_col, source_col = st.columns(
        [2.2, 1],
        gap="medium",
        vertical_alignment="top",
    )

    # 왼쪽: AI 답변, 이어서 묻기, 검색 결과
    with content_col:

        # S-04 AI 답변
        if saved.get("rag_error"):
            st.error(saved["rag_error"])

        elif saved.get("rag_result") is not None:
            render_rag_answer_card(saved["rag_result"])

        # 이어서 묻기
        # 실제 검색 질문이 아닌 최초 질문을 기준으로 생성
        if (
            saved.get("rag_result") is not None
            and saved["rag_result"].get("answer") != "찾을 수 없음"
        ):
            render_followup_questions(
                saved.get("base_query") or saved["query"]
            )

        # S-01 검색 결과 목록
        render_search_result_list(chunks)

    # 오른쪽: AI 인용 출처 및 원문 보기
    with source_col:

        rag_result = saved.get("rag_result")

        render_rag_source_panel(
            rag_result.get("sources") or []
            if rag_result is not None
            else []
        )

        # S-05 선택된 원문 보기
        if st.session_state.get(SELECTED_SOURCE_KEY):
            with st.expander(
                "선택한 문서 원문",
                expanded=True,
            ):
                render_selected_source(user)


def _group_by_document(chunks: list[dict]) -> list[dict]:
    """청크를 문서(doc_id)별로 묶는다. 문서 순서는 가장 관련도 높은 청크 기준."""

    documents: dict[str, dict] = {}

    # 관련도 순으로 처음 만난 청크가 문서의 최고 점수
    for chunk in chunks:
        doc = documents.setdefault(
            chunk["doc_id"],
            {
                "metadata": chunk["metadata"],
                "score": chunk["score"],
                "chunk_count": 0,
            },
        )
        doc["chunk_count"] += 1

    return list(documents.values())
