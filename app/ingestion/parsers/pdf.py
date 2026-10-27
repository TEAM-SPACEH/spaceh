"""I-01 PDF 파싱 (텍스트·표·페이지 위치)."""

import logging
from pathlib import Path

import pdfplumber

from app.ingestion.preprocessing.normalizer import (
    normalize_blocks,
    table_to_markdown,
)

logger = logging.getLogger(__name__)


def parse_pdf(file_path: str | Path) -> list[dict]:
    """I-01 텍스트 PDF에서 표 중복 없이 페이지·좌표 순서로 추출한다."""
    blocks = []
    with pdfplumber.open(file_path) as document:
        for number, page in enumerate(document.pages, 1):
            if page.images and not page.chars:
                # 이미지 표지 때문에 나머지 텍스트 페이지까지 잃지 않게 한다.
                logger.warning("PDF %s페이지는 이미지뿐이라 건너뜁니다. OCR이 필요합니다.",
                               number)
                continue
            tables = page.find_tables()

            def outside_tables(obj):
                """I-01 중심점이 표 안에 있는 문자를 본문 추출에서 제외한다."""
                x = (obj["x0"] + obj["x1"]) / 2
                y = (obj["top"] + obj["bottom"]) / 2
                return not any(t.bbox[0] <= x <= t.bbox[2]
                               and t.bbox[1] <= y <= t.bbox[3] for t in tables)

            # 표는 별도 블록으로 넣으므로 본문에서 같은 문자를 이중 수집하지 않는다.
            items = [(line["top"], line["x0"], "text", line["text"])
                     for line in page.filter(outside_tables).extract_text_lines()]
            items.extend(
                (t.bbox[1], t.bbox[0], "table", table_to_markdown(t.extract()))
                for t in tables
            )
            # shortcut: PDF 제목 추측 안 함, 제목이 필요하면 실제 문서로 판별 규칙 합의.
            for top, left, kind, text in sorted(items, key=lambda item: item[:2]):
                blocks.append({
                    "block_type": kind, "text": text, "page": number,
                    "location": f"p.{number}",
                    "section": "",
                })
    return normalize_blocks(blocks)
