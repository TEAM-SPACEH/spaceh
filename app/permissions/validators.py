"""M-03 열람 요청 사유 검증."""

# 요청 사유 글자 수 규칙. 팀 정책이 바뀌면 이 값만 고친다.
_MIN_REASON_LEN = 5
_MAX_REASON_LEN = 500


def validate_request_reason(reason: str) -> bool:
    """M-03 요청 사유가 쓸 만한지 검사한다. 앞뒤 공백을 떼고 5~500자면 True.

    너무 짧으면(공백·'ㅇ' 등) 왜 보려는지 알 수 없고, 너무 길면(500자 초과) 받지 않는다.
    DB를 건드리지 않는 순수 형식 검증이라 validators에 둔다(계층 규칙).
    """
    if not isinstance(reason, str):
        return False
    trimmed = reason.strip()  # 앞뒤 공백 제거 후 길이로만 판단
    return _MIN_REASON_LEN <= len(trimmed) <= _MAX_REASON_LEN
