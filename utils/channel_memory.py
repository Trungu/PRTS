from __future__ import annotations

from collections import deque
from threading import Lock
from datetime import datetime

import settings


_lock = Lock()
# channel_id -> deque of message rows (oldest -> newest)
_channel_rows: dict[int, deque[dict]] = {}


def remember_message(
    *,
    channel_id: int,
    author_name: str,
    content: str,
    author_is_bot: bool,
    created_at: datetime | None = None,
) -> None:
    """Store a message row in transient channel memory."""
    text = (content or "").strip()
    if not text:
        return

    ts = (created_at or datetime.now().astimezone()).isoformat()
    row = {
        "timestamp": ts,
        "author": author_name,
        "content": text,
        "author_is_bot": bool(author_is_bot),
    }

    with _lock:
        dq = _channel_rows.get(channel_id)
        if dq is None or dq.maxlen != settings.TEMP_MEMORY_BUFFER_SIZE:
            dq = deque(maxlen=settings.TEMP_MEMORY_BUFFER_SIZE)
            _channel_rows[channel_id] = dq
        dq.append(row)


def lookup_messages(
    *,
    channel_id: int,
    lookback: int = 20,
    query: str | None = None,
    include_bot_messages: bool = False,
) -> list[dict]:
    """Return recent messages for a channel, bounded and optionally filtered."""
    cap = max(1, min(int(lookback), settings.TEMP_MEMORY_MAX_LOOKBACK))
    needle = (query or "").strip().lower()

    with _lock:
        rows = list(_channel_rows.get(channel_id, ()))

    if not include_bot_messages:
        rows = [r for r in rows if not r.get("author_is_bot")]

    if needle:
        rows = [
            r
            for r in rows
            if needle in str(r.get("content", "")).lower()
            or needle in str(r.get("author", "")).lower()
        ]

    if cap < len(rows):
        rows = rows[-cap:]
    return rows


def reset_channel_memory() -> None:
    """Clear all in-memory channel history (for tests/admin utilities)."""
    with _lock:
        _channel_rows.clear()
