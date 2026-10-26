"""M-01 로그인 서비스: login(), logout().

사전에 등록된 사원번호·비밀번호(data/users.csv)와 일치하는지 확인해 로그인한다.
비밀번호 원문은 저장하지 않고 pbkdf2(SHA-256) 해시로만 비교한다.
DB(users 테이블)가 생기면 _find_user의 조회부만 바꾸면 된다.
"""

import csv
import hashlib
import hmac
import logging
from pathlib import Path

from app.auth import session

logger = logging.getLogger(__name__)

# 등록 사용자 CSV: 저장소 루트의 data/users.csv (이 파일은 app/auth/services 아래)
_USERS_CSV = Path(__file__).resolve().parents[3] / "data" / "users.csv"
# pbkdf2 반복 횟수. CSV의 해시를 만든 값과 반드시 같아야 한다.
_PBKDF2_ITERATIONS = 200_000


def _hash_password(password: str, salt: str) -> str:
    """비밀번호와 salt(사용자별 무작위 값)로 pbkdf2(SHA-256) 해시를 16진수 문자열로 만든다."""
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ITERATIONS
    )
    return digest.hex()


def _find_user(employee_id: str) -> dict | None:
    """CSV에서 사원번호로 사용자 한 명을 찾는다. 없으면 None."""
    if not _USERS_CSV.exists():
        logger.warning("사용자 CSV가 없다: %s", _USERS_CSV)
        return None
    with _USERS_CSV.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("employee_id", "").strip() == employee_id:
                return row
    return None


def login(employee_id: str, password: str) -> bool:
    """M-01 사원번호·비밀번호가 등록된 값과 일치하면 세션에 로그인하고 True를 돌려준다."""
    employee_id = (employee_id or "").strip()
    if not employee_id or not password:
        return False

    user = _find_user(employee_id)
    if user is None:
        logger.info("로그인 실패: 등록되지 않은 사원번호")
        return False

    expected = user.get("password_hash", "").strip()
    salt = user.get("salt", "").strip()
    if not expected or not salt:
        logger.warning("로그인 실패: 해시·salt 없음 (CSV 확인 필요)")
        return False

    # 비밀번호 비교는 타이밍 공격을 피하려고 == 대신 compare_digest를 쓴다.
    if not hmac.compare_digest(_hash_password(password, salt), expected):
        logger.info("로그인 실패: 비밀번호 불일치")
        return False

    # 세션에는 비밀번호 해시·salt를 빼고 넣는다.
    session.set_current_user(
        {
            "employee_id": user["employee_id"].strip(),
            "name": user.get("name", "").strip(),
            "role": user.get("role", "").strip(),
        }
    )
    logger.info("로그인 성공")
    return True


def logout() -> None:
    """M-01 현재 로그인 상태를 해제한다."""
    session.clear_current_user()
