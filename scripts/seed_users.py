"""시드 계정 7개를 넣는다. 비밀번호는 .env의 SEED_DEFAULT_PASSWORD, DB에는 해시만 저장한다.

실행 (저장소 루트, db/schema.sql·db/seed.sql 다음): python -m scripts.seed_users
다시 실행하면 같은 사원번호의 이름·역할·비밀번호를 덮어쓴다.
"""

import sys

from core import config
from core.constants import ROLE_COMPANY_ADMIN, ROLE_EMPLOYEE, ROLE_SUPER_ADMIN
from core.database import get_connection
from core.security import hash_password

SEED_USERS = [
    # (사원번호, 이름, 역할, 소속)
    ("HRI-0001", "김연구", ROLE_EMPLOYEE, "HRI"),
    ("HRI-0002", "박관리", ROLE_COMPANY_ADMIN, "HRI"),
    ("MVX-0001", "이물류", ROLE_EMPLOYEE, "MVX"),
    ("MVX-0002", "최관리", ROLE_COMPANY_ADMIN, "MVX"),
    ("ELV-0001", "정승강", ROLE_EMPLOYEE, "ELV"),
    ("ELV-0002", "한관리", ROLE_COMPANY_ADMIN, "ELV"),
    ("ADM-0001", "윤총괄", ROLE_SUPER_ADMIN, None),
]


def main() -> None:
    password = config.SEED_DEFAULT_PASSWORD
    if not password:
        sys.exit(".env에 SEED_DEFAULT_PASSWORD를 채운 뒤 다시 실행하세요.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            for employee_no, name, role, company_id in SEED_USERS:
                cur.execute(
                    """
                    INSERT INTO users (employee_no, password_hash, name, role, company_id)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                      password_hash = VALUES(password_hash), name = VALUES(name),
                      role = VALUES(role), company_id = VALUES(company_id)
                    """,
                    (employee_no, hash_password(password), name, role, company_id),
                )
    print(f"시드 계정 {len(SEED_USERS)}개를 넣었습니다.")


if __name__ == "__main__":
    main()
