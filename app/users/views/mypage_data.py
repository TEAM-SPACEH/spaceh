"""M-02·M-03·M-04 내 정보 화면이 쓰는 순수 계산: 통계 3개, 최근 30일 요청, 사용 기록 묶음.

DB·Streamlit을 부르지 않는다. 입력은 history_service(get_user_history·get_access_request_history)가 준 dict 목록이고,
시각은 서비스가 만든 "YYYY-MM-DD HH:MM" 문자열이다. 화면(mypage.py)은 이 결과를 그리기만 한다.
"""

from datetime import date, datetime, timedelta

_TIME_FORMAT = "%Y-%m-%d %H:%M"

# "최근 30일" 열람 권한 요청 (Figma 카드 오른쪽 위 글자와 같다)
REQUEST_WINDOW_DAYS = 30

# 사용 기록 종류. history_type 값(audit_logs.action)과 열람 권한 요청(access_request)을 한 줄로 합친다.
KIND_ACCESS_REQUEST = "access_request"


def parse_time(value: str | None) -> datetime | None:
    """서비스가 준 "YYYY-MM-DD HH:MM" 문자열을 시각으로 바꾼다. 없거나 모양이 다르면 None."""
    if not value:
        return None
    try:
        return datetime.strptime(value, _TIME_FORMAT)
    except ValueError:
        return None


def usage_counts(history: list[dict], requests: list[dict], today: date) -> dict[str, int]:
    """M-02 프로필 카드 통계: 이번 달 질문 수, 만든 보고서 수, 승인된 열람 요청 수."""
    month = (today.year, today.month)
    asked = 0
    for item in history:
        when = parse_time(item.get("created_at"))
        if item.get("history_type") == "ask" and when and (when.year, when.month) == month:
            asked += 1
    return {
        "asked": asked,
        "reports": sum(1 for item in history if item.get("history_type") == "report_create"),
        "approved": sum(1 for request in requests if request.get("status") == "approved"),
    }


def recent_requests(requests: list[dict], now: datetime, days: int = REQUEST_WINDOW_DAYS) -> list[dict]:
    """M-03 최근 days일 안에 낸 요청만 남긴다 (서비스가 준 최신순을 유지한다)."""
    since = now - timedelta(days=days)
    return [request for request in requests if (parse_time(request.get("created_at")) or datetime.min) >= since]


def build_timeline(history: list[dict], requests: list[dict]) -> list[dict]:
    """M-04 사용 이력과 열람 권한 요청을 시간 역순 한 목록으로 합친다.

    반환 항목: {"kind", "title", "when"(datetime), "result_count", "is_blocked"}
    시각을 읽을 수 없는 항목은 날짜 묶음을 만들 수 없어 뺀다.
    """
    entries = []
    for item in history:
        when = parse_time(item.get("created_at"))
        if when is None:
            continue
        entries.append({
            "kind": item["history_type"], "title": item.get("summary") or "", "when": when,
            "result_count": item.get("result_count"), "is_blocked": bool(item.get("is_blocked")),
        })
    for request in requests:
        when = parse_time(request.get("created_at"))
        if when is None:
            continue
        entries.append({
            "kind": KIND_ACCESS_REQUEST, "title": request.get("title") or "", "when": when,
            "result_count": None, "is_blocked": False,
        })
    entries.sort(key=lambda entry: entry["when"], reverse=True)
    return entries


def group_label(day: date, today: date) -> str:
    """날짜 묶음 제목: 오늘 / 어제 / MM.DD."""
    if day == today:
        return "오늘"
    if day == today - timedelta(days=1):
        return "어제"
    return day.strftime("%m.%d")


def group_by_day(entries: list[dict], today: date) -> list[tuple[str, list[dict]]]:
    """시간 역순 목록을 (묶음 제목, 항목들)로 나눈다. 같은 날은 한 묶음이다."""
    groups: list[tuple[str, list[dict]]] = []
    last_day = None
    for entry in entries:
        day = entry["when"].date()
        if day != last_day:
            groups.append((group_label(day, today), []))
            last_day = day
        groups[-1][1].append(entry)
    return groups
