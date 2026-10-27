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

## 2. 공통 문서 형식

모든 로더는 파일 형식과 관계없이 같은 `list[dict]`를 반환한다. I-03 마스킹도 dict 블록을 받으므로 별도 데이터클래스 변환 없이 전달한다. 문서·청크 모델은 아래 후속 처리 설계 예시이며 I-01에서 구현하지 않는다.

블록은 아래 5개 필드만 가진다. 원문 순서를 유지하고 빈 내용은 제외한다. `page`는 1 이상이며, 마스킹 전후에도 `page`·`location`·`section`을 보존한다. 회사·문서 ID·보안 등급은 문서 메타데이터에서 관리한다.

```python
block = {
    "block_type": "text",     # "text" / "table" / "title"
    "text": "추출한 내용",     # 표는 Markdown 표
    "page": 3,               # 형식별 위치 번호 (아래 표)
    "location": "p.3",
    "section": "",           # 가까운 제목, 없으면 빈 문자열
}

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
    blocks: list[dict]
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
| DOCX | 본문의 문단·표 통합 순번 (빈 문단도 순번에 포함) | `문단 3`, `표 4` (제목은 `section`) | 텍스트 뷰어, 해당 절 |
| PPTX | 슬라이드 번호 | `슬라이드 5` | 텍스트 뷰어, 해당 슬라이드 |
| XLSX | 시트 순번 | `시트 '사양표' A1:F20` | 표 뷰어 |
| HWP | 문단·표 순번 | `문단 12` | 텍스트 뷰어 |
| DART | 섹션 순번 | `사업보고서 > II. 사업의 내용` | DART 뷰어 (접수번호로 주소 생성) |

내부 문서 원본은 권한을 확인한 뒤 앱 안에서만 보여 준다. 외부 공유 링크(구글 드라이브 등)는 쓰지 않는다.

### I-01 파싱 범위

- `load_document(file_path)`는 PDF·DOCX·PPTX를 지원한다. 입력 파일은 20 MiB(20 × 1024 × 1024바이트) 이하로 제한하며, 파서를 호출하기 전에 검사한다. 형식 오류·손상 파일·빈 추출 결과는 예외로 알린다. XLSX·HWP는 I-04에서 추가한다. 이 제한은 입력 파일 기준으로, 압축 해제 후 크기·처리 시간·메모리 사용량의 상한은 아니다.
- PDF는 표 영역을 본문에서 제외한 뒤 위→아래, 왼쪽→오른쪽 순서로 텍스트 줄·표를 배치한다. 제목을 추측하지 않고 `section=""`로 두므로 I-02의 페이지 단위 대체 규칙을 사용한다. 이미지뿐인 페이지는 페이지 번호와 OCR 필요 경고를 로그에 남기고 건너뛴다. 뒤 페이지의 실제 번호는 유지하며, 문서 전체에서 추출 결과가 없으면 기존처럼 오류로 알린다. 좌표는 읽기 순서 정렬에만 사용하고 `location`에는 페이지 번호만 둔다. 이미지 속 글자·복잡한 다단 읽기 순서는 지원 범위 밖이다.
- DOCX는 본문 문단·표 순서를 보존하고 `Title`·`Heading` 스타일을 제목으로 사용한다. 머리말·꼬리말·텍스트 상자는 포함하지 않는다.
- PPTX는 슬라이드와 그룹 안 개체를 각각 위→아래, 왼쪽→오른쪽 순서로 읽고 슬라이드 제목을 `section`에 둔다. 이미지·차트·SmartArt·발표자 노트는 포함하지 않는다.
- 표는 행·열 격자를 유지하며 병합 시작 셀에 내용을 두고 연속 셀은 비운다. Markdown에 병합 표현이 없어 병합 범위 자체는 보존하지 않는다. PDF는 라이브러리가 반환한 빈 셀을 유지한다.
- 첫 행을 임의로 헤더로 해석하지 않고 빈 Markdown 헤더 뒤에 원본 모든 행을 둔다. 셀 줄바꿈(PPTX 소프트 줄바꿈 포함)은 `<br>`, 파이프·역슬래시는 이스케이프한다. 중첩 DOCX 표는 부모 셀 안에 텍스트로 포함한다.

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

✅ = `db/schema.sql`에 있음. 나머지 이름은 ERD가 끝나면 바뀔 수 있다.

| 테이블 | 용도 | 기능 |
| --- | --- | --- |
| ✅ `companies` | 계열사 | A-07 |
| ✅ `users` | 사용자 (사원번호 `employee_no` 로그인) | M-01, M-02 |
| ✅ `documents` | 문서 메타데이터·색인 상태·공유 | I-02, A-01~A-03 |
| `document_access_requests` | 열람 권한 요청 | M-03, A-05 |
| `document_permissions` | 승인된 문서 단위 열람 권한 | A-05 → S-03 |
| `reports` · `report_sections` · `report_footnotes` | 보고서·섹션·각주 | R-02~R-05, A-06 |
| `user_histories` | 내 사용 히스토리 | M-04 |
| `audit_logs` | 감사 로그 (차단 포함 전부) | A-04 |
| `dart_collect_jobs` | DART 수집 이력 | I-05 |

`user_histories`는 성공한 사용 이력, `audit_logs`는 차단을 포함한 모든 행위다. 같은 서비스 함수에서 둘 다 기록한다.

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
