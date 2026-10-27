"""역할·문서 보안 등급 값. 여러 패키지가 같은 문자열을 쓰도록 여기 한 곳에 모은다.

DB와 Chroma 메타데이터에는 이 문자열이 그대로 저장된다.
값을 바꾸거나 추가하면 db/schema.sql의 CHECK 제약(ck_users_role·ck_documents_access_level)도 같이 고친다.
"""

# 사용자 역할 (users.role)
ROLE_EMPLOYEE = "employee"
ROLE_COMPANY_ADMIN = "company_admin"
ROLE_SUPER_ADMIN = "super_admin"
ROLES = (ROLE_EMPLOYEE, ROLE_COMPANY_ADMIN, ROLE_SUPER_ADMIN)

# 문서 보안 등급 (documents.access_level, Chroma 메타데이터 access_level)
ACCESS_PUBLIC = "public"
ACCESS_INTERNAL = "internal"
ACCESS_CONFIDENTIAL = "confidential"
ACCESS_LEVELS = (ACCESS_PUBLIC, ACCESS_INTERNAL, ACCESS_CONFIDENTIAL)
