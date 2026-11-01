-- spaceH 테이블 (팀 ERD·DB 스키마 정의서 기준, 10/27)
-- 실행: mysql -u root -p spaceh < db/schema.sql
-- 기존 테이블을 지우고 다시 만든다. 데이터가 모두 사라지니 개발 DB에서만 실행한다.
-- 값 표기는 영어 소문자 (회사 코드·분기만 대문자). 허용 값은 docs/architecture/data-model.md를 따른다.
-- CHECK는 COLLATE utf8mb4_bin으로 대소문자를 구분한다 ('PUBLIC'은 거부).

SET FOREIGN_KEY_CHECKS = 0;
DROP TABLE IF EXISTS dart_sync_jobs;
DROP TABLE IF EXISTS audit_logs;
DROP TABLE IF EXISTS reports;
DROP TABLE IF EXISTS access_grants;
DROP TABLE IF EXISTS access_requests;
DROP TABLE IF EXISTS documents;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS companies;
SET FOREIGN_KEY_CHECKS = 1;

-- 계열사 (A-07). company_id는 회사 코드 자체다: 'HRI', 'MVX', 'ELV'
CREATE TABLE companies (
  company_id  VARCHAR(20)  NOT NULL                COMMENT '회사 코드 (대문자, 사원번호 앞부분)',
  name        VARCHAR(100) NOT NULL                COMMENT '회사명',
  dart_code   VARCHAR(8)   NULL                    COMMENT 'DART 고유번호 8자리 (I-05), 비상장·입력 전은 NULL',
  default_share_enabled TINYINT(1) NOT NULL DEFAULT 0 COMMENT '새 사내 문서를 올릴 때 그룹사 공유를 켠 채로 시작 (A-07 설정, A-01이 읽음)',
  is_active   TINYINT(1)   NOT NULL DEFAULT 1      COMMENT '사용 여부',
  created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (company_id),
  UNIQUE KEY uq_companies_name (name),
  UNIQUE KEY uq_companies_dart_code (dart_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='계열사';

-- 사용자 (M-01 로그인, M-02 내 정보)
CREATE TABLE users (
  id             INT          NOT NULL AUTO_INCREMENT,
  employee_no    VARCHAR(20)  NOT NULL                COMMENT '사원번호 (로그인 ID), 예: MVX-0001',
  password_hash  VARCHAR(100) NOT NULL                COMMENT 'PBKDF2 해시 (core/security.py). 평문 저장 금지',
  name           VARCHAR(50)  NOT NULL,
  role           VARCHAR(20)  NOT NULL                COMMENT 'employee / company_admin / super_admin',
  company_id     VARCHAR(20)  NULL                    COMMENT '소속. super_admin만 NULL',
  is_active      TINYINT(1)   NOT NULL DEFAULT 1,
  created_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_employee_no (employee_no),
  KEY idx_users_company (company_id),
  CONSTRAINT fk_users_company FOREIGN KEY (company_id) REFERENCES companies (company_id),
  CONSTRAINT ck_users_role CHECK (role COLLATE utf8mb4_bin IN ('employee', 'company_admin', 'super_admin')),
  CONSTRAINT ck_users_company CHECK (role COLLATE utf8mb4_bin = 'super_admin' OR company_id IS NOT NULL)
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
  doc_no            VARCHAR(20)   NULL                    COMMENT 'DART 접수번호 14자리. 내부 문서는 NULL',
  published_date    DATE          NOT NULL                COMMENT '작성·공시일 (S-02 기간 필터). 파일에서 못 읽으면 업로드일',
  finance_year      SMALLINT      NULL                    COMMENT '문서가 다루는 회계연도',
  quarter           VARCHAR(2)    NULL                    COMMENT 'Q1 / Q2 / Q3 / Q4',
  access_level      VARCHAR(20)   NOT NULL DEFAULT 'internal' COMMENT 'public / internal / confidential',
  is_group_shared   TINYINT(1)    NOT NULL DEFAULT 0      COMMENT '그룹사 공유 (A-03), internal만 켤 수 있음',
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
  UNIQUE KEY uq_documents_doc_no (doc_no),
  KEY idx_documents_company (company_id),
  KEY idx_documents_hash (content_hash),
  CONSTRAINT fk_documents_company FOREIGN KEY (company_id) REFERENCES companies (company_id),
  CONSTRAINT fk_documents_uploaded_by FOREIGN KEY (uploaded_by) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT fk_documents_shared_by FOREIGN KEY (shared_by) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT ck_documents_doc_type CHECK (doc_type COLLATE utf8mb4_bin IN ('report', 'disclosure', 'manual', 'spec', 'intro', 'memo')),
  CONSTRAINT ck_documents_file_format CHECK (file_format COLLATE utf8mb4_bin IN ('pdf', 'docx', 'pptx', 'xlsx', 'hwp', 'dart_xml')),
  CONSTRAINT ck_documents_source_type CHECK (source_type COLLATE utf8mb4_bin IN ('internal', 'dart')),
  CONSTRAINT ck_documents_access_level CHECK (access_level COLLATE utf8mb4_bin IN ('public', 'internal', 'confidential')),
  CONSTRAINT ck_documents_shared_internal CHECK (is_group_shared = 0 OR access_level COLLATE utf8mb4_bin = 'internal'),
  CONSTRAINT ck_documents_index_status CHECK (index_status COLLATE utf8mb4_bin IN ('pending', 'indexing', 'done', 'failed')),
  CONSTRAINT ck_documents_quarter CHECK (quarter IS NULL OR quarter COLLATE utf8mb4_bin IN ('Q1', 'Q2', 'Q3', 'Q4'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='문서';

-- 열람 권한 요청 (M-03 요청, A-05 승인·반려)
CREATE TABLE access_requests (
  id                  INT           NOT NULL AUTO_INCREMENT,
  user_id             INT           NOT NULL                COMMENT '요청한 사용자',
  doc_id              VARCHAR(100)  NOT NULL                COMMENT '요청 문서',
  owner_company_code  VARCHAR(20)   NOT NULL                COMMENT '문서 소유 회사 코드 (companies.company_id 값). 이 회사 관리자가 처리',
  reason              TEXT          NOT NULL                COMMENT '요청 사유',
  status              VARCHAR(20)   NOT NULL DEFAULT 'pending' COMMENT 'pending / approved / rejected',
  reviewer_id         INT           NULL                    COMMENT '처리한 관리자',
  review_comment      TEXT          NULL                    COMMENT '반려 사유 등',
  created_at          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at         DATETIME      NULL,
  PRIMARY KEY (id),
  KEY idx_access_requests_owner_status (owner_company_code, status),
  KEY idx_access_requests_user (user_id),
  CONSTRAINT fk_access_requests_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT fk_access_requests_doc FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE,
  CONSTRAINT fk_access_requests_reviewer FOREIGN KEY (reviewer_id) REFERENCES users (id) ON DELETE SET NULL,
  CONSTRAINT ck_access_requests_status CHECK (status COLLATE utf8mb4_bin IN ('pending', 'approved', 'rejected'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='열람 권한 요청';

-- 열람 권한 부여 (A-05 승인 결과, S-03 승인 문서 조건). 기간 없이 영구 승인, 같은 행이 여러 개여도 된다.
CREATE TABLE access_grants (
  id          INT           NOT NULL AUTO_INCREMENT,
  user_id     INT           NOT NULL                COMMENT '열람 권한을 받은 사용자',
  doc_id      VARCHAR(100)  NOT NULL                COMMENT '열람 허용 문서',
  request_id  INT           NULL                    COMMENT '근거 요청',
  granted_by  INT           NULL                    COMMENT '승인한 관리자',
  created_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_access_grants_user (user_id),
  CONSTRAINT fk_access_grants_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT fk_access_grants_doc FOREIGN KEY (doc_id) REFERENCES documents (doc_id) ON DELETE CASCADE,
  CONSTRAINT fk_access_grants_request FOREIGN KEY (request_id) REFERENCES access_requests (id) ON DELETE SET NULL,
  CONSTRAINT fk_access_grants_granted_by FOREIGN KEY (granted_by) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='열람 권한 부여';

-- 보고서 (R-02~R-05, A-06)
CREATE TABLE reports (
  id                INT           NOT NULL AUTO_INCREMENT,
  user_id           INT           NOT NULL                COMMENT '만든 사용자',
  template          VARCHAR(20)   NOT NULL                COMMENT 'comprehensive(종합) / quarterly(분기 실적)',
  title             VARCHAR(300)  NOT NULL,
  params            JSON          NOT NULL                COMMENT '주제·회사·기간 등 생성 조건',
  content_md        LONGTEXT      NOT NULL                COMMENT '보고서 본문 (사람이 읽는 Markdown)',
  sections          JSON          NOT NULL                COMMENT '섹션 목록 (종류·제목·본문·근거 여부·일부 제외). 다시 열기용 (R-02)',
  footnotes         JSON          NULL                    COMMENT '각주 목록 (R-03)',
  exec_summary      JSON          NULL                    COMMENT '1페이지 요약 항목·유의사항 (R-04)',
  doc_ids           JSON          NULL                    COMMENT '근거 문서 ID 목록',
  max_access_level  VARCHAR(20)   NOT NULL DEFAULT 'public' COMMENT '근거 문서 중 가장 높은 보안 등급 (A-06)',
  created_at        DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_reports_user (user_id),
  CONSTRAINT fk_reports_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
  CONSTRAINT ck_reports_max_access_level CHECK (max_access_level COLLATE utf8mb4_bin IN ('public', 'internal', 'confidential'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='보고서';

-- 감사 로그 (A-04). 차단을 포함한 모든 행동. M-04 내 사용 히스토리도 여기서 읽는다.
-- 사용자 정보는 행동 당시 값을 그대로 남긴다 (나중에 역할·소속이 바뀌어도 기록은 그대로).
CREATE TABLE audit_logs (
  id              BIGINT        NOT NULL AUTO_INCREMENT,
  created_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  user_id         INT           NULL                    COMMENT '행동한 사용자. 로그인 실패 등은 NULL',
  employee_no     VARCHAR(20)   NULL,
  role            VARCHAR(20)   NULL                    COMMENT '행동 당시 역할',
  company_code    VARCHAR(20)   NULL                    COMMENT '행동 당시 소속 회사 코드',
  action          VARCHAR(40)   NOT NULL                COMMENT 'login / search / ask / view_document / download / report_create / upload / share_change / access_request / access_review 등',
  target_type     VARCHAR(20)   NULL                    COMMENT 'document / report / user / company / access_request',
  target_id       VARCHAR(100)  NULL,
  query           TEXT          NULL                    COMMENT '검색어·질문',
  filters         JSON          NULL,
  doc_ids         JSON          NULL                    COMMENT '결과·근거 문서 ID',
  doc_companies   JSON          NULL                    COMMENT '결과 문서의 회사 코드',
  result_count    INT           NULL,
  is_blocked      TINYINT(1)    NOT NULL DEFAULT 0      COMMENT '권한 등으로 차단됐으면 1',
  block_reason    VARCHAR(200)  NULL,
  context_detail  JSON          NULL                    COMMENT '추가 정보',
  PRIMARY KEY (id),
  KEY idx_audit_logs_created (created_at),
  KEY idx_audit_logs_company_created (company_code, created_at),
  KEY idx_audit_logs_user_created (user_id, created_at),
  CONSTRAINT fk_audit_logs_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='감사 로그';

-- DART 수집 작업 (I-05)
CREATE TABLE dart_sync_jobs (
  id             INT           NOT NULL AUTO_INCREMENT,
  requested_by   INT           NOT NULL                COMMENT '실행한 사용자',
  company_codes  JSON          NOT NULL                COMMENT '수집할 회사 코드 배열, 예: ["MVX", "ELV"]',
  date_from      DATE          NOT NULL,
  date_to        DATE          NOT NULL,
  report_types   JSON          NOT NULL                COMMENT 'DART 공시 유형 배열',
  status         VARCHAR(20)   NOT NULL DEFAULT 'running' COMMENT 'running / completed / failed',
  found_count    INT           NOT NULL DEFAULT 0,
  indexed_count  INT           NOT NULL DEFAULT 0,
  skipped_count  INT           NOT NULL DEFAULT 0,
  failed_count   INT           NOT NULL DEFAULT 0,
  error_message  TEXT          NULL,
  started_at     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  finished_at    DATETIME      NULL,
  PRIMARY KEY (id),
  CONSTRAINT fk_dart_sync_jobs_user FOREIGN KEY (requested_by) REFERENCES users (id),
  CONSTRAINT ck_dart_sync_jobs_status CHECK (status COLLATE utf8mb4_bin IN ('running', 'completed', 'failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='DART 수집 작업';
