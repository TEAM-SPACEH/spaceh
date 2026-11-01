---
name: task-workflow
description: 기능 ID(예: S-06) 또는 새 작업을 시작할 때 사용합니다. 이슈 생성 → 브랜치 → 구현 → 검증 → 커밋 → PR → 머지까지의 순서를 안내합니다.
---

# 작업 워크플로

## 목적

모든 작업을 같은 흐름(이슈 → 브랜치 → PR → 머지)으로 진행하고, 완료 근거를 남긴다.

## 읽기 전략

항상 확인한다.

- `docs/features.md` — 기능 ID의 패키지·담당·선행
- 「기능명세표」의 해당 기능 행, 메소드 명세서의 해당 메소드 (사용자에게 받거나 팀 드라이브에서 확인)
- `docs/conventions/git.md` — 브랜치·커밋·PR 형식
- `docs/conventions/coding.md` — 폴더 계층·DB·보안 규칙

작업 종류에 따라 추가로 확인한다.

- 권한이 걸리는 기능(검색·답변·보고서·원문·공유·승인): `docs/architecture/overview.md` §2
- 다른 묶음의 함수를 부르거나 내 함수를 남이 부름: `docs/architecture/overview.md` §3
- 로더·청킹·Chroma·DB: `docs/architecture/data-model.md`
- "이거 정한 거였나?": `docs/decisions.md`

## 절차

1. **작업 확인**: 기능 ID의 상세 설명·우선순위·담당을 확인한다. 담당이 현재 사용자(`git config user.name`)와 다르면 진행 전에 확인한다. 명세에 없는 작업이면 먼저 묻는다.
2. **이슈 생성**: `.github/ISSUE_TEMPLATE`의 형식으로, 제목에 기능 ID를 넣는다.
3. **브랜치 생성**: `develop` 최신화 후 `prefix/{이슈번호}-work-summary`.
4. **구현**: 메소드 명세서의 이름·입력·출력을 그대로 쓴다. 요청 범위 밖 기능·추상화를 추가하지 않는다. 다른 사람 담당 파일은 고치지 않는다.
5. **검증**: 실제로 실행한 검증만 기록한다. 권한 관련 변경은 권한 없는 계정으로도 확인한다. MySQL·API 키가 없어 못 한 검증은 "미검증"으로 남긴다.
6. **커밋**: `commit-planning-workflow`로 단위를 나눠 커밋한다.
7. **PR**: `pr-prep-workflow`로 본문 작성, `closes #N` 포함.
8. **머지**: 리뷰 승인 1명 후 팀장이 merge commit으로 머지한다 (브랜치 보호로 팀장만 가능). 팀원 작업이면 팀 채팅에 머지를 요청하라고 안내한다.

## 하지 말 것

- `main`·`develop`에 직접 커밋·push
- 검색 결과를 받은 뒤 권한을 거르는 사후 필터
- `.env`·원본 문서·`data/` 내용 커밋
