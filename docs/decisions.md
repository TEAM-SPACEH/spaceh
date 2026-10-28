# 결정 기록

코드로 뒤집힐 수 있는 결정만 적는다. AI 도구가 아래와 반대되는 방법을 제안하면 따르지 말고 팀장에게 먼저 묻는다.

- 담당·일정은 [features](./features.md), 권한 규칙은 [구조 개요](./architecture/overview.md)에 있다. 여기에 중복해서 적지 않는다.
- 결정을 바꾸는 PR은 이 문서도 **같은 PR에서** 고친다. 옛 줄은 지우지 않고 `→ 변경 (날짜)`을 붙인다.

| 날짜 | 결정 | 이유 |
| --- | --- | --- |
| 10/21 | 쓰지 않는 기술: FastAPI·ORM·Docker·CI 도구(ruff·pre-commit·Actions) (수업 밖) / LangGraph·리랭킹 (배웠지만 범위 밖) → 변경 (10/26): Actions는 아래 PR 자동화에만 쓴다 | 8일 일정, 수업 범위 |
| 10/21 | 로컬 실행 시연, 배포 없음 | 8일 일정 |
| 10/21 | 임베딩 `text-embedding-3-small` 고정 | 바꾸면 전체 재색인 |
| 10/21 | 청킹 3규칙(절 / 페이지·슬라이드 / 표 통째로) + 800자 재분할 → 변경 (10/27): 긴 표는 행 단위 분할, 머리글·문맥 반복. DOCX 문단 순번을 페이지 경계로 사용하지 않는 기준은 [데이터 모델](./architecture/data-model.md#청킹-i-02)을 따른다 | ChatPDF 평가: 조문 단위 90% vs 500자 고정 61.7% |
| 10/20 | 권한은 검색 전에 거는 사전 필터만, 사후 필터 금지 | 권한 없는 청크가 LLM에 들어가는 경로 차단 |
| 10/20 | 원문은 앱 안 뷰어 + DART 뷰어만, 외부 공유 링크 금지 | 링크로 권한 우회 방지 |
| 10/20 | PII는 색인 전에 마스킹, 계약 단가는 마스킹 대신 `confidential` | 개인정보가 Chroma·LLM에 들어가지 않게, 단가는 검색이 필요 |
| 10/26 | 「기능명세표」 28개만 만든다. KPI CSV·문서 요약·클러스터링·3사 비교는 만들지 않는다 | 명세표에 없는 기능 |
| 10/26 | 로그인은 시드 계정 + 사원번호·비밀번호 유지, 해시는 `hashlib.pbkdf2_hmac` | 권한 시연에 계정 전환이 필요, bcrypt는 수업에 없음 |
| 10/26 | 수업에서 배운 기술만 쓴다. 표준 라이브러리로 대체: 테스트 `unittest`, HTTP(DART) `urllib.request`, 해시 `hashlib`. 예외: `python-docx`·`python-pptx`(I-01 필수), `PyMySQL`+`cryptography`(Week4 MySQL 연결) | 수업 범위 안에서 설명할 수 있게 |
| 10/26 | PR 자동화: `CODEOWNERS` 리뷰어 요청, 작성자 assignee·라벨(Actions). 테스트·린트 CI·AI 리뷰 봇은 두지 않는다 | 손으로 하던 지정 제거, 리뷰 누락 방지. 앱 코드가 아니라 수업 범위 규칙과 무관 |
| 10/26 | 핵심 테이블은 팀 ERD 이름을 따른다: `company_id`는 회사 코드(`HRI`·`MVX`·`ELV`) 문자열 PK, `doc_id`는 앱이 만드는 uuid 문자열, 보안 등급 `access_level`, 작성일 `published_date`, 대상 기간 `finance_year`·`quarter`를 둔다 | ERD 확정, Chroma 메타데이터도 같은 이름으로 |
| 10/27 | DB 8개 테이블 확정 (`db/schema.sql`이 원본, 스키마 정의서 엑셀은 제출용 사본). 값은 영어 소문자(회사 코드·분기만 대문자). `password_hash`, 작성일 필수, `company_code` 이름은 `audit_logs.company_code`·`access_requests.owner_company_code` 두 컬럼에만 유지하고(FK 없음, 값은 `companies.company_id`), 나머지 테이블(`companies`·`users`·`documents`)은 `company_id`를 쓴다. 열람 승인은 기간·중복 제약 없이 `access_grants`에 쌓고, `companies.default_share_enabled`는 두지 않는다 → 변경 (10/28): A-07 계열사 화면 시안(Figma 「기본 그룹사 공유」)에 맞춰 `companies.default_share_enabled`(기본 0)를 둔다. M-04 히스토리는 `audit_logs`에서 읽는다 | ERD·정의서 확정, 관문 일정상 단순하게. 변경 이유: 시안에 회사별 기본값 설정이 있고 새 사내 문서 업로드(A-01)의 공유 초기값으로 쓴다 (팀장 리뷰 필요, 스키마 정의서 사본도 같이 수정) |
| 10/28 | 계열사 관리자의 감사 로그 조회 범위는 **자사 직원이 행동한 로그만**(`audit_logs.company_code`). 타사 직원이 자사 문서를 열람하려다 차단된 로그는 보이지 않는다 | 타사 직원의 검색어·질문 원문이 노출되지 않게 함. 최종 어드민은 전체 조회 |
| 10/26 | `main.py`·`core`·`models`는 저장소 루트, 의존성은 `requirements.txt` + Python 3.11 | 루트에서 실행해야 import가 됨, pip만으로 환경 통일 |
| 10/27 | I-02의 등록 제목이 없거나 공백이면 파일명의 마지막 확장자를 뺀 이름으로 대체한다. 작성일은 파일명·수정 시각으로 추측하지 않고 [데이터 모델의 I-02 작성일 규칙](./architecture/data-model.md#공통-메타데이터-구성-i-02)을 따른다 | 사용자 합의, 출처 제목 누락 방지와 날짜 오인 방지 |
| 10/27 | I-01 로더의 공통 블록은 `block_type`·`text`·`page`·`location`·`section` 5개 필드의 `list[dict]`로 제안하고 PR 리뷰로 확정한다. 데이터클래스 예시는 이 형식으로 변경 | I-03 마스킹과 직접 연결, 필드·위치 규칙은 `architecture/data-model.md` 한 곳에서 관리 |

## 아직 정하지 않은 것

이 항목에 걸린 작업은 혼자 정하지 말고 팀장에게 묻는다.

- 분기 실적 보고서(R-02 ②)의 수치를 DART 공시 표 청크만으로 만들지
- I-04 XLSX·HWP 확장 파싱(P3)을 할 경우 쓸 라이브러리 (수업에 없음 — 시작 전에 결정)
