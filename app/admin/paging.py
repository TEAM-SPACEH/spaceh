"""관리자 목록 화면(A-03 공유 설정·A-04 감사 로그)이 함께 쓰는 페이지 번호·건수 값 보정.

화면에서 온 값(0, 음수, 너무 큰 수, 글자)이 이상해도 서비스가 안전한 범위로 맞춰 쓰게 한다.
"""


def as_int(value, default: int) -> int:
    """정수로 바꾼다. 바꿀 수 없으면 default."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def clamp(value, low: int, high: int) -> int:
    """정수로 바꿔 low~high 범위로 맞춘다. 숫자로 바꿀 수 없으면 low 로 본다."""
    return min(max(as_int(value, low), low), high)
