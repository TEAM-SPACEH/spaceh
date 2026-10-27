# 데이터 모델

> 컬럼 이름은 팀 ERD와 `db/schema.sql`을 따른다. 지금 확정된 테이블은 `companies`·`users`·`documents` 3개이고, 나머지는 ERD가 끝나면 추가한다. ERD가 바뀌면 `db/schema.sql`과 이 문서를 같은 PR에서 고친다.

## 1. 공통 값

| 항목 | 값 |
| --- | --- |
| 역할 `role` | `employee` · `company_admin` · `super_admin` |
| 회사 `company_id` | 회사 코드 대문자: `HRI`(현대경제연구원) · `MVX`(현대무벡스) · `ELV`(현대엘리베이터). 사원번호 앞부분과 같다 |
| 보안 등급 `access_level` | `public` · `internal` · `confidential` |
| 문서 유형 `doc_type` | `report`(연구 보고서) · `disclosure`(공시) · `manual`(매뉴얼·교육·FAQ) · `spec`(사양서) · `intro`(회사·제품 소개) · `memo`(내부 메모·목데이터) |
| 파일 형식 `file_format` | `pdf` · `docx` · `pptx` · `xlsx` · `hwp` · `dart_xml` |
| 출처 `source_type` | `internal` · `dart` |
| 색인 상태 `index_status` | `pending` · `indexing` · `done` · `failed` |
| 분기 `quarter` | `Q1` · `Q2` · `Q3` · `Q4` (회계연도는 `finance_year`) |

- 코드와 DB에는 영어 소문자 값만 저장한다 (예외: 회사 코드·분기는 대문자). 화면에 보일 한글 이름은 화면에서 바꾼다.
- `doc_id`는 `documents` 행을 만들 때 앱이 `uuid.uuid4().hex`(32자)로 만든다.
- 회사는 고정 목록이 아니다 (A-07). `companies` 테이블에서 읽는다.

## 2. 공통 문서 형식 (`models/`)

모든 로더는 파일 형식과 관계없이 같은 모양을 반환한다. 이것이 "통합 젠더"다.

```python
@dataclass
class Block:                 # 로더 출력의 최소 단위
    block_type: str          # "text" / "table" / "title"
    text: str                # 표는 Markdown 표
    page: int                # 위치 번호 (아래 표)
    location: str            # 출처 표기용 "p.3", "슬라이드 5"
    section: str = ""        # 소속 장·절 제목

@dataclass
class NormalizedDocument:
    doc_id: str
    company_id: str
    title: str
    file_name: str
    file_format: str
    doc_type: str
    access_level: str
    is_group_shared: bool
    blocks: list[Block]
    content_hash: str        # 원본 SHA-256 (중복 검사)
    pii_masked_count: int = 0

@dataclass
class Chunk:                 # 검색 단위 = Chroma 1건
    chunk_id: str            # "{doc_id}#{순번 4자리}" 예: "3f9c0a…#0003"
    text: str                # 맨 앞에 "[회사명 · 제목 · 위치]" 한 줄
    metadata: dict           # 아래 4장
```

### 형식별 위치 규칙

| 형식 | `page` | `location` 예 | 원문 보기 (S-05) |
| --- | --- | --- | --- |
| PDF | 페이지 번호 | `p.3` | 해당 페이지 이미지 + 근거 문단 |
| DOCX | 문단·표 순번 | `4.2 고장 대처` (가까운 제목) | 텍스트 뷰어, 해당 절 |
| PPTX | 슬라이드 번호 | `슬라이드 5` | 텍스트 뷰어, 해당 슬라이드 |
| XLSX | 시트 순번 | `시트 '사양표' A1:F20` | 표 뷰어 |
| HWP | 문단·표 순번 | `문단 12` | 텍스트 뷰어 |
| DART | 섹션 순번 | `사업보고서 > II. 사업의 내용` | DART 뷰어 (접수번호로 주소 생성) |

내부 문서 원본은 권한을 확인한 뒤 앱 안에서만 보여 준다. 외부 공유 링크(구글 드라이브 등)는 쓰지 않는다.

## 3. 처리 규칙

### PII 마스킹 (I-03) — 로더 직후, 청킹 전

| 대상 | 적용 | 치환 |
| --- | --- | --- |
| 주민등록번호 | 항상 | `[마스킹: 주민번호]` |
| 휴대전화 (010·011·016~019) | 항상 | `[마스킹: 연락처]` |
| 이메일 | 항상 | `[마스킹: 이메일]` |
| 계좌번호 | 같은 줄에 "계좌·은행·입금"이 있을 때만 | `[마스킹: 계좌]` |
| 회사 대표번호·유선, 사업자번호, 공시 접수번호 | 마스킹 안 함 | - |

계약 단가는 마스킹하지 않는다. 그런 문서는 `confidential`로 지정해 권한으로 막는다.

### 청킹 (I-02)

| 규칙 | 적용 문서 |
| --- | --- |
| 절 단위 (제목 기준) | `report` · `disclosure` · `manual` · `memo` |
| 페이지·슬라이드 단위 | `intro` |
| 표는 자르지 않고 통째로 (앞에 표 제목·섹션명) | `spec` + 모든 문서의 표 |

- 800자를 넘는 청크만 800자·겹침 150자로 다시 자른다 (개발 중 조정).
- 제목 구조가 없는 PDF는 페이지 단위 + 800자 규칙으로 대신한다.

## 4. Chroma

| 항목 | 값 |
| --- | --- |
| 컬렉션 | `documents` 하나 (전 계열사) |
| id | `chunk_id` |
| 임베딩 | `text-embedding-3-small` (바꾸면 전체 재색인) |
| 저장 위치 | `data/chroma/` (Git 제외) |

메타데이터 값은 `str`·`int`·`float`·`bool`만 가능하다. 날짜는 `YYYYMMDD` 정수, 빈 값은 `""` 또는 `0`.

| 필드 | 타입 | 용도 |
| --- | --- | --- |
| `doc_id` | str | 원본 연결, 승인 문서 필터 |
| `chunk_index` | int | 문서 안 순번 |
| `company_id` | str | 회사 필터, **권한 필터** |
| `access_level` | str | **권한 필터** |
| `is_group_shared` | bool | **권한 필터** (A-03 변경 시 일괄 갱신) |
| `doc_type` | str | 유형 필터 |
| `source_type` | str | DART만 보기 필터 |
| `published_date` | int | 기간 필터 (`YYYYMMDD`, DB `documents.published_date`) |
| `company_name`, `title`, `file_name`, `file_format` | str | 출처 배지·각주 |
| `page`, `location`, `section`, `block_type` | int/str | 위치 표시·원문 이동 |
| `source_url` | str | DART 뷰어 연결 (없으면 `""`) |

## 5. MySQL 테이블

8개 테이블 모두 `db/schema.sql`에 있다. 컬럼 설명은 팀 「DB 스키마 정의서」(제출용 사본)와 `schema.sql`의 COMMENT에 있고, 둘이 다르면 `schema.sql`을 따른다.

| 테이블 | 용도 | 기능 |
| --- | --- | --- |
| `companies` | 계열사 | A-07 |
| `users` | 사용자 (사원번호 `employee_no` 로그인, `password_hash`) | M-01, M-02 |
| `documents` | 문서 메타데이터·색인 상태·공유 | I-02, A-01~A-03 |
| `access_requests` | 열람 권한 요청 (`owner_company_code` 회사 관리자가 처리) | M-03, A-05 |
| `access_grants` | 승인된 문서 단위 열람 권한 (기간 없음) | A-05 → S-03 |
| `reports` | 보고서 본문·각주·1페이지 요약 (각주는 JSON) | R-02~R-05, A-06 |
| `audit_logs` | 감사 로그 (차단 포함 전부) | A-04, M-04 |
| `dart_sync_jobs` | DART 수집 작업 | I-05 |

- 내 사용 히스토리(M-04)는 별도 테이블 없이 `audit_logs`에서 본인 행을 읽는다.
- 회사 참조 컬럼 이름: `companies`·`users`·`documents`는 `company_id`(FK), `audit_logs.company_code`와 `access_requests.owner_company_code` 두 컬럼만 `*_code`다. 두 컬럼에도 `companies.company_id` 값(HRI 등)을 넣고 FK는 걸지 않는다. Chroma 메타데이터는 `company_id`.
- `documents.published_date`는 필수다. 파일에서 날짜를 못 읽으면 업로드일을 넣는다.

## 6. 시드 계정 (7개)

| 사원번호 | 역할 | 소속 |
| --- | --- | --- |
| `HRI-0001` / `HRI-0002` | 일반 사원 / 계열사 관리자 | 현대경제연구원 |
| `MVX-0001` / `MVX-0002` | 일반 사원 / 계열사 관리자 | 현대무벡스 |
| `ELV-0001` / `ELV-0002` | 일반 사원 / 계열사 관리자 | 현대엘리베이터 |
| `ADM-0001` | 최종 어드민 | 없음 (`company_id` NULL) |

이름은 가짜 이름. 비밀번호는 `.env`의 `SEED_DEFAULT_PASSWORD`로만 넣고(`python -m scripts.seed_users`), DB `users.password`에는 해시만 저장한다. 해시·검증은 `core/security.py`의 `hash_password()`·`verify_password()`를 쓴다 (`hashlib.pbkdf2_hmac`).

## 7. 목데이터

회사마다 권한 시나리오를 확인할 문서를 둔다.

- `internal` 공유 ON 1건 이상, 공유 OFF 1건 이상
- `confidential` 1건 이상 (계약 단가 포함)
- 가짜 연락처·이메일을 심은 문서 1건 (마스킹 확인용)
