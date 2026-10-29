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


# UI v4 화면별 스타일 (Figma 05~09). 화면마다 아래 상수 하나에만 CSS를 넣는다 (공통 스타일은 위 _CSS).
# 글꼴·색·모서리는 config.toml 테마와 위 _CSS 클래스(.sh-tag·.sh-cite·.sh-r-crumb/title/desc 등)를 먼저 쓴다.
_CSS_REPORT_VIEW = """
<style>
/* R-03·R-04·R-05 보고서 보기 (Figma 05): 목차 사이드바 · 제목/내려받기 · 탭 · 요약 카드 720 + 각주 330 */
.stMainBlockContainer:has(.st-key-rv_root){padding-left:32px;padding-right:32px;padding-bottom:22px}
.st-key-rv_root{gap:18px}
/* 사이드바: 일반 메뉴 대신 목차. 범위 안내 상자는 숨기고 사용자 칩을 목차 바로 아래에 둔다 */
[data-testid="stSidebar"]:has(.st-key-rv_toc) [data-testid="stSidebarNav"]{display:none}
/* 사이드바 기본 구조가 안쪽을 좌우 10px 더 띄우므로 Figma의 16px에서 그만큼 뺀다 */
[data-testid="stSidebar"]:has(.st-key-rv_toc) [data-testid="stSidebarContent"]{padding:20px 6px}
[data-testid="stSidebar"]:has(.st-key-rv_toc) .sh-scope{display:none}
[data-testid="stSidebar"]:has(.st-key-rv_toc) [data-testid="stLayoutWrapper"]:has(>.st-key-sh_sidebar_bottom){margin-top:10px}
.st-key-rv_toc{gap:4px}
.st-key-rv_toc [data-testid="stElementContainer"],.st-key-rv_toc .stButton{width:100%}
.st-key-rv_back{padding-bottom:14px;margin-bottom:0}
.st-key-rv_back button,.st-key-rv_blocked_back button,.st-key-rv_missing_back button{min-height:0;height:19px;padding:0;gap:8px;justify-content:flex-start;color:#004098;background:transparent;border:none}
.st-key-rv_back button::before,.st-key-rv_blocked_back button::before,.st-key-rv_missing_back button::before{content:"";width:14px;height:14px;flex:none;background:url("app/static/icons/arrow-left.svg") center/contain no-repeat}
.st-key-rv_back button p,.st-key-rv_blocked_back button p,.st-key-rv_missing_back button p{font-size:12px;line-height:18.6px;letter-spacing:-.1px}
.sh-rv-toc-label{padding:0 8px 6px;font-size:12px;line-height:18.6px;font-weight:700;color:#868E96;letter-spacing:-.1px}
[class*="st-key-rv_toc_off_"] button,[class*="st-key-rv_toc_on_"] button{width:100%;height:32px;min-height:0;padding:0 10px;
  justify-content:flex-start;border:none;border-radius:6px;background:transparent;color:#495057}
.st-key-rv_back button>div,[class*="st-key-rv_toc_off_"] button>div,[class*="st-key-rv_toc_on_"] button>div{width:100%;justify-content:flex-start}
.st-key-rv_back button p,[class*="st-key-rv_toc_off_"] button p,[class*="st-key-rv_toc_on_"] button p{text-align:left}
[class*="st-key-rv_toc_off_"] button:hover{background:#F8F9FA}
[class*="st-key-rv_toc_off_"] button p,[class*="st-key-rv_toc_on_"] button p{font-size:12px;line-height:18.6px;letter-spacing:-.1px;font-weight:400}
[class*="st-key-rv_toc_on_"] button{background:#EAF6EF;border-radius:8px;color:#007A36}
[class*="st-key-rv_toc_on_"] button p{font-weight:700}
/* 제목 줄: 왼쪽 종류·기간·제목, 오른쪽 내려받기 2개 + 다시 만들기 */
.st-key-rv_head{align-items:flex-end;flex-wrap:nowrap;gap:16px}
.st-key-rv_head>[data-testid="stElementContainer"]:first-child{flex:1 1 auto;min-width:0}
[data-testid="stLayoutWrapper"]:has(>.st-key-rv_actions){flex:0 0 auto;width:auto}
.st-key-rv_actions{gap:8px;flex-wrap:nowrap;width:auto}
.sh-rv-meta-row{display:flex;align-items:center;gap:8px}
.sh-rv-kind{display:inline-flex;align-items:center;height:22px;padding:0 7px;border-radius:6px;background:#F1F3F5;color:#343A40;
  font-size:11.5px;line-height:17.8px;font-weight:700;letter-spacing:-.1px}
.sh-rv-meta{font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-rv-title{padding-top:6px;font-size:28px;line-height:31.2px;font-weight:700;color:#111111;letter-spacing:-.5px}
.st-key-rv_dl_md button,.st-key-rv_dl_docx button,.st-key-rv_rebuild button{display:flex;align-items:center;gap:6px;height:36px;min-height:36px;padding:0 14px;border-radius:8px}
.st-key-rv_dl_md button,.st-key-rv_dl_docx button{background:#FFFFFF;border:1px solid #CED4DA;color:#111111}
.st-key-rv_dl_md button:hover:not(:disabled),.st-key-rv_dl_docx button:hover:not(:disabled){background:#F8F9FA;border-color:#ADB5BD}
.st-key-rv_dl_md button:disabled,.st-key-rv_dl_docx button:disabled{opacity:.5}
.st-key-rv_dl_md button::before,.st-key-rv_dl_docx button::before{content:"";width:15px;height:15px;flex:none;
  background:url("app/static/icons/download-gray.svg") center/contain no-repeat}
.st-key-rv_rebuild button{border:none;background:#009944;box-shadow:0 2px 3px rgba(0,153,68,.22)}
.st-key-rv_rebuild button:hover{background:#007A36}
.st-key-rv_rebuild button::before{content:"";width:15px;height:15px;flex:none;background:url("app/static/icons/refresh-white.svg") center/contain no-repeat}
.st-key-rv_dl_md button p,.st-key-rv_dl_docx button p,.st-key-rv_rebuild button p{font-size:13.5px;line-height:20.9px;font-weight:700;letter-spacing:-.1px;white-space:nowrap}
.st-key-rv_rebuild button p{color:#FFFFFF}
/* 탭: 밑줄 없이 굵기·색으로만 구분, 근거 문서 개수는 회색 칩 */
.st-key-r04_result_tab [role="tablist"]{gap:22px;padding:0;border-bottom:1px solid #E9ECEF}
.st-key-r04_result_tab [data-testid="stTab"]{height:auto;padding:9px 0 11px;margin:0;background:transparent;border-radius:0}
.st-key-r04_result_tab [data-testid="stTab"] p{display:flex;align-items:center;gap:6px;font-size:14px;line-height:21.7px;font-weight:400;
  color:#6B7280;letter-spacing:-.1px}
.st-key-r04_result_tab [data-testid="stTab"][data-selected="true"] p{font-weight:700;color:#111111}
.st-key-r04_result_tab .react-aria-SelectionIndicator{display:none}
.st-key-r04_result_tab [data-testid="stTab"] .stMarkdownBadge{margin:0;padding:0 6px;border-radius:6px;background:#F1F3F5!important;
  color:#343A40!important;font-size:11.5px!important;line-height:17.8px;font-weight:400}
.st-key-r04_result_tab [data-testid="stTabPanel"]{padding-top:18px}
/* 본문 카드 + 오른쪽 330 */
[data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] .st-key-rv_side){gap:20px;align-items:flex-start}
[data-testid="stColumn"]:has(.st-key-rv_side){flex:0 0 330px;width:330px;min-width:330px}
.stVerticalBlock.st-key-sh-card-rv_summary,.stVerticalBlock.st-key-sh-card-rv_full{padding:28px 36px;gap:22px;min-height:786px}
.st-key-rv_group_key,.st-key-rv_group_advice{gap:0}
.sh-rv-h{font-size:16px;line-height:24.8px;font-weight:700;color:#111111;letter-spacing:-.1px}
.st-key-rv_list_key,.st-key-rv_list_advice{padding:10px 0 0 18px;gap:9px}
[class*="st-key-rv_item_"]{gap:0}
.sh-rv-li{position:relative;font-size:15px;line-height:25.5px;color:#111111;letter-spacing:-.1px}
.sh-rv-mark{position:absolute;left:-21px;width:15px;text-align:right}
.st-key-rv_list_advice .sh-rv-mark{left:-24px;width:18px}
.sh-rv-li .sh-cite{margin-left:4px;font-size:10.5px;line-height:18px;vertical-align:1px}
.sh-rv-li .sh-tag{margin-right:4px}
[class*="st-key-rv_item_"] .stButton button,[class*="st-key-rv_section_"] .stButton button{min-height:0;height:auto;padding:0;color:#004098;background:transparent;border:none}
[class*="st-key-rv_item_"] .stButton button p,[class*="st-key-rv_section_"] .stButton button p{font-size:12px;line-height:normal;font-weight:400}
[class*="st-key-rv_item_"] .stButton button:hover,[class*="st-key-rv_section_"] .stButton button:hover{text-decoration:underline;background:transparent}
[data-testid="stElementContainer"]:has(.sh-rv-foot){margin-top:auto}
.sh-rv-foot{display:flex;align-items:center;gap:8px;font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-rv-foot img{flex:none}
.sh-rv-body{font-size:15px;line-height:25.5px;color:#111111;letter-spacing:-.1px;white-space:pre-wrap;overflow-wrap:anywhere}
[class*="st-key-rv_section_"]{gap:8px}
.st-key-rv_side{gap:12px}
.stVerticalBlock.st-key-sh-card-rv_footnotes,.stVerticalBlock.st-key-sh-card-rv_evidence{padding:0;gap:0;overflow:hidden}
.sh-rv-card-head{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid #E9ECEF}
.sh-rv-card-head b{font-size:16px;line-height:23.25px;font-weight:700;color:#111111;letter-spacing:-.2px}
.sh-rv-card-head span{font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.st-key-rv_fn_list,.st-key-rv_fn_list>[data-testid="stVerticalBlock"]{gap:0}
.st-key-rv_fn_list [data-testid="stHorizontalBlock"],.st-key-sh-card-rv_evidence [data-testid="stHorizontalBlock"]{width:100%;flex-wrap:nowrap;align-items:flex-start;
  gap:8px;padding:11px 16px;border-bottom:1px solid #F1F3F5;box-sizing:border-box}
.st-key-rv_fn_list [data-testid="stLayoutWrapper"]:last-child [data-testid="stHorizontalBlock"]{border-bottom:none}
.st-key-rv_fn_list [data-testid="stHorizontalBlock"]>[data-testid="stElementContainer"]:first-child,
.st-key-sh-card-rv_evidence [data-testid="stHorizontalBlock"]>[data-testid="stElementContainer"]:first-child{flex:1 1 auto;min-width:0}
.sh-rv-fn{display:flex;align-items:flex-start;gap:8px}
.sh-rv-fn .sh-cite{margin:1px 0 0;flex:none;font-size:10.5px}
.sh-rv-fn-body{min-width:0}
.sh-rv-fn-name{font-size:12px;line-height:18.6px;font-weight:700;color:#111111;letter-spacing:-.1px;overflow-wrap:anywhere}
.sh-rv-fn-meta{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-rv-fn-meta .sh-tag{display:inline-flex;align-items:center;height:22px;padding:0 7px;border-radius:6px;font-size:11.5px;line-height:17.8px;letter-spacing:0}
.sh-rv-doc-at{display:inline-flex;align-items:center;gap:4px}
.sh-rv-doc-at .sh-cite{margin:0}
.st-key-rv_fn_list .stButton button,.st-key-sh-card-rv_evidence .stButton button{min-height:0;height:auto;padding:0;margin-top:-4px;color:#004098;background:transparent;border:none}
.st-key-rv_fn_list .stButton button p,.st-key-sh-card-rv_evidence .stButton button p{font-size:12px;line-height:18.6px;font-weight:400;letter-spacing:-.1px}
.st-key-rv_fn_list .stButton button:hover,.st-key-sh-card-rv_evidence .stButton button:hover{text-decoration:underline;background:transparent}
.stVerticalBlock.st-key-sh-card-rv_notice{padding:12px 14px}
.sh-rv-notice{display:flex;align-items:flex-start;gap:8px;font-size:12px;line-height:18.6px;color:#343A40}
.sh-rv-notice img{flex:none;margin-top:2px}
</style>
"""

_CSS_MYPAGE = """
<style>
/* M-02·M-03·M-04 내 정보 (Figma 06): 프로필 카드 위, 아래에 요청 표(가변)와 사용 기록(460) 두 카드 */
.stMainBlockContainer:has(.st-key-mp_root){padding-bottom:22px}
.st-key-mp_root{gap:18px}
.stVerticalBlock.st-key-sh-card-mp_profile{padding:20px 24px;gap:0}
.st-key-mp_profile_row{gap:32px;flex-wrap:nowrap}
.st-key-mp_profile_row>[data-testid="stElementContainer"]{flex:none;width:auto}
.st-key-mp_profile_row>[data-testid="stElementContainer"]:first-child{flex:1 1 0;min-width:0;margin-right:-16px}
.sh-mp-name{display:flex;align-items:center;gap:8px}
.sh-mp-name b{font-size:20px;line-height:31px;font-weight:700;letter-spacing:-.4px;color:#111111}
.sh-mp-name .sh-tag:last-child{letter-spacing:-.1px}
.sh-mp-meta{padding-top:2px;font-size:12px;line-height:18.6px;color:#6B7280}
.sh-mp-stats{display:flex;gap:32px}
.sh-mp-stat-label{font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px;white-space:nowrap}
.sh-mp-stat-num{font-size:24px;line-height:31px;font-weight:700;color:#111111;letter-spacing:-.1px}
.st-key-mp_edit{width:auto}
.st-key-mp_edit button{display:flex;align-items:center;gap:6px;min-height:36px;height:36px;padding:0 14px;background:#FFFFFF;
  border:1px solid #CED4DA;border-radius:8px;color:#111111}
.st-key-mp_edit button::before{content:"";width:15px;height:15px;flex:none;
  background:url("app/static/icons/profile-edit.svg") center/contain no-repeat}
.st-key-mp_edit button p{font-size:13.5px;line-height:20.9px;font-weight:700}
[data-testid="stHorizontalBlock"]:has(.st-key-sh-card-mp_requests){gap:20px;flex-wrap:nowrap}
[data-testid="stColumn"]:has(.st-key-sh-card-mp_requests){flex:1 1 0;min-width:0}
[data-testid="stColumn"]:has(.st-key-sh-card-mp_history){flex:0 0 460px;width:460px;min-width:460px}
/* 두 카드는 화면 아래까지 채운다 (헤더 56 + 위아래 여백 44 + 프로필 카드 93 + 간격 18) */
.stVerticalBlock.st-key-sh-card-mp_requests,.stVerticalBlock.st-key-sh-card-mp_history{padding:0;gap:0;overflow:hidden;
  min-height:calc(100vh - 211px)}
.stVerticalBlock.st-key-sh-card-mp_history{position:relative}
.sh-mp-head{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid #E9ECEF}
.sh-mp-h{font-size:16px;line-height:23.25px;font-weight:700;color:#111111;letter-spacing:-.2px}
.sh-mp-note{font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-mp-name .sh-tag,.sh-mp-table .sh-tag{display:inline-flex;align-items:center;gap:4px;height:22px;padding:0 7px;border-radius:6px;
  font-size:11.5px;line-height:normal;font-weight:700;letter-spacing:-.1px}
.sh-mp-name .sh-co,.sh-mp-table .sh-co{letter-spacing:.2px}
.sh-mp-row{display:grid;grid-template-columns:minmax(0,315.94fr) 95.33fr 140.84fr 117.89fr;align-items:center;height:60px;
  border-bottom:1px solid #F1F3F5}
.sh-mp-row>*{padding:0 14px;min-width:0}
.sh-mp-row-head{height:36.5px;background:#FBFBFC;border-bottom-color:#E9ECEF;font-size:11.5px;font-weight:700;color:#6B7280;letter-spacing:-.1px}
.sh-mp-doc b{display:block;font-size:13.5px;line-height:normal;font-weight:700;color:#111111;letter-spacing:-.1px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sh-mp-sub{display:block;font-size:12px;line-height:normal;color:#6B7280;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sh-mp-sub-bad{color:#E03131;letter-spacing:-.1px}
.sh-mp-when{font-size:12px;color:#343A40;letter-spacing:-.1px;white-space:nowrap}
.sh-mp-list{padding:6px 18px}
.sh-mp-scroll{max-height:calc(100vh - 263px);overflow-y:auto}
.sh-mp-day{padding:10px 0 4px;font-size:12px;line-height:18.6px;font-weight:700;color:#6B7280;letter-spacing:-.1px}
.sh-mp-item+.sh-mp-day{padding-top:12px}
.sh-mp-item{display:flex;align-items:flex-start;gap:12px;padding:9px 0}
.sh-mp-item img{flex:none}
.sh-mp-item-text{flex:1 1 0;min-width:0}
.sh-mp-item-title{font-size:14px;line-height:21.7px;color:#111111;letter-spacing:-.1px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sh-mp-item-sub{font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-mp-item-time{flex:none;font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
/* [전체 보기]는 카드 머리 오른쪽 끝에 겹쳐 둔 파란 링크 */
.st-key-mp_all{position:absolute;top:14px;right:18px;width:auto;z-index:1}
.st-key-mp_all button{min-height:0;height:23.25px;padding:0;color:#004098}
.st-key-mp_all button p{font-size:12px;line-height:18.6px;letter-spacing:-.1px}
</style>"""

_CSS_ADMIN_DOCS = """
<style>
/* A-01·A-02·A-03 관리자 문서 화면 (Figma 07). 위쪽 카드·표·상세 패널 */
.st-key-ad_actions{gap:8px;flex-wrap:nowrap}
.st-key-ad_actions button{display:inline-flex;align-items:center;justify-content:center;gap:6px;height:36px;min-height:36px;padding:0 14px;
  border:1px solid #CED4DA;border-radius:8px;background:#FFFFFF}
.st-key-ad_actions button p{font-size:13.5px;line-height:20.9px;font-weight:700;color:#111111;letter-spacing:-.1px;white-space:nowrap}
.st-key-ad_actions button:disabled{opacity:.5}
.st-key-ad_reindex_failed button::before{content:"";width:15px;height:15px;flex:none;background:url("app/static/icons/refresh-gray.svg") center/contain no-repeat}
.st-key-ad_upload button{border-color:#009944;background:#009944;box-shadow:0 2px 3px rgba(0,153,68,.22)}
.st-key-ad_upload button:hover:not(:disabled){background:#007A36;border-color:#007A36}
.st-key-ad_upload button p{color:#FFFFFF}
.st-key-ad_upload button::before{content:"";width:15px;height:15px;flex:none;background:url("app/static/icons/upload-white.svg") center/contain no-repeat}
/* 위쪽 요약 카드 4개 */
.sh-ad-stats{display:flex;gap:12px;margin-top:2px}
.sh-ad-stat{flex:1 1 0;min-width:0;box-sizing:border-box;padding:14px 16px;background:#FFFFFF;border:1px solid #E5E8EB;border-radius:12px;
  box-shadow:0 1px 1px rgba(16,24,40,.04),0 2px 3px rgba(16,24,40,.06)}
.sh-ad-stat-label{display:flex;align-items:center;gap:6px;height:18.6px;font-size:12px;line-height:18.6px;color:#343A40;letter-spacing:-.1px}
.sh-ad-dot{display:block;width:7px;height:7px;border-radius:4px}
.sh-ad-dot-green{background:#009944}
.sh-ad-dot-red{background:#E03131}
.sh-ad-dot-yellow{background:#FABE00}
.sh-ad-stat-value{display:flex;align-items:center;justify-content:space-between;height:38px}
.sh-ad-stat-value b{padding-top:4px;font-size:26px;line-height:34.1px;font-weight:700;color:#111111;letter-spacing:-.5px}
.sh-ad-stat-sub{font-size:11.5px;line-height:17.8px;color:#6B7280;letter-spacing:-.1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sh-ad-spark{display:flex;align-items:flex-end;gap:3px;height:28px}
.sh-ad-spark-bar{display:block;width:6px;border-radius:1px;background:#CED4DA}
.sh-ad-spark-now{background:#009944}
/* 표 카드와 상세 패널 */
.st-key-ad_main{--ad-h:max(560px,calc(100vh - 317px));margin-top:2px}
.st-key-ad_main>[data-testid="stLayoutWrapper"]>[data-testid="stHorizontalBlock"]{gap:20px;align-items:stretch;flex-wrap:nowrap}
[data-testid="stColumn"]:has(.st-key-sh-card-ad_panel){flex:0 0 330px;width:330px;min-width:330px}
[data-testid="stColumn"]:has(.st-key-sh-card-ad_list){flex:1 1 0;min-width:0}
.stVerticalBlock.st-key-sh-card-ad_list{padding:0;gap:0;overflow:hidden;min-height:var(--ad-h)}
.stVerticalBlock.st-key-sh-card-ad_panel{padding:20px;gap:18px;min-height:var(--ad-h);box-sizing:border-box}
/* 검색창과 필터 칩 */
.st-key-ad_toolbar{padding:12px 14px;border-bottom:1px solid #E9ECEF;gap:0}
.st-key-ad_toolbar [data-testid="stHorizontalBlock"]{gap:8px;flex-wrap:nowrap;align-items:center}
.st-key-ad_toolbar [data-testid="stColumn"]{flex:0 0 auto;width:auto;min-width:0}
.st-key-ad_toolbar [data-testid="stColumn"]:first-child{flex:1 1 0}
.st-key-ad_toolbar [data-testid="stTextInputRootElement"]{height:34px;background:#F8F9FA url("app/static/icons/search-muted.svg") 11px center/15px 15px no-repeat;
  border:1px solid #E9ECEF;border-radius:4px}
.st-key-ad_toolbar [data-testid="stTextInputRootElement"] input{height:100%;padding:0 11px 0 34px;font-size:13.5px;letter-spacing:-.1px}
.st-key-ad_toolbar [data-testid="stTextInputRootElement"] input::placeholder{color:#6B7280;opacity:1}
.st-key-ad_toolbar [data-testid="stPopover"] button{height:30px;min-height:30px;padding:0 11px;border:1px solid #DEE2E6;border-radius:8px;background:#FFFFFF}
.st-key-ad_toolbar [data-testid="stPopover"] button p{font-size:12.5px;line-height:19.4px;color:#111111;letter-spacing:-.1px;white-space:nowrap}
.st-key-ad_toolbar [data-testid="stPopover"] button [data-testid="stIconMaterial"]{display:none}
/* 표 */
.st-key-ad_table{gap:0}
.st-key-ad_table [data-testid="stHorizontalBlock"]{gap:0;align-items:center;flex-wrap:nowrap}
.st-key-ad_table [data-testid="stColumn"]{padding:0 14px;min-width:0;box-sizing:border-box}
.st-key-ad_table [data-testid="stColumn"]>[data-testid="stVerticalBlock"]{gap:0}
.stVerticalBlock.st-key-ad_thead{box-sizing:border-box;background:#FBFBFC;border-bottom:1px solid #E9ECEF;height:36.5px;min-height:36.5px;justify-content:center;gap:0}
.sh-ad-th{font-size:11.5px;font-weight:700;color:#6B7280;letter-spacing:-.1px}
.stVerticalBlock[class*="st-key-ad_row"]{position:relative;height:60px;min-height:60px;box-sizing:border-box;justify-content:center;gap:0;border-bottom:1px solid #F1F3F5}
.stVerticalBlock[class*="st-key-ad_row-"]:hover{background:#FAFBFC}
.stVerticalBlock[class*="st-key-ad_rowsel-"]{background:#F6FDF8}
[class*="st-key-ad_pick-"]{position:absolute;inset:0;z-index:1;width:100%!important;height:100%!important}
[class*="st-key-ad_pick-"] [data-testid="stButton"],[class*="st-key-ad_pick-"] button{width:100%;height:100%;min-height:0;padding:0;opacity:0;cursor:pointer}
[class*="st-key-group-share-"]{position:relative;z-index:2}
.sh-ad-doc{display:flex;align-items:center;gap:10px;min-width:0}
.sh-ad-doc-text{display:flex;flex-direction:column;min-width:0}
.sh-ad-doc-text b{font-size:13.5px;line-height:normal;font-weight:700;color:#111111;letter-spacing:-.1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sh-ad-doc-text span{font-size:12px;line-height:normal;color:#6B7280;letter-spacing:-.1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sh-ad-type{display:flex;align-items:flex-end;justify-content:center;flex:none;box-sizing:border-box;width:26px;height:30px;padding-bottom:5px;border-radius:4px;
  font-size:9px;line-height:normal;font-weight:700;letter-spacing:.2px}
.sh-ad-type-lg{width:30px;height:34px}
.sh-ad-type-pdf{background:#FFF5F5;color:#C92A2A}
.sh-ad-type-doc{background:#E7F5FF;color:#1864AB}
.sh-ad-type-ppt{background:#FFF4E6;color:#D9480F}
.sh-ad-type-dart{background:#EBFBEE;color:#2B8A3E}
.sh-ad-type-etc{background:#F1F3F5;color:#495057}
.sh-ad-cell{font-size:14px;line-height:normal;color:#111111;letter-spacing:-.1px}
.sh-ad-cell-sm{font-size:12px;color:#343A40}
.sh-ad-cell-muted{font-size:12px;color:#6B7280}
.sh-ad-tag{display:inline-flex;align-items:center;gap:4px;height:22px;padding:0 7px;box-sizing:border-box;border-radius:6px;font-size:11.5px;line-height:normal;
  font-weight:700;letter-spacing:-.1px;white-space:nowrap}
.sh-ad-tag-pub{background:#EBFBEE;color:#2B8A3E}
.sh-ad-tag-int{background:#FFF4CC;color:#7A5A00}
.sh-ad-tag-con{background:#FFF5F5;color:#E03131}
.sh-ad-tag-etc{background:#F1F3F5;color:#343A40}
.sh-ad-state{display:inline-flex;align-items:center;gap:8px;font-size:12px;line-height:normal;letter-spacing:-.1px}
.sh-ad-state img{flex:none}
.sh-ad-state-done{color:#2B8A3E}
.sh-ad-state-failed{color:#E03131;font-weight:700}
.sh-ad-state-wait{color:#7A5A00}
.sh-ad-state-busy{flex-direction:column;align-items:flex-start;gap:4px}
.sh-ad-state-busy b{color:#7A5A00;font-weight:700}
.sh-ad-bar{position:relative;display:block;width:80px;height:4px;overflow:hidden;border-radius:2px;background:#F1F3F5}
.sh-ad-bar i{position:absolute;top:0;left:0;width:50px;height:4px;border-radius:2px;background:#009944;animation:sh-ad-slide 1.6s ease-in-out infinite}
@keyframes sh-ad-slide{from{transform:translateX(-52px)}to{transform:translateX(82px)}}
@media(prefers-reduced-motion:reduce){.sh-ad-bar i{animation:none;width:40px}}
/* 표 아래 쪽 번호 */
[data-testid="stLayoutWrapper"]:has(>.st-key-ad_pager){margin-top:auto}
.st-key-ad_pager{box-sizing:border-box;min-height:51px;padding:10px 14px;border-top:1px solid #E9ECEF;justify-content:center;gap:0}
.st-key-ad_pager [data-testid="stHorizontalBlock"]{gap:8px;flex-wrap:nowrap;align-items:center}
.st-key-ad_pager [data-testid="stColumn"]{flex:0 0 auto;width:auto;min-width:0}
.st-key-ad_pager [data-testid="stColumn"]:first-child{flex:1 1 0}
.sh-ad-pager-info{font-size:12px;line-height:18.6px;color:#343A40;letter-spacing:-.1px}
.st-key-ad_pager button{height:30px;min-height:30px;padding:0 10px;border:1px solid #CED4DA;border-radius:8px;background:#FFFFFF}
.st-key-ad_pager button p{font-size:12.5px;line-height:19.4px;font-weight:700;color:#111111;letter-spacing:-.1px}
.st-key-ad_pager button:disabled{opacity:.5}
/* 상세 패널 */
.sh-ad-panel-head{display:flex;align-items:center;gap:8px}
.sh-ad-panel-title{padding-top:10px;font-size:17px;line-height:26.35px;font-weight:700;color:#111111;letter-spacing:-.3px;overflow-wrap:anywhere}
.sh-ad-panel-sub{font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.st-key-sh-card-ad_panel [data-testid="stSelectbox"] [data-testid="stWidgetLabel"],.st-key-sh-card-ad_panel [data-testid="stSelectbox"] [data-testid="stWidgetLabel"] p{opacity:1;color:#343A40;font-size:12.5px;line-height:19.4px;font-weight:700;letter-spacing:-.1px}
.st-key-sh-card-ad_panel .react-aria-ComboBox>[role="group"]{min-height:38px;border:1px solid #CED4DA;border-radius:8px;background:#FFFFFF;opacity:1}
.st-key-sh-card-ad_panel .react-aria-ComboBox input{color:#111111;-webkit-text-fill-color:#111111;opacity:1;font-size:14px;letter-spacing:-.1px}
.st-key-sh-card-ad_panel .react-aria-ComboBox button{opacity:1}
.st-key-sh-card-ad_panel [data-testid="stHorizontalBlock"]:not(.st-key-ad_panel_actions){gap:0;align-items:center;flex-wrap:nowrap}
.st-key-sh-card-ad_panel [data-testid="stColumn"]:has(.sh-ad-share-title){flex:1 1 0;min-width:0}
.st-key-sh-card-ad_panel [data-testid="stColumn"]:has(.stCheckbox){flex:0 0 34px;width:34px;min-width:34px}
.sh-ad-share-title{font-size:14px;line-height:21.7px;font-weight:700;color:#111111;letter-spacing:-.1px}
.sh-ad-share-note{max-width:220px;font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-ad-divider{height:1px;background:#E9ECEF}
.sh-ad-viewers-title{padding-bottom:10px;font-size:14px;line-height:21.7px;font-weight:700;color:#111111;letter-spacing:-.1px}
.sh-ad-viewer{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:10px;font-size:12px;line-height:18.6px;color:#111111;letter-spacing:-.1px}
.sh-ad-viewer:last-child{margin-bottom:0}
.sh-ad-viewer em{font-style:normal;color:#6B7280}
.sh-ad-viewer .sh-tag{display:inline-flex;align-items:center;height:22px;margin-left:6px;padding:0 7px;border-radius:6px;font-size:11.5px;line-height:normal;letter-spacing:.2px}
[data-testid="stLayoutWrapper"]:has(>.st-key-ad_panel_actions){margin-top:auto}
.st-key-ad_panel_actions{gap:8px;flex-wrap:nowrap;align-items:center}
.st-key-ad_panel_actions button{height:36px;min-height:36px;padding:0 14px;border:1px solid #DEE2E6;border-radius:8px;background:#FFFFFF}
.st-key-ad_panel_actions button p{font-size:13.5px;line-height:20.9px;font-weight:700;color:#111111;letter-spacing:-.1px;white-space:nowrap}
.st-key-ad_panel_actions button:disabled{opacity:.5}
[class*="st-key-admin-docs-delete-"] button p{color:#E03131}
[class*="st-key-ad-panel-save-"]{margin-left:auto}
[class*="st-key-ad-panel-save-"] button{border-color:#009944;background:#009944;box-shadow:0 2px 3px rgba(0,153,68,.22)}
[class*="st-key-ad-panel-save-"] button p{color:#FFFFFF}
/* 그룹사 공유 토글 (34×20) — 표와 패널이 같이 쓴다 */
.st-key-ad_main .stCheckbox label{display:flex;align-items:center;min-height:0}
.st-key-ad_main .stCheckbox label>div:not([data-testid="stWidgetLabel"]){position:relative;flex:none;width:34px;height:20px;box-sizing:border-box;padding:0;border:0;border-radius:10px;background:#DEE2E6;transition:background .15s}
.st-key-ad_main .stCheckbox label>div:not([data-testid="stWidgetLabel"])>div{position:absolute;top:2px;left:2px;width:16px;height:16px;margin:0;border-radius:8px;background:#FFFFFF;transform:none;transition:left .15s}
.st-key-ad_main .stCheckbox label:has(input:checked)>div:not([data-testid="stWidgetLabel"]){background:#009944}
.st-key-ad_main .stCheckbox label:has(input:checked)>div:not([data-testid="stWidgetLabel"])>div{left:16px}
.st-key-ad_main .stCheckbox label:has(input:disabled){opacity:.5}
.st-key-ad_main .stCheckbox [data-testid="stWidgetLabel"]{display:none}
</style>
"""

_CSS_UPLOAD_MODAL = """
<style>
/* A-01 문서 올리기 팝업 (Figma 08). 이 팝업 안에서만 쓰는 규칙이라 모두 .sh-upload-dialog-marker 로 범위를 좁힌다 */
[data-testid="stDialog"]:has(.sh-upload-dialog-marker)>div{width:560px!important;min-width:0!important;max-width:calc(100vw - 32px)!important;box-sizing:border-box}
section[role="dialog"]:has(.sh-upload-dialog-marker){width:100%!important;min-width:0;max-height:calc(100dvh - 32px);overflow-y:auto;box-sizing:border-box;padding:0;
  background:#FFFFFF;border:1px solid #E9ECEF;border-radius:12px;box-shadow:0 2px 6px rgba(16,24,40,.06),0 1px 2px rgba(16,24,40,.04);
  font-family:"NeoHyundai","Segoe UI",sans-serif;color:#111111}
section[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stMarkdownContainer"] p{margin:0}
section[role="dialog"]:has(.sh-upload-dialog-marker)>h2{margin:0;padding:20px 64px 0 24px}
section[role="dialog"]:has(.sh-upload-dialog-marker)>h2 p{font-size:18px;line-height:26px;font-weight:700;color:#111111;letter-spacing:normal}
section[role="dialog"]:has(.sh-upload-dialog-marker)>button[aria-label="Close"]{position:absolute;top:20px;right:16px;width:32px;height:32px;padding:0;
  border:0;border-radius:4px;background:transparent url("app/static/icons/modal-close.svg") center no-repeat;color:transparent}
section[role="dialog"]:has(.sh-upload-dialog-marker)>button[aria-label="Close"] svg{display:none}
section[role="dialog"]:has(.sh-upload-dialog-marker)>button[aria-label="Close"]:hover{background-color:#F1F3F5}
section[role="dialog"]:has(.sh-upload-dialog-marker)>div:last-child{padding:0 24px}
section[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stLayoutWrapper"],
section[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stVerticalBlock"],
section[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stHorizontalBlock"]{min-width:0;max-width:100%;box-sizing:border-box}
section[role="dialog"]:has(.sh-upload-dialog-marker)>div:last-child>[data-testid="stVerticalBlock"]{gap:12px}
section[role="dialog"]:has(.sh-upload-dialog-marker) [data-testid="stElementContainer"]:has(.sh-upload-dialog-marker){display:none}
.sh-up-sub{margin-bottom:12px;font-size:12.5px;line-height:18px;color:#6B7280}
/* 드롭존 */
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]{display:flex;align-items:center;gap:16px;box-sizing:border-box;min-height:76px;padding:16px;
  border:0;border-radius:6px;background:#F8F9FA}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]::before{content:"";flex:none;order:0;width:44px;height:44px;background:url("app/static/icons/upload-gray.svg") center no-repeat}
.st-key-upload-picker [data-testid="stFileUploaderDropzoneInstructions"]{order:1;flex:1 1 0;min-width:0;display:flex;flex-direction:column;align-items:flex-start;justify-content:center;gap:2px;text-align:left}
.st-key-upload-picker [data-testid="stFileUploaderDropzoneInstructions"]>*{display:none}
.st-key-upload-picker [data-testid="stFileUploaderDropzoneInstructions"]::before{content:"파일을 여기로 끌어다 놓으세요";font-size:14px;line-height:22px;font-weight:700;color:#111111;letter-spacing:normal}
.st-key-upload-picker [data-testid="stFileUploaderDropzoneInstructions"]::after{content:"파일당 최대 20MB • PDF, DOCX, PPTX";font-size:11.5px;line-height:normal;color:#6B7280}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]>span{order:2;flex:none}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]>span>button{display:flex;align-items:center;padding:7px 12px;min-height:0;border:1px solid #DEE2E6;border-radius:8px;background:#FFFFFF}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]>span>button>*{display:none}
.st-key-upload-picker [data-testid="stFileUploaderDropzone"]>span>button::after{content:"파일 찾기";font-size:12.5px;line-height:18px;font-weight:700;color:#111111;letter-spacing:-.1px}
/* 선택한 파일 머리줄 */
.st-key-upload-file-heading{margin-top:12px}
.st-key-upload-file-heading [data-testid="stHorizontalBlock"]{gap:6px;flex-wrap:nowrap;align-items:center}
.sh-up-list-head{display:flex;align-items:center;gap:6px;font-size:12.5px;line-height:18px;font-weight:700;color:#343A40;letter-spacing:-.1px}
.sh-up-count{padding:1px 7px;border-radius:6px;background:#F1F3F5;font-size:11.5px;line-height:16px;font-weight:700}
.st-key-upload-file-heading button{min-height:0;padding:0;background:transparent}
.st-key-upload-file-heading button p{font-size:12px;line-height:18px;font-weight:400;color:#6B7280;letter-spacing:-.1px}
.st-key-upload-file-heading button:hover p{color:#111111;text-decoration:none}
/* 파일 행 */
.stVerticalBlock.st-key-upload-file-list{gap:8px}
.stVerticalBlock[class*="st-key-upload-document-card-"]{box-sizing:border-box;padding:10px 12px;gap:0;border:1px solid #E9ECEF!important;border-radius:10px;background:#FFFFFF}
[class*="st-key-upload-document-card-"] [data-testid="stHorizontalBlock"]{gap:12px;flex-wrap:nowrap;align-items:center}
[class*="st-key-upload-document-card-"] [data-testid="stColumn"]{flex:1 1 0;width:auto;min-width:0}
[class*="st-key-upload-document-card-"] [data-testid="stColumn"]:first-child{flex:0 0 30px}
[class*="st-key-upload-document-card-"] [data-testid="stColumn"]:last-child{flex:0 0 24px}
[class*="st-key-upload-document-card-"] [data-testid="stColumn"]>[data-testid="stVerticalBlock"]{gap:3px}
.sh-up-name{font-size:13px;line-height:18px;font-weight:700;color:#111111;letter-spacing:-.1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sh-up-wait{font-size:11.5px;line-height:16px;color:#6B7280}
[class*="st-key-remove-"] button{width:24px;height:24px;min-height:0;padding:0;border:0;border-radius:4px;background:transparent url("app/static/icons/remove.svg") center no-repeat;font-size:0}
[class*="st-key-remove-"] button p{display:none}
[class*="st-key-remove-"] button:hover{background-color:#F1F3F5}
/* 파일별 처리 결과 (upload_status_html 이 만드는 HTML) */
.sh-upload-status{display:flex;align-items:center;gap:4px;box-sizing:border-box;font-size:11.5px;line-height:16px;color:#6B7280}
.sh-upload-status>span{display:block;margin:0;padding:0;overflow-wrap:anywhere}
.sh-upload-status-done::before,.sh-upload-status-failed::before,.sh-upload-status-duplicate::before{content:"";flex:none;width:12px;height:12px;background:center no-repeat}
.sh-upload-status-done::before{background-image:url("app/static/icons/check-small.svg")}
.sh-upload-status-failed{color:#C92A2A}
.sh-upload-status-failed::before{background-image:url("app/static/icons/warn-small.svg")}
.sh-upload-status-duplicate{color:#7A5A00}
.sh-upload-status-duplicate::before{background-image:url("app/static/icons/warning.svg")}
.sh-upload-status-busy{gap:8px;color:#8A5A00;font-weight:700}
.sh-upload-status-busy .sh-upload-spinner{position:relative;flex:1 1 0;min-width:0;height:4px;overflow:hidden;border-radius:2px;background:#E9ECEF}
.sh-upload-status-busy .sh-upload-spinner::after{content:"";position:absolute;top:0;left:0;width:40%;height:4px;border-radius:2px;background:#009944;animation:sh-upload-slide 1.4s ease-in-out infinite}
.sh-upload-status-busy>span:last-child{flex:none}
@keyframes sh-upload-slide{from{transform:translateX(-100%)}to{transform:translateX(260%)}}
@media(prefers-reduced-motion:reduce){.sh-upload-status-busy .sh-upload-spinner::after{animation:none;width:60%}}
.sh-up-dup{margin-top:2px;font-size:11.5px;line-height:16px;color:#6B7280;overflow-wrap:anywhere}
/* 문서 정보 */
.stVerticalBlock.st-key-upload-info{gap:14px;margin-top:12px}
.sh-up-info-title{font-size:15px;line-height:normal;font-weight:700;color:#111111}
.sh-up-info-sub{margin-top:4px;font-size:12px;line-height:normal;color:#6B7280}
.sh-up-help{margin-top:-8px;font-size:12px;line-height:normal;color:#6B7280}
.st-key-upload-info [data-testid="stWidgetLabel"],.st-key-upload-info [data-testid="stWidgetLabel"] p{opacity:1;font-size:13px;line-height:normal;font-weight:700;color:#343A40;letter-spacing:normal}
.st-key-upload-info [data-testid="stWidgetLabel"]{min-height:0;margin-bottom:6px}
.st-key-upload-info .react-aria-ComboBox>[role="group"]{min-height:40px;border:1px solid #CED4DA;border-radius:8px;background:#FFFFFF;opacity:1}
.st-key-upload-info .react-aria-ComboBox input{padding-left:12px;font-size:14px;color:#111111;-webkit-text-fill-color:#111111;opacity:1;letter-spacing:normal}
.st-key-upload-info .react-aria-ComboBox[data-disabled="true"]>[role="group"]{background:#F4F6F8;border-color:#E5E8EB}
.st-key-upload-info .react-aria-ComboBox[data-disabled="true"] input{color:#495057;-webkit-text-fill-color:#495057}
.st-key-upload-info [data-testid="stHorizontalBlock"]{gap:12px;flex-wrap:nowrap}
.st-key-upload-info [data-testid="stHorizontalBlock"]>[data-testid="stColumn"]{flex:1 1 0;width:auto;min-width:0}
.st-key-upload-info [data-testid="stRadio"],.st-key-upload-info [data-testid="stElementContainer"]:has([data-testid="stRadio"]){width:100%}
.st-key-upload-info [data-testid="stRadioGroup"]{display:flex;align-items:stretch;width:100%;gap:0;height:40px;box-sizing:border-box;overflow:hidden;border:1px solid #CED4DA;border-radius:8px}
.st-key-upload-info [data-testid="stRadioGroup"]>div{flex:1 1 0;min-width:0;background:#FFFFFF;border-right:1px solid #CED4DA}
.st-key-upload-info [data-testid="stRadioGroup"]>div:last-child{border-right:0}
.st-key-upload-info [data-testid="stRadioGroup"]>div[data-selected="true"]{background:#EAF6EF}
.st-key-upload-info [data-testid="stRadioOption"]{display:flex;align-items:center;justify-content:center;width:100%;height:100%;margin:0;padding:0;cursor:pointer}
.st-key-upload-info [data-testid="stRadioOption"]>div{display:flex;align-items:center;justify-content:center}
.st-key-upload-info [data-testid="stRadioOption"]>div>div:first-child{display:none}
.st-key-upload-info [data-testid="stRadioOption"] p{font-size:14px;line-height:normal;font-weight:400;color:#343A40;letter-spacing:normal}
.st-key-upload-info [data-testid="stRadioGroup"]>div[data-selected="true"] p{font-weight:700;color:#007A36}
.sh-up-note{display:flex;gap:6px;align-items:flex-start;padding:10px;border-radius:6px;background:#E6ECF5;font-size:11.5px;line-height:normal;color:#004098}
.sh-up-note-icon{display:flex;align-items:center;justify-content:center;flex:none;width:14px;height:14px}
.st-key-upload-info [data-testid="stExpander"]{border:1px solid #E9ECEF;border-radius:8px;background:#FFFFFF}
.st-key-upload-info [data-testid="stExpander"] summary{padding:8px 12px;font-size:12.5px;color:#495057}
.st-key-upload-info [data-testid="stExpanderDetails"] [data-testid="stVerticalBlock"]{gap:10px}
/* 푸터: 아래에 붙인다 */
.stVerticalBlock.st-key-upload-footer{position:sticky;bottom:0;z-index:2;margin:12px 0 0;padding:14px 0;gap:0;background:#FFFFFF}
.st-key-upload-footer [data-testid="stHorizontalBlock"]{gap:8px;flex-wrap:nowrap;align-items:center}
.st-key-upload-footer .sh-muted{font-size:12px;line-height:normal;color:#6B7280}
.st-key-upload-footer [data-testid="stColumn"]:last-child{flex:0 0 auto;width:auto}
.st-key-upload-footer [data-testid="stColumn"]:first-child{flex:1 1 0;min-width:0}
.st-key-upload-footer button{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:0;padding:7.5px 16px;border:1px solid #CED4DA;border-radius:8px;background:#FFFFFF}
.st-key-upload-footer button p{font-size:13.5px;line-height:21px;font-weight:700;color:#111111;letter-spacing:-.1px;white-space:nowrap}
.st-key-upload-footer button[kind="primary"]{border-color:#009944;background:#009944;box-shadow:0 2px 6px rgba(0,153,68,.22)}
.st-key-upload-footer button[kind="primary"] p{color:#FFFFFF}
.st-key-upload-footer button[kind="primary"]::before{content:"";width:15px;height:15px;flex:none;background:url("app/static/icons/upload-white-15.svg") center no-repeat}
.st-key-upload-footer button:disabled{opacity:.5}
</style>
"""

_CSS_ACCESS_REQUESTS = """
<style>
/* A-05 열람 권한 요청 (Figma 09): 왼쪽 420 목록 카드 · 오른쪽 상세 카드. 두 카드는 화면 높이(머리글·여백·제목 줄 제외)를 채운다 */
.stMainBlockContainer:has(.st-key-sh-card-ar_list){padding-bottom:22px}
[data-testid="stHorizontalBlock"]:has(>[data-testid="stColumn"] .st-key-sh-card-ar_list){gap:20px;margin-top:2px}
[data-testid="stColumn"]:has(.st-key-sh-card-ar_list){flex:0 0 420px;width:420px;min-width:420px}
.stVerticalBlock.st-key-sh-card-ar_list{padding:0;gap:0;overflow:hidden;min-height:calc(100vh - 196px)}
.stVerticalBlock.st-key-sh-card-ar_detail{padding:24px 28px;gap:20px;min-height:calc(100vh - 196px)}
.stVerticalBlock.st-key-sh-card-ar_detail>[data-testid="stElementContainer"]{width:100%}
/* 상태 탭: 밑줄 없이 굵기·색으로 구분하고 이름 뒤에 숫자 칩을 붙인다 (숫자는 목록 코드가 CSS로 넣는다) */
.st-key-ar_status{padding:0 18px;border-bottom:1px solid #E9ECEF}
.st-key-ar_status [data-testid="stRadio"]>label{display:none}
.st-key-ar_status [data-testid="stRadioGroup"]{gap:22px}
.st-key-ar_status [data-testid="stRadioOption"]{box-sizing:border-box;min-height:42px;padding:9px 0 11px;margin:0;cursor:pointer}
.st-key-ar_status [data-testid="stRadioOption"]>div{display:flex;align-items:center;gap:6px;margin:0}
.st-key-ar_status [data-testid="stRadioOption"]>div>div:first-child{display:none}
.st-key-ar_status [data-testid="stRadioOption"] p{font-size:14px;line-height:21.7px;color:#6B7280;letter-spacing:-.1px}
.st-key-ar_status [data-testid="stRadioOption"][data-selected="true"] p{font-weight:700;color:#111111}
.st-key-ar_status [data-testid="stRadioOption"]>div::after{display:inline-block;padding:0 6px;border-radius:6px;background:#F1F3F5;
  color:#343A40;font-size:11.5px;line-height:17.8px;letter-spacing:-.1px}
.st-key-ar_status [data-testid="stRadioOption"][data-selected="true"]>div::after{font-weight:700}
/* 요청 목록: 행 전체가 버튼이다 (보이지 않는 버튼을 행 위에 덮는다) */
.st-key-ar_items{gap:0;overflow-y:auto;max-height:calc(100vh - 196px - 56px)}
[class*="st-key-ar_item_"]{position:relative;gap:0;padding:14px 18px;border-bottom:1px solid #F1F3F5}
[class*="st-key-ar_item_on_"]{background:#F6FDF8}
[class*="st-key-ar_item_"] .stButton{position:absolute;inset:0;width:100%}
[class*="st-key-ar_item_"] .stButton button{width:100%;height:100%;min-height:0;opacity:0;cursor:pointer}
.sh-ar-top{display:flex;align-items:center;gap:8px}
.sh-ar-name{font-size:14px;line-height:21.7px;font-weight:700;color:#111111;letter-spacing:-.1px}
.sh-ar-top .sh-tag{display:inline-flex;align-items:center;height:22px;padding:0 7px;border-radius:6px;font-size:11.5px;line-height:17.8px;letter-spacing:.2px}
.sh-ar-ago{margin-left:auto;font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-ar-role{font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-ar-doc{display:flex;align-items:center;gap:8px;padding-top:8px}
.sh-ar-doc-title{font-size:12px;line-height:18.6px;color:#111111;letter-spacing:-.1px;overflow-wrap:anywhere}
.sh-ar-doc .sh-tag{display:inline-flex;align-items:center;height:22px;padding:0 7px;border-radius:6px;font-size:11.5px;line-height:17.8px}
.st-key-ar_list_empty{padding:32px 18px}
.st-key-ar_pager{justify-content:center;align-items:center;padding:10px 0}
.sh-ar-page{font-size:12px;color:#6B7280}
/* 상세: 문서 머리글 */
.st-key-ar_doc_head{justify-content:space-between;align-items:flex-start;flex-wrap:nowrap}
.sh-ar-label{font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-ar-title{display:flex;align-items:center;gap:8px;padding-top:4px;font-size:19px;line-height:29.45px;font-weight:700;color:#111111;letter-spacing:-.3px}
.sh-ar-title .sh-tag,.sh-ar-card .sh-tag{display:inline-flex;align-items:center;height:22px;padding:0 7px;border-radius:6px;font-size:11.5px;line-height:17.8px}
.sh-ar-lock{gap:4px}
.sh-ar-meta{padding-top:2px}
.st-key-ar_doc_head .stButton button{min-height:30px;height:30px;padding:0 10px;gap:6px;background:#FFFFFF;border:1px solid #CED4DA;border-radius:8px;color:#111111}
.st-key-ar_doc_head .stButton button::before{content:"";width:14px;height:14px;flex:none;background:url("app/static/icons/eye.svg") center/contain no-repeat}
.st-key-ar_doc_head .stButton button p{font-size:12.5px;line-height:19.4px;font-weight:700;letter-spacing:-.1px}
.sh-ar-cards{display:flex;gap:16px}
.sh-ar-card{flex:1 1 0;min-width:0;padding:14px 16px;border:1px solid #E9ECEF;border-radius:10px}
.sh-ar-value{padding-top:6px;font-size:14px;line-height:21.7px;font-weight:700;color:#111111;letter-spacing:-.1px}
.sh-ar-subtext{display:flex;align-items:center;gap:6px;font-size:12px;line-height:18.6px;color:#343A40}
.sh-ar-section-title{font-size:12.5px;line-height:19.4px;font-weight:700;color:#343A40;letter-spacing:-.1px}
.sh-ar-reason{margin-top:6px;padding:4px 0 4px 14px;border-left:3px solid #DEE2E6;font-size:14.5px;line-height:24.65px;color:#111111;letter-spacing:-.1px;overflow-wrap:anywhere}
[class*="st-key-access_review_reason_"] label p{font-size:12.5px;line-height:19.4px;font-weight:700;color:#343A40;letter-spacing:-.1px}
[class*="st-key-access_review_reason_"] textarea{font-size:13.5px;letter-spacing:-.1px}
[class*="st-key-access_review_reason_"] [data-testid="stTextAreaRootElement"]{background:#FFFFFF;border:1px solid #CED4DA;border-radius:4px}
[class*="st-key-access_review_reason_"] [data-testid="stTextAreaRootElement"]{min-height:76px}
[class*="st-key-access_review_reason_"] textarea{min-height:74px;padding:10px 11px;background:transparent}
/* 상세: 맨 아래 처리 줄 */
[data-testid="stLayoutWrapper"]:has(>.st-key-ar_footer){margin-top:auto}
.st-key-ar_footer{justify-content:space-between;align-items:center;flex-wrap:nowrap;padding-top:16px;border-top:1px solid #E9ECEF}
.sh-ar-footnote{max-width:420px;font-size:12px;line-height:18.6px;color:#6B7280;letter-spacing:-.1px}
.sh-ar-done{padding-top:16px;border-top:1px solid #E9ECEF}
.st-key-ar_actions{gap:8px;flex-wrap:nowrap}
.st-key-ar_actions button{min-height:36px;height:36px;padding:0 14px;gap:6px;border-radius:8px}
.st-key-ar_actions button p{font-size:13.5px;line-height:20.9px;font-weight:700;letter-spacing:-.1px}
.st-key-ar_actions button[kind="secondary"]{background:#FFFFFF;border:1px solid #CED4DA;color:#111111}
.st-key-ar_actions button[kind="primary"]{border:none;background:#009944;color:#FFFFFF;box-shadow:0 2px 3px rgba(0,153,68,.22)}
.st-key-ar_empty_detail{padding-top:32px}
</style>
"""

_SCREEN_CSS = _CSS_REPORT_VIEW + _CSS_MYPAGE + _CSS_ADMIN_DOCS + _CSS_UPLOAD_MODAL + _CSS_ACCESS_REQUESTS


def apply_theme() -> None:
    """공통 배지와 화면별 스타일을 적용한다. main.py에서만 부른다."""
    st.markdown(_CSS + _SCREEN_CSS, unsafe_allow_html=True)


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
