"""A-02 문서 검색창과 기업·문서 유형·보안 등급·색인 상태 필터 UI."""

import streamlit as st

# 선택 상자의 "선택 안 함" 항목. 이 항목이 고른 값이면 서비스에는 빈 문자열(전체)로 넘긴다.
_ALL = "전체"

# session_state 키. 화면이 다시 그려져도 선택이 유지된다.
KEYWORD_KEY = "admin-docs-keyword"
_COMPANY_KEY = "admin-docs-company"
_TYPE_KEY = "admin-docs-type"
_LEVEL_KEY = "admin-docs-level"
_STATUS_KEY = "admin-docs-status"


def _chip(column, chip: str, label: str, options: dict, key: str) -> str:
    """선택 칩(popover) 하나를 그리고 고른 값(코드)을 돌려준다. "전체"는 빈 문자열이다.

    chip: 칩 글자(짧게). label: 안쪽 선택 상자 이름
    options: {코드: 화면 이름}. 칩 이름은 위젯이 만들어지기 전에 정해야 하므로 직전 선택을 session_state에서 읽는다.
    """
    # 화면에는 이름("사내")을 보여 주고, 돌려줄 때는 코드("internal")로 바꾸기 위한 표다. 선택 결과가 서비스가 쓰는 코드와 같아야 한다.
    names = {_ALL: "", **{name: code for code, name in options.items()}}
    # 칩에 "보안 등급: 사내"처럼 현재 선택을 보여 주려면 위젯을 만들기 전에 이름을 정해야 한다.
    # st.session_state 는 화면이 다시 그려져도 값을 기억하는 저장 공간이고, 위젯의 key 로 같은 이름을 쓰면 직전 선택이 거기에 들어 있다.
    current = st.session_state.get(key, _ALL)
    with column.popover(f"{chip}: {current}" if current != _ALL else chip):
        choice = st.selectbox(label, list(names), key=key)
    return names[choice]


def render_document_filters(companies: list[dict], doc_types: dict, security_levels: dict,
                            index_statuses: dict | None = None) -> dict:
    """A-02 검색창과 기업·문서 유형·보안 등급·색인 상태 필터를 한 줄로 그리고 선택값을 반환한다.

    companies: [{"company_id", "name"}]. 한 곳뿐이면(계열사 관리자) 기업 필터를 숨긴다.
    doc_types·security_levels·index_statuses: {코드: 화면 이름}
    반환: {"company_id", "doc_type", "access_level", "index_status", "keyword"} (전체는 빈 문자열)
    """
    show_company = len(companies) > 1
    # 검색창은 남는 폭을 모두 차지하고, 칩은 글자 폭만큼만 둔다 (폭 계산은 ui.py의 .st-key-ad_toolbar CSS).
    with st.container(key="ad_toolbar"):
        columns = st.columns([1] + [0.1] * (3 + int(show_company)), vertical_alignment="center")
        with columns[0]:
            # 문서 검색창. label_visibility="collapsed" 는 라벨을 숨기되 접근성용 이름은 남긴다.
            keyword = st.text_input(
                "문서 검색", key=KEYWORD_KEY, label_visibility="collapsed",
                placeholder="제목이나 파일명으로 찾기",
            ).strip()
        chips = iter(columns[1:])
        company_id = ""
        if show_company:
            company_id = _chip(next(chips), "기업", "기업", {c["company_id"]: c["name"] for c in companies}, _COMPANY_KEY)
        doc_type = _chip(next(chips), "유형", "문서 유형", doc_types, _TYPE_KEY)
        access_level = _chip(next(chips), "보안 등급", "보안 등급", security_levels, _LEVEL_KEY)
        index_status = _chip(next(chips), "색인 상태", "색인 상태", index_statuses or {}, _STATUS_KEY)
    return {"company_id": company_id, "doc_type": doc_type, "access_level": access_level,
            "index_status": index_status, "keyword": keyword}
