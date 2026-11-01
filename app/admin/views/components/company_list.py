"""A-07 계열사 목록 UI: render_company_list()."""

import html

import streamlit as st

from app.common.ui import card, company_tag_html, empty_state, show_text

# 열 너비 비율: 회사, 코드, 문서, 보안 등급 분포, 사용자, 상태
_COLUMN_WIDTHS = [2.4, 1.2, 1, 3.6, 1, 1.6]
_HEADERS = ["회사", "코드", "문서", "보안 등급 분포", "사용자", "상태"]

# 보안 등급 분포 막대의 (CSS 클래스, 서비스가 주는 문서 수 키). 공개(초록)·사내(노랑)·기밀(빨강) 순이다.
_LEVEL_COUNTS = (
    ("sh-dist-pub", "doc_public"),
    ("sh-dist-int", "doc_internal"),
    ("sh-dist-con", "doc_confidential"),
)

# 상태는 공통 CSS 클래스(app/common/ui.py)를 쓴다. 사용 중은 초록 글자, 중지는 회색 글자다 (Figma 11).
_ACTIVE_HTML = '<span class="sh-ok">✓ 사용 중</span>'
_INACTIVE_HTML = '<span class="sh-muted">중지</span>'

# 표 아래 막대 색 범례
_LEGEND_HTML = (
    '<div class="sh-legend"><span><i class="sh-dist-pub"></i>공개</span>'
    '<span><i class="sh-dist-int"></i>사내</span><span><i class="sh-dist-con"></i>기밀</span></div>'
)


def render_company_list(companies: list[dict]) -> None:
    """A-07 계열사 표(회사·코드·문서·보안 등급 분포·사용자·상태)를 흰 카드 안에 보여 준다 (Figma 11).

    companies: get_companies() 결과. 비어 있으면 안내 문구만 보여 준다.
    보안 등급 분포는 공개·사내·기밀 비율 막대로 보여 주고, 표 아래에 색 범례를 둔다.
    """
    with card("company-list"):
        if not companies:
            empty_state("등록된 계열사가 없습니다. 오른쪽에서 계열사를 더해 보세요.")
            return

        # 머리글 줄 회색 바탕·행 구분선은 공통 CSS가 key(sh-thead-…, sh-trow-…-N)로 그린다.
        with st.container(key="sh-thead-company"):
            header = st.columns(_COLUMN_WIDTHS)
        for cell, label in zip(header, _HEADERS):
            with cell:
                show_text(label, bold=True, muted=True)

        for index, company in enumerate(companies):
            with st.container(key=f"sh-trow-company-{index}"):
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

        st.html(_LEGEND_HTML)


def _distribution_html(company: dict) -> str:
    """보안 등급 분포 막대: 공개·사내·기밀 문서 수 비율만큼 칸을 칠한다. 문서가 없으면 "문서 없음".

    막대에 마우스를 올리면 등급별 문서 수가 보인다 (title).
    """
    total = company["doc_total"]
    if not total:
        return '<span class="sh-muted">문서 없음</span>'
    counts = {key: int(company[key]) for _, key in _LEVEL_COUNTS}
    title = f"공개 {counts['doc_public']} · 사내 {counts['doc_internal']} · 기밀 {counts['doc_confidential']}"
    segments = "".join(
        f'<span class="{css}" style="width:{counts[key] / total * 100:.1f}%"></span>' for css, key in _LEVEL_COUNTS
    )
    return f'<div class="sh-dist" title="{html.escape(title)}">{segments}</div>'
