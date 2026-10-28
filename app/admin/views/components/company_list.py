"""A-07 계열사 목록 UI: render_company_list()."""

import html

import streamlit as st

from app.common.ui import company_tag_html, empty_state, security_badge_html, show_text
from core.constants import ACCESS_CONFIDENTIAL, ACCESS_INTERNAL, ACCESS_PUBLIC

# 열 너비 비율: 회사, 코드, 문서, 보안 등급 분포, 사용자, 상태
_COLUMN_WIDTHS = [2.4, 1.2, 1, 3.6, 1, 1.6]
_HEADERS = ["회사", "코드", "문서", "보안 등급 분포", "사용자", "상태"]

# 보안 등급 분포로 보여 줄 (등급, 서비스가 주는 문서 수 키). 공개·사내·기밀 순이다.
_LEVEL_COUNTS = (
    (ACCESS_PUBLIC, "doc_public"),
    (ACCESS_INTERNAL, "doc_internal"),
    (ACCESS_CONFIDENTIAL, "doc_confidential"),
)

# 상태 배지는 공통 CSS 클래스(app/common/ui.py)를 쓴다. 사용 중은 초록, 중지는 회색이다.
_ACTIVE_HTML = '<span class="sh-tag sh-pub">사용 중</span>'
_INACTIVE_HTML = '<span class="sh-tag sh-co">중지</span>'


def render_company_list(companies: list[dict]) -> None:
    """A-07 계열사 표(회사·코드·문서·보안 등급 분포·사용자·상태)를 카드 안에 보여 준다.

    companies: get_companies() 결과. 비어 있으면 안내 문구만 보여 준다.
    보안 등급 분포는 막대 대신 공통 등급 배지 + 문서 수로 보여 준다 (색은 공통 배지와 같다).
    """
    with st.container(border=True):
        if not companies:
            empty_state("등록된 계열사가 없습니다. 오른쪽에서 계열사를 더해 보세요.")
            return

        header = st.columns(_COLUMN_WIDTHS)
        for cell, label in zip(header, _HEADERS):
            with cell:
                show_text(label, bold=True, muted=True)

        for company in companies:
            cells = st.columns(_COLUMN_WIDTHS, vertical_alignment="center")
            # 회사명은 관리자가 입력한 글자라 Markdown 해석 없이 보여 준다.
            with cells[0]:
                show_text(company["name"], bold=True)
            cells[1].html(company_tag_html(company["company_id"]))
            with cells[2]:
                show_text(f"{company['doc_total']:,}")
            cells[3].html(_distribution_html(company))
            with cells[4]:
                show_text(f"{company['user_count']:,}")
            cells[5].html(_ACTIVE_HTML if company["is_active"] else _INACTIVE_HTML)


def _distribution_html(company: dict) -> str:
    """보안 등급 분포: 등급 배지마다 문서 수를 붙인다. 문서가 없으면 "문서 없음"."""
    if not company["doc_total"]:
        return '<span class="sh-muted">문서 없음</span>'
    parts = [
        f'{security_badge_html(level)} <span class="sh-muted">{html.escape(str(company[key]))}</span>'
        for level, key in _LEVEL_COUNTS
    ]
    return " ".join(parts)
