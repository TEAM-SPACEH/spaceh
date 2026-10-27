"""S-02 검색 필터 UI. 기업·문서 유형·기간을 고르는 다중 필터를 화면에 그린다."""

from datetime import date

import streamlit as st


def apply_spaceh_theme() -> None:
    """spaceH 공통 디자인 테마 CSS를 주입한다.

    st.markdown에 <style>을 넣으면 그 CSS가 화면 전체에 적용된다.
    (원래 공통 테마는 main.py 같은 공용 위치에서 한 번만 부르는 게 좋지만,
     이번 작업 범위가 이 파일로 한정돼 여기서 함께 둔다.)
    """
    st.markdown(
        """
        <style>
        /* 1. 폰트 및 기본 캔버스 설정 */
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');

        html, body, [class*="css"] {
            font-family: "NeoHyundai", "Marine", "Pretendard", -apple-system, sans-serif;
            color: #111111;
            background-color: #FFFFFF;
        }

        /* 2. Streamlit 기본 헤더/푸터 정리 */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}

        /* 3. 버튼 스타일 통일 */
        .stButton > button {
            background-color: #009944;
            color: #FFFFFF;
            border-radius: 4px;
            border: none;
            font-weight: 600;
            padding: 8px 16px;
            transition: all 0.2s ease;
        }
        .stButton > button:hover {
            background-color: #007A36;
            color: #FFFFFF;
            box-shadow: 0 2px 6px rgba(0, 153, 68, 0.2);
        }

        /* 4. 카드 컨테이너 */
        .spaceh-card {
            background-color: #FFFFFF;
            border: 1px solid #E9ECEF;
            border-radius: 6px;
            padding: 16px;
            margin-bottom: 12px;
            transition: border-color 0.2s;
        }
        .spaceh-card:hover {
            border-color: #009944;
        }

        /* 5. 3사 비교 헤더 라인 */
        .card-hri { border-top: 3px solid #004098 !important; }
        .card-movex { border-top: 3px solid #009944 !important; }
        .card-hdel { border-top: 3px solid #FABE00 !important; }

        /* 6. 인용 하이라이트 */
        .citation-highlight {
            background-color: rgba(250, 190, 0, 0.15);
            padding: 2px 4px;
            border-radius: 3px;
            font-weight: 500;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_search_filters(companies: list, doc_types: list, dates) -> dict:
    """S-02 기업·문서 유형·기간을 고르는 다중 필터 UI를 그리고 선택값을 dict로 돌려준다.

    입력
        companies: 고를 수 있는 회사 목록. 예: [{"id": "HRI", "name": "현대경제연구원"}, ...]
        doc_types: 고를 수 있는 문서 유형 목록. 예: [{"code": "report", "label": "연구 보고서"}, ...]
        dates:     기간으로 고를 수 있는 (최소 날짜, 최대 날짜). 예: (date(2020, 1, 1), date.today())
                   범위를 제한하지 않으려면 None.

    반환 — apply_metadata_filters()가 그대로 받는 모양:
        {
            "companies": ["HRI", ...],   # 고른 회사 코드(없으면 빈 리스트)
            "doc_types": ["report", ...],# 고른 문서 유형 코드
            "date_from": 20250101,       # 시작일(YYYYMMDD 정수), 안 골랐으면 None
            "date_to": 20251231,         # 종료일(YYYYMMDD 정수), 안 골랐으면 None
        }
    """
    # 공통 디자인 테마(폰트·초록 버튼 등)를 먼저 입힌다.
    apply_spaceh_theme()

    st.markdown("**검색 필터**")

    # 1) 기업 다중 선택
    #    multiselect는 값으로 회사 코드(id)를 쓰고, 화면에는 회사 이름을 보여 준다.
    #    format_func: "화면에 보일 글자"를 정하는 함수 (값 → 글자).
    company_ids = [c["id"] for c in companies]
    company_name = {c["id"]: c["name"] for c in companies}
    selected_companies = st.multiselect(
        "기업",
        options=company_ids,
        format_func=lambda cid: company_name.get(cid, cid),
    )

    # 2) 문서 유형 다중 선택 (값=코드 report 등, 화면=한글 이름)
    type_codes = [t["code"] for t in doc_types]
    type_label = {t["code"]: t["label"] for t in doc_types}
    selected_types = st.multiselect(
        "문서 유형",
        options=type_codes,
        format_func=lambda code: type_label.get(code, code),
    )

    # 3) 기간 선택: 시작일과 종료일을 '각각' 고른다. 하나만 골라도 된다(예: 종료일만).
    #    value=None 이면 처음엔 비어 있고, 안 고르면 None이 돌아온다.
    min_date = dates[0] if dates else None
    max_date = dates[1] if dates else None
    start = st.date_input("시작일", value=None, min_value=min_date, max_value=max_date)
    end = st.date_input("종료일", value=None, min_value=min_date, max_value=max_date)

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
