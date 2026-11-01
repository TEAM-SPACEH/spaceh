"""A-07 계열사 입력값 형식 검증. DB 에는 접근하지 않는다 (중복 확인은 저장소·서비스가 한다).

각 함수는 값을 다듬어 돌려주고(앞뒤 공백 제거, 코드는 대문자), 형식이 틀리면 화면에 그대로 보여 줄 수 있는
쉬운 문구의 ValueError 를 낸다.
"""

import re

# 사원번호 앞부분(예: MVX-0001)으로 쓰이므로 영문만 허용한다. [A-Za-z] 로 ASCII 영문만 받는다
# (str.isalpha() 는 한글·전각 문자도 통과시킨다).
_COMPANY_CODE_PATTERN = re.compile(r"[A-Za-z]{2,5}")
# 숫자도 [0-9] 로 ASCII 만 받는다 (\\d 는 전각·아라비아 숫자까지 통과시킨다).
_DART_CODE_PATTERN = re.compile(r"[0-9]{8}")

# companies.name 컬럼 길이 (VARCHAR(100)). 넘으면 INSERT 가 실패하므로 미리 막는다.
COMPANY_NAME_MAX_LENGTH = 100


def validate_company_name(name: str | None) -> str:
    """회사명의 앞뒤 공백을 떼고 돌려준다. 비어 있거나 100자를 넘으면 ValueError."""
    text = (name or "").strip()
    if not text:
        raise ValueError("회사명을 입력해 주세요.")
    if len(text) > COMPANY_NAME_MAX_LENGTH:
        raise ValueError(f"회사명은 {COMPANY_NAME_MAX_LENGTH}자 이하로 입력해 주세요.")
    return text


def validate_company_code(code: str | None) -> str:
    """회사 코드를 영문 대문자 2–5자로 맞춰 돌려준다. 소문자로 입력해도 대문자로 바꿔 받는다. 형식이 틀리면 ValueError."""
    text = (code or "").strip()
    if not _COMPANY_CODE_PATTERN.fullmatch(text):
        raise ValueError("코드는 영문 대문자 2–5자로 입력해 주세요. 예: HIP")
    return text.upper()


def validate_dart_code(code: str | None) -> str | None:
    """DART 고유번호(숫자 8자리)를 돌려준다. 비어 있으면 None(비상장·입력 전). 형식이 틀리면 ValueError."""
    text = (code or "").strip()
    if not text:
        return None
    if not _DART_CODE_PATTERN.fullmatch(text):
        raise ValueError("DART 고유번호는 숫자 8자리로 입력해 주세요.")
    return text
