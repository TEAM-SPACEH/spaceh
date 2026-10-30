"""I-01 OCR의 위치·중복·실패 처리. 외부 모델 호출은 대체한다."""

import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

from PIL import Image
from docx import Document
from pptx import Presentation
from pptx.util import Inches

from app.ingestion.parsers import ocr
from app.ingestion.parsers.docx import parse_docx
from app.ingestion.parsers.pptx import parse_pptx


def image_bytes():
    with Image.new("RGB", (100, 100), "white") as image, io.BytesIO() as buffer:
        image.save(buffer, format="PNG")
        return buffer.getvalue()


class OcrTest(unittest.TestCase):
    def tearDown(self):
        ocr._close_worker()

    @patch.object(ocr, "_process")
    @patch.object(ocr, "_connection")
    def test_duplicate_text_and_empty_lines_are_removed(self, connection, process):
        process.is_alive.return_value = True
        connection.recv.return_value = (True, ["Existing text", "새 글자", "새 글자", " "])
        self.assertEqual(ocr.extract_image_text(image_bytes(), "Existing text"), "새 글자")

    @patch.object(ocr, "_process")
    @patch.object(ocr, "_connection")
    def test_timeout_stops_worker(self, connection, process):
        process.is_alive.return_value = True
        connection.poll.return_value = False
        with self.assertRaises(TimeoutError):
            ocr.extract_image_text(image_bytes())
        process.terminate.assert_called_once()

    @patch.object(ocr, "_process")
    @patch.object(ocr, "_connection")
    def test_model_failure_is_not_empty_success(self, connection, process):
        process.is_alive.return_value = True
        connection.recv.return_value = (False, [])
        with self.assertRaises(RuntimeError):
            ocr.extract_image_text(image_bytes())

    @patch("app.ingestion.parsers.docx.extract_image_text", return_value="이미지 글자")
    def test_docx_paragraph_and_table_images_keep_location(self, extract):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sample.docx"
            doc = Document()
            doc.add_paragraph("본문").add_run().add_picture(io.BytesIO(image_bytes()))
            doc.add_table(1, 1).cell(0, 0).paragraphs[0].add_run().add_picture(io.BytesIO(image_bytes()))
            doc.save(path)
            blocks = parse_docx(path)
            self.assertEqual(blocks[0]["location"], "문단 1")
            self.assertEqual(blocks[1]["location"], "표 2")
            self.assertTrue(all("이미지 글자" in b["text"] for b in blocks))
            self.assertEqual(extract.call_count, 2)

    @patch("app.ingestion.parsers.pptx.extract_image_text", return_value="이미지 글자")
    def test_pptx_image_keeps_slide_and_shape(self, extract):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sample.pptx"
            ppt = Presentation()
            slide = ppt.slides.add_slide(ppt.slide_layouts[6])
            shape = slide.shapes.add_picture(io.BytesIO(image_bytes()), Inches(1), Inches(1))
            ppt.save(path)
            blocks = parse_pptx(path)
            self.assertEqual(blocks[0]["text"], "이미지 글자")
            self.assertEqual(blocks[0]["location"], f"슬라이드 1 이미지 {shape.shape_id}")
