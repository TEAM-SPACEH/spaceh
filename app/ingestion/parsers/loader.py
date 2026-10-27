"""I-01 파일 형식에 맞는 파서 호출."""

from pathlib import Path

from app.ingestion.parsers.docx import parse_docx
from app.ingestion.parsers.pdf import parse_pdf
from app.ingestion.parsers.pptx import parse_pptx


def load_document(file_path: str | Path) -> list[dict]:
    """I-01 PDF·DOCX·PPTX를 읽고 검증된 공통 블록 목록을 반환한다."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError("읽을 문서 파일이 없습니다.")
    parsers = {".pdf": parse_pdf, ".docx": parse_docx, ".pptx": parse_pptx}
    parser = parsers.get(path.suffix.lower())
    if parser is None:
        raise ValueError("PDF·DOCX·PPTX 형식만 지원합니다.")
    blocks = parser(path)
    if not blocks:
        raise ValueError("문서에 추출 가능한 텍스트나 표가 없습니다.")
    return blocks
