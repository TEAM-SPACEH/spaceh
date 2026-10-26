-- spaceH 핵심 테이블 (팀 ERD 기준, 10/26)
-- 실행: mysql -u root -p spaceh < db/schema.sql
-- 기존 테이블을 지우고 다시 만든다. 데이터가 모두 사라지니 개발 DB에서만 실행한다.
-- 나머지 테이블(권한 요청·보고서·히스토리·감사 로그·DART 수집)은 ERD가 끝나면 이 파일에 추가한다.

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS documents;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS companies;
SET FOREIGN_KEY_CHECKS = 1;

-- 계열사 (A-07). company_id는 회사 코드 자체다: 'HRI', 'MVX', 'ELV'
CREATE TABLE companies (
  company_id  VARCHAR(20)  NOT NULL                COMMENT '회사 코드 (대문자, 사원번호 앞부분)',
  name        VARCHAR(100) NOT NULL                COMMENT '회사명',
  dart_code   VARCHAR(8)   NULL                    COMMENT 'DART 고유번호 8자리 (I-05)',
  is_active   TINYINT(1)   NOT NULL DEFAULT 1      COMMENT '사용 여부',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (company_id),
  UNIQUE KEY uq_companies_name (name),
  UNIQUE KEY uq_companies_dart_code (dart_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='계열사';

-- 사용자 (M-01 로그인, M-02 내 정보)
CREATE TABLE users (
  id           INT          NOT NULL AUTO_INCREMENT,
  employee_no  VARCHAR(20)  NOT NULL                COMMENT '사원번호 (로그인 ID), 예: MVX-0001',
  password     VARCHAR(100) NOT NULL                COMMENT '비밀번호 해시 (core/security.py). 평문 저장 금지',
  name         VARCHAR(50)  NOT NULL,
  role         VARCHAR(20)  NOT NULL                COMMENT 'employee / company_admin / super_admin',
  company_id   VARCHAR(20)  NULL                    COMMENT '소속. super_admin만 NULL',
  is_active    TINYINT(1)   NOT NULL DEFAULT 1,
  created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_employee_no (employee_no),
  KEY idx_users_company (company_id),
  CONSTRAINT fk_users_company FOREIGN KEY (company_id) REFERENCES companies (company_id),
  CONSTRAINT ck_users_role CHECK (role IN ('employee', 'company_admin', 'super_admin')),
  CONSTRAINT ck_users_company CHECK (role = 'super_admin' OR company_id IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='사용자';

-- 문서 (I-02 색인, A-01~A-03 관리). 행을 먼저 만들고 그 doc_id로 청크 ID를 만든다.
CREATE TABLE documents (
  doc_id            VARCHAR(100)  NOT NULL                COMMENT '앱이 uuid4().hex로 생성. 청크 ID = {doc_id}#0001',
  company_id        VARCHAR(20)   NOT NULL                COMMENT '문서 소유 회사',
  doc_type          VARCHAR(20)   NOT NULL                COMMENT 'report / disclosure / manual / spec / intro / memo',
  title             VARCHAR(500)  NOT NULL,
  file_name         VARCHAR(255)  NOT NULL                COMMENT '원래 파일명',
  file_format       VARCHAR(10)   NOT NULL                COMMENT 'pdf / docx / pptx / xlsx / hwp / dart_xml',
  source_type       VARCHAR(20)   NOT NULL DEFAULT 'internal' COMMENT 'internal / dart',
  source_url        VARCHAR(1000) NULL                    COMMENT 'DART 뷰어 주소. 내부 문서는 NULL',
  doc_no            VARCHAR(20)   NULL                    COMMENT '문서 번호 (용도 확인 필요)',
  published_date    DATE          NULL                    COMMENT '작성·공시일 (S-02 기간 필터)',
  finance_year      SMALLINT      NULL                    COMMENT '문서가 다루는 회계연도',
  quarter           VARCHAR(2)    NULL                    COMMENT 'Q1 / Q2 / Q3 / Q4',
  access_level      VARCHAR(20)   NOT NULL DEFAULT 'internal' COMMENT 'public / internal / confidential',
  is_group_shared   TINYINT(1)    NOT NULL DEFAULT 0      COMMENT '그룹사 공유 (A-03), internal만 의미 있음',
  is_mock           TINYINT(1)    NOT NULL DEFAULT 0      COMMENT '직접 만든 목데이터 여부',
  file_path         VARCHAR(500)  NOT NULL                COMMENT 'data/uploads/ 아래 저장 위치',
  content_hash      CHAR(64)      NOT NULL                COMMENT '원본 SHA-256 (중복 검사)',
  page_count        INT           NOT NULL DEFAULT 0,
  chunk_count       INT           NOT NULL DEFAULT 0,
  pii_masked_count  INT           NOT NULL DEFAULT 0      COMMENT 'I-03 마스킹 개수',
  index_status      VARCHAR(20)   NOT NULL DEFAULT 'pending' COMMENT 'pending / indexing / done / failed',
  error_message     TEXT          NULL                    COMMENT '색인 실패 이유',
  uploaded_by       INT           NULL                    COMMENT '업로드한 사용자',
  shared_by         INT           NULL                    COMMENT '공유를 마지막으로 바꾼 사용자',
  shared_at         DATETIME      NULL,
  created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (doc_id),
  KEY idx_documents_company (company_id),
  KEY idx_documents_hash (content_hash),
  CONSTRAINT fk_documents_company FOREIGN KEY (company_id) REFERENCES companies (company_id),
  CONSTRAINT fk_documents_uploaded_by FOREIGN KEY (uploaded_by) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT fk_documents_shared_by FOREIGN KEY (shared_by) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT ck_documents_access_level CHECK (access_level IN ('public', 'internal', 'confidential')),
  CONSTRAINT ck_documents_source_type CHECK (source_type IN ('internal', 'dart')),
  CONSTRAINT ck_documents_index_status CHECK (index_status IN ('pending', 'indexing', 'done', 'failed')),
  CONSTRAINT ck_documents_quarter CHECK (quarter IS NULL OR quarter IN ('Q1', 'Q2', 'Q3', 'Q4'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='문서';
