"""공통 화면 요소. 모든 views는 반복되는 UI를 직접 만들지 말고 여기 함수를 부른다.

- 색·글꼴·둥글기는 .streamlit/config.toml 테마가 정한다. views에서 `<style>`을 넣지 않는다.
- 문서 제목·파일명·본문처럼 업로드한 사람이 정할 수 있는 값은 `st.markdown`·`st.caption`·`st.write`에
  넘기지 않는다. 이 함수들은 Markdown을 해석해 `[링크](https://…)`·`![이미지](…)`를 그대로 그린다.
  대신 `show_text()` 또는 `*_html()` + `st.html()`을 쓴다 (html.escape 후 Markdown 해석 없이 표시).
"""

import html

import streamlit as st

from core.constants import ACCESS_CONFIDENTIAL, ACCESS_INTERNAL, ACCESS_PUBLIC

# 루트 design.md 2.3 기준. 기밀은 기존 권한 모델의 표시를 유지한다.
ACCESS_LABELS = {ACCESS_PUBLIC: "공개", ACCESS_INTERNAL: "사내", ACCESS_CONFIDENTIAL: "기밀"}
_ACCESS_CLASS = {ACCESS_PUBLIC: "sh-pub", ACCESS_INTERNAL: "sh-int", ACCESS_CONFIDENTIAL: "sh-con"}

_CSS = """
<style>
@font-face{font-family:"NeoHyundai";src:url("app/static/fonts/NeoHyundai-R.ttf") format("truetype");font-weight:400;font-display:swap}
@font-face{font-family:"NeoHyundai";src:url("app/static/fonts/NeoHyundai-B.ttf") format("truetype");font-weight:700;font-display:swap}
:root{--sh-font:"NeoHyundai","Segoe UI",sans-serif}
.stApp,.stApp [data-testid="stMarkdownContainer"],.stApp input,.stApp textarea,.stApp button,
[data-testid="stDialog"]{font-family:var(--sh-font);font-size:14px;line-height:1.6;color:#111111}
h1,h2,h3,h4{font-family:var(--sh-font)!important;color:#111111}
.stApp h1{font-size:22px;line-height:1.35;font-weight:700}
.stApp h2,[data-testid="stDialog"] h2{font-size:18px;line-height:1.4;font-weight:600}
.stApp h3,[data-testid="stDialog"] h3{font-size:15px;line-height:1.45;font-weight:500}
[data-testid="stCaptionContainer"]{font-size:12px;line-height:1.5;color:#868E96}
#MainMenu,footer{visibility:hidden}
[data-testid="stSidebarCollapsedControl"]{visibility:visible}
.stButton>button{border-radius:4px;font-weight:600;padding:8px 16px;transition:background-color .2s}
.stButton>button[kind="primary"]{background:#009944;color:#FFFFFF;border:1px solid transparent}
.stButton>button[kind="primary"]:hover:not(:disabled){background:#007A36}
.stButton>button[kind="primary"]:active:not(:disabled){background:#005C29}
.stButton>button[kind="secondary"]{background:#FFFFFF;color:#009944;border:1px solid #009944}
.stButton>button[kind="secondary"]:hover:not(:disabled){background:#F0FDF4}
.stButton>button[kind="tertiary"]{background:transparent;color:#004098;border:none}
.stButton>button[kind="tertiary"]:hover:not(:disabled){text-decoration:underline}
.stButton>button:disabled{opacity:.5}
[class*="st-key-upload-file-"]{border:1px solid #E9ECEF!important;border-radius:6px;padding:16px;margin-bottom:12px}
[class*="st-key-upload-file-"]:hover{border-color:#009944!important;box-shadow:0 2px 8px rgba(0,153,68,.08)}
[data-testid="stDialog"]:has(.sh-upload-dialog-marker)>div{width:560px!important;min-width:0!important;
  max-width:calc(100vw - 32px)!important;box-sizing:border-box}
[role="dialog"]:has(.sh-upload-dialog-marker){width:100%!important;min-width:0;max-width:100%;box-sizing:border-box;
  max-height:calc(100dvh - 32px);overflow-y:auto;background:#FFFFFF;border:1px solid #E9ECEF;border-radius:8px}
[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stLayoutWrapper"],
[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stVerticalBlock"],
[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stHorizontalBlock"]{min-width:0;max-width:100%;box-sizing:border-box}
[role="dialog"]:has(.sh-upload-dialog-marker) .sh-text{overflow-wrap:anywhere}
[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stVerticalBlock"]{gap:12px}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]{background:#F8F9FA;border:1px dashed #009944;
  border-radius:6px;padding:24px 16px;min-height:172px;min-width:0;width:100%;box-sizing:border-box;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]::before{content:"↑";display:grid;place-items:center;
  width:44px;height:44px;border-radius:50%;background:#E6F4EA;color:#009944;font-size:26px;font-weight:700}
.st-key-upload-picker [data-testid="stFileUploaderDropzoneInstructions"]{display:none}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"] button{background:transparent;border:none;color:#004098}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"] button>*{display:none}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"] button::after{content:"내 컴퓨터에서 파일 선택";font-size:14px;font-weight:600}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]::after{content:"파일을 여기로 끌어 놓으세요";order:1;text-align:center;font-size:14px;font-weight:700}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]>span{order:2}
.st-key-upload-company [role="radiogroup"],.st-key-upload-access [role="radiogroup"]{display:flex;gap:8px;flex-wrap:wrap}
.st-key-upload-company label[data-testid="stRadioOption"],
.st-key-upload-access label[data-testid="stRadioOption"]{padding:12px;border:1px solid #CED4DA;border-radius:6px;flex:1;min-width:100px;margin:0}
.st-key-upload-company label[data-selected="true"],
.st-key-upload-access label[data-selected="true"]{background:#F0FDF4;border-color:#009944}
.st-key-upload-company label:focus-within,.st-key-upload-access label:focus-within{outline:2px solid #004098;outline-offset:2px}
.st-key-upload-access [role="radiogroup"]{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));width:100%;gap:8px}
.st-key-upload-access [role="radiogroup"]>div{min-width:0;width:100%}
.st-key-upload-access label[data-testid="stRadioOption"]{display:flex;align-items:center;justify-content:center;
  min-width:0;width:100%;min-height:44px;box-sizing:border-box;padding:10px 8px}
.st-key-upload-access label[data-testid="stRadioOption"]>div{justify-content:center}
.st-key-upload-permission-note p{word-break:keep-all;overflow-wrap:break-word}
.sh-tag{display:inline-block;padding:1px 7px;border-radius:4px;font-size:12px;font-weight:600;line-height:20px;white-space:nowrap}
.sh-pub{background:#EBFBEE;color:#2B8A3E}
.sh-int{background:#E7F5FF;color:#1971C2}
.sh-con{background:#FFF5F5;color:#E03131}
.sh-co{background:#F1F3F5;color:#343A40;font-weight:700}
.sh-cite{display:inline-block;min-width:19px;padding:0 4px;border-radius:9px;background:#E7F5FF;color:#004098;font-size:11px;font-weight:700;line-height:18px;text-align:center;margin-left:3px}
.sh-hl{background:rgba(250,190,0,0.15);border-radius:2px;padding:0 2px}
.sh-muted{color:#868E96;font-size:12px}
.sh-text{white-space:pre-wrap;line-height:1.6}
</style>
"""


def apply_theme() -> None:
    """루트 design.md의 공통 타이포그래피·버튼·카드·배지를 적용한다."""
    st.markdown(_CSS, unsafe_allow_html=True)


def page_header(title: str, description: str | None = None) -> None:
    """페이지 맨 위 제목과 한 줄 설명. 모든 페이지는 이것으로 시작한다."""
    st.title(title)
    if description:
        st.caption(description)


def security_badge_html(access_level: str, *, is_own_company: bool | None = None) -> str:
    """소속 비교가 있으면 자사·타사 internal을 구분하고 알 수 없는 등급은 회색으로 표시한다."""
    label = ACCESS_LABELS.get(access_level, access_level)
    css = _ACCESS_CLASS.get(access_level, "sh-co")
    if access_level == ACCESS_INTERNAL and is_own_company is not None:
        label = "사내 · 자사" if is_own_company else "사내 · 타사"
        css = "sh-int" if is_own_company else "sh-con"
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
