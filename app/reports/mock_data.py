"""R-02·R-04 목(가짜) 데이터. R-01 수집·R-03 각주 기능이 완성되면 이 파일을 지운다."""

# ─────────────────────────────────────────────────────────────
# 김소은의 R-01(문서 수집)·R-03(각주)이 아직 없어서 가짜로 대신하는 것:
#   1) select_section_evidence() ← 섹션별 근거 고르기 (진짜: services/report_collector)
#   2) MOCK_REQUEST, MOCK_COLLECTION ← 확인용 화면·테스트에서 쓸 가짜 조건과 수집 결과
#   3) build_mock_report(), make_quote() ← 보고서 전체 각주 번호 매기기·원문 인용
#                                          (진짜: services/citation_mapper의 map_footnotes·renumber_footnotes)
#
# 진짜가 완성되면 import 줄만 바꾸고 이 파일은 지워요.
# 청크 내용은 모두 지어낸 "가상 자료"예요. 실제 회사 정보가 아니에요.
# ─────────────────────────────────────────────────────────────

import re
from dataclasses import replace  # replace(객체, 칸=값): 일부 칸만 바꾼 "복사본"을 만들어요
from datetime import date

from app.reports.models.report_models import (
    Chunk, CollectionResult, Footnote, Report, ReportRequest, ReportTemplate, Section, SectionType,
)

# 원문 인용 최대 글자 수 (팀 결정: 마스킹된 청크 본문에서 150자 정도)
QUOTE_MAX_CHARS = 150

# 청크 맨 앞의 출처 머리말 "[현대엘리베이터 · 2025 사업보고서 · p.12] " 를 찾는 패턴.
#   ^\s*\[      맨 앞의 "["
#   [^\]]*·[^\]]*  "]"가 아닌 글자들 사이에 "·"가 하나 이상 (일반 대괄호 글과 구분하려고)
#   \]\s*       "]"와 뒤의 빈칸
CHUNK_HEADER_PATTERN = re.compile(r"^\s*\[[^\]]*·[^\]]*\]\s*")
CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def select_section_evidence(section_type: SectionType, collection: CollectionResult) -> list[Chunk]:
    """[임시] 섹션별 근거 선별. 진짜는 김소은이 report_collector에 만든다 (R-01)."""
    # 진짜는 섹션 목적(현황=회사별 사업, 시너지=공통 주제)에 맞게 골라 주지만,
    # 지금은 모아 온 청크를 전부 그대로 돌려줘요.
    return collection.chunks


def make_quote(text: str, max_chars: int = QUOTE_MAX_CHARS) -> str:
    """[임시 R-03] 청크 본문에서 원문 인용을 만든다. 앞머리를 떼고 max_chars자로 자른다."""
    # 청크 본문은 색인할 때(I-03) 이미 마스킹돼 있어서 여기서 따로 마스킹하지 않아요.
    # ① 앞머리 [회사 · 제목 · 위치] 떼기: 안 떼면 머리말이 150자 중 상당 부분을 차지해요.
    text = CHUNK_HEADER_PATTERN.sub("", text, count=1)
    # ② 줄바꿈·여러 빈칸을 빈칸 하나로: \s+ = 빈칸·줄바꿈이 1개 이상 이어진 곳
    text = re.sub(r"\s+", " ", text).strip()
    # ③ 길면 자르고 "…"를 붙여요. rstrip()은 자른 끝에 남은 빈칸을 지워요.
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "…"


def build_mock_report(request: ReportRequest, sections: list[Section]) -> Report:
    """[임시 R-03] 섹션마다 [1]부터인 번호를 보고서 전체 번호로 다시 매기고 각주 목록을 만든다."""
    # 진짜는 김소은의 map_footnotes()·renumber_footnotes()가 해요. 같은 규칙을 따라요.
    #   - 본문에 처음 나온 순서대로 [1], [2] … 를 다시 매겨요.
    #   - 같은 청크를 여러 섹션에서 인용하면 같은 번호를 써요.
    #   - 존재하지 않는 번호를 가리키는 표시는 지워요.
    # 예: 개요 "…[1]"(ELV) / 현황 "…[1]"(MVX) → 개요 "…[1]" / 현황 "…[2]"
    numbers_by_chunk: dict[str, int] = {}  # 청크 ID → 보고서 전체 번호
    footnotes: list[Footnote] = []
    new_sections: list[Section] = []

    for section in sections:
        if not section.has_evidence:
            new_sections.append(section)  # 근거 없는 섹션은 바꿀 번호가 없어요
            continue

        def to_global(match: re.Match) -> str:
            """섹션 안 번호 [n] 하나를 보고서 전체 번호로 바꾼다."""
            local = int(match.group(1))
            if not 1 <= local <= len(section.evidence):
                return ""  # 존재하지 않는 근거를 가리키는 번호는 지워요
            chunk = section.evidence[local - 1]     # [1] = evidence[0]
            if chunk.chunk_id not in numbers_by_chunk:
                # 처음 나온 청크 → 새 번호를 주고 각주를 만들어요.
                number = len(footnotes) + 1
                numbers_by_chunk[chunk.chunk_id] = number
                source = section.sources[local - 1]  # S-04 출처 모양 (회사·파일·위치·doc_id)
                footnotes.append(Footnote(
                    number=number,
                    company=str(source.get("company") or ""),
                    company_id=str(source.get("company_id") or ""),
                    filename=str(source.get("filename") or ""),
                    location=str(source.get("location") or ""),
                    quote=make_quote(chunk.text),
                    text=chunk.text,
                    doc_id=str(source.get("doc_id") or ""),
                    chunk_id=chunk.chunk_id,
                ))
            return f"[{numbers_by_chunk[chunk.chunk_id]}]"

        # re.sub에 함수를 넘기면, 찾은 [n]마다 그 함수가 돌려준 글자로 바꿔요.
        new_sections.append(replace(section, body=CITATION_PATTERN.sub(to_global, section.body)))

    return Report(request=request, sections=new_sections, footnotes=footnotes)


# 가짜 보고서 생성 조건: "스마트 물류" 주제로 3사 종합 보고서
MOCK_REQUEST = ReportRequest(
    template=ReportTemplate.COMPREHENSIVE,
    topic="스마트 물류",
    company_ids=["ELV", "MVX", "HRI"],  # 회사 코드 (이름은 get_company_names()가 찾아요)
    start_date=date(2025, 1, 1),
    end_date=date(2025, 12, 31),
)

# 가짜 수집 결과. text 맨 앞의 [회사 · 제목 · 위치]는 팀 청크 규칙(data-model.md)을 따랐어요.
# metadata 칸 이름도 data-model.md §4(Chroma 메타데이터)와 똑같이 맞췄어요.
#   company_id = 회사 코드(ELV/MVX/HRI). S-04 출처 패널이 이 값으로 회사별 카드를 묶어요.
#   doc_id = 문서 번호(글자). S-05 원문 뷰어가 이 값으로 원문을 찾아요.
#   file_name·location = 출처에 보일 파일명·위치
MOCK_COLLECTION = CollectionResult(
    chunks=[
        Chunk(
            chunk_id="doc-elv#0003",
            text="[현대엘리베이터 · 2025 사업보고서(가상) · p.12] "
                 "물류센터용 고속 화물 승강기 공급을 확대하고 있으며, "
                 "2025년 물류 시설 대상 수주가 전년 대비 증가함.",
            metadata={
                "company_id": "ELV", "company_name": "현대엘리베이터", "doc_id": "doc-elv",
                "title": "2025 사업보고서(가상)", "file_name": "elv_2025_report.pdf",
                "page": 12, "location": "p.12",
            },
        ),
        Chunk(
            chunk_id="doc-mvx#0010",
            text="[현대무벡스 · 2025 반기보고서(가상) · II. 사업의 내용] "
                 "스마트 물류 자동화 설비(자동창고, 컨베이어) 사업을 주력으로 하며, "
                 "물류센터 자동화 수요 증가에 대응해 설비 공급을 늘리고 있음.",
            metadata={
                "company_id": "MVX", "company_name": "현대무벡스", "doc_id": "doc-mvx",
                "title": "2025 반기보고서(가상)", "file_name": "2025 반기보고서(가상)",
                "page": 0, "location": "II. 사업의 내용",
            },
        ),
        Chunk(
            chunk_id="doc-hri#0002",
            text="[현대경제연구원 · 물류산업 전망 보고서(가상) · p.5] "
                 "국내 물류센터의 자동화율은 아직 낮은 수준이며, "
                 "인력난으로 자동화 투자 수요가 계속 늘어날 것으로 전망됨.",
            metadata={
                "company_id": "HRI", "company_name": "현대경제연구원", "doc_id": "doc-hri",
                "title": "물류산업 전망 보고서(가상)", "file_name": "hri_logistics_outlook.pdf",
                "page": 5, "location": "p.5",
            },
        ),
    ],
    empty_companies=[],
)
