# spaceH Agent Guide

agent용 허브 문서다. 상세 규칙을 여기에 복붙하지 말고, 작업 종류에 맞는 source of truth 문서를 먼저 읽는다.

## 저장소 정체

- Product: spaceH — 현대경제연구원·현대무벡스·현대엘리베이터 문서를 권한 범위 안에서 통합 검색·질의응답·보고서로 만드는 플랫폼 (현대 AI 서비스 개발자 부트캠프 프로젝트 1)
- 스택: Python 3.11 · Streamlit · LangChain · Chroma · MySQL 8(PyMySQL 직접 SQL) · OpenAI API — **수업에서 배운 기술만** 쓴다 (예외는 `docs/decisions.md`)
- 기능 기준: 팀 드라이브의 「기능명세표」 28개 (S·I·M·A·R) 와 메소드 명세서. 저장소 안 색인은 [features](./docs/features.md) (담당·순서·선행 포함).
- 작업 키: GitHub 이슈 번호 `#N` (이슈 제목에 기능 ID, 예: `[FEAT] S-06 하이브리드 검색` → 브랜치 `feat/12-hybrid-search`)
- 로컬 실행만 한다 (배포 없음). 시연은 로컬 PC.

## 기본 순서

1. 「기능명세표」·메소드 명세서에서 기능 ID와 메소드 시그니처 확인
2. GitHub 이슈 생성 → `develop`에서 브랜치 생성
3. 구현 → 실제 실행으로 검증
4. 커밋 계획 → 커밋 → push → `develop`으로 PR (`closes #N`)
5. 리뷰 승인 → merge commit으로 머지

절차 상세: [task-workflow](./.claude/skills/task-workflow/SKILL.md), 형식: [Git 규칙](./docs/conventions/git.md)

## 작업 유형별 라우팅

| 작업 유형 | 먼저 볼 문서 |
|---|---|
| 작업 시작 (기능 ID) | `.claude/skills/task-workflow/SKILL.md`, `docs/features.md` |
| 코드 추가·수정 | `docs/conventions/coding.md`, `docs/architecture/overview.md` §3 (패키지 사이 약속) |
| 검색·답변·보고서·원문 보기 (권한이 걸리는 모든 것) | `docs/architecture/overview.md` §2 (권한 규칙) |
| 로더·청킹·Chroma·DB 필드 | `docs/architecture/data-model.md` |
| 이미 정한 것인지 확인 | `docs/decisions.md` |
| 환경 설정·실행·패키지 추가 | `docs/workflows/local-development.md` |
| AI 도구로 코드 생성 | `docs/conventions/ai.md` |
| 커밋 분해 | `.claude/skills/commit-planning-workflow/SKILL.md`, `docs/conventions/git.md` |
| PR 작성 | `.claude/skills/pr-prep-workflow/SKILL.md`, `.github/pull_request_template.md` |

## 필수 작업 원칙

- **권한 필터 우선**: 검색·질의응답·보고서 수집은 S-03 권한 필터를 벡터·BM25 검색 **전에** 적용한다. 결과를 받은 뒤 거르지 않는다. 원문 보기·다운로드 전에는 문서 접근 권한을 다시 확인한다.
- **명세 우선**: 메소드 이름·입력·출력은 메소드 명세서대로 쓴다. 바꿔야 하면 명세서를 먼저 고치고 팀에 알린다.
- **계층 지키기**: `views` → `services` → `repositories`. 화면에서 SQL·Chroma를 직접 부르지 않는다.
- **SQL은 `%s` 바인딩만**: f-string·문자열 연결로 SQL을 만들지 않는다.
- **비밀 값은 `.env`만**: API 키·DB 비밀번호·시드 비밀번호를 코드·문서·로그에 쓰지 않는다.
- **패키지는 `requirements.txt`에 있는 것만**: 새 패키지는 팀장 승인 후 추가한다. 표준 라이브러리로 되는 일(해시 `hashlib`, HTTP `urllib.request`, 테스트 `unittest`)에 외부 패키지를 들이지 않는다.
- 확실하지 않은 기술 정보는 "(확인 필요)"로 표시하고 공식 문서로 확인한 뒤 지운다.
- 요청 범위 밖 기능·추상화·refactor를 추가하지 않는다. 다른 사람 담당 파일은 고치지 않는다.

## 검증

```bash
git diff --check
python -m unittest          # 테스트가 있는 변경
streamlit run main.py       # 화면 변경 — 직접 띄워 확인
```

실행하지 못한 검증(MySQL·API 키 없음 등)은 "미검증"으로 남기고 이유를 적는다.

## 완료 후 확인

- 기능명세표의 상세 설명을 충족했는지
- 권한 없는 계정으로도 확인했는지 (권한 관련 변경)
- `.env`, 원본 문서, `data/` 내용, 임시 파일이 diff에 없음
- 실행한 검증과 생략한 검증(이유 포함)을 요약에 남김

## 하지 말 것

- `AGENTS.md`·`CLAUDE.md`에 긴 규칙 원문, 진행 상황, 작업 로그를 넣지 않는다.
- `docs/*` 내용을 복붙해 중복 source of truth를 만들지 않는다.
- `main`·`develop`에 직접 push하지 않는다. force push, `--no-verify`를 쓰지 않는다.
