from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current UTC datetime with timezone info."""
    return datetime.now(tz=timezone.utc)


def isoformat(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat() if dt else None
