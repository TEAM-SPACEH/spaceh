"""AI coding agent 공용 guard hook.

Claude Code · Codex · Gemini CLI의 "셸 명령 실행 전" hook에서 호출한다.
규칙을 우회하는 git/gh 명령이면 exit 2로 실행을 막고 이유를 stderr로 알린다.

도구마다 stdin JSON 모양이 달라서 아래 위치를 차례로 찾는다.
- Claude Code · Codex · Gemini CLI: tool_input.command
- Cursor (beforeShellExecution): command

규칙 근거: docs/conventions/git.md
"""

import json
import re
import sys

SEGMENT = r"[^;&|\n]*"  # 같은 명령 조각 안에서만 매칭 (;, &&, |, 줄바꿈으로 끊김)

BLOCKED = [
    (
        re.compile(rf"\bgit\b{SEGMENT}\s--no-verify\b"),
        "--no-verify로 git 훅을 우회할 수 없습니다.",
    ),
    (
        re.compile(rf"\bgit\s+push\b{SEGMENT}\s(--force(-with-lease)?|-f)\b"),
        "force push는 금지입니다. 새 커밋으로 고쳐서 push하세요.",
    ),
    (
        re.compile(rf"\bgit\s+push\b{SEGMENT}\s(\S+:)?(main|develop)\b"),
        "main·develop에 직접 push할 수 없습니다. 작업 브랜치 → PR로 올리세요.",
    ),
    (
        re.compile(rf"\bgh\s+pr\s+merge\b{SEGMENT}--admin\b"),
        "리뷰 승인 없이 관리자 권한으로 머지할 수 없습니다.",
    ),
]


def extract_command(event: object) -> str:
    if not isinstance(event, dict):
        return ""
    tool_input = event.get("tool_input")
    candidates = [
        tool_input.get("command") if isinstance(tool_input, dict) else None,
        event.get("command"),
    ]
    return next((c for c in candidates if isinstance(c, str) and c), "")


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    command = extract_command(event)
    for pattern, reason in BLOCKED:
        if pattern.search(command):
            print(f"[spaceH 규칙] {reason} (docs/conventions/git.md)", file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
