"""A-02 기업·문서 유형·보안 등급 필터 UI."""

import streamlit as st

# 선택 상자의 "선택 안 함" 항목. 이 항목이 고른 값이면 서비스에는 빈 문자열(전체)로 넘긴다.
_ALL = "전체"

# session_state 키. 화면이 다시 그려져도 선택이 유지된다.
KEYWORD_KEY = "admin-docs-keyword"
_COMPANY_KEY = "admin-docs-company"
_TYPE_KEY = "admin-docs-type"
_LEVEL_KEY = "admin-docs-level"
_STATUS_KEY = "admin-docs-status"


def _chip(column, label: str, icon: str, options: dict, key: str) -> str:
    """선택 칩(popover) 하나를 그리고 고른 값(코드)을 돌려준다. "전체"는 빈 문자열이다.

    options: {코드: 화면 이름}. 칩 이름은 위젯이 만들어지기 전에 정해야 하므로 직전 선택을 session_state에서 읽는다.
    """
    # 화면에는 이름("사내")을 보여 주고, 돌려줄 때는 코드("internal")로 바꾸기 위한 표다. 선택 결과가 서비스가 쓰는 코드와 같아야 한다.
    names = {_ALL: "", **{name: code for code, name in options.items()}}
    # 칩에 "보안 등급: 사내"처럼 현재 선택을 보여 주려면 위젯을 만들기 전에 이름을 정해야 한다.
    # st.session_state 는 화면이 다시 그려져도(버튼·입력 때마다 스크립트가 처음부터 다시 실행된다) 값을 기억하는 저장 공간이고,
    # 위젯의 key 로 같은 이름을 쓰면 직전 선택이 거기에 들어 있다.
    current = st.session_state.get(key, _ALL)
    with column.popover(f"{label}: {current}" if current != _ALL else label, icon=icon):
        choice = st.selectbox(label, list(names), key=key)
    return names[choice]


def render_document_filters(companies: list[dict], doc_types: dict, security_levels: dict,
                            index_statuses: dict | None = None) -> dict:
    """A-02 검색창과 기업·문서 유형·보안 등급·색인 상태 필터를 그리고 선택값을 반환한다.

    companies: [{"company_id", "name"}]. 한 곳뿐이면(계열사 관리자) 기업 필터를 숨긴다.
    doc_types·security_levels·index_statuses: {코드: 화면 이름}
    반환: {"company_id", "doc_type", "access_level", "index_status", "keyword"} (전체는 빈 문자열)
    """
    # 문서 검색창. label_visibility="collapsed" 는 라벨을 숨기되 접근성용 이름은 남긴다.
    keyword = st.text_input(
        "문서 검색", key=KEYWORD_KEY, label_visibility="collapsed", icon=":material/search:",
        placeholder="제목이나 파일명으로 찾기 (예: 스마트팩토리 사양서)",
    ).strip()
    columns = st.columns([1.2, 1.2, 1.2, 1.2, 2])
    company_id = ""
    # 선택할 수 있는 기업이 둘 이상일 때만 기업 필터를 보여 준다. 계열사 관리자는 자사 하나뿐이라 필터를 숨긴다
    # (어차피 서비스가 자사로 고정한다).
    if len(companies) > 1:
        company_id = _chip(columns[0], "기업", ":material/apartment:",
                           {c["company_id"]: c["name"] for c in companies}, _COMPANY_KEY)
    return {
        "company_id": company_id,
        "doc_type": _chip(columns[1], "문서 유형", ":material/description:", doc_types, _TYPE_KEY),
        "access_level": _chip(columns[2], "보안 등급", ":material/lock:", security_levels, _LEVEL_KEY),
        "index_status": _chip(columns[3], "색인 상태", ":material/sync:", index_statuses or {}, _STATUS_KEY),
        "keyword": keyword,
    }
