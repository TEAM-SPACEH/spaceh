# 코드 규칙

「기능명세표」·메소드 명세서·「패키지 및 폴더구조」 시트가 기준이다. 이 문서와 시트가 다르면 시트를 따르고 이 문서를 고친다.

## 1. 기본

- Python 3.11, PEP 8, 들여쓰기 4칸, UTF-8
- **수업에서 배운 기술만 쓴다.** 패키지는 `requirements.txt`에 있는 것만 쓰고, 표준 라이브러리로 되는 일은 표준 라이브러리로 한다. ([패키지 추가 규칙](../workflows/local-development.md#패키지-추가-규칙))
- `print()` 대신 `logging`을 쓴다. 비밀번호·API 키·문서 본문은 로그에 남기지 않는다.

## 2. 폴더 구조와 계층

```text
main.py          # Streamlit 진입점 (streamlit run main.py)
core/            # 설정(.env), DB 연결 — 팀장과 상의 후 수정
models/          # 공통 데이터 모델 (공통 문서 형식 등)
app/
├── search/      # S-01 S-02 S-04 S-06 S-07
├── ingestion/   # I-01~I-05
├── auth/        # M-01
├── users/       # M-02
├── permissions/ # S-03 M-03
├── documents/   # S-05
├── reports/     # R-01~R-05, A-06
├── history/     # M-04
└── admin/       # A-01~A-05, A-07, I-05 화면, 관리자 대시보드
data/            # uploads/, chroma/ (Git 제외)
tests/           # app과 같은 구조 (tests/search/test_search_service.py)
```

패키지 안은 아래 계층을 따른다.

| 계층 | 하는 일 | 하면 안 되는 일 |
| --- | --- | --- |
| `views/`, `views/components/` | Streamlit 화면, 입력 받기, 결과 표시 | SQL·Chroma 직접 호출, 권한 판단 |
| `services/` | 업무 로직, 권한 확인, LLM 호출, 감사 로그 기록 | `st.*` 호출 |
| `repositories/` | MySQL·Chroma 읽기/쓰기 | 업무 판단 |
| `validators.py` | 입력값 형식 검증 | DB 접근 |

- 화면은 `services`만 호출한다. 다른 패키지의 기능은 그 패키지의 `services`를 거친다.
- import는 루트 기준으로 쓴다: `from core.database import get_connection`, `from app.search.services.search_service import search_documents`

## 3. 이름

| 대상 | 규칙 | 예 |
| --- | --- | --- |
| 함수·변수·모듈 | snake_case | `get_user_info()`, `user_service.py` |
| 클래스 | PascalCase | `DocumentIndexer` |
| 상수 | UPPER_SNAKE_CASE | `MAX_UPLOAD_MB` |
| 불리언 | `is_`, `has_`, `can_` | `is_authenticated()` |

메소드 이름·입력·출력은 메소드 명세서와 똑같이 쓴다.

## 4. 함수

다른 파일에서 부르는 함수에는 타입 힌트와 한 줄 docstring을 붙이고, docstring에 기능 ID를 적는다.

```python
def update_email(user_id: int, email: str) -> bool:
    """M-02 이메일 형식을 검증하고 본인의 이메일 정보를 변경한다."""
```

주석은 "왜"를 적는다. 주석 처리한 옛 코드는 남기지 않는다.

## 5. DB (MySQL + PyMySQL)

- 연결은 `core.database.get_connection()`으로만 연다.
- Chroma는 `core.chroma.open_chroma_client()`로만 연다 (`with` 블록). `chromadb.PersistentClient`를 직접 만들지 않는다. 동시에 열고 닫을 때 생기는 Chroma 내부 참조 오류와 Windows 파일 잠금을 막는다.
- SQL 값은 반드시 `%s` 바인딩으로 넘긴다.

```python
with get_connection() as conn, conn.cursor() as cur:
    cur.execute("SELECT * FROM users WHERE employee_no = %s", (employee_no,))
    user = cur.fetchone()
```

- 테이블 변경은 팀 ERD와 `db/schema.sql`에 함께 반영하고 팀에 알린다. ORM은 쓰지 않는다.

## 6. 보안 필수 규칙

1. 검색·질의응답·보고서 수집은 S-03 권한 필터를 벡터·BM25 검색 **전에** 적용한다.
2. 원문 보기·다운로드·보고서 다시 열기 전에는 문서 접근 권한을 다시 확인한다.
3. 로그인·검색·원문 열람·보고서 생성·다운로드·공유 변경·권한 승인은 감사 로그(A-04)에 기록한다.
4. 비밀번호는 표준 라이브러리 `hashlib.pbkdf2_hmac`(SHA-256, 사용자별 salt)으로 해시해 저장하고, 비교는 `hmac.compare_digest`로 한다.
5. API 키·DB 비밀번호는 `core.config`를 거쳐 `.env`에서만 읽는다.

## 7. 설정·경로

- 모델 이름·top-k·청크 크기 같은 값은 `core/config.py`에 모은다.
- 경로는 `pathlib.Path`로 만든다. OS마다 다른 구분자를 직접 쓰지 않는다.

### 화면 (views)

- 색·글꼴·둥글기는 `.streamlit/config.toml` 테마가 정한다. views에서 `<style>`·CSS를 넣지 않는다.
- 문서 제목·파일명·청크 본문·회사명처럼 데이터에서 온 글자는 `st.markdown`·`st.caption`·`st.write`에 넣지 않는다. Markdown 링크·이미지가 그대로 그려진다. `app.common.ui.show_text()`를 쓴다.
- 보안 등급 배지, 회사 태그, 각주 번호, 근거 하이라이트, 권한 없음 안내, 빈 결과, 현황 카드, 상태 표시(색인·열람 요청·DART 수집), 파일 형식 아이콘은 `app/common/ui.py` 함수를 쓴다. 없는 요소가 필요하면 직접 만들지 말고 팀장에게 요청한다.
- 페이지는 `page_header()` → 필터 → 본문 순서로 만든다. 주요 버튼만 `st.button(..., type="primary")`.
- 화면 문구는 "~합니다"체. 입력칸 예시는 "현대무벡스 3분기 실적 보고서"처럼 구체적으로 쓴다.

## 8. 오류 처리

- `services`는 메소드 명세서의 출력(`bool`, `None`, `dict`)으로 결과를 알린다.
- 화면은 실패를 `st.error()`로 쉬운 말로 보여 주고, 스택 트레이스는 로그에만 남긴다.
- `except: pass`로 오류를 삼키지 않는다.

## 9. LLM

- 모델 이름은 `core.config`에서 읽는다. 개발은 `gpt-4o-mini`, 시연은 `gpt-4o`.
- 임베딩은 `text-embedding-3-small`로 고정한다. 바꾸면 전체 재색인이 필요하다.
- 프롬프트는 패키지별 `services/prompts.py`에 상수로 모은다.
- 근거 기반 답변·보고서는 컨텍스트 안의 내용만 쓰게 하고, 근거가 없으면 "찾을 수 없음"으로 답하게 한다.

## 10. 테스트

- 표준 라이브러리 `unittest`, 파일은 `tests/<패키지>/test_<모듈>.py` (폴더마다 빈 `__init__.py`). 실행: `python -m unittest`
- P1 서비스 함수는 정상·실패 케이스를 하나 이상 테스트한다.
- 권한 누출 테스트(계정별 금지 문서 0건)는 통과해야 머지한다.
