"""R-01~R-04 보고서 데이터 모델: 양식, 섹션 종류, 생성 조건, 수집 결과, 섹션, 각주, 보고서, 1페이지 요약."""

# ─────────────────────────────────────────────────────────────
# models 파일 = 함수들이 주고받는 "그릇" 모음이에요.
# 그릇 모양을 한 곳에 정해 두면, 여러 사람이 만든 함수도 서로 잘 맞물려요.
#
# 누가 정하는 그릇인지:
#   - ReportTemplate, SectionType, Section, Report  R-02 (박예원)
#   - SummaryItem, ExecSummary .................... R-04 (박예원)
#   - Footnote .................................... R-03 (김소은) ← 📌 R-04 화면 때문에 먼저 만들었어요
#   - ReportRequest, CollectionResult ............. R-01 (김소은) ← 📌 모양 꼭 맞춰 보기
#   - Chunk ....................................... 공통 models (data-model.md에 정해진 모양)
#                                                  공통 models에 생기면 여기서 지우고 그걸 불러와요.
# ─────────────────────────────────────────────────────────────

from dataclasses import dataclass, field  # dataclass: 데이터를 담는 클래스를 쉽게 만드는 도구
from datetime import date                 # 날짜 자료형 (예: date(2025, 1, 1))
from enum import Enum                     # Enum: 정해진 값 중에서만 고르게 하는 도구


class ReportTemplate(str, Enum):
    """R-02 보고서 양식."""
    # Enum을 쓰면 "comprehensive"를 "comprehensiv"로 잘못 쳐서 생기는 실수를 막을 수 있어요.
    # (str, Enum)으로 만들면 글자처럼 비교하고 DB에 저장할 수도 있어요.
    COMPREHENSIVE = "comprehensive"  # 종합 보고서
    QUARTERLY = "quarterly"          # 분기 실적 보고서


class SectionType(str, Enum):
    """R-02 보고서 섹션 종류."""
    OVERVIEW = "overview"        # 개요
    STATUS = "status"            # 현황
    SYNERGY = "synergy"          # 시너지
    ADVICE = "advice"            # 제언
    PERFORMANCE = "performance"  # 실적 비교 (분기 실적 보고서용, 📌 임시)


@dataclass
class Chunk:
    """[임시] 검색 단위 청크. 공통 models에 생기면 그것으로 바꾼다."""
    chunk_id: str   # 예: "17#0003" (17번 문서의 3번째 조각)
    text: str       # 맨 앞에 "[회사명 · 제목 · 위치]" 한 줄이 붙은 본문
    metadata: dict  # 회사·문서·페이지 등 부가 정보 (Chroma 메타데이터)


@dataclass
class ReportRequest:
    """R-01 보고서 생성 조건 (양식·주제·회사·기간)."""
    template: ReportTemplate  # 양식
    topic: str                # 주제 (예: "스마트 물류")
    # 대상 회사 코드 목록 (예: ["ELV", "MVX", "HRI"]).
    # 이름이 아니라 코드를 쓰는 이유: A-07로 계열사를 추가·수정하면 이름은 바뀔 수 있지만 코드는 그대로예요.
    # #80(통합 검색 출처)도 회사를 company_id로 구분해요. 📌 R-01(김소은)도 이 모양으로 채워 줘야 해요.
    company_ids: list[str]
    start_date: date          # 기간 시작일
    end_date: date            # 기간 종료일


@dataclass
class CollectionResult:
    """R-01 회사별 균형 수집 결과."""
    chunks: list[Chunk]  # 모아 온 근거 청크 전체
    # field(default_factory=list): 값을 안 넣으면 "새 빈 리스트"로 시작해요.
    # 그냥 = [] 로 쓰면 모든 객체가 리스트 하나를 같이 써 버리는 버그가 생겨서 이렇게 써요.
    empty_companies: list[str] = field(default_factory=list)  # 근거가 0건인 회사 코드


@dataclass
class Section:
    """R-02 보고서 섹션 (종류·제목·본문·근거)."""
    section_type: SectionType  # 섹션 종류
    title: str                 # 화면에 보일 한글 제목 (예: "현황")
    body: str                  # AI가 쓴 본문. 문장 끝에 [1], [2] ... 가 붙어 있어요.
    # 본문의 [1]은 evidence[0], [2]는 evidence[1]을 가리켜요.
    # 김소은(R-03)이 이 목록으로 [번호] → 각주(회사·파일·위치)를 만들어요.
    evidence: list[Chunk] = field(default_factory=list)
    has_evidence: bool = True  # False면 "근거 자료 없음" 섹션
    # evidence를 S-04 답변 출처(sources)와 똑같은 모양으로 바꾼 목록이에요.
    #   {"text", "company", "company_id", "filename", "location", "doc_id", "chunk_id", "citation_number"}
    # 같은 모양이라 보고서 화면에서 S-04 출처 패널(render_rag_source_panel)과
    # S-05 원문 뷰어(render_selected_source)를 고치지 않고 그대로 쓸 수 있어요.
    sources: list[dict] = field(default_factory=list)
    # True면 "검증에 실패한 문장 일부를 빼고 남긴 섹션"이에요.
    # 화면·요약(R-04)·내보내기(R-05)에서 "일부 문장이 검증에 실패해 제외됨" 유의사항을 보여 줄 때 써요.
    partial: bool = False


@dataclass
class Footnote:
    """R-03 각주 한 개: 보고서 전체 번호·회사·파일·위치·원문 인용."""
    # 명세서: "Footnote는 각주 번호·회사명·파일명·위치·인용 문장·원문 연결 정보를 담는다."
    number: int        # 보고서 전체에서 하나뿐인 번호. 본문의 [3]이 이 번호예요.
    company: str       # 회사명 (예: "현대엘리베이터")
    company_id: str    # 회사 코드 (예: "ELV")
    filename: str      # 파일명
    location: str      # 문서 안 위치 (예: "p.12")
    quote: str         # 원문 인용: 청크 앞머리 [회사 · 제목 · 위치]를 떼고 150자로 자른 글
    text: str          # 청크 본문 전체. 요약의 수치 확인과 원문 뷰어의 근거 문단 하이라이트에 써요.
    doc_id: str        # 원문 연결 정보: S-05 원문 뷰어가 이 값으로 원문(내부 문서·DART)을 찾아요.
    chunk_id: str      # 같은 청크를 여러 번 인용하면 같은 번호로 묶을 때 써요.


@dataclass
class SummaryItem:
    """R-04 1페이지 요약 항목 한 개 (핵심 내용 / 계열사별 시사점 / 권고안)."""
    kind: str                    # "key" 핵심 내용 / "company" 계열사별 시사점 / "advice" 권고안
    text: str                    # 문장마다 [n]. 번호는 상세보고서와 같은 보고서 전체 각주 번호예요.
    section_ref: SectionType     # [상세 보기]를 누르면 이동할 상세보고서 섹션
    company_id: str | None = None  # 계열사별 시사점일 때만 회사 코드


@dataclass
class ExecSummary:
    """R-04 1페이지 요약: 항목 목록과 코드가 쓴 유의사항."""
    items: list[SummaryItem] = field(default_factory=list)
    # 근거 없는 섹션·일부 문장 제외 섹션·근거 없는 회사처럼 AI가 아니라 코드가 쓰는 안내예요.
    notes: list[str] = field(default_factory=list)


@dataclass
class Report:
    """R-02 보고서 전체: 조건·섹션·각주·1페이지 요약."""
    # 📌 명세서의 작성자·최고 보안 등급은 저장 기능(report_repository)을 만들 때 추가해요.
    request: ReportRequest
    # ⚠️ Report 안의 섹션 본문 [n]은 "보고서 전체 번호"예요(= footnotes의 number).
    #    섹션마다 1부터 매기던 R-02 번호와 다르니, 번호로 근거를 찾을 때는 footnotes를 써요.
    sections: list[Section]
    footnotes: list[Footnote] = field(default_factory=list)
    exec_summary: ExecSummary | None = None
    report_id: int | None = None  # 저장 기능이 생기면 채워져요
