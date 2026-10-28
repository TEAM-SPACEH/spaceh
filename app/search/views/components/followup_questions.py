"""S-07 이어서 묻기 질문 버튼 UI."""

import streamlit as st


def _set_followup_query(question: str) -> None:
    """선택한 질문을 검색창에 반영하고 검색 실행을 요청합니다."""
    st.session_state["s61_query_input"] = question
    st.session_state["s61_followup_pending"] = True


def render_followup_questions(query: str) -> None:
    """기존 검색어를 활용해 후속 질문 버튼을 표시합니다."""

    if not query.strip():
        return

    questions = [
        (
            "관련 근거 자세히",
            f"{query} 관련 문서의 근거를 더 자세히 알려줘.",
        ),
        (
            "기업별 내용 비교",
            f"{query}에 대한 기업별 정보를 비교해줘.",
        ),
        (
            "추가 자료 확인",
            f"{query}와 관련된 추가 문서가 있나요?",
        ),
    ]

    label_col, *question_cols = st.columns(
        [1, 2, 2, 2],
        gap="small",
        vertical_alignment="center",
    )

    with label_col:
        st.caption("이어서 묻기")

    for index, (label, question) in enumerate(questions):
        with question_cols[index]:
            st.button(
                label,
                key=f"s61_followup_{index}",
                on_click=_set_followup_query,
                args=(question,),
                width="stretch",
            )
