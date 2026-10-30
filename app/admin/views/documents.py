"""A-01 문서 업로드·색인, A-02 문서 목록·삭제·재색인, A-03 그룹사 공유를 한 화면에 합친 관리자 문서 화면 (Figma 07)."""

import html
import logging

import streamlit as st

from app.admin.services.access_service import get_share_scope_name
from app.admin.services.document_service import (
    get_document_filter_options,
    get_document_overview,
    get_upload_companies,
    reindex_failed_documents,
)
from app.admin.views.components.document_filters import render_document_filters
from app.admin.views.components.document_list import notice, render_document_list, show_notice
from app.admin.views.components.document_panel import render_document_panel
from app.admin.views.components.document_upload import clear_upload_files, render_document_upload
from app.admin.views.components.document_labels import DOC_TYPE_NAMES
from app.common.ui import ACCESS_LABELS, card

logger = logging.getLogger(__name__)

# 최근 7일 추가 막대의 높이(px) 범위. 가장 많은 날이 최대, 0건이어도 막대가 보이도록 최소 높이를 둔다.
_SPARK_MIN, _SPARK_MAX = 6, 28


def _spark_html(daily: list[int]) -> str:
    """최근 7일 문서 추가 건수를 작은 막대로 그린다. 가장 최근 날(오늘)만 초록이다."""
    peak = max(daily) or 1
    bars = []
    for index, count in enumerate(daily):
        height = _SPARK_MIN + round((_SPARK_MAX - _SPARK_MIN) * count / peak)
        today = " sh-ad-spark-now" if index == len(daily) - 1 else ""
        bars.append(f'<i class="sh-ad-spark-bar{today}" style="height:{height}px"></i>')
    return f'<span class="sh-ad-spark" aria-hidden="true">{"".join(bars)}</span>'


def _age_text(hours: int) -> str:
    """가장 오래된 대기 요청이 얼마나 지났는지. 하루 미만이면 시간, 한 시간 미만이면 "방금"으로 쓴다."""
    if hours >= 24:
        return f"{hours // 24}일 전"
    if hours >= 1:
        return f"{hours}시간 전"
    return "방금"


def stats_html(overview: dict) -> str:
    """위쪽 카드 4개: 전체 문서·그룹사 공유 중·색인 실패·열람 요청 대기. 숫자와 문서 제목은 escape한다."""
    failed_title = overview["failed_title"]
    if overview["failed"] > 1:
        failed_sub = f"{failed_title} 외 {overview['failed'] - 1}건"
    else:
        failed_sub = failed_title or "실패한 문서가 없습니다."
    pending_sub = (f"가장 오래된 요청 {_age_text(overview['oldest_pending_hours'])}"
                   if overview["pending_requests"] else "대기 중인 요청이 없습니다.")
    cards = [
        ('<div class="sh-ad-stat-label">전체 문서</div>'
         f'<div class="sh-ad-stat-value"><b>{overview["total"]:,}</b>{_spark_html(overview["daily"])}</div>'
         f'<div class="sh-ad-stat-sub">최근 7일 {overview["week_added"]:,}건 추가</div>'),
        ('<div class="sh-ad-stat-label"><i class="sh-ad-dot sh-ad-dot-green"></i>그룹사 공유 중</div>'
         f'<div class="sh-ad-stat-value"><b>{overview["shared"]:,}</b></div>'
         f'<div class="sh-ad-stat-sub">사내 문서 {overview["internal_total"]:,}건 중</div>'),
        ('<div class="sh-ad-stat-label"><i class="sh-ad-dot sh-ad-dot-red"></i>색인 실패</div>'
         f'<div class="sh-ad-stat-value"><b>{overview["failed"]:,}</b></div>'
         f'<div class="sh-ad-stat-sub">{html.escape(failed_sub)}</div>'),
        ('<div class="sh-ad-stat-label"><i class="sh-ad-dot sh-ad-dot-yellow"></i>열람 요청 대기</div>'
         f'<div class="sh-ad-stat-value"><b>{overview["pending_requests"]:,}</b></div>'
         f'<div class="sh-ad-stat-sub">{pending_sub}</div>'),
    ]
    return '<div class="sh-ad-stats">' + "".join(f'<div class="sh-ad-stat">{card}</div>' for card in cards) + "</div>"


def _render_head(user: dict, scope_name: str, failed_count: int) -> None:
    """페이지 머리: 범위 이름·제목·설명과 오른쪽 [실패 문서 재색인]·[문서 올리기]."""
    left, right = st.columns([3, 2], vertical_alignment="bottom")
    left.html(
        f'<div class="sh-r-crumb">{html.escape(scope_name)} 관리</div>'
        '<div class="sh-r-title">문서</div>'
        '<div class="sh-r-desc">보안 등급, 색인 상태, 그룹사 공유를 관리합니다.</div>'
    )
    with right, st.container(key="ad_actions", horizontal=True, horizontal_alignment="right"):
        if st.button("실패 문서 재색인", key="ad_reindex_failed", disabled=failed_count == 0,
                     help=None if failed_count else "색인에 실패한 문서가 없습니다."):
            with st.spinner("실패한 문서를 다시 색인하는 중입니다. 잠시만 기다려 주세요."):
                try:
                    summary = reindex_failed_documents(user)
                except PermissionError:
                    notice("error", "관리자 권한이 없거나 변경되었습니다. 다시 로그인해 주세요.")
                except Exception:
                    logger.exception("A-02 실패 문서 일괄 재색인 실패")
                    notice("error", "실패 문서를 다시 색인하지 못했습니다. 잠시 후 다시 시도해 주세요.")
                else:
                    text = f"실패 문서 {summary['total']}건 중 {summary['done']}건을 다시 색인했습니다."
                    if summary["failed"]:
                        text += f" {summary['failed']}건은 다시 실패했습니다."
                    if summary["skipped"]:
                        text += f" {summary['skipped']}건은 원본이 없어 건너뛰었습니다."
                    notice("success" if not summary["failed"] else "warning", text)
            st.rerun()
        if st.button("문서 올리기", key="ad_upload", type="primary"):
            clear_upload_files()
            render_document_upload(user)


def render_admin_documents(user: dict) -> None:
    """A-01·A-02·A-03 관리자 권한을 확인한 뒤 머리·요약 카드·문서 표·상세 패널을 한 화면에 구성한다."""
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

    try:
        overview = get_document_overview(user)
        scope_name = get_share_scope_name(user)
    except Exception:
        logger.exception("A-02 문서 요약 조회 실패")
        overview, scope_name = None, "관리자"

    show_notice()
    _render_head(user, scope_name, overview["failed"] if overview else 0)
    if overview is not None:
        st.html(stats_html(overview))
    else:
        st.error("요약을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.")

    # 문서 유형·보안 등급은 서비스가 준 코드에 화면 이름을 붙여 {코드: 화면 이름}으로 만든다.
    # 기업 선택지는 권한에 따라 달라서 위에서 따로 받았다.
    options = get_document_filter_options()
    doc_types = {code: DOC_TYPE_NAMES[code] for code in options["doc_types"] if code in DOC_TYPE_NAMES}
    security_levels = {code: ACCESS_LABELS[code] for code in options["security_levels"]}
    with st.container(key="ad_main"):
        table_col, panel_col = st.columns([800, 330])
        with table_col, card("ad_list"):
            filters = render_document_filters(companies, doc_types, security_levels, options["index_statuses"])
            selected = render_document_list(user, filters)
        with panel_col:
            render_document_panel(user, selected)
