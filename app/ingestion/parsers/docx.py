"""I-01 DOCX 파싱 (문단·표 순번)."""

from pathlib import Path
import logging

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from app.ingestion.parsers.ocr import extract_image_text, ocr_document

from app.ingestion.preprocessing.normalizer import (
    normalize_blocks,
    table_to_markdown,
)

logger = logging.getLogger(__name__)


def _paragraph_text(paragraph: Paragraph) -> str:
    """문단 XML 순서대로 글자와 이미지 OCR 결과를 연결한다."""
    parts = []
    existing = paragraph.text
    for element in paragraph._p.iter():
        if any(parent.tag in (
            qn("w:txbxContent"),
            "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback",
        ) for parent in element.iterancestors()):
            continue
        if element.tag == "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t":
            parts.append(element.text or "")
        elif element.tag == qn("w:tab") and element.getparent().tag == qn("w:r"):
            parts.append("\t")
        elif element.tag in (qn("w:br"), qn("w:cr")) and element.getparent().tag == qn("w:r"):
            parts.append("\n")
        elif element.tag == "{http://schemas.openxmlformats.org/drawingml/2006/main}blip":
            relation = element.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
            if not relation:
                continue
            try:
                data = paragraph.part.related_parts[relation].blob
            except KeyError:
                logger.warning("DOCX 이미지 관계가 없어 해당 그림을 건너뜁니다.")
                continue
            image_text = extract_image_text(data, existing)
            if image_text:
                parts.append("\n" + image_text + "\n")
                existing += "\n" + image_text
    return "".join(parts)


def _table_rows(table: Table) -> list[list[str]]:
    """I-01 병합 셀 중복을 없애고 중첩 표를 포함한 셀 격자를 만든다."""
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
            # cell.text에는 중첩 표가 빠지므로 셀 내부도 문서 순서로 읽는다.
            for item in cell.iter_inner_content():
                if isinstance(item, Paragraph):
                    content.append(_paragraph_text(item))
                else:
                    content.append(table_to_markdown(_table_rows(item)))
            values.append("\n".join(content))
        rows.append(values + [""] * row.grid_cols_after)
    return rows


@ocr_document
def parse_docx(file_path: str | Path) -> list[dict]:
    """I-01 DOCX 본문의 문단·표를 원문 순서와 제목 정보로 추출한다."""
    blocks = []
    section = ""
    # 빈 문단도 순번에 포함해야 원문 위치가 내용 정리에 따라 바뀌지 않는다.
    for index, item in enumerate(Document(file_path).iter_inner_content(), 1):
        if isinstance(item, Table):
            kind = "table"
            text = table_to_markdown(_table_rows(item))
        else:
            style = item.style.name if item.style is not None else ""
            is_title = style.startswith("Heading") or style == "Title"
            kind = "title" if is_title else "text"
            text = _paragraph_text(item)
            if kind == "title" and text.strip():
                section = text.strip()
        blocks.append({
            "block_type": kind, "text": text, "page": index,
            "location": f"{'표' if kind == 'table' else '문단'} {index}",
            "section": section,
        })
    return normalize_blocks(blocks)
