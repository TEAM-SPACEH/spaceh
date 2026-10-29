"""공통 화면 요소. 모든 views는 반복되는 UI를 직접 만들지 말고 여기 함수를 부른다.

- 색·글꼴·둥글기는 .streamlit/config.toml 테마가 정한다. views에서 `<style>`을 넣지 않는다.
- 문서 제목·파일명·본문처럼 업로드한 사람이 정할 수 있는 값은 `st.markdown`·`st.caption`·`st.write`에
  넘기지 않는다. 이 함수들은 Markdown을 해석해 `[링크](https://…)`·`![이미지](…)`를 그대로 그린다.
  대신 `show_text()` 또는 `*_html()` + `st.html()`을 쓴다 (html.escape 후 Markdown 해석 없이 표시).
"""

import html

import streamlit as st

from core.constants import (
    ACCESS_CONFIDENTIAL,
    ACCESS_INTERNAL,
    ACCESS_PUBLIC,
    DOC_TYPE_DISCLOSURE,
    DOC_TYPE_INTRO,
    DOC_TYPE_MANUAL,
    DOC_TYPE_MEMO,
    DOC_TYPE_REPORT,
    DOC_TYPE_SPEC,
)

# 보안 등급 화면 이름과 배지 색 (design.md 2.3: 공개 그린, 사내 옐로, 기밀 빨강)
ACCESS_LABELS = {ACCESS_PUBLIC: "공개", ACCESS_INTERNAL: "사내", ACCESS_CONFIDENTIAL: "기밀"}
_ACCESS_CLASS = {ACCESS_PUBLIC: "sh-pub", ACCESS_INTERNAL: "sh-int", ACCESS_CONFIDENTIAL: "sh-con"}

# 문서 유형 화면 이름 (data-model.md 1장). 선택지 순서도 이 순서를 쓴다.
DOC_TYPE_LABELS = {
    DOC_TYPE_REPORT: "연구 보고서",
    DOC_TYPE_DISCLOSURE: "공시",
    DOC_TYPE_MANUAL: "매뉴얼",
    DOC_TYPE_SPEC: "사양서",
    DOC_TYPE_INTRO: "회사·제품 소개",
    DOC_TYPE_MEMO: "내부 메모",
}

_CSS = """
<style>
.sh-tag{display:inline-block;padding:1px 7px;border-radius:4px;font-size:12px;font-weight:600;line-height:20px;white-space:nowrap}
.sh-pub{background:#EBFBEE;color:#2B8A3E}
.sh-int{background:#FFF4CC;color:#7A5A00}
.sh-con{background:#FFF5F5;color:#E03131}
.sh-co{background:#F1F3F5;color:#343A40;font-weight:700}
.sh-cite{display:inline-block;min-width:19px;padding:0 4px;border-radius:9px;background:#E7F0FA;color:#004098;font-size:11px;font-weight:700;line-height:18px;text-align:center;margin-left:3px}
.sh-hl{background:rgba(250,190,0,0.24);border-radius:2px;padding:0 2px}
.sh-muted{color:#6B7280;font-size:13px}
.sh-text{white-space:pre-wrap;line-height:1.6}
.stVerticalBlock[class*="st-key-sh-card-"]{background:#FFFFFF;border:1px solid #E5E8EB!important;border-radius:12px;
  box-shadow:0 1px 2px rgba(16,24,40,.04),0 2px 6px rgba(16,24,40,.06)}
[role="dialog"],[data-testid="stPopoverBody"]{background:#FFFFFF}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker){font-family:"NeoHyundai","Segoe UI",sans-serif;font-size:14px;line-height:1.6;color:#111111}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) input,[data-testid="stDialog"]:has(.sh-upload-dialog-marker) textarea,[data-testid="stDialog"]:has(.sh-upload-dialog-marker) button{font:inherit}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) [data-testid="stMarkdownContainer"]{font-family:"NeoHyundai","Segoe UI",sans-serif;font-size:14px;line-height:1.6;color:#111111}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) button [data-testid="stMarkdownContainer"]{color:inherit}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) h2{font-size:18px;line-height:1.4;font-weight:600}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) [data-testid="stCaptionContainer"]{font-size:12px;line-height:1.5;color:#626B73}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) .stButton>button{border-radius:4px;font-weight:600;padding:8px 16px;transition:background-color .2s}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) .stButton>button[kind="primary"]{background:#007A36;color:#FFFFFF;border:1px solid transparent}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) .stButton>button[kind="primary"]:hover:not(:disabled){background:#005C29}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) .stButton>button[kind="primary"]:active:not(:disabled){background:#00451F}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) .stButton>button[kind="secondary"]{background:#FFFFFF;color:#007A36;border:1px solid #009944}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) .stButton>button[kind="secondary"]:hover:not(:disabled){background:#F0FDF4}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) .stButton>button[kind="tertiary"]{background:transparent;color:#004098;border:none}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) .stButton>button[kind="tertiary"]:hover:not(:disabled){text-decoration:underline}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker) .stButton>button:disabled{opacity:.5}
[class*="st-key-upload-document-card-"]{border:1px solid #E9ECEF!important;border-radius:6px;padding:10px 12px;margin-bottom:0}
[class*="st-key-upload-document-card-"]:hover{border-color:#009944!important;box-shadow:0 2px 8px rgba(0,153,68,.08)}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker)>div{width:560px!important;min-width:0!important;
  max-width:calc(100vw - 32px)!important;box-sizing:border-box}
[role="dialog"]:has(.sh-upload-dialog-marker){width:100%!important;min-width:0;max-width:100%;box-sizing:border-box;
  max-height:calc(100dvh - 32px);overflow-y:auto;background:#FFFFFF;border:1px solid #E9ECEF;border-radius:8px}
[role="dialog"]:has(.sh-upload-dialog-marker)>[slot="title"]{padding:16px 20px 8px!important;font-size:18px}
[role="dialog"]:has(.sh-upload-dialog-marker)>div:last-child{padding:0 20px 12px!important}
[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stLayoutWrapper"],
[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stVerticalBlock"],
[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stHorizontalBlock"]{min-width:0;max-width:100%;box-sizing:border-box}
[role="dialog"]:has(.sh-upload-dialog-marker) .sh-text{overflow-wrap:anywhere}
[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stVerticalBlock"]{gap:6px}
[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stLayoutWrapper"]:has(>.stElementContainer .sh-upload-dialog-marker){display:none}
[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stElementContainer"]:has(.sh-upload-dialog-marker){display:none}
[role="dialog"]:has(.sh-upload-dialog-marker) h2{margin:0;padding-bottom:8px}
[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stMarkdownContainer"] p{margin-bottom:0}
[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stCaptionContainer"]{margin:0}
[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stCaptionContainer"] p{font-size:12px;line-height:1.4}
.st-key-upload-file-list{scrollbar-gutter:stable}
.st-key-upload-section-heading{padding:8px 0 6px;margin:0;min-height:32px;box-sizing:border-box}
.st-key-upload-section-heading p{font-size:14px;line-height:20px;margin:0!important}
.st-key-upload-company [data-testid="stWidgetLabel"],
.st-key-upload-access [data-testid="stWidgetLabel"]{min-height:20px;margin:0 0 6px;padding:0}
.st-key-upload-company [data-testid="stWidgetLabel"] p,
.st-key-upload-access [data-testid="stWidgetLabel"] p{font-size:12px;line-height:20px;margin:0}
[class*="st-key-upload-document-card-"] [data-testid="stVerticalBlock"]{gap:4px!important}
[class*="st-key-upload-document-card-"] .stButton>button{min-width:24px;min-height:24px;padding:0;line-height:20px}
.st-key-upload-footer{position:sticky;bottom:0;z-index:2;background:#FFFFFF;padding:8px 0 0}
.st-key-upload-footer hr{margin:0 0 8px}
.st-key-upload-footer .sh-muted{font-size:12px;color:#626B73}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]{background:#F8F9FA;border:1px dashed #009944;
  border-radius:6px;padding:8px 12px;min-height:104px;min-width:0;width:100%;box-sizing:border-box;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]::before{content:"↑";display:grid;place-items:center;
  width:28px;height:28px;border-radius:50%;background:#E6F4EA;color:#009944;font-size:20px;font-weight:700}
.st-key-upload-picker [data-testid="stFileUploaderDropzoneInstructions"]{display:none}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]>span>button{background:transparent;border:none;color:#004098}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]>span>button>*{display:none}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]>span>button::after{content:"내 컴퓨터에서 파일 선택";font-size:14px;font-weight:600}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]::after{content:"파일을 여기로 끌어 놓으세요";order:1;text-align:center;font-size:14px;font-weight:700}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]>span{order:2}
.st-key-upload-file-heading{margin:4px 0 0;padding:0}
.st-key-upload-file-heading .stButton>button{min-height:24px;padding:0;line-height:20px}
.st-key-upload-file-heading p{margin:0!important;font-size:13px;line-height:20px}
.st-key-upload-file-heading .sh-text{font-size:13px;line-height:24px}
.st-key-upload-permission-note{padding:10px 12px;margin:4px 0;background:#F8F9FA;border-radius:4px}
.st-key-upload-permission-note .sh-text{word-break:keep-all;overflow-wrap:break-word;font-size:12px;line-height:20px;white-space:pre-line}
.st-key-upload-registration [data-testid="stExpanderDetails"]{padding:12px}
.st-key-upload-registration [data-testid="stVerticalBlock"]{gap:10px!important}
.st-key-upload-registration [data-testid="stCaptionContainer"] p{margin:0!important;font-size:12px;line-height:18px}
.st-key-upload-registration [data-testid="stWidgetLabel"]{margin-bottom:4px;min-height:20px}
.sh-upload-status{display:flex;align-items:center;gap:8px;box-sizing:border-box;min-height:36px;
  padding:8px 12px;border-radius:4px;font-family:"NeoHyundai","Segoe UI",sans-serif;font-size:13px;line-height:20px}
.sh-upload-status>span{display:block;margin:0;padding:0;line-height:20px;overflow-wrap:anywhere}
.sh-upload-status-busy{background:#F8F9FA;color:#495057}
.sh-upload-status-done{background:#EBFBEE;color:#237032}
.sh-upload-status-duplicate{background:#FFF9DB;color:#7A5A00}
.sh-upload-status-failed{background:#FFF5F5;color:#C92A2A}
.sh-upload-status .sh-upload-spinner{flex:0 0 14px;width:14px;height:14px;box-sizing:border-box;
  border:2px solid #CED4DA;border-top-color:#009944;border-radius:50%;animation:sh-upload-spin .8s linear infinite}
@keyframes sh-upload-spin{to{transform:rotate(360deg)}}
@media(prefers-reduced-motion:reduce){.sh-upload-status .sh-upload-spinner{animation:none}}
@media(max-height:750px){
  .st-key-upload-picker [data-testid="stFileUploaderDropzone"]{min-height:88px;padding:6px 12px}
  .st-key-upload-picker [data-testid="stFileUploaderDropzone"]::before{display:none}
}
.st-key-s61_rag_card{border-left: 3px solid #009944 !important;}
.sh-rag-header{display: flex; align-items: center; gap: 10px; margin-bottom: 12px;}
.sh-rag-title{font-size: 15px; font-weight: 700; color: #111111;}
.sh-rag-meta{font-size: 12px; color: #868E96;}
.sh-rag-body{font-size: 14px; line-height: 1.75; color: #212529; white-space: pre-wrap; overflow-wrap: anywhere;}
.sh-rag-footer{margin-top: 14px; font-size: 12px; color: #868E96;}
.sh-rag-copy{margin-left: auto; padding: 5px 10px; border: 1px solid #DEE2E6; border-radius: 4px; background: #FFFFFF; color: #343A40; font-size: 12px; font-weight: 600; cursor: pointer;}
.sh-rag-copy:hover{background: #F8F9FA; border-color: #ADB5BD;}
.sh-s61-source-title{font-size: 15px; font-weight: 700; color: #111111; margin: 0 0 12px;}
.sh-s61-source-header{display: flex; align-items: center; gap: 7px; font-size: 12px; color: #212529;}
.sh-s61-source-count{margin-left: auto; font-size: 11px; color: #868E96;}
.sh-s61-source-entry{display: flex; align-items: center; gap: 7px; margin-top: 14px;}
.sh-s61-source-file{font-size: 13px; font-weight: 600; color: #212529; overflow-wrap: anywhere;}
.sh-s61-source-location{margin: 5px 0 8px 27px; font-size: 12px; color: #868E96;}
.sh-s61-results{background:#FFFFFF;border:1px solid #E9ECEF;border-radius:6px;overflow:hidden;}
.sh-s61-results-header{display:flex;align-items:center;gap:8px;padding:14px 16px;font-size:14px;border-bottom:1px solid #E9ECEF;}
.sh-s61-results-header span{font-size:12px;color:#868E96;}
.sh-s61-results-sort{margin-left:auto;}
.sh-s61-result-row{display:grid;grid-template-columns:42px minmax(0,1fr) 80px;gap:10px;padding:14px 12px;border-bottom:1px solid #F1F3F5;align-items:start;}
.sh-s61-result-row:last-child{border-bottom:none;}
.sh-s61-result-type{background:#F1F3F5;color:#495057;border-radius:4px;padding:4px;font-size:10px;font-weight:700;text-align:center;}
.sh-s61-result-name{font-size:13px;font-weight:600;color:#212529;overflow-wrap:anywhere;}
.sh-s61-result-preview{font-size:12px;line-height:1.5;color:#868E96;margin-top:6px;overflow-wrap:anywhere;}
.sh-s61-result-date{font-size:11px;color:#868E96;text-align:right;}
</style>
"""


def apply_theme() -> None:
    """공통 배지와 A-01 업로드 전용 스타일을 적용한다. main.py에서만 부른다."""
    st.markdown(_CSS, unsafe_allow_html=True)


def upload_status_html(message: str, status: str) -> str:
    """A-01 상태 문구를 Markdown 없이 같은 행 높이와 수직 중앙 정렬로 표시한다."""
    if status not in {"busy", "done", "duplicate", "failed"}:
        raise ValueError("지원하지 않는 업로드 상태입니다.")
    role = "alert" if status == "failed" else "status"
    spinner = '<span class="sh-upload-spinner" aria-hidden="true"></span>' if status == "busy" else ""
    return (f'<div class="sh-upload-status sh-upload-status-{status}" role="{role}">'
            f'{spinner}<span>{html.escape(message)}</span></div>')


def page_header(title: str, description: str | None = None) -> None:
    """페이지 맨 위 제목과 한 줄 설명. 모든 페이지는 이것으로 시작한다."""
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


def card(key: str):
    """연회색 본문 위의 흰 카드. `with card("search-answer"):` 안에서 내용을 그린다.

    st.container(border=True)는 바탕이 투명해 본문 회색이 그대로 보이므로 카드는 이 함수로 만든다.
    key는 화면 안에서 겹치지 않게 준다.
    """
    return st.container(border=True, key=f"sh-card-{key}")


def no_permission_notice(title: str, company_name: str, key: str) -> bool:
    """권한 없는 문서 안내 (S-05·M-03). 제목은 보여 주고 본문은 보여 주지 않는다.

    반환: [열람 권한 요청] 버튼을 눌렀으면 True. key는 화면 안에서 겹치지 않게 doc_id 등으로 준다.
    """
    with card(f"no-permission-{key}"):
        st.html(f"<div>🔒 <b>{html.escape(title)}</b></div>")
        show_text(f"{company_name} 문서라 내 권한으로는 내용을 볼 수 없습니다. 답변 근거에서도 뺐습니다.", muted=True)
        return st.button("열람 권한 요청", key=f"request-{key}")


def empty_state(message: str) -> None:
    """결과가 없을 때. 무엇을 하면 되는지 한 문장으로 쓴다 (예: "다른 검색어로 찾아보세요.")."""
    st.info(message)
