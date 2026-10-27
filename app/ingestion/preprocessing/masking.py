"""I-03 개인정보 마스킹.

로더(parsers)가 만든 공통 형식 블록을 받아, 색인(Chroma)·LLM으로 넘어가기 전에
개인정보를 `[마스킹: 유형]` 문자열로 치환한다. 파이프라인 위치는 "로더 직후, 청킹 전".

마스킹 대상과 제외 대상은 docs/architecture/data-model.md 의 "PII 마스킹 (I-03)" 표를 따른다.
"""

import logging
import re

logger = logging.getLogger(__name__)

# 마스킹 유형 이름. 치환 문자열 `[마스킹: {유형}]`과 반환 건수 딕셔너리의 키로 함께 쓴다.
RRN = "주민번호"
PHONE = "연락처"
EMAIL = "이메일"
ACCOUNT = "계좌"

# --- 탐지용 정규식 -------------------------------------------------------
# 모든 숫자 패턴은 앞뒤에 (?<!\d) / (?!\d) 를 붙여 "더 긴 숫자열의 일부"는 잡지 않는다.
# 예) 14자리 공시 접수번호 안에서 13자리나 11자리만 떼어 오탐하는 것을 막는다.

# 주민등록번호: YYMMDD + (선택) 구분자 + 성별 자리(1~8) + 6자리.
#  - 월(01~12)·일(01~31)을 검사해 임의의 13자리 숫자가 걸리는 오탐을 줄인다.
#  - 성별 자리 1~8: 1~4는 내국인, 5~8은 외국인 등록번호.
_RRN_RE = re.compile(
    r"(?<!\d)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[-\s]?[1-8]\d{6}(?!\d)"
)

# 휴대전화: 010·011·016~019 로 시작, 중간 3~4자리, 끝 4자리. 구분자는 -, ., 공백 허용.
# 국제 형식(+82 10-1234-5678, +8210-1234-5678, +82 010-1234-5678)도 잡는다.
# 02·031 같은 유선과 1588 대표번호는 01x 로 시작하지 않으므로 걸리지 않는다.
_PHONE_RE = re.compile(
    r"(?:(?<!\d)\+82[-.\s]?0?|(?<!\d)0)1[016-9][-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)"
)
# 법인등록번호(6-7자리)는 모양이 주민등록번호와 같다. 앞에 이 단어가 붙어 있으면 마스킹하지 않는다.
_CORP_LABEL_RE = re.compile(r"법인\s*(?:등록)?\s*번호\s*[:：]?\s*$")

# 이메일: 로컬파트@도메인(점 1개 이상). 엄밀한 RFC 검증이 아니라 문서 속 일반적인 형태만 잡는다.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")

# 계좌번호 후보: 하이픈으로 구분된 숫자열 2~4덩어리 (예: 110-123-456789).
# 앞뒤에 숫자·하이픈이 더 붙은 경우는 제외한다 (더 긴 숫자열의 일부).
# 사업자번호·날짜와 모양이 겹치므로 아래 두 정규식으로 후처리에서 걸러 낸다.
_ACCOUNT_RE = re.compile(r"(?<![\d-])\d{2,6}(?:-\d{2,8}){1,3}(?![\d-])")
# 이 단어 중 하나가 같은 줄에 있을 때만 계좌번호로 취급한다 (오탐 방지).
_ACCOUNT_KEYWORDS = ("계좌", "은행", "입금")
# 사업자등록번호 (3-2-5). 마스킹하지 않는다.
_BIZ_NO_RE = re.compile(r"\d{3}-\d{2}-\d{5}")
# 날짜 (YYYY-MM-DD). 계좌 키워드가 있는 줄(예: "2024-03-12 입금")에서도 마스킹하지 않는다.
_DATE_RE = re.compile(r"\d{4}-\d{1,2}-\d{1,2}")
# 회사 유선(02-1234-5678, 031-123-4567)과 대표번호(1588-1234 등). "○○은행 대표 02-…"처럼
# 계좌 키워드가 있는 줄에서도 마스킹하지 않는다 (명세: 대표번호·유선은 마스킹 안 함).
_LANDLINE_RE = re.compile(r"0\d{1,2}-\d{3,4}-\d{4}|1[5-8]\d{2}-\d{4}")


def _mask_text(text: str, counts: dict[str, int]) -> str:
    """텍스트 하나를 마스킹해 돌려주고, 치환한 건수를 `counts`에 누적한다.

    `counts`는 호출자가 넘긴 딕셔너리를 직접 갱신한다 (블록 여러 개의 합계를 내기 위함).
    """

    def sub_with(pattern: re.Pattern[str], label: str, line: str) -> str:
        """pattern 에 걸린 부분을 전부 `[마스킹: label]` 로 바꾸고 건수를 센다."""
        line, n = pattern.subn(f"[마스킹: {label}]", line)
        counts[label] += n
        return line

    def sub_account(line: str) -> str:
        """계좌 후보 중 사업자번호·날짜·유선/대표번호가 아닌 것만 치환한다."""

        def repl(match: re.Match[str]) -> str:
            value = match.group()
            # 사업자번호·날짜·유선/대표번호는 원문 그대로 둔다 (건수에도 포함하지 않는다).
            if (
                _BIZ_NO_RE.fullmatch(value)
                or _DATE_RE.fullmatch(value)
                or _LANDLINE_RE.fullmatch(value)
            ):
                return value
            counts[ACCOUNT] += 1
            return f"[마스킹: {ACCOUNT}]"

        return _ACCOUNT_RE.sub(repl, line)

    def sub_rrn(line: str) -> str:
        """주민번호를 치환하되, "법인등록번호: " 라벨이 바로 앞에 붙은 번호는 그대로 둔다."""

        def repl(match: re.Match[str]) -> str:
            if _CORP_LABEL_RE.search(line[: match.start()]):
                return match.group()
            counts[RRN] += 1
            return f"[마스킹: {RRN}]"

        return _RRN_RE.sub(repl, line)

    lines = []
    # 줄 단위로 처리해야 "계좌 키워드가 같은 줄에 있는지"를 판단할 수 있다.
    # split("\n") / join("\n") 은 줄바꿈 구조를 그대로 보존한다.
    for line in text.split("\n"):
        # 적용 순서가 중요하다.
        #  1) 주민번호를 먼저: 13자리 숫자가 뒤의 휴대전화·계좌 패턴과 섞이지 않게 한다.
        #  2) 이미 치환된 "[마스킹: ...]" 안에는 숫자가 없으므로 이후 패턴과 충돌하지 않는다.
        line = sub_rrn(line)
        line = sub_with(_PHONE_RE, PHONE, line)
        line = sub_with(_EMAIL_RE, EMAIL, line)
        # 계좌는 키워드가 있는 줄에서만 (회사 번호·접수번호 등 오탐 방지).
        if any(keyword in line for keyword in _ACCOUNT_KEYWORDS):
            line = sub_account(line)
        lines.append(line)
    return "\n".join(lines)


def mask_sensitive_data(
    blocks: list[dict],
) -> tuple[list[dict], dict[str, int]]:
    """
    공통 형식 블록 목록을 입력받아 민감 개인정보를 정규식으로 탐지하고
    [마스킹: 유형] 형태로 치환한 블록 목록과 유형별 처리 건수를 반환한다.

    입력 블록은 수정하지 않고 복사본을 돌려준다. 건수 키는
    주민번호·연락처·이메일·계좌이며, 탐지되지 않은 유형은 0이다.
    """
    # 항상 네 유형을 모두 담아 호출자가 키 존재 여부를 따로 확인하지 않게 한다.
    counts = {RRN: 0, PHONE: 0, EMAIL: 0, ACCOUNT: 0}
    masked_blocks: list[dict] = []

    for block in blocks:
        # 얕은 복사: 원본 dict 를 건드리지 않고 text 만 교체한다.
        # page·location·block_type 등 나머지 키는 그대로 유지된다.
        new_block = dict(block)
        text = block.get("text")
        # text 가 없거나 비어 있거나 문자열이 아닌 블록은 그대로 통과시킨다.
        if isinstance(text, str) and text:
            new_block["text"] = _mask_text(text, counts)
        masked_blocks.append(new_block)

    total = sum(counts.values())
    if total:
        # 원문 값은 로그에 남기지 않고 건수만 기록한다 (로그로 개인정보가 새지 않게).
        logger.info("민감 정보 %d건 마스킹: %s", total, counts)
    return masked_blocks, counts
