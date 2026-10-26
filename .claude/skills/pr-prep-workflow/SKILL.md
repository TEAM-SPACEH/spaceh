---
name: pr-prep-workflow
description: 브랜치 작업을 마치고 push와 PR을 만들 때 사용합니다. PR 제목·본문을 템플릿 기준으로 작성하고 머지 전 확인 사항을 점검합니다.
---

# PR 준비 워크플로

## 읽기 전략

- `.github/pull_request_template.md`
- `docs/conventions/git.md` (PR 제목 형식, 리뷰어)

## 절차

1. 커밋이 정리됐는지 확인한다: `git log --oneline origin/develop..HEAD`
2. `develop` 최신 내용을 합친다: `git fetch origin && git merge origin/develop`
3. push: `git push -u origin <branch>`
4. 제목: `[PREFIX] #N 작업 요약`
5. 본문: 템플릿 섹션 구조를 유지하고 문단형으로 쓴다.
   - `Related Issues`에 `closes #N`
   - `Verification`에는 실제 실행한 것만
   - 화면 변경이면 `Screenshot`에 캡처, 없으면 없다고 적기
   - AI 비중이 크면 `Implementation Notes`에 AI 활용 한 줄
6. 생성: `gh pr create --base develop --title "..." --body-file <file>`
7. 리뷰어 지정: 같은 묶음 짝꿍. 공용 파일·권한 변경이면 팀장도.

## 하지 말 것

- 실행하지 않은 검증을 성공처럼 쓰기
- 리뷰 승인 없이 머지
- squash 머지 (나눠 둔 커밋 보존을 위해 merge commit 사용)
