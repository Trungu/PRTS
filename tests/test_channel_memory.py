from datetime import datetime, timezone

from utils import channel_memory as cm


def setup_function(_fn) -> None:
    cm.reset_channel_memory()


def test_remember_and_lookup_messages_respects_order_and_cap(monkeypatch) -> None:
    monkeypatch.setattr(cm.settings, "TEMP_MEMORY_MAX_LOOKBACK", 2, raising=False)
    monkeypatch.setattr(cm.settings, "TEMP_MEMORY_BUFFER_SIZE", 10, raising=False)

    cm.remember_message(
        channel_id=1,
        author_name="alice",
        content="first",
        author_is_bot=False,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    cm.remember_message(
        channel_id=1,
        author_name="bob",
        content="second",
        author_is_bot=False,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    cm.remember_message(
        channel_id=1,
        author_name="carol",
        content="third",
        author_is_bot=False,
        created_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
    )

    rows = cm.lookup_messages(channel_id=1, lookback=50)
    assert len(rows) == 2
    assert rows[0]["content"] == "second"
    assert rows[1]["content"] == "third"


def test_lookup_filters_query_and_excludes_bot_by_default() -> None:
    cm.remember_message(channel_id=7, author_name="alice", content="disk full", author_is_bot=False)
    cm.remember_message(channel_id=7, author_name="PRTS", content="bot note", author_is_bot=True)
    cm.remember_message(channel_id=7, author_name="bob", content="network issue", author_is_bot=False)

    rows = cm.lookup_messages(channel_id=7, query="disk")
    assert len(rows) == 1
    assert rows[0]["author"] == "alice"

    rows_no_bots = cm.lookup_messages(channel_id=7, lookback=10)
    assert all(not r["author_is_bot"] for r in rows_no_bots)

    rows_with_bots = cm.lookup_messages(channel_id=7, lookback=10, include_bot_messages=True)
    assert any(r["author_is_bot"] for r in rows_with_bots)
