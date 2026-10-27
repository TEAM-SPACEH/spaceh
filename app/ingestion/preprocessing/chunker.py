"""I-02 마스킹된 블록을 원문 위치·권한을 유지한 검색 청크로 변환한다."""

from bisect import bisect_left, bisect_right
import re


def _split_table(text: str, context: list[str], size: int):
    """긴 Markdown 표를 행 단위로 나누고 머리글·문맥을 반복한다."""
    whole = "\n".join([*context, text])
    if len(whole) <= size:
        yield whole
        return
    lines = text.splitlines()
    header_end = 0
    if (len(lines) > 1 and "-" in lines[1]
            and re.fullmatch(r"[| :\-]+", lines[1])):
        header_end = 2
        # I-01의 빈 Markdown 머리글 다음 첫 원본 행도 문맥으로 반복한다.
        if not lines[0].strip("| ") and len(lines) > 2:
            header_end = 3
    header = lines[:header_end]
    rows = []
    for row in lines[header_end:]:
        candidate = "\n".join([*context, *header, *rows, row])
        if rows and len(candidate) > size:
            yield "\n".join([*context, *header, *rows])
            rows = []
        rows.append(row)
    # shortcut: 한 행·머리글 자체가 크면 상한을 넘겨 보존, 임베딩 연결 시 토큰 한도 검증 필요.
    if rows or header:
        yield "\n".join([*context, *header, *rows])


def split_into_chunks(
    blocks: list[dict], metadata: dict, chunking_config: dict,
) -> list[dict]:
    """I-02 절·페이지별 본문과 행을 보존하는 표 청크를 구성한다."""
    size = chunking_config.get("chunk_size", 800)
    overlap = chunking_config.get("chunk_overlap", 150)
    if (type(size) is not int or type(overlap) is not int
            or size <= 0 or not 0 <= overlap < size):
        raise ValueError("청크 크기는 양수, 겹침은 0 이상 크기 미만이어야 합니다.")
    required = ("doc_id", "company_id", "company_name", "title", "doc_type",
                "access_level", "file_name", "file_format", "source_type")
    if any(not isinstance(metadata.get(key), str) or not metadata[key].strip()
           for key in required):
        raise ValueError("검증된 문서 공통 메타데이터가 필요합니다.")
    if any(type(value) not in (str, int, float, bool)
           for value in metadata.values()):
        raise ValueError("메타데이터에는 문자열·숫자·bool만 허용합니다.")
    if metadata["doc_type"] not in {
        "report", "disclosure", "manual", "spec", "intro", "memo",
    }:
        raise ValueError("지원하지 않는 문서 유형입니다.")
    if metadata["access_level"] not in {"public", "internal", "confidential"}:
        raise ValueError("지원하지 않는 보안 등급입니다.")
    if type(metadata.get("is_group_shared")) is not bool:
        raise ValueError("공유 여부는 bool이어야 합니다.")
    if metadata["is_group_shared"] and metadata["access_level"] != "internal":
        raise ValueError("그룹사 공유는 internal 문서만 가능합니다.")

    chunks = []
    group = []
    group_key = None
    recent = []
    unit = None
    context_key = None

    def append_chunk(text, sources, kind, section):
        """본문 범위의 시작·끝 위치와 공통 권한을 새 메타데이터에 복사한다."""
        if not text.strip():
            return
        index = len(chunks) + 1
        first, last = sources[0], sources[-1]
        location = first["location"]
        if location != last["location"]:
            location += " ~ " + last["location"]
        # 입력 블록의 추가 필드가 등록된 회사·권한 정보를 덮어쓰지 못하게 한다.
        chunk_metadata = {**metadata, "chunk_index": index,
                          "page": first["page"], "location": location,
                          "section": section, "block_type": kind}
        header = f"[{metadata['company_name']} · {metadata['title']} · {location}]"
        chunks.append({"chunk_id": f"{metadata['doc_id']}#{index:04d}",
                       "text": header + "\n" + text,
                       "metadata": chunk_metadata})

    def flush_text():
        """그룹 본문을 분할하며 각 구간에 실제로 포함된 블록 위치를 연결한다."""
        if not group:
            return
        text = "\n".join(block["text"] for block in group)
        starts, ends = [], []
        cursor = 0
        for block in group:
            starts.append(cursor)
            # 블록 사이 줄바꿈은 앞 블록에 귀속해 출처 없는 구간을 만들지 않는다.
            cursor += len(block["text"]) + 1
            ends.append(cursor)
        start = 0
        while start < len(text):
            stop = min(start + size, len(text))
            first = bisect_right(ends, start)
            last = bisect_left(starts, stop)
            append_chunk(text[start:stop], group[first:last], "text",
                         group[0]["section"])
            if stop == len(text):
                break
            start = stop - overlap
        group.clear()

    for block in blocks:
        if not isinstance(block, dict):
            raise ValueError("블록은 dict 형식이어야 합니다.")
        if any(not isinstance(block.get(key), str)
               for key in ("text", "section", "location", "block_type")):
            raise ValueError("블록 내용·제목·위치·유형은 문자열이어야 합니다.")
        if (type(block.get("page")) is not int or block["page"] < 1
                or not block["location"].strip()):
            raise ValueError("블록에는 1 이상 위치 번호와 원문 위치가 필요합니다.")
        if block["block_type"] not in {"text", "title", "table"}:
            raise ValueError("지원하지 않는 블록 유형입니다.")
        if not block["text"].strip():
            continue
        section = block["section"]
        if (block["page"], section) != context_key:
            recent, unit = [], None
            context_key = (block["page"], section)

        if block["block_type"] == "table":
            flush_text()
            # 제목을 추측하지 않고 직전 같은 페이지의 두 블록을 문맥으로 보존한다.
            context = [section] if section else []
            context.extend(item["text"] for item in recent)
            if unit is not None:
                context.append(unit["text"])
            context = list(dict.fromkeys(context))
            sources = [*recent, block]
            for text in _split_table(block["text"], context, size):
                append_chunk(text, sources, "table", section)
            recent = []
            continue

        by_page = metadata["doc_type"] == "intro" or not section
        key = ("page", block["page"]) if by_page else ("section", section)
        new_title = block["block_type"] == "title"
        if group and (key != group_key or (new_title and not by_page)):
            flush_text()
        if new_title:
            recent, unit = [], None
        group.append(block)
        group_key = key
        recent = [*recent, block][-2:]
        if re.search(r"단위\s*[:：]", block["text"]):
            unit = block
    flush_text()
    return chunks
