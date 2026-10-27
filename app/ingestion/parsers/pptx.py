"""I-01 PPTX 파싱 (슬라이드 번호)."""

from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from app.ingestion.preprocessing.normalizer import (
    normalize_blocks,
    table_to_markdown,
)


def _iter_shapes(shapes):
    for shape in sorted(shapes, key=lambda item: (item.top, item.left)):
        if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_shapes(shape.shapes)
        else:
            yield shape


def parse_pptx(file_path: str | Path) -> list[dict]:
    """I-01 슬라이드의 텍스트·표를 위→아래, 왼쪽→오른쪽으로 추출한다."""
    blocks = []
    for number, slide in enumerate(Presentation(file_path).slides, 1):
        title = slide.shapes.title
        section = title.text.strip() if title is not None else ""
        for shape in _iter_shapes(slide.shapes):
            if shape.has_table:
                kind = "table"
                rows = [
                    ["" if cell.is_spanned else cell.text for cell in row.cells]
                    for row in shape.table.rows
                ]
                text = table_to_markdown(rows)
            elif shape.has_text_frame:
                is_title = title is not None and shape.shape_id == title.shape_id
                kind = "title" if is_title else "text"
                text = shape.text.replace("\v", "\n")
            else:
                continue
            blocks.append({
                "block_type": kind, "text": text, "page": number,
                "location": f"슬라이드 {number} · 개체 {shape.shape_id}",
                "section": section,
            })
    return normalize_blocks(blocks)
