"""A-01·A-02·A-03 관리자 문서 화면(UI v4)이 함께 쓰는 파일 형식 타일·보안 등급 배지·유형 이름."""

import html

from app.common.ui import ACCESS_LABELS

# config.toml의 enableStaticServing으로 static/ 폴더가 app/static/ 주소로 나간다.
LOCK_RED_ICON_URL = "app/static/icons/lock-red.svg"

# 파일 형식 → (타일에 적는 글자, 색 종류). 색은 ui.py의 .sh-ad-type-* 가 정한다.
FORMAT_TILES = {
    "pdf": ("PDF", "pdf"),
    "docx": ("DOC", "doc"),
    "pptx": ("PPT", "ppt"),
    "dart_xml": ("DART", "dart"),
    "xlsx": ("XLS", "etc"),
    "hwp": ("HWP", "etc"),
}

# 문서 유형 이름 (Figma 07·08). 검색 화면의 공통 이름(DOC_TYPE_LABELS)보다 짧게 쓴다.
DOC_TYPE_NAMES = {
    "report": "보고서",
    "disclosure": "공시",
    "manual": "매뉴얼",
    "spec": "사양서",
    "intro": "소개",
    "memo": "메모",
}

_ACCESS_KIND = {"public": "pub", "internal": "int", "confidential": "con"}


def format_tile_html(file_format: str, *, large: bool = False) -> str:
    """파일 형식 타일 (PDF·DOC·PPT·DART). large는 오른쪽 패널·팝업용 큰 타일."""
    label, kind = FORMAT_TILES.get(file_format, (str(file_format).upper()[:4], "etc"))
    size = " sh-ad-type-lg" if large else ""
    return f'<span class="sh-ad-type sh-ad-type-{kind}{size}">{html.escape(label)}</span>'


def access_tag_html(access_level: str) -> str:
    """보안 등급 배지. 기밀에는 자물쇠 아이콘을 붙인다."""
    label = ACCESS_LABELS.get(access_level, access_level)
    kind = _ACCESS_KIND.get(access_level, "etc")
    icon = f'<img src="{LOCK_RED_ICON_URL}" width="11" height="11" alt="">' if access_level == "confidential" else ""
    return f'<span class="sh-ad-tag sh-ad-tag-{kind}">{icon}{html.escape(label)}</span>'
