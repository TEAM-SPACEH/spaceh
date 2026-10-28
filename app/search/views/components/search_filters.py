"""S-02 검색 필터 UI. 기업·문서 유형·기간을 고르는 다중 필터를 화면에 그린다."""

from datetime import date

import streamlit as st
from contextlib import nullcontext

def render_search_filters(
    companies: list,
    doc_types: list,
    dates,
    key: str = "search",
    compact: bool = False,
) -> dict:
    """S-02 기업·문서 유형·기간 다중 검색 필터 UI.

    Args:
        companies: 회사 id와 name을 포함한 딕셔너리 목록
        doc_types: 문서 유형 code와 label을 포함한 딕셔너리 목록
        dates: 선택 가능한 최소·최대 날짜
        key: Streamlit 위젯 키 접두사
        compact: True면 가로형 팝오버, False면 기존 세로형 UI

    Returns:
        선택된 검색 조건 딕셔너리.
        {
            "companies": 선택한 회사 ID 목록,
            "doc_types": 선택한 문서 유형 코드 목록,
            "date_from": 시작일(YYYYMMDD) 또는 None,
            "date_to": 종료일(YYYYMMDD) 또는 None,
        }
    """
    if compact:
        company_col, type_col, date_col, _ = st.columns(
            [1.3, 1.5, 1.3, 5],
            gap="small",
        )

        # 현재 선택된 필터 상태
        n_company = len(st.session_state.get(f"{key}_companies") or [])
        n_type = len(st.session_state.get(f"{key}_doc_types") or [])

        has_date = bool(
            st.session_state.get(f"{key}_date_from")
            or st.session_state.get(f"{key}_date_to")
        )

        # 선택 상태에 따라 팝오버 버튼 라벨 변경
        company_box = company_col.popover(
            f"계열사 {n_company}개" if n_company else "계열사 전체"
        )

        type_box = type_col.popover(
            f"문서 유형 {n_type}개" if n_type else "문서 유형 전체"
        )

        date_box = date_col.popover(
            "기간 지정" if has_date else "기간 전체"
        )

    else:
        st.subheader("검색 필터")
        company_box = nullcontext()
        type_box = nullcontext()
        date_box = nullcontext()

    # 1. 기업 선택
    company_ids = [c["id"] for c in companies]
    company_names = {c["id"]: c["name"] for c in companies}

    with company_box:
        selected_companies = st.multiselect(
            "기업",
            options=company_ids,
            format_func=lambda cid: company_names.get(cid, cid),
            key=f"{key}_companies",
        )

    # 2. 문서 유형 선택
    type_codes = [t["code"] for t in doc_types]
    type_labels = {t["code"]: t["label"] for t in doc_types}

    with type_box:
        selected_types = st.multiselect(
            "문서 유형",
            options=type_codes,
            format_func=lambda code: type_labels.get(code, code),
            key=f"{key}_doc_types",
        )

    # 3. 기간 선택
    min_date = dates[0] if dates else None
    max_date = dates[1] if dates else None

    with date_box:
        start = st.date_input(
            "시작일",
            value=None,
            min_value=min_date,
            max_value=max_date,
            key=f"{key}_date_from",
        )

        end = st.date_input(
            "종료일",
            value=None,
            min_value=min_date,
            max_value=max_date,
            key=f"{key}_date_to",
        )

    return {
        "companies": selected_companies,
        "doc_types": selected_types,
        "date_from": _to_yyyymmdd(start),
        "date_to": _to_yyyymmdd(end),
    }

def _to_yyyymmdd(picked: date | None) -> int | None:
    """고른 날짜(date)를 YYYYMMDD 정수로 바꾼다. 안 골랐으면(None) None.

    예: 2025-01-02 → 20250102
    """
    if not picked:
        return None
    return picked.year * 10000 + picked.month * 100 + picked.day
