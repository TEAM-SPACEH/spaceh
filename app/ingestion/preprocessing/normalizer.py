"""I-01 공통 블록 검증·공백 정리·Markdown 표 변환."""

import re


def normalize_text(text: str) -> str:
    """I-01·I-03 줄바꿈을 보존하면서 마스킹에 쓰일 공백을 동일하게 정리한다."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(re.sub(r"[^\S\n]+", " ", line).strip()
                     for line in text.split("\n")).strip()


def normalize_blocks(blocks: list[dict]) -> list[dict]:
    """I-01 블록을 검증하고 위치·줄바꿈·표 구조를 유지해 정리한다."""
    normalized = []
    for block in blocks:
        if block.get("block_type") not in {"text", "table", "title"}:
            raise ValueError("지원하지 않는 블록 유형입니다.")
        if type(block.get("page")) is not int or block["page"] < 1:
            raise ValueError("블록 위치 번호는 1 이상의 정수여야 합니다.")
        if any(not isinstance(block.get(key), str)
               for key in ("text", "location", "section")):
            raise ValueError("블록의 내용·위치·절 제목은 문자열이어야 합니다.")
        if not block["location"].strip():
            raise ValueError("블록의 원문 위치가 필요합니다.")
        # 마스킹의 같은 줄 판정에 쓰이므로 줄바꿈은 합치지 않는다.
        text = normalize_text(block["text"])
        if text:
            normalized.append({
                "block_type": block["block_type"],
                "text": text,
                "page": block["page"],
                "location": block["location"].strip(),
                "section": normalize_text(block["section"]),
            })
    return normalized


def table_to_markdown(rows: list[list[str | None]]) -> str:
    """I-01 빈 셀과 열 수를 보존하며 셀 격자를 Markdown 표로 바꾼다."""
    width = max((len(row) for row in rows), default=0)
    if not width:
        return ""
    escaped_rows = []
    for row in rows:
        cells = []
        for value in row:
            text = "" if value is None else value
            text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
            # PPTX 셀은 소프트 줄바꿈을 수직 탭으로 반환한다.
            text = text.replace("\v", "\n")
            text = text.replace("\\", "\\\\").replace("|", "\\|")
            cells.append(text.replace("\n", "<br>"))
        escaped_rows.append(cells + [""] * (width - len(cells)))
    if not any(cell for row in escaped_rows for cell in row):
        return ""
    # 첫 행이 데이터일 수도 있으므로 빈 헤더를 사용해 모든 원본 행을 본문에 둔다.
    lines = [[""] * width, ["---"] * width, *escaped_rows]
    return "\n".join("| " + " | ".join(row) + " |" for row in lines)
