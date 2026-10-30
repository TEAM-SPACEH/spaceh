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

# config.toml의 enableStaticServing으로 static/ 폴더가 app/static/ 주소로 나간다.
LOCK_ICON_URL = "app/static/icons/lock.svg"

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
/* S-04 답변 카드 (Figma 02): 연초록 바탕, 연초록 테두리 + 왼쪽 4px 초록 */
.st-key-s61_rag_card{background:#F8FCFA;border:1px solid #BFE5CE!important;border-left:4px solid #009944!important;
  border-radius:12px;box-shadow:0 1px 2px rgba(16,24,40,.04),0 2px 6px rgba(16,24,40,.06)}
.sh-rag-header{display: flex; align-items: center; gap: 10px; margin-bottom: 12px;}
.sh-rag-title{font-size: 16px; font-weight: 700; color: #111111;}
.sh-rag-meta{font-size: 12px; color: #6B7280;}
.sh-rag-body{font-size: 14px; line-height: 1.75; color: #343A40; white-space: pre-wrap; overflow-wrap: anywhere;}
.sh-rag-footer{margin-top: 14px; font-size: 12px; color: #6B7280;}
.sh-rag-sources{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px}
.sh-rag-src{display:inline-flex;align-items:center;gap:6px;padding:3px 8px 3px 4px;background:#FFFFFF;
  border:1px solid #D3EEDD;border-radius:6px;font-size:12px;color:#343A40}
.sh-rag-src .sh-cite{margin-left:0}
.sh-rag-copy{margin-left: auto; padding: 5px 10px; border: 1px solid #DEE2E6; border-radius: 8px; background: #FFFFFF; color: #343A40; font-size: 12px; font-weight: 600; cursor: pointer;}
.sh-rag-copy:hover{background: #F8F9FA; border-color: #ADB5BD;}
.sh-s61-source-title{display:flex;align-items:baseline;font-size: 16px; font-weight: 700; color: #111111; margin: 0 0 12px;}
.sh-s61-source-title span{margin-left:auto;font-size:12px;font-weight:400;color:#6B7280}
/* 출처 카드의 [원문] 버튼은 오른쪽 끝 파란 링크 모양 */
[class*="st-key-sh-card-s61_source"] .stButton{display:flex;justify-content:flex-end}
[class*="st-key-sh-card-s61_source"] .stButton button{color:#004098;font-size:12px;min-height:0;padding:12px 0 0}
[class*="st-key-sh-card-s61_source"] .stButton button p{font-size:12px}
.sh-s61-source-header{display: flex; align-items: center; gap: 7px; font-size: 13px; color: #111111;}
.sh-s61-source-count{margin-left: auto; font-size: 12px; color: #6B7280;}
.sh-s61-source-entry{display: flex; align-items: center; gap: 7px; margin-top: 14px;}
.sh-s61-source-file{font-size: 13px; font-weight: 600; color: #111111; overflow-wrap: anywhere;}
.sh-s61-source-location{margin: 5px 0 8px 27px; font-size: 12px; color: #6B7280;}
.sh-s61-results{background:#FFFFFF;border:1px solid #E5E8EB;border-radius:12px;overflow:hidden;
  box-shadow:0 1px 2px rgba(16,24,40,.04),0 2px 6px rgba(16,24,40,.06)}
.sh-s61-results-header{display:flex;align-items:center;gap:8px;padding:16px 18px;font-size:16px;border-bottom:1px solid #E9ECEF;}
.sh-s61-results-header span{font-size:12px;color:#6B7280;}
.sh-s61-results-sort{margin-left:auto;}
.sh-s61-result-row{display:grid;grid-template-columns:42px minmax(0,1fr) 80px;gap:12px;padding:14px 18px;border-bottom:1px solid #F1F3F5;align-items:start;}
.sh-s61-result-row:last-child{border-bottom:none;}
.sh-s61-result-type{background:#F1F3F5;color:#495057;border-radius:6px;padding:6px 4px;font-size:10px;font-weight:700;text-align:center;}
.sh-s61-result-name{font-size:15px;font-weight:700;color:#111111;overflow-wrap:anywhere;}
.sh-s61-result-name .sh-tag{margin-left:6px;vertical-align:1px}
.sh-s61-result-preview{font-size:14px;line-height:1.5;color:#343A40;margin-top:6px;overflow-wrap:anywhere;}
.sh-s61-result-date{font-size:12px;color:#6B7280;text-align:right;}
.sh-type-pdf{background:#FFF5F5;color:#E03131}
.sh-type-dart{background:#EBFBEE;color:#2B8A3E}
.sh-type-doc,.sh-type-docx{background:#E7F5FF;color:#1971C2}
.sh-type-ppt,.sh-type-pptx{background:#FFF4E6;color:#D9480F}
/* S-07 이어서 묻기: 둥근 알약 버튼 */
.st-key-s61_followup_row{gap:8px;justify-content:flex-start}
.st-key-s61_followup_row>[data-testid="stElementContainer"]{flex:0 0 auto;width:auto}
.st-key-s61_followup_row [data-testid="stCaptionContainer"]{margin-right:4px}
.st-key-s61_followup_row .stButton button{border-radius:16px;min-height:0;padding:5px 12px;background:#FFFFFF;border-color:#DEE2E6}
.st-key-s61_followup_row .stButton button p{font-size:13px}
/* M-03 권한 없는 문서 카드 (Figma 02 출처 칸) */
.sh-np-head{display:flex;align-items:baseline;gap:8px;font-size:14px;color:#111111}
.sh-np-head span{margin-left:auto;font-size:12px;color:#6B7280}
.sh-np-title{display:flex;align-items:center;gap:6px;margin-top:8px;font-size:14px;font-weight:600;color:#111111}
.sh-np-note{margin-top:2px;padding-left:20px;font-size:12px;color:#6B7280}
/* A-04 감사 로그 (Figma 10) */
.st-key-sh-card-audit-summary [data-testid="stMetricValue"]{font-size:26px;font-weight:700}
.st-key-sh-card-audit-summary [data-testid="stMetricDelta"]{background:transparent;padding:0;font-size:12px;color:#6B7280}
.st-key-sh-card-audit-summary [data-testid="stColumn"]:nth-child(2) [data-testid="stMetricValue"]{color:#E03131}
.st-key-sh-card-audit-summary [data-testid="stColumn"]:nth-child(4) [data-testid="stMetricValue"]{font-size:14px;font-weight:400;color:#6B7280}
.st-key-audit-filter-row [data-testid="stHorizontalBlock"]{align-items:center;gap:8px}
.st-key-audit-filter-row [data-testid="stColumn"]{flex:0 0 auto;width:auto;min-width:0}
.st-key-audit-filter-row [data-testid="stColumn"]:last-child{margin-left:auto}
.st-key-audit-head{background:#F8F9FA;border-top:1px solid #E9ECEF;border-bottom:1px solid #E9ECEF;
  margin:0 -17px;padding:8px 17px;width:calc(100% + 34px)!important;max-width:none}
[class*="st-key-audit-row-"]{border-bottom:1px solid #F1F3F5;margin:0 -17px;padding:4px 17px;width:calc(100% + 34px)!important;max-width:none}
[class*="st-key-audit-row-"] .sh-text,[class*="st-key-audit-row-"] .stHtml{font-size:14px}
.st-key-sh-card-audit-detail h3{font-size:18px;padding-top:0}
.st-key-audit-pager{gap:12px}
/* M-03 내 권한 요청 팝업 (Figma 15)의 문서 상자 */
.sh-req-doc{background:#F4F6F8;border-radius:10px;padding:12px 14px}
.sh-req-title{margin-top:6px;font-size:15px;font-weight:700;color:#111111;overflow-wrap:anywhere}
.sh-req-note{margin-top:2px;font-size:12px;color:#6B7280}
/* S-01 사이드바 최근 질문: 메뉴 아래 작은 글자 줄 */
.st-key-s61_recent{gap:0}
.st-key-s61_recent .stButton button{justify-content:flex-start;min-height:0;padding:6px 10px;color:#343A40;width:100%}
.st-key-s61_recent .stButton button>div{justify-content:flex-start;max-width:100%}
.st-key-s61_recent .stButton button p{font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sh-recent-title{padding:14px 10px 4px;font-size:11px;font-weight:600;color:#6B7280}
/* S-01 검색 상자 (Figma 02·02-0): 흰 카드 안 입력칸은 테두리 없이 크게 */
.st-key-sh-card-search-box [data-testid="stTextInputRootElement"]{background:#FFFFFF;border-color:transparent}
.st-key-sh-card-search-box input{font-size:16px}
/* S-01 초기 화면 (Figma 02-0): 인사말과 검색 상자를 화면 가운데쯤에 둔다 */
.stMainBlockContainer:has(.st-key-search-hero){padding-top:22vh}
/* S-02 필터 버튼 줄: 칸을 비율로 나누지 않고 글자 폭만큼 두어 "계열…"처럼 잘리지 않게 한다 */
.st-key-sh-card-search-box [data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]),
.st-key-search-top [data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] [data-testid="stPopover"]){flex-wrap:wrap}
.st-key-sh-card-search-box [data-testid="stColumn"]:has([data-testid="stPopover"]),
.st-key-search-top [data-testid="stColumn"]:has([data-testid="stPopover"]){flex:0 0 auto;width:auto;min-width:0}
.sh-hero-title{font-size:32px;font-weight:700;line-height:1.3;color:#111111}
.sh-hero-title b{color:#007A36}
.sh-hero-sub{font-size:26px;font-weight:700;line-height:1.4;color:#343A40;margin-top:4px}
.sh-hero-desc{font-size:14px;color:#6B7280;margin-top:8px}
/* S-05 원문 보기 (Figma 03): 왼쪽 쪽 미리보기 112 · 가운데 원문 · 오른쪽 문서 정보 340 */
.st-key-s05_viewer [data-testid="stHorizontalBlock"]{gap:0;align-items:stretch}
[data-testid="stColumn"]:has(.st-key-s05_thumbs){flex:0 0 112px;width:112px;min-width:112px;padding:16px 18px}
[data-testid="stColumn"]:has(.st-key-s05_page_area){padding:18px 32px}
[data-testid="stColumn"]:has(.st-key-s05_info){flex:0 0 340px;width:340px;min-width:340px;background:#FFFFFF;
  border-left:1px solid #E9ECEF;padding:22px}
.st-key-s05_thumbs{align-items:center;gap:12px}
.sh-v-thumb-count{font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-v-thumb-no{font-size:12px;line-height:18.6px;font-weight:700;color:#007A36;letter-spacing:-.1px}
.st-key-s05_thumbs>*{width:100%}
.sh-v-thumb-count,.sh-v-thumb-no{text-align:center}
[data-testid="stLayoutWrapper"]:has(>[class*="st-key-s05_thumb_"]){display:flex;justify-content:center}
[class*="st-key-s05_thumb_"]{flex:none;width:64px;height:84px;box-sizing:border-box;background:#FFFFFF;border:1px solid #E9ECEF;
  border-radius:2px;overflow:hidden;gap:0}
.st-key-s05_thumb_current{border:2px solid #DEE2E6}
[class*="st-key-s05_thumb_"] img{display:block;width:100%;height:100%;object-fit:cover;object-position:top}
.st-key-s05_page_area{gap:14px}
.st-key-s05_toolbar{align-items:center;justify-content:space-between;gap:8px;flex-wrap:nowrap}
.st-key-s05_zoom{align-items:center;gap:8px;flex:0 0 auto;width:auto}
.st-key-s05_toolbar>*,.st-key-s05_zoom>*{flex:0 0 auto;width:auto}
[data-testid="stLayoutWrapper"]:has(>.st-key-s05_zoom){flex:0 0 auto;width:auto;margin-left:auto}
.st-key-s05_back{width:fit-content;flex:0 0 auto;align-self:flex-start}
.st-key-s05_back button{min-height:0;height:20px;padding:0;gap:8px;justify-content:flex-start;color:#004098;font-size:12px;letter-spacing:-.1px;background:transparent;border:none}
.st-key-s05_back button::before{content:"";width:14px;height:14px;flex:none;background:url("app/static/icons/arrow-left.svg") center/contain no-repeat}
.st-key-s05_back button p{font-size:12px;line-height:18.6px}
.st-key-s05_back button:hover{text-decoration:underline;background:transparent}
.st-key-s05_zoom_out,.st-key-s05_zoom_in{width:auto;flex:0 0 auto}
.st-key-s05_zoom_out button,.st-key-s05_zoom_in button{min-height:30px;height:30px;padding:0 10px;background:#FFFFFF;border:1px solid #CED4DA;
  border-radius:8px;color:#111111}
.st-key-s05_zoom_out button p,.st-key-s05_zoom_in button p{font-size:12.5px;font-weight:700;line-height:19.4px}
.sh-v-zoom{display:flex;align-items:center;justify-content:center;width:44px;height:30px;font-size:12px;line-height:18.6px;color:#343A40;letter-spacing:-.1px}
.st-key-s05_page{background:#FFFFFF;border:1px solid #E9ECEF;border-radius:2px;padding:56px 72px;gap:14px;
  width:720px;max-width:100%;margin:0 auto;overflow-x:auto;min-height:640px}
.st-key-s05_page [data-testid="stImage"],.st-key-s05_page [data-testid="stImageContainer"],.st-key-s05_page img{max-width:none!important}
.sh-v-page-head{display:flex;justify-content:space-between;font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-v-para{font-size:14px;line-height:24.5px;color:#111111;letter-spacing:-.1px;white-space:pre-wrap;overflow-wrap:anywhere}
.sh-v-para-hl{background:rgba(250,190,0,.2);padding:10px 14px}
.sh-v-info-head{display:flex;gap:8px;align-items:center}
.sh-v-type{display:flex;align-items:flex-end;justify-content:center;flex:none;width:30px;height:34px;padding-bottom:5px;
  border-radius:4px;box-sizing:border-box;font-size:9px;line-height:13.95px;font-weight:700;letter-spacing:.2px}
.sh-v-type-pdf{background:#FFF5F5;color:#C92A2A}
.sh-v-type-docx{background:#E7F5FF;color:#1971C2}
.sh-v-type-pptx{background:#FFF4E6;color:#D9480F}
.sh-v-type-dart_xml{background:#EBFBEE;color:#2B8A3E}
.sh-v-tags{display:flex;gap:8px;align-items:center}
.sh-v-tags .sh-tag{display:inline-flex;align-items:center;height:22px;padding:0 7px;border-radius:6px;font-size:11.5px;line-height:17.8px}
.sh-v-tags .sh-co{letter-spacing:.2px}
.sh-v-title{padding-top:10px;font-size:17px;line-height:26.35px;font-weight:700;color:#111111;letter-spacing:-.3px;overflow-wrap:anywhere}
.sh-v-sub{font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-v-section{display:flex;flex-direction:column;gap:8px}
.sh-v-section-title{font-size:12px;line-height:18.6px;font-weight:700;color:#343A40;letter-spacing:-.1px}
.sh-v-answer{display:flex;flex-direction:column;border:1px solid #E9ECEF;border-radius:6px;padding:12px}
.sh-v-answer-head{display:flex;gap:8px;align-items:center;font-size:12px;line-height:18.6px;font-weight:700;color:#111111}
.sh-v-answer-head .sh-cite{margin-left:0;flex:none;width:19px;box-sizing:border-box;padding:0 4px;font-size:10.5px;line-height:18px}
.sh-v-answer-sub{padding-top:4px;font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px;overflow-wrap:anywhere}
.sh-v-rows{display:flex;flex-direction:column;gap:9px}
.sh-v-row{display:flex;justify-content:space-between;gap:12px;font-size:12px;line-height:18.6px;letter-spacing:-.1px}
.sh-v-row span:first-child{color:#6B7280;flex:none}
.sh-v-row span:last-child{color:#111111;text-align:right;overflow-wrap:anywhere}
.st-key-s05_info{gap:20px;height:100%}
.st-key-s05_download{margin-top:auto;gap:8px}
.st-key-s05_download [data-testid="stDownloadButton"] button{width:100%;min-height:36px;height:36px;padding:0 14px;gap:6px;background:#FFFFFF;
  border:1px solid #DEE2E6;border-radius:8px;color:#007A36}
.st-key-s05_download [data-testid="stDownloadButton"] button::before{content:"";width:15px;height:15px;flex:none;
  background:url("app/static/icons/download.svg") center/contain no-repeat}
.st-key-s05_download [data-testid="stDownloadButton"] button p{font-size:13.5px;font-weight:700;line-height:20.9px;letter-spacing:-.1px}
.sh-v-note{font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
/* R-01 새 보고서 (Figma 04): 왼쪽 세 단계 입력 카드 · 오른쪽 380 근거 문서·목차·만들기 */
.sh-r-crumb{font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-r-title{padding-top:2px;font-size:28px;line-height:31.2px;font-weight:700;color:#111111;letter-spacing:-.5px}
.sh-r-desc{padding-top:3px;font-size:14px;line-height:21.7px;color:#343A40;letter-spacing:-.1px}
[data-testid="stColumn"]:has(.st-key-r01_side){flex:0 0 380px;width:380px;min-width:380px}
.stVerticalBlock.st-key-sh-card-r01_form{padding:24px 28px;gap:26px}
.stVerticalBlock.st-key-sh-card-r01_evidence{padding:20px}
.stVerticalBlock.st-key-sh-card-r01_outline{padding:18px 20px}
.st-key-r01_side{gap:14px}
[class*="st-key-r01_step"]{padding-left:40px;gap:12px}
.sh-r-step-head{position:relative;font-size:16px;line-height:23.25px;font-weight:700;color:#111111;letter-spacing:-.2px}
.sh-r-no{position:absolute;left:-40px;top:-1px;display:flex;align-items:center;justify-content:center;width:26px;height:26px;
  border-radius:4px;background:#E6F4EA;color:#007A36;font-size:12px;line-height:18.6px;letter-spacing:-.1px}
.sh-r-sep{height:1px;background:#E9ECEF}
.sh-r-label{font-size:12.5px;line-height:19.4px;font-weight:700;color:#343A40;letter-spacing:-.1px}
.st-key-r01_topic [data-testid="stTextInputRootElement"]{height:42px;background:#FFFFFF;border:1px solid #CED4DA;border-radius:8px}
.st-key-r01_topic input{padding:0 11px;font-size:14.5px;letter-spacing:-.1px}
.st-key-r01_quick{align-items:center;justify-content:flex-start;gap:8px}
.st-key-r01_quick>*{flex:0 0 auto;width:auto}
.sh-r-quick-label{font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px;white-space:nowrap}
.st-key-r01_quick .stButton{width:auto;flex:0 0 auto}
.st-key-r01_quick button{min-height:30px;height:30px;padding:0 11px;background:#FFFFFF;border:1px solid #DEE2E6;border-radius:15px;color:#111111}
.st-key-r01_quick button p{font-size:12.5px;line-height:19.4px;letter-spacing:-.1px}
.st-key-r01_companies [data-testid="stButtonGroup"]{gap:8px;flex-wrap:wrap}
.st-key-r01_companies button{min-height:30px;height:30px;padding:0 11px;gap:6px;background:#FFFFFF;border:1px solid #DEE2E6;border-radius:15px;color:#111111}
.st-key-r01_companies button p{font-size:12.5px;line-height:19.4px;letter-spacing:-.1px}
.st-key-r01_companies button[data-selected="true"]{background:#F0FDF4;border-color:#B2DFC2;color:#007A36}
.st-key-r01_companies button[data-selected="true"] p{font-weight:700}
.st-key-r01_companies button[data-selected="true"]::before{content:"";width:13px;height:13px;flex:none;
  background:url("app/static/icons/chip-check.svg") center/contain no-repeat}
.st-key-r01_start label p,.st-key-r01_end label p{font-size:12.5px;line-height:19.4px;font-weight:700;color:#343A40;letter-spacing:-.1px}
/* 날짜 칸: 흰 바탕·회색 테두리, 달력 아이콘은 Streamlit 기본(오른쪽) 대신 Figma처럼 왼쪽에 둔다 */
.st-key-r01_start [data-testid="stDateInputField"],.st-key-r01_end [data-testid="stDateInputField"]{box-sizing:border-box;height:38px;
  padding-left:18px;background:#FFFFFF url("app/static/icons/calendar.svg") 11px center/15px 15px no-repeat;border:1px solid #CED4DA;border-radius:8px}
.st-key-r01_start [data-testid="stDateInputField"] svg,.st-key-r01_end [data-testid="stDateInputField"] svg{display:none}
.st-key-r01_start [data-testid="stDateInputField"] span,.st-key-r01_end [data-testid="stDateInputField"] span{font-size:14px;letter-spacing:-.1px;color:#111111}
[class*="st-key-r01_tpl_"]{width:100%}
[class*="st-key-r01_tpl_"] button{display:block;width:100%;height:auto;min-height:87px;padding:14px 16px;text-align:left;background:#FFFFFF;
  border:1px solid #DEE2E6;border-radius:6px;position:relative}
[class*="st-key-r01_tpl_"] button>div,[class*="st-key-r01_tpl_"] button span,[class*="st-key-r01_tpl_"] [data-testid="stMarkdownContainer"]{
  display:block;width:100%;text-align:left}
[class*="st-key-r01_tpl_"] [data-testid="stMarkdownContainer"]{height:auto;overflow:visible}
[class*="st-key-r01_tpl_"] button p{display:block;margin:0;font-size:12px;line-height:18.6px;font-weight:400;color:#343A40;letter-spacing:-.1px;text-align:left}
[class*="st-key-r01_tpl_"] button p:first-child{padding-bottom:4px;font-size:14px;line-height:21.7px;font-weight:700;color:#111111}
[class*="st-key-r01_tpl_"][class*="_on"] button{border-color:#E9ECEF;border-radius:10px}
[class*="st-key-r01_tpl_"][class*="_on"] button::after{content:"";position:absolute;top:14px;right:16px;width:16px;height:16px;
  background:url("app/static/icons/check.svg") center/contain no-repeat}
.sh-r-h{font-size:16px;line-height:23.25px;font-weight:700;color:#111111;letter-spacing:-.2px}
.sh-r-ev-head{display:flex;align-items:center;justify-content:space-between}
.sh-r-total{font-size:18px;line-height:27.9px;font-weight:700;color:#111111;letter-spacing:-.1px}
.sh-r-ev-desc{padding-top:2px;font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.3px}
.sh-r-ev-empty{padding-top:14px}
.sh-r-rows{display:flex;flex-direction:column;gap:14px;padding-top:18px}
.sh-r-co-top{display:flex;align-items:center;justify-content:space-between}
.sh-r-co-name{display:flex;align-items:center;gap:8px;font-size:12px;line-height:18.6px;color:#111111;letter-spacing:-.1px}
.sh-r-co-name .sh-tag{display:inline-flex;align-items:center;height:22px;padding:0 7px;border-radius:6px;font-size:11.5px;line-height:17.8px;letter-spacing:.2px}
.sh-r-co-count{font-size:12px;line-height:18.6px;color:#111111;letter-spacing:-.1px}
.sh-r-zero{color:#6B7280}
.sh-r-bar{height:6px;margin-top:7px;border-radius:3px;background:#F1F3F5;overflow:hidden}
.sh-r-bar i{display:block;height:6px;border-radius:3px;background:#009944}
.sh-r-warn{display:flex;gap:8px;align-items:flex-start;margin-top:16px;padding:10px 12px;border-radius:4px;background:#FFF9DB;
  font-size:12px;line-height:18.6px;color:#111111;letter-spacing:-.1px}
.sh-r-warn img{flex:none;margin-top:2px}
.sh-r-outline{display:flex;flex-direction:column;gap:7px;padding-top:10px;font-size:12px;line-height:18.6px;color:#343A40;letter-spacing:-.1px}
.st-key-r01_submit button{display:flex;align-items:center;justify-content:center;min-height:46px;height:46px;padding:0 14px;gap:6px;
  border:none;border-radius:8px;background:#009944;box-shadow:0 2px 3px rgba(0,153,68,.22)}
.st-key-r01_submit button>div{width:auto;flex:none}
.st-key-r01_submit button:hover:not(:disabled){background:#007A36}
.st-key-r01_submit button::before{content:"";width:16px;height:16px;flex:none;background:url("app/static/icons/chart-line.svg") center/contain no-repeat}
.st-key-r01_submit button p{font-size:15px;line-height:23.25px;font-weight:700;color:#FFFFFF;letter-spacing:-.1px}
.sh-r-note{text-align:center;font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
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
        st.html(
            f'<div class="sh-np-head"><b>{html.escape(company_name)}</b><span>열람 불가</span></div>'
            f'<div class="sh-np-title"><img src="{LOCK_ICON_URL}" width="14" height="14" alt="">'
            f"{html.escape(title)}</div>"
            f'<div class="sh-np-note">{html.escape(company_name)} 문서라 내 권한으로는 내용을 볼 수 없습니다. '
            "답변 근거에서도 뺐습니다.</div>"
        )
        # M-03 명세의 버튼 이름은 '내 권한 요청'이다.
        return st.button("내 권한 요청", key=f"request-{key}")


def empty_state(message: str) -> None:
    """결과가 없을 때. 무엇을 하면 되는지 한 문장으로 쓴다 (예: "다른 검색어로 찾아보세요.")."""
    st.info(message)
