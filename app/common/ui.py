"""공통 화면 요소. 모든 views는 반복되는 UI를 직접 만들지 말고 여기 함수를 부른다.

- 색·글꼴·둥글기는 .streamlit/config.toml 테마가 정한다. views에서 `<style>`을 넣지 않는다.
- 문서 제목·파일명·본문처럼 업로드한 사람이 정할 수 있는 값은 `st.markdown`·`st.caption`·`st.write`에
  넘기지 않는다. 이 함수들은 Markdown을 해석해 `[링크](https://…)`·`![이미지](…)`를 그대로 그린다.
  대신 `show_text()` 또는 `*_html()` + `st.html()`을 쓴다 (html.escape 후 Markdown 해석 없이 표시).
"""

import html

import streamlit as st

from core.constants import ACCESS_CONFIDENTIAL, ACCESS_INTERNAL, ACCESS_PUBLIC

# 보안 등급 화면 이름과 배지 색 (design.md 2.3: 공개 그린, 사내 옐로, 기밀 빨강)
ACCESS_LABELS = {ACCESS_PUBLIC: "공개", ACCESS_INTERNAL: "사내", ACCESS_CONFIDENTIAL: "기밀"}
_ACCESS_CLASS = {ACCESS_PUBLIC: "sh-pub", ACCESS_INTERNAL: "sh-int", ACCESS_CONFIDENTIAL: "sh-con"}

# 상태 화면 이름 (db/schema.sql의 CHECK 값). 종류마다 같은 값(pending 등)의 뜻이 달라 나눠 둔다.
STATUS_LABELS = {
    "index": {"pending": "대기", "indexing": "색인 중", "done": "완료", "failed": "실패"},  # documents.index_status
    "request": {"pending": "검토 중", "approved": "승인", "rejected": "반려"},  # access_requests.status
    "dart": {"running": "수집 중", "completed": "완료", "failed": "실패"},  # dart_sync_jobs.status
}
# 상태 색은 배지 배경 없이 글자색만 쓴다 (UI v4). 보안 등급 배지와 겉모양으로 구분된다.
_STATUS_TONE = {
    "done": "ok", "approved": "ok", "completed": "ok",
    "pending": "wait", "indexing": "wait", "running": "wait",
    "failed": "bad", "rejected": "bad",
}
_TONE_MARK = {"ok": "✓ ", "bad": "⚠ ", "wait": ""}

# 파일 형식 아이콘 글자 (documents.file_format). DART 공시는 원본이 XML이라도 DART로 보여 준다.
FILE_TYPE_LABELS = {"pdf": "PDF", "docx": "DOCX", "pptx": "PPT", "xlsx": "XLSX", "hwp": "HWP", "dart_xml": "DART"}

_CSS = """
<style>
.sh-tag{display:inline-block;padding:1px 7px;border-radius:4px;font-size:12px;font-weight:600;line-height:20px;white-space:nowrap}
.sh-pub{background:#EBFBEE;color:#2B8A3E}
.sh-int{background:#FFF4CC;color:#7A5A00}
.sh-con{background:#FFF5F5;color:#E03131}
.sh-co{background:#F1F3F5;color:#343A40;font-weight:700}
.sh-cite{display:inline-block;min-width:19px;padding:0 4px;border-radius:9px;background:#E7F0FA;color:#004098;font-size:11px;font-weight:700;line-height:18px;text-align:center;margin-left:3px}
.sh-hl{background:rgba(250,190,0,0.24);border-radius:2px;padding:0 2px}
.sh-muted{color:#868E96;font-size:13px}
.sh-text{white-space:pre-wrap;line-height:1.6}
.sh-st{font-size:13px;font-weight:600;white-space:nowrap}
.sh-st-ok{color:#2B8A3E}
.sh-st-wait{color:#B07D00}
.sh-st-bad{color:#E03131}
.sh-file{display:inline-block;min-width:34px;padding:2px 4px;border-radius:4px;font-size:10px;font-weight:800;line-height:14px;text-align:center;background:#F1F3F5;color:#495057}
.sh-file-pdf{background:#FFF5F5;color:#E03131}
.sh-file-docx{background:#E7F5FF;color:#1C7ED6}
.sh-file-pptx{background:#FFF4E6;color:#E8590C}
.sh-file-dart_xml{background:#EBFBEE;color:#2B8A3E}
.sh-eyebrow{color:#868E96;font-size:13px;margin-bottom:-12px}
.sh-stat-label{color:#495057;font-size:13px}
.sh-stat-value{color:#111111;font-size:28px;font-weight:700;line-height:1.3}
.sh-dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:6px;vertical-align:middle}
.sh-dot-ok{background:#2B8A3E}
.sh-dot-wait{background:#FABE00}
.sh-dot-bad{background:#E03131}
</style>
"""


def apply_theme() -> None:
    """배지·각주·하이라이트용 CSS를 한 번 넣는다. main.py에서만 부른다."""
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, description: str | None = None, eyebrow: str | None = None) -> None:
    """페이지 맨 위 제목과 한 줄 설명. 모든 페이지는 이것으로 시작한다.

    eyebrow: 제목 위 작은 줄 (UI v4 관리 화면의 "현대무벡스 관리"). 회사명이 들어가므로 escape해서 그린다.
    """
    if eyebrow:
        st.html(f'<div class="sh-eyebrow">{html.escape(eyebrow)}</div>')
    st.title(title)
    if description:
        st.caption(description)


def security_badge_html(access_level: str) -> str:
    """보안 등급 배지. 모르는 값이면 회색으로 값 그대로 보여 준다."""
    label = ACCESS_LABELS.get(access_level, access_level)
    css = _ACCESS_CLASS.get(access_level, "sh-co")
    return f'<span class="sh-tag {css}">{html.escape(label)}</span>'


def company_tag_html(company_code: str) -> str:
    """회사 코드 태그 (HRI·MVX·ELV). 회사마다 색을 다르게 하지 않는다 (보안 등급 색과 헷갈림)."""
    return f'<span class="sh-tag sh-co">{html.escape(company_code)}</span>'


def citation_html(number: int) -> str:
    """답변·보고서 본문 안의 각주 번호 [1]."""
    return f'<span class="sh-cite">{int(number)}</span>'


def highlight_html(text: str) -> str:
    """근거 문장·검색어 하이라이트 (옐로)."""
    return f'<span class="sh-hl">{html.escape(text)}</span>'


def status_tag_html(kind: str, status: str) -> str:
    """상태 표시 (✓ 완료, 색인 중, ⚠ 실패 등). kind: "index"(색인) / "request"(열람 요청) / "dart"(DART 수집).

    모르는 값이면 회색 글자로 값 그대로 보여 준다.
    """
    label = STATUS_LABELS.get(kind, {}).get(status, status)
    tone = _STATUS_TONE.get(status) if status in STATUS_LABELS.get(kind, {}) else None
    if tone is None:
        return f'<span class="sh-st sh-muted">{html.escape(label)}</span>'
    return f'<span class="sh-st sh-st-{tone}">{_TONE_MARK[tone]}{html.escape(label)}</span>'


def file_type_html(file_format: str) -> str:
    """파일 형식 아이콘 (PDF·DOCX·PPT·DART). 검색 결과·문서 목록·원문 보기 제목 앞에 둔다."""
    label = FILE_TYPE_LABELS.get(file_format, (file_format or "").upper())
    css = f"sh-file-{file_format}" if file_format in FILE_TYPE_LABELS else ""
    return f'<span class="sh-file {css}">{html.escape(label)}</span>'


def stat_card_html(label: str, value: int | str, note: str | None = None, tone: str | None = None) -> str:
    """현황 카드 안쪽 HTML. tone("ok"·"wait"·"bad")을 주면 이름 앞에 색 점을 붙인다."""
    dot = f'<span class="sh-dot sh-dot-{tone}"></span>' if tone in _TONE_MARK else ""
    shown = f"{value:,}" if isinstance(value, int) else str(value)
    note_html = f'<div class="sh-muted">{html.escape(note)}</div>' if note else ""
    return (
        f'<div class="sh-stat-label">{dot}{html.escape(label)}</div>'
        f'<div class="sh-stat-value">{html.escape(shown)}</div>{note_html}'
    )


def stat_card(label: str, value: int | str, note: str | None = None, tone: str | None = None) -> None:
    """현황 카드 1개 (UI v4 관리 화면 위쪽: 전체 문서 48 / 색인 실패 1 등).

    여러 개는 st.columns로 나란히 둔다:
        for col, (label, value) in zip(st.columns(4), items):
            with col:
                stat_card(label, value)
    """
    with st.container(border=True):
        st.html(stat_card_html(label, value, note, tone))


def text_html(text: str, *, bold: bool = False, muted: bool = False) -> str:
    """문서에서 온 글자를 Markdown·HTML 해석 없이 보여 줄 HTML. 줄바꿈은 유지한다."""
    css = "sh-text sh-muted" if muted else "sh-text"
    body = html.escape(text)
    return f'<div class="{css}">{f"<b>{body}</b>" if bold else body}</div>'


def show_text(text: str, *, bold: bool = False, muted: bool = False) -> None:
    """문서 제목·파일명·본문 미리보기를 그대로 표시한다. st.markdown·st.caption·st.write 대신 쓴다."""
    st.html(text_html(text, bold=bold, muted=muted))


def source_line(company_code: str, access_level: str, title: str, location: str = "") -> None:
    """출처 한 줄: [회사] [보안 등급] 제목, 위치. 검색 결과·출처·각주 목록에서 같이 쓴다."""
    meta = f' <span class="sh-muted">{html.escape(location)}</span>' if location else ""
    st.html(
        f"<div>{company_tag_html(company_code)} {security_badge_html(access_level)} "
        f"<b>{html.escape(title)}</b>{meta}</div>"
    )


def no_permission_notice(title: str, company_name: str, key: str) -> bool:
    """권한 없는 문서 안내 (S-05·M-03). 제목은 보여 주고 본문은 보여 주지 않는다.

    반환: [열람 권한 요청] 버튼을 눌렀으면 True. key는 화면 안에서 겹치지 않게 doc_id 등으로 준다.
    """
    with st.container(border=True):
        st.html(f"<div>🔒 <b>{html.escape(title)}</b></div>")
        show_text(f"{company_name} 문서라 내 권한으로는 내용을 볼 수 없습니다. 답변 근거에서도 뺐습니다.", muted=True)
        return st.button("열람 권한 요청", key=f"request-{key}")


def empty_state(message: str) -> None:
    """결과가 없을 때. 무엇을 하면 되는지 한 문장으로 쓴다 (예: "다른 검색어로 찾아보세요.")."""
    st.info(message)
