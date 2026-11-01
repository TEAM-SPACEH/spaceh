# Git 규칙

Git 규칙의 원본이다. README에는 요약만 두고, 둘이 다르면 이 문서를 따른다.

## 1. 브랜치 전략

```text
main ─────────●──────────────●────  시연 가능한 상태만
               ↑ Day 5 관문    ↑ Day 7 동결
develop ──●──●──●──●──●──●──●──●──  통합(기본) 브랜치
           ↑     ↑
   feat/12-hybrid-search   fix/20-login-error
```

| 브랜치 | 역할 | 머지 |
| --- | --- | --- |
| `main` | 시연 가능한 상태만 둔다. | 팀장 |
| `develop` | 통합 브랜치이자 기본 브랜치. 모든 작업은 여기서 분기한다. | 리뷰 승인 후 팀장 |
| `prefix/{이슈번호}-work-summary` | 작업 브랜치. 요약은 영어 소문자와 `-` | - |

- `main`·`develop`에 직접 push하지 않는다. 항상 PR로 합친다.
- `main` 머지는 Day 5 관문 통과 후, Day 7 기능 동결 후. 동결 이후에는 `fix/` 브랜치만 받는다. 발표 버전에 `v1.0` 태그를 단다.

## 2. 작업 순서

```bash
# 1. GitHub 이슈 생성 → 이슈 번호 확인
git switch develop
git pull origin develop
git switch -c feat/12-hybrid-search

git add -- <파일>
git commit -m "feat: #12 BM25 검색 결과 결합 구현"
git push -u origin feat/12-hybrid-search
# 2. develop으로 PR → 승인 → 머지 → 브랜치 삭제
```

하루 한 번 이상, PR 보내기 직전에는 꼭 develop을 받아 합친다. 이미 push한 브랜치는 rebase하지 않는다.

```bash
git fetch origin
git merge origin/develop
```

## 3. 커밋

```text
prefix: #{이슈번호} 작업 요약

body (필요할 때만)
```

| Prefix | 설명 |
| --- | --- |
| `feat` | 새로운 기능 추가 |
| `fix` | 버그 수정 |
| `refactor` | 동작 변화 없는 코드 구조 개선 |
| `test` | 테스트 추가 및 변경 |
| `docs` | 문서 수정 |
| `chore` | 패키지, 설정, 기타 작업 |
| `style` | 코드 동작 변경이 없는 formatting 변경 |
| `perf` | 성능 개선 |

- 요약은 한글 명사형으로 끝낸다. (추가, 구현, 보정, 수정)
- 커밋은 독립적으로 리뷰하고 되돌릴 수 있는 단위로 나눈다. 리팩터링과 동작 변경을 섞지 않는다.
- `git add .` 대신 파일을 지정해 stage하고, 커밋 전 `git status`로 확인한다.
- 커밋 메시지·PR에 AI 도구 서명(`Co-Authored-By` 등)을 넣지 않는다.

## 4. PR과 리뷰

- 제목: `[FEAT] #12 BM25 검색 결과 결합 구현` (커밋 형식, prefix 대문자·대괄호)
- 본문은 `.github/pull_request_template.md`를 따른다. Verification에는 실제로 실행한 것만 쓴다.
- 리뷰어: 같은 묶음 짝꿍 1명. `core/`, `models/`, `main.py`, `requirements.txt`, DB 스키마, 권한(S-03) 변경은 팀장도 넣는다.
- 자동으로 되는 것: 리뷰어 요청(`.github/CODEOWNERS`, 바뀐 경로 기준), 작성자 assignee, 라벨(브랜치 prefix → `FEAT`·`FIX` 등, 경로 → `검색·계정`·`문서·관리자`·`답변·보고서`·`공통`). 자동 요청이 빠졌거나 틀리면 손으로 고친다. DB 스키마 파일은 경로가 정해지면 CODEOWNERS에 추가한다.
- 리뷰 요청은 반나절 안에 본다. 승인 1명 이상이면 **팀장이** merge commit으로 합친다. 스쿼시하지 않는다.
- `develop`·`main`은 브랜치 보호로 팀장만 머지할 수 있다. 승인을 받았으면 팀 채팅에 PR 링크를 올려 머지를 요청한다.
- PR은 기능 ID 하나 단위로 작게. 화면 변경은 스크린샷을 붙인다.
- 정해 둔 결정을 바꾸는 PR은 [결정 기록](../decisions.md)도 같은 PR에서 고친다.

## 5. 올리면 안 되는 파일

- `.env`, `.venv/`, `__pycache__/`
- `data/uploads/`, `data/chroma/` 내용, 수집한 원본 문서 (공유는 구글 드라이브)

실수로 `.env`를 올렸다면 바로 팀장에게 알리고 키를 재발급한다. 커밋을 지워도 기록에 남는다.

## 6. 충돌

- 그 파일을 마지막에 고친 사람(`git log -- <파일>`)과 같이 해결한다.
- 공용 파일(`core/`, `models/`, `main.py`, `requirements.txt`) 충돌은 팀장과 같이 본다.

## 7. AI 도구 가드

Claude Code·Codex·Gemini CLI는 `scripts/agent_guard.py` 훅으로 force push, `--no-verify`, `main`·`develop` 직접 push, `gh pr merge --admin`을 막는다. 훅이 막으면 우회하지 말고 규칙대로 다시 한다.
