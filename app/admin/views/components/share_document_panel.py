"""A-03 선택한 문서의 공유 설정 패널 UI: render_share_document_panel()."""

import html

import streamlit as st

from app.admin.views.components.group_share_toggle import render_group_share_toggle
from app.common.ui import company_tag_html, security_badge_html, show_text
from core.constants import ACCESS_CONFIDENTIAL

# 패널 안 토글의 위젯 이름 접두어. 표의 토글과 이름이 겹치지 않게 한다.
PANEL_KEY_PREFIX = "share-panel"


def render_share_document_panel(doc: dict | None, user: dict) -> None:
    """A-03 표에서 고른 문서의 보안 등급과 그룹사 공유 설정을 오른쪽 패널로 보여 준다.

    doc: 고른 문서 dict (get_manageable_documents() 결과의 한 건). 고른 문서가 없으면 None
    user: 로그인 사용자
    """
    with st.container(border=True):
        if doc is None:
            show_text("표에서 문서를 고르면 공유 설정이 여기에 보입니다.", muted=True)
            return

        # 파일 형식·회사명·제목은 올린 사람이 정한 글자라 html.escape 한 뒤 HTML 로 그린다.
        st.html(
            f'<div><span class="sh-tag sh-co">{html.escape(doc["file_format"].upper())}</span> '
            f'{security_badge_html(doc["access_level"])}</div>'
        )
        show_text(doc["title"], bold=True)
        st.html(f'<div class="sh-muted">{company_tag_html(doc["company_id"])} 올린 날 {html.escape(doc["created_at"])}</div>')
        st.divider()

        text_col, toggle_col = st.columns([4, 1], vertical_alignment="center")
        with text_col:
            show_text("그룹사 공유", bold=True)
            if doc["access_level"] == ACCESS_CONFIDENTIAL:
                show_text("기밀 문서는 공유할 수 없습니다. 사내 문서만 켤 수 있습니다.", muted=True)
            else:
                state = "켜짐: 다른 계열사 사용자도 볼 수 있습니다." if doc["is_group_shared"] else "꺼짐: 우리 회사에서만 볼 수 있습니다."
                show_text(state, muted=True)
        with toggle_col:
            render_group_share_toggle(doc, user, key_prefix=PANEL_KEY_PREFIX)
