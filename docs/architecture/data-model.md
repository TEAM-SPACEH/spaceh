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
| 휴대전화 (010·011·016~019, 국제형식 +82 포함) | 항상 | `[마스킹: 연락처]` |
| 이메일 | 항상 | `[마스킹: 이메일]` |
| 계좌번호 | 같은 줄에 "계좌·은행·입금"이 있을 때만 | `[마스킹: 계좌]` |
| 회사 대표번호·유선, 사업자번호, 법인등록번호("법인등록번호" 라벨이 앞에 붙은 경우), 공시 접수번호 | 마스킹 안 함 | - |

주민등록번호는 서비스에서 쓰지 않기로 해서 마스킹하지 않는다. 법인등록번호는 계좌번호 모양과 겹쳐, "은행·계좌" 키워드가 있는 줄에서도 계좌로 오인해 가리지 않게 한 예외다.

계약 단가는 마스킹하지 않는다. 그런 문서는 `confidential`로 지정해 권한으로 막는다.

### 청킹 (I-02)

| 규칙 | 적용 문서 |
| --- | --- |
| 절 단위 (제목 기준) | `report` · `disclosure` · `manual` · `memo` |
| 페이지·슬라이드 단위 | `intro` |
| 표는 행 단위로 분할, 머리글·표 제목·섹션명 반복 | `spec` + 모든 문서의 표 |

- 800자를 넘는 청크만 800자·겹침 150자로 다시 자른다 (개발 중 조정).
- 제목 구조가 없는 PDF는 페이지 단위 + 800자 규칙으로 대신한다.

#### 청킹 함수 계약

`split_into_chunks(blocks, metadata, chunking_config)`는 **마스킹을 완료한** I-01 dict 블록과 검증된 문서 공통 메타데이터를 받는다. DB·API·Chroma를 호출하거나 마스킹을 대신 수행하지 않는다. 반환은 위 `Chunk`와 같은 `chunk_id`·`text`·`metadata` 필드의 dict 목록이다. 입력 블록·메타데이터는 변경하지 않는다.

- 설정 키는 `chunk_size`(기본 800), `chunk_overlap`(기본 150)이며 정수만 받는다. 크기는 양수, 겹침은 0 이상 크기 미만이어야 한다. 출처 접두어를 제외한 본문 문자 수에 적용하며 공백뿐인 조각은 반환하지 않는다.
- `report`·`disclosure`·`manual`·`memo`는 같은 절을 페이지 경계 너머로 묶을 수 있다. 절이 없는 블록과 `spec`의 제목 없는 본문은 페이지 기준, `intro`는 절 유무와 무관하게 페이지·슬라이드 기준으로 묶는다. 새 제목과 표 앞에서는 본문 그룹을 닫는다(`intro`의 제목은 페이지 그룹에 포함).
- 표는 문맥·머리글을 포함해 설정 크기를 넘으면 행 단위로 나누고 문맥과 Markdown 머리글을 반복한다. I-01이 만든 빈 Markdown 머리글 뒤 첫 원본 행도 머리글 문맥으로 반복한다(의미상 머리글인지 추론하지 않음). 행은 겹치거나 잘라 버리지 않는다. 한 행이나 반복 머리글·문맥 자체가 크면 크기를 초과하는 단독 청크로 보존하며, 임베딩 연결 시 토큰 한도를 별도로 검사해야 한다. 같은 페이지·절의 직전 비표 블록 최대 2개와 `section`을 표 앞에 붙인다. 이는 표 제목을 자동 판별하는 것이 아니라 원문 문맥을 보존하는 규칙이다. `단위:`·`단위：`가 있는 비표 블록은 같은 페이지·절의 연속 표에도 유지한다. 다른 페이지·절이나 새 제목에서는 문맥을 초기화한다.
- 여러 블록을 합칠 때 줄바꿈으로 연결한다. 긴 본문은 고정 문자 구간과 겹침으로 분할하며 해당 구간에 실제 포함된 블록의 시작 페이지·시작~끝 위치를 기록한다. 문장을 기준으로 경계를 조정하지는 않는다.
- 청크 ID는 `{doc_id}#{1부터 시작하는 순번:04d}`, `chunk_index`도 1부터 시작한다. 본문 앞에는 `[회사명 · 문서 제목 · 위치]` 한 줄을 붙인다. 회사·보안·공유 값은 공통 메타데이터에서만 복사하며 블록으로 덮어쓰지 않는다.
- 표의 단위가 앞 페이지에만 있거나 이미지로 들어 있으면 현재 규칙만으로 연결하지 못한다. 표 전체 길이에 따른 과대 청크는 행 분할로 줄이지만, 한 행·반복 머리글 자체가 입력 한도를 넘는 경우는 임베딩 단계에서 별도로 처리해야 한다.

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

### 공통 메타데이터 구성 (I-02)

`build_metadata(doc_id, document_info, extracted_info)`는 DB·파일을 직접 조회하지 않고 전달받은 정보를 검증·매핑한다. 제목이 없거나 공백이면 `file_name`의 마지막 확장자를 뺀 이름으로 대체한다. 등록한 제목이 있으면 유지하며 파일명에서 작성일·회사·보안 등급을 추측하지 않는다.

- `document_info` 필수 값: `company_id`, `company_name`, `file_name`(경로 제외), `file_format`, `doc_type`, `access_level`, `is_group_shared`. 회사명은 호출자가 계열사 정보에서 조회해 전달한다. 신규 회사 코드를 고정 목록으로 제한하지 않는다.
- 선택 값: `title`, `source_type`(기본 `internal`), `source_url`. `published_date`는 DB `date` 또는 ISO 날짜 문자열을 받아 검색용 `YYYYMMDD` 정수로 변환한다. 작성일이 없거나 `NULL`·빈 문자열이면 문서 업로드 시각 `created_at`의 날짜로 대체한다(`date`·`datetime` 또는 ISO 날짜·시각 문자열). 둘 다 없거나 날짜 형식이 잘못되면 오류로 알리며 `0`·현재 날짜·파일명 날짜로 대체하지 않는다.
- 문서 등록 호출자는 같은 확정 날짜를 DB의 `documents.published_date`에도 저장해야 한다. DB에서 이미 읽어 온 작성일은 그대로 사용한다. 이 함수는 입력 정보나 DB를 변경하지 않으며, 재색인 시에도 최초 업로드일을 사용한다.
- `is_group_shared`는 bool 또는 DB의 정수 `0`·`1`을 받아 bool로 변환한다. 그룹사 공유는 `internal` 문서에만 허용한다. 권한 필드는 `document_info`에서만 받는다.
- `extracted_info`에는 I-01 블록의 `page`, `location`, `section`, `block_type`을 전달한다. 문서 공통값만 구성할 때는 `{}`를 전달해 위치를 `0`·`""`로 두고 후속 청크 생성에서 실제 위치를 붙인다. 블록의 `text`는 메타데이터에 복사하지 않는다.
- 이 단계는 문서 ID 생성·원본 해시 계산·DB 저장·청크 번호 부여·임베딩을 수행하지 않는다. 원본 해시는 문서 등록 정보에서 별도로 관리한다.

### Chroma 색인 저장 (I-02)

`DocumentIndexer(chroma_config=None, collection_name=None)`는 연결 설정 `{"path": 경로}`와 컬렉션명을 받는다. 생략하면 공통 설정의 Chroma 경로·컬렉션명을 사용한다. 클라이언트와 컬렉션을 객체에 보관하며 `with DocumentIndexer(...) as indexer:` 또는 `close()`로 반드시 종료한다. 연결은 `core.chroma.open_chroma_client()`로만 연다. 벡터를 직접 전달하므로 Chroma 자동 임베딩은 사용하지 않는다.

- `index_chunks(doc_id, chunks, embeddings)`는 입력 순서에 대응하는 청크·벡터를 저장하고 `{"doc_id": 문서 ID, "chunk_count": 저장 수, "index_status": "done"}`을 반환한다. MySQL 문서 상태 변경은 호출자가 수행한다.
- 모든 입력을 먼저 검증한다. 청크 ID는 `{doc_id}#...` 형식이고 문서 메타데이터의 `doc_id`도 일치해야 한다. 중복 ID·빈 청크 목록·빈 텍스트·잘못된 권한 필드·중첩 메타데이터·개수 또는 차원이 다른 벡터·비유한 수는 거부한다. 빈 목록으로 기존 색인을 지우지 않는다.
- 저장 전에 입력 ID의 기존 메타데이터를 배치별로 조회한다. 다른 문서가 소유하거나 `doc_id`로 소유자를 확인할 수 없는 기존 ID가 하나라도 있으면 모든 쓰기를 거부한다. ID 접두사 검사만으로 소유권을 판단하지 않는다.
- [Chroma 클라이언트의 배치 상한](https://docs.trychroma.com/reference/python)을 따라 소유권을 모두 확인한 뒤 `upsert`하고, 새 청크 저장이 모두 끝난 뒤 해당 문서의 오래된 ID만 삭제한다. 다른 문서는 유지한다. 실패는 예외로 전달하며 성공 상태를 반환하지 않는다.
- 여러 배치에 걸친 교체는 트랜잭션이 아니다. 중간 오류가 나면 일부 새 내용과 기존 내용이 함께 남을 수 있으므로 호출자는 문서를 실패로 기록하고 같은 입력으로 재시도해야 한다. 같은 문서에 대한 동시 재색인은 호출자가 직렬화해야 한다. DB 상태와 검색 노출의 연결은 적재 파이프라인에서 검증한다.

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
