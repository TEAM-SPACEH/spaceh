"""I-01 DOCX 파싱 (문단·표 순번)."""

from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from app.ingestion.preprocessing.normalizer import (
    normalize_blocks,
    table_to_markdown,
)


def _table_rows(table: Table) -> list[list[str]]:
    rows = []
    seen = set()
    for row in table.rows:
        values = [""] * row.grid_cols_before
        for cell in row.cells:
            # 병합 연속 셀이 같은 XML을 가리키므로 시작 셀에만 내용을 남긴다.
            if cell._tc in seen:
                values.append("")
                continue
            seen.add(cell._tc)
            content = []
            for item in cell.iter_inner_content():
                if isinstance(item, Paragraph):
                    content.append(item.text)
                else:
                    content.append(table_to_markdown(_table_rows(item)))
            values.append("\n".join(content))
        rows.append(values + [""] * row.grid_cols_after)
    return rows


def parse_docx(file_path: str | Path) -> list[dict]:
    """I-01 DOCX 본문의 문단·표를 원문 순서와 제목 정보로 추출한다."""
    blocks = []
    section = ""
    for index, item in enumerate(Document(file_path).iter_inner_content(), 1):
        if isinstance(item, Table):
            kind = "table"
            text = table_to_markdown(_table_rows(item))
        else:
            style = item.style.name if item.style is not None else ""
            is_title = style.startswith("Heading") or style == "Title"
            kind = "title" if is_title else "text"
            text = item.text
            if kind == "title" and text.strip():
                section = text.strip()
        blocks.append({
            "block_type": kind, "text": text, "page": index,
            "location": f"{'표' if kind == 'table' else '문단'} {index}",
            "section": section,
        })
    return normalize_blocks(blocks)
