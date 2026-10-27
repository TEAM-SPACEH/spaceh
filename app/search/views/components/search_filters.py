"""S-02 검색 필터 UI. 기업·문서 유형·기간을 고르는 다중 필터를 화면에 그린다."""

from datetime import date

import streamlit as st


def render_search_filters(companies: list, doc_types: list, dates, key: str = "search") -> dict:
    """S-02 기업·문서 유형·기간을 고르는 다중 필터 UI를 그리고 선택값을 dict로 돌려준다.

    입력
        companies: 고를 수 있는 회사 목록. 예: [{"id": "HRI", "name": "현대경제연구원"}, ...]
        doc_types: 고를 수 있는 문서 유형 목록. 예: [{"code": "report", "label": "연구 보고서"}, ...]
        dates:     기간으로 고를 수 있는 (최소 날짜, 최대 날짜). 예: (date(2020, 1, 1), date.today())
                   범위를 제한하지 않으려면 None.
        key:       위젯 key 앞부분. 같은 페이지에 필터를 두 번 그리면 Streamlit이 "중복 위젯"
                   오류를 내므로, 필터마다 다른 key를 주려고 받는다. 기본값 "search".

    반환 — apply_metadata_filters()가 그대로 받는 모양:
        {
            "companies": ["HRI", ...],   # 고른 회사 코드(없으면 빈 리스트)
            "doc_types": ["report", ...],# 고른 문서 유형 코드
            "date_from": 20250101,       # 시작일(YYYYMMDD 정수), 안 골랐으면 None
            "date_to": 20251231,         # 종료일(YYYYMMDD 정수), 안 골랐으면 None
        }
    """
    # 색·글꼴 등 공통 테마는 .streamlit/config.toml + app/common/ui.py(main.py의 apply_theme)가
    # 맡는다. 이 컴포넌트는 <style>을 넣지 않는다.
    st.subheader("검색 필터")

    # 1) 기업 다중 선택
    #    multiselect는 값으로 회사 코드(id)를 쓰고, 화면에는 회사 이름을 보여 준다.
    #    format_func: "화면에 보일 글자"를 정하는 함수 (값 → 글자).
    company_ids = [c["id"] for c in companies]
    company_name = {c["id"]: c["name"] for c in companies}
    selected_companies = st.multiselect(
        "기업",
        options=company_ids,
        format_func=lambda cid: company_name.get(cid, cid),
        key=f"{key}_companies",
    )

    # 2) 문서 유형 다중 선택 (값=코드 report 등, 화면=한글 이름)
    type_codes = [t["code"] for t in doc_types]
    type_label = {t["code"]: t["label"] for t in doc_types}
    selected_types = st.multiselect(
        "문서 유형",
        options=type_codes,
        format_func=lambda code: type_label.get(code, code),
        key=f"{key}_doc_types",
    )

    # 3) 기간 선택: 시작일과 종료일을 '각각' 고른다. 하나만 골라도 된다(예: 종료일만).
    #    value=None 이면 처음엔 비어 있고, 안 고르면 None이 돌아온다.
    min_date = dates[0] if dates else None
    max_date = dates[1] if dates else None
    start = st.date_input("시작일", value=None, min_value=min_date, max_value=max_date, key=f"{key}_date_from")
    end = st.date_input("종료일", value=None, min_value=min_date, max_value=max_date, key=f"{key}_date_to")

    # 고른 날짜만 YYYYMMDD 정수로 바꾼다(안 골랐으면 None). 종료일만 고르면 date_to만 채워진다.
    date_from = _to_yyyymmdd(start)
    date_to = _to_yyyymmdd(end)

    return {
        "companies": selected_companies,
        "doc_types": selected_types,
        "date_from": date_from,
        "date_to": date_to,
    }


def _to_yyyymmdd(picked: date | None) -> int | None:
    """고른 날짜(date)를 YYYYMMDD 정수로 바꾼다. 안 골랐으면(None) None.

    예: 2025-01-02 → 20250102
    """
    if not picked:
        return None
    return picked.year * 10000 + picked.month * 100 + picked.day
