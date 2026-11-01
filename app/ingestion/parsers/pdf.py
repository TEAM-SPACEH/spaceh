"""I-01 PDF 파싱 (텍스트·표·페이지 위치)."""

import io
import logging
from pathlib import Path

import pdfplumber
from app.ingestion.parsers.ocr import extract_image_text, ocr_document, ocr_limit_reached
from core import config

from app.ingestion.preprocessing.normalizer import (
    normalize_blocks,
    table_to_markdown,
)

logger = logging.getLogger(__name__)


@ocr_document
def parse_pdf(file_path: str | Path) -> list[dict]:
    """I-01 텍스트 PDF에서 표 중복 없이 페이지·좌표 순서로 추출한다."""
    blocks = []
    with pdfplumber.open(file_path) as document:
        for number, page in enumerate(document.pages, 1):
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
            existing = "\n".join(item[3] for item in items)
            seen_images = set()
            for image in page.images:
                if ocr_limit_reached():
                    logger.warning("PDF %s페이지 OCR 문서 한도 또는 모델 준비 상태로 중단합니다.", number)
                    break
                if min(image.get("srcsize", (100, 100))) < config.OCR_MIN_SIDE:
                    continue
                bounds = (max(page.bbox[0], image["x0"]), max(page.bbox[1], image["top"]),
                          min(page.bbox[2], image["x1"]), min(page.bbox[3], image["bottom"]))
                if bounds in seen_images or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
                    continue
                seen_images.add(bounds)
                pixels = (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]) * (config.OCR_RENDER_DPI / 72) ** 2
                if pixels > config.OCR_MAX_PIXELS:
                    logger.warning("PDF %s페이지 OCR 이미지 크기 한도 초과로 건너뜁니다.", number)
                    continue
                rendered = None
                try:
                    rendered = page.crop(bounds).to_image(resolution=config.OCR_RENDER_DPI).original
                    with io.BytesIO() as buffer:
                        rendered.save(buffer, format="PNG")
                        text = extract_image_text(buffer.getvalue(), existing)
                except Exception as error:
                    logger.warning("PDF %s페이지 OCR 이미지 건너뜀 (%s)", number, type(error).__name__)
                    continue
                finally:
                    if rendered is not None:
                        rendered.close()
                if text:
                    items.append((bounds[1], bounds[0], "text", text))
                    existing += "\n" + text
            # shortcut: PDF 제목 추측 안 함, 제목이 필요하면 실제 문서로 판별 규칙 합의.
            for top, left, kind, text in sorted(items, key=lambda item: item[:2]):
                blocks.append({
                    "block_type": kind, "text": text, "page": number,
                    "location": f"p.{number}",
                    "section": "",
                })
    return normalize_blocks(blocks)
