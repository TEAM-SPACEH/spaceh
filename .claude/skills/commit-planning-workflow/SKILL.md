---
name: commit-planning-workflow
description: 커밋 요청 또는 PR 준비 시 실제 diff를 기능·작업·검증 단위로 분해하고 stage/commit 계획을 세울 때 사용합니다.
---

# 커밋 계획 워크플로

## 목적

커밋 전에 실제 diff를 기준으로 작업 단위를 나눈다. 커밋 수를 1~2개로 제한하지 않는다. 독립적으로 리뷰·revert·검증 가능한 단위라면 필요한 만큼 나눈다.

## 입력 점검

- 현재 브랜치와 이슈 번호 (`git branch --show-current`에서 `{이슈번호}` 추출)
- 변경 파일 목록
- 제외해야 할 파일: `.env`, 개인 설정, 원본 문서, `data/` 내용, 무관한 사용자 변경

이슈 번호를 확인할 수 없으면 커밋 전에 사용자에게 묻는다.

```bash
git status --short
git diff --stat
git diff --cached --name-only
```

## 분해 기준

아래 중 하나라도 다르면 별도 커밋을 우선 고려한다.

- 변경 surface: 화면(`views`) / 서비스·저장소 / `core`·`models` / 테스트 / 문서 / 설정·패키지
- 순수 refactor·rename·remove와 동작 변경
- `requirements.txt` 변경은 항상 따로

## 계획 형식

```markdown
## Commit Plan

- Commit 1: `prefix: #N 작업 요약`
  - files:
  - reason:
  - verification:
```

## 실행

1. 명시적 path로 stage한다: `git add -- path/to/file`
2. 커밋마다 확인한다: `git diff --cached --name-only`, `git diff --cached --check`
3. 메시지 형식: `prefix: #{이슈번호} 작업 요약` + 필요 시 body (`docs/conventions/git.md`)
4. Co-Authored-By 등 AI 서명 푸터를 넣지 않는다.
