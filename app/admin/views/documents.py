"""A-01 문서 업로드·색인, A-02 문서 목록·삭제·재색인, A-03 그룹사 공유 화면."""

import streamlit as st

from app.admin.services.document_service import get_document_filter_options, get_upload_companies
from app.admin.views.components.document_filters import render_document_filters
from app.admin.views.components.document_list import render_document_list
from app.admin.views.components.document_upload import clear_upload_files, render_document_upload
from app.admin.views.sharing import render_admin_sharing
from app.common.ui import ACCESS_LABELS, DOC_TYPE_LABELS, page_header


def render_admin_documents(user: dict) -> None:
    """A-01·A-02 관리자 권한을 확인한 뒤 업로드 버튼과 필터·문서 목록을 구성한다. 공유 설정(A-03)은 탭으로 둔다."""
    page_header("문서", "보안 등급과 색인 상태를 확인하고 문서를 등록합니다.")
    try:
        # 관리자 권한을 DB 에서 다시 확인하고, 이 관리자가 다룰 수 있는 기업(계열사 관리자는 자사만)을 받아 온다.
        # A-01 업로드와 같은 규칙이라 같은 함수를 쓴다. 권한이 없으면 아래 화면은 그리지 않는다.
        companies = get_upload_companies(user)
    except PermissionError:
        st.warning("관리자 권한이 없거나 변경되었습니다. 다시 로그인해 주세요.")
        return
    except Exception:
        st.error("관리자 권한을 확인할 수 없습니다. DB 연결을 확인해 주세요.")
        return
    # 탭 2개: 문서 목록(A-01 업로드·A-02 조회·삭제·재색인)과 그룹사 공유(A-03).
    # A-03 화면은 별도 파일(sharing.py)을 그대로 불러 쓰고 여기서는 자리만 만든다.
    list_tab, share_tab = st.tabs(["문서 목록", "그룹사 공유"])
    with list_tab:
        if st.button("문서 올리기", type="primary", icon=":material/upload:"):
            clear_upload_files()
            render_document_upload(user)
        # 문서 유형·보안 등급은 서비스가 준 코드에 공통 화면 이름(DOC_TYPE_LABELS·ACCESS_LABELS)을 붙여 {코드: 화면 이름}으로 만든다.
        # 기업 선택지는 권한에 따라 달라서 위에서 따로 받았다.
        options = get_document_filter_options()
        doc_types = {code: DOC_TYPE_LABELS[code] for code in options["doc_types"]}
        security_levels = {code: ACCESS_LABELS[code] for code in options["security_levels"]}
        filters = render_document_filters(companies, doc_types, security_levels, options["index_statuses"])
        # 필터 값으로 목록을 조회해 표시한다. 삭제·재색인 요청도 이 안에서 서비스를 부른다. 이 화면은 SQL 을 직접 실행하지 않는다.
        render_document_list(user, filters)
    with share_tab:
        render_admin_sharing(user)
