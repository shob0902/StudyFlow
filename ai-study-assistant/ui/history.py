# Grouping, relative times and markup for the study-session history in the sidebar.
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from ui.cards import esc
TODAY = "Today"
YESTERDAY = "Yesterday"
PREVIOUS_7_DAYS = "Previous 7 days"
OLDER = "Older"
GROUP_ORDER = [TODAY, YESTERDAY, PREVIOUS_7_DAYS, OLDER]
# Parse a stored ISO timestamp, treating a naive value as UTC.
def parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
# Which bucket a timestamp belongs in, counted in whole days back from today.
def group_for(value: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    moment = parse_time(value)
    if moment is None:
        return OLDER
    days = (now.date() - moment.astimezone(now.tzinfo).date()).days
    if days <= 0:
        return TODAY
    if days == 1:
        return YESTERDAY
    if days <= 7:
        return PREVIOUS_7_DAYS
    return OLDER
# Sessions split into Today / Yesterday / Previous 7 days / Older, keeping the given order
# and dropping any group that has nothing in it.
def group_sessions(
    records: Iterable[Any], now: datetime | None = None
) -> list[tuple[str, list[Any]]]:
    now = now or datetime.now(timezone.utc)
    buckets: dict[str, list[Any]] = {label: [] for label in GROUP_ORDER}
    for record in records:
        buckets[group_for(record.updated_at, now)].append(record)
    return [(label, buckets[label]) for label in GROUP_ORDER if buckets[label]]
# A short, human description of when something last changed.
def relative_time(value: str, now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    moment = parse_time(value)
    if moment is None:
        return ""
    delta = now - moment.astimezone(now.tzinfo)
    if delta < timedelta(minutes=1):
        return "just now"
    if delta < timedelta(hours=1):
        minutes = int(delta.total_seconds() // 60)
        return f"{minutes} min ago"
    if delta < timedelta(days=1) and group_for(value, now) == TODAY:
        hours = int(delta.total_seconds() // 3600)
        return f"{hours} hr ago" if hours > 1 else "1 hr ago"
    if group_for(value, now) == YESTERDAY:
        return "Yesterday"
    local = moment.astimezone(now.tzinfo)
    if local.year == now.year:
        return local.strftime("%d %b")
    return local.strftime("%d %b %Y")
# A date-group heading in the sidebar.
def group_header(label: str) -> str:
    return f"<div class='sa-hist-group'>{esc(label)}</div>"
# The small line under a session's name: when it changed, and how it went.
def item_meta(record: Any, now: datetime | None = None) -> str:
    parts = [relative_time(record.updated_at, now)]
    if record.score is not None:
        parts.append(f"{record.score:.0f}%")
    elif record.status == "active":
        parts.append("in progress")
    return f"<div class='sa-hist-meta'>{esc(' · '.join(part for part in parts if part))}</div>"
# The empty state, shown before the user has studied anything.
def empty_state() -> str:
    return (
        "<div class='sa-hist-empty'>No sessions yet.<br>"
        "Pick a topic to start your first one.</div>"
    )
