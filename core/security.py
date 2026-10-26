"""비밀번호 해시·검증. 저장 형식: pbkdf2_sha256$반복횟수$salt$hash (salt·hash는 base64)."""

import base64
import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return "$".join([ALGORITHM, str(ITERATIONS), _b64(salt), _b64(digest)])


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = stored.split("$")
    except ValueError:
        return False
    if algorithm != ALGORITHM:
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", password.encode(), base64.b64decode(salt), int(iterations)
    )
    return hmac.compare_digest(candidate, base64.b64decode(digest))


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()
