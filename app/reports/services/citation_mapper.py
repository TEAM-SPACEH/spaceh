"""R-03·R-04 각주 매핑, 각주 번호 정리, 원문 연결 정보, 섹션 앵커 생성."""

# ─────────────────────────────────────────────────────────────
# 이 파일은 R-03(김소은)과 R-04(박예원)가 같이 써요. (김소은님과 합의)
#   - map_footnotes(), renumber_footnotes(), build_source_link() ..... R-03 (김소은) ← 아직 없음
#   - build_section_anchor() ......................................... R-04 (박예원)
#
# R-03 함수가 생기기 전까지 보고서 전체 번호 매기기는 mock_data.build_mock_report()가 대신해요.
# services 파일이라 화면 코드(st.*)는 쓰지 않아요. (팀 규칙)
# ─────────────────────────────────────────────────────────────

from app.reports.models.report_models import SectionType

# 앵커 ID 앞부분. 샘플 양식(정기·감사보고서)의 "#sec-…" 모양을 따랐어요.
SECTION_ANCHOR_PREFIX = "sec-"


def build_section_anchor(section_ref: SectionType) -> str:
    """R-04 요약 항목의 section_ref를 상세보고서 섹션의 앵커 ID로 바꾼다."""
    # 예: SectionType.STATUS → "sec-status"
    # 화면의 섹션 이동, Markdown 파일 안 링크(#sec-status), DOCX 책갈피(R-05)가
    # 모두 같은 ID를 써야 해서 이 한 곳에서만 만들어요. (명세서: "한 곳에서만 만든다")
    # 영어 값(value)을 써서 HTML id·DOCX 책갈피 이름으로 써도 문제가 없어요.
    return f"{SECTION_ANCHOR_PREFIX}{SectionType(section_ref).value}"
