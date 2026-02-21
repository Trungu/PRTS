# tests/test_admin.py — Unit tests for utils/admin and bot/cogs/admin.py.
#
# Coverage
# --------
#   load_admin_file         — valid IDs, comments/blanks, bad entries, missing file
#   reload_allowed_users    — updates module-level state
#   is_allowed              — membership checks
#   set_admin_only /        — toggle behaviour + persistence
#     is_admin_only
#   _save_state / load_state — JSON persistence across restarts
#   AdminCog registration   — all three commands registered on the bot
#   AdminCog._admin_only    — blocked for non-admin, enabled by admin, reloads list
#   AdminCog._admin_off     — blocked for non-admin, disabled by admin
#   "admin on" alias        — behaves identically to "admin only"
#   Bot.on_message guard    — commands blocked when admin-only active
#   Bot.on_message pass     — commands pass for allowed user in admin-only mode

import asyncio
from typing import Any, cast

import pytest

import utils.admin as admin_module
from utils.admin import (
    load_admin_file,
    reload_allowed_users,
    is_allowed,
    set_admin_only,
    is_admin_only,
    load_state,
    ban_user,
    unban_user,
    is_banned,
)
from bot.cogs.admin import AdminCog, _parse_user_id


# ---------------------------------------------------------------------------
# Shared test doubles
# ---------------------------------------------------------------------------

class DummyBot:
    def __init__(self) -> None:
        self.registered: dict = {}

    def register_command(self, name: str, handler) -> None:
        self.registered[name] = handler


class DummyChannel:
    def __init__(self) -> None:
        self.sent: list[tuple] = []

    async def send(self, content, **kwargs):
        self.sent.append((content, kwargs))


class DummyAuthor:
    def __init__(self, user_id: int = 0, *, bot: bool = False) -> None:
        self.id = user_id
        self.bot = bot

    def __str__(self) -> str:
        return f"User({self.id})"


class DummyMessage:
    def __init__(self, user_id: int = 0) -> None:
        self.author = DummyAuthor(user_id)
        self.channel = DummyChannel()


# ---------------------------------------------------------------------------
# load_admin_file
# ---------------------------------------------------------------------------

def test_load_admin_file_valid_ids(tmp_path) -> None:
    f = tmp_path / "admin.txt"
    f.write_text("111111111111111111\n222222222222222222\n")

    result = load_admin_file(str(f))

    assert result == {111111111111111111, 222222222222222222}


def test_load_admin_file_ignores_comments_and_blanks(tmp_path) -> None:
    f = tmp_path / "admin.txt"
    f.write_text("# admin list\n\n123456789\n\n# trailing comment\n")

    result = load_admin_file(str(f))

    assert result == {123456789}


def test_load_admin_file_skips_invalid_entries(tmp_path) -> None:
    f = tmp_path / "admin.txt"
    f.write_text("not_an_id\n999\n\nalso-bad\n")

    result = load_admin_file(str(f))

    assert result == {999}


def test_load_admin_file_missing_file_returns_empty_set(tmp_path) -> None:
    result = load_admin_file(str(tmp_path / "nonexistent.txt"))

    assert result == set()


def test_load_admin_file_empty_file_returns_empty_set(tmp_path) -> None:
    f = tmp_path / "admin.txt"
    f.write_text("")

    result = load_admin_file(str(f))

    assert result == set()


# ---------------------------------------------------------------------------
# reload_allowed_users / is_allowed
# ---------------------------------------------------------------------------

def test_reload_allowed_users_updates_state(tmp_path, monkeypatch) -> None:
    f = tmp_path / "admin.txt"
    f.write_text("42\n")
    monkeypatch.setattr(admin_module, "_allowed_ids", set())

    reload_allowed_users(str(f))

    assert is_allowed(42)
    assert not is_allowed(99)


def test_is_allowed_false_when_set_empty(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", set())

    assert not is_allowed(12345)


# ---------------------------------------------------------------------------
# set_admin_only / is_admin_only
# ---------------------------------------------------------------------------

def test_admin_only_starts_disabled(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_admin_only", False)

    assert not is_admin_only()


def test_set_admin_only_enable(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_admin_only", False)
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    set_admin_only(True)

    assert is_admin_only()


def test_set_admin_only_disable(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_admin_only", True)
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    set_admin_only(False)

    assert not is_admin_only()


def test_admin_only_toggle_roundtrip(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_admin_only", False)
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    assert not is_admin_only()
    set_admin_only(True)
    assert is_admin_only()
    set_admin_only(False)
    assert not is_admin_only()


# ---------------------------------------------------------------------------
# AdminCog — command registration
# ---------------------------------------------------------------------------

def test_admin_cog_registers_both_commands() -> None:
    bot = DummyBot()
    AdminCog(cast(Any, bot))

    assert "admin only" in bot.registered
    assert "admin on" in bot.registered
    assert "admin off" in bot.registered


# ---------------------------------------------------------------------------
# AdminCog._admin_only — non-admin is denied
# ---------------------------------------------------------------------------

def test_admin_only_denied_for_non_admin(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {999})
    monkeypatch.setattr(admin_module, "_admin_only", False)

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=123)  # NOT in allowed list

    asyncio.run(cog._admin_only(cast(Any, msg), "admin only"))

    assert msg.channel.sent[0][0] == "⛔ You are not authorised to change admin settings."
    assert not is_admin_only()  # mode was NOT enabled


# ---------------------------------------------------------------------------
# AdminCog._admin_only — allowed user enables the mode
# ---------------------------------------------------------------------------

def test_admin_only_enabled_by_allowed_user(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {42})
    monkeypatch.setattr(admin_module, "_admin_only", False)
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)
    # Prevent reload_allowed_users from overwriting the state we set above.
    monkeypatch.setattr("bot.cogs.admin.reload_allowed_users", lambda path=None: None)

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=42)

    asyncio.run(cog._admin_only(cast(Any, msg), "admin only"))

    assert is_admin_only()
    assert "enabled" in msg.channel.sent[0][0].lower()


# ---------------------------------------------------------------------------
# AdminCog._admin_only — reload_allowed_users is called before locking down
# ---------------------------------------------------------------------------

def test_admin_only_calls_reload(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {7})
    monkeypatch.setattr(admin_module, "_admin_only", False)
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    reload_called: list[bool] = []
    monkeypatch.setattr(
        "bot.cogs.admin.reload_allowed_users",
        lambda path=None: reload_called.append(True),
    )

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=7)

    asyncio.run(cog._admin_only(cast(Any, msg), "admin only"))

    assert reload_called == [True]


# ---------------------------------------------------------------------------
# AdminCog._admin_off — non-admin is denied
# ---------------------------------------------------------------------------

def test_admin_off_denied_for_non_admin(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {999})
    monkeypatch.setattr(admin_module, "_admin_only", True)

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=123)  # NOT in allowed list

    asyncio.run(cog._admin_off(cast(Any, msg), "admin off"))

    assert msg.channel.sent[0][0] == "⛔ You are not authorised to change admin settings."
    assert is_admin_only()  # mode remains ON


# ---------------------------------------------------------------------------
# AdminCog._admin_off — allowed user disables the mode
# ---------------------------------------------------------------------------

def test_admin_off_disabled_by_allowed_user(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {42})
    monkeypatch.setattr(admin_module, "_admin_only", True)
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=42)

    asyncio.run(cog._admin_off(cast(Any, msg), "admin off"))

    assert not is_admin_only()
    assert "disabled" in msg.channel.sent[0][0].lower()


# ---------------------------------------------------------------------------
# Bot.on_message — admin-only gate blocks non-admin commands
# ---------------------------------------------------------------------------

def test_on_message_blocked_when_admin_only(monkeypatch) -> None:
    from bot.client import Bot

    bot = Bot()
    handled: list[str] = []

    async def handler(message, command):
        handled.append(command)

    bot.register_command("hello", handler)

    channel = DummyChannel()

    monkeypatch.setattr("bot.client.get_command", lambda _: "hello")
    monkeypatch.setattr("bot.client.is_admin_only", lambda: True)
    monkeypatch.setattr("bot.client.is_allowed", lambda uid: False)

    class _Author:
        bot = False
        id = 123

    class _Msg:
        content = "gemma hello"
        author = _Author()

    msg = _Msg()
    msg.channel = channel  # type: ignore[attr-defined]

    asyncio.run(bot.on_message(cast(Any, msg)))

    # Command handler must NOT have been called.
    assert handled == []
    # Bot must have replied with the admin-only notice.
    assert len(channel.sent) == 1
    assert "admin" in channel.sent[0][0].lower()


# ---------------------------------------------------------------------------
# Bot.on_message — allowed user passes the admin-only gate
# ---------------------------------------------------------------------------

def test_on_message_passes_for_allowed_user_when_admin_only(monkeypatch) -> None:
    from bot.client import Bot

    bot = Bot()
    handled: list[str] = []

    async def handler(message, command):
        handled.append(command)

    bot.register_command("hello", handler)

    monkeypatch.setattr("bot.client.get_command", lambda _: "hello")
    monkeypatch.setattr("bot.client.is_admin_only", lambda: True)
    monkeypatch.setattr("bot.client.is_allowed", lambda uid: True)

    class _Author:
        bot = False
        id = 42

    class _Msg:
        content = "gemma hello"
        author = _Author()
        channel = DummyChannel()

    async def fake_process(m):
        pass

    bot.process_commands = fake_process  # type: ignore[assignment]

    asyncio.run(bot.on_message(cast(Any, _Msg())))

    assert handled == ["hello"]


# ---------------------------------------------------------------------------
# Bot.on_message — guard is skipped entirely when mode is off
# ---------------------------------------------------------------------------

def test_on_message_no_gate_when_admin_only_off(monkeypatch) -> None:
    from bot.client import Bot

    bot = Bot()
    handled: list[str] = []

    async def handler(message, command):
        handled.append(command)

    bot.register_command("hello", handler)

    monkeypatch.setattr("bot.client.get_command", lambda _: "hello")
    monkeypatch.setattr("bot.client.is_admin_only", lambda: False)
    # is_allowed would return False for this user — but shouldn't matter
    monkeypatch.setattr("bot.client.is_allowed", lambda uid: False)

    class _Author:
        bot = False
        id = 999  # NOT in any admin list

    class _Msg:
        content = "gemma hello"
        author = _Author()
        channel = DummyChannel()

    async def fake_process(m):
        pass

    bot.process_commands = fake_process  # type: ignore[assignment]

    asyncio.run(bot.on_message(cast(Any, _Msg())))

    # Command should still run because admin-only mode is OFF.
    assert handled == ["hello"]


# ---------------------------------------------------------------------------
# Persistence — _save_state / load_state
# ---------------------------------------------------------------------------

def test_save_state_writes_enabled(monkeypatch, tmp_path) -> None:
    state_file = str(tmp_path / "state.json")
    monkeypatch.setattr(admin_module, "STATE_FILE", state_file)
    monkeypatch.setattr(admin_module, "_admin_only", True)
    monkeypatch.setattr(admin_module, "_banned_ids", set())

    admin_module._save_state()

    import json
    with open(state_file) as fh:
        data = json.load(fh)
    assert data["admin_only"] is True
    assert data["banned_ids"] == []


def test_save_state_writes_disabled(monkeypatch, tmp_path) -> None:
    state_file = str(tmp_path / "state.json")
    monkeypatch.setattr(admin_module, "STATE_FILE", state_file)
    monkeypatch.setattr(admin_module, "_admin_only", False)
    monkeypatch.setattr(admin_module, "_banned_ids", set())

    admin_module._save_state()

    import json
    with open(state_file) as fh:
        data = json.load(fh)
    assert data["admin_only"] is False
    assert data["banned_ids"] == []


def test_load_state_restores_enabled(monkeypatch, tmp_path) -> None:
    import json
    state_file = str(tmp_path / "state.json")
    (tmp_path / "state.json").write_text(json.dumps({"admin_only": True}))
    monkeypatch.setattr(admin_module, "STATE_FILE", state_file)
    monkeypatch.setattr(admin_module, "_admin_only", False)  # start opposite

    load_state()

    assert is_admin_only() is True


def test_load_state_restores_disabled(monkeypatch, tmp_path) -> None:
    import json
    state_file = str(tmp_path / "state.json")
    (tmp_path / "state.json").write_text(json.dumps({"admin_only": False}))
    monkeypatch.setattr(admin_module, "STATE_FILE", state_file)
    monkeypatch.setattr(admin_module, "_admin_only", True)  # start opposite

    load_state()

    assert is_admin_only() is False


def test_load_state_missing_file_defaults_false(monkeypatch, tmp_path) -> None:
    state_file = str(tmp_path / "nonexistent.json")
    monkeypatch.setattr(admin_module, "STATE_FILE", state_file)
    monkeypatch.setattr(admin_module, "_admin_only", True)  # would be wrong if kept

    load_state()

    assert is_admin_only() is False


def test_load_state_corrupt_file_defaults_false(monkeypatch, tmp_path) -> None:
    state_file = str(tmp_path / "state.json")
    (tmp_path / "state.json").write_text("not valid json{{")
    monkeypatch.setattr(admin_module, "STATE_FILE", state_file)
    monkeypatch.setattr(admin_module, "_admin_only", True)

    load_state()

    assert is_admin_only() is False


def test_set_admin_only_persists_to_state_file(monkeypatch, tmp_path) -> None:
    """End-to-end: setting mode writes to file; loading restores it."""
    import json
    state_file = str(tmp_path / "state.json")
    monkeypatch.setattr(admin_module, "STATE_FILE", state_file)
    monkeypatch.setattr(admin_module, "_admin_only", False)

    set_admin_only(True)

    # File must exist and reflect the new state.
    with open(state_file) as fh:
        data = json.load(fh)
    assert data["admin_only"] is True

    # Simulated restart: reset in-memory flag, then load from file.
    monkeypatch.setattr(admin_module, "_admin_only", False)
    load_state()
    assert is_admin_only() is True


# ---------------------------------------------------------------------------
# "admin on" alias
# ---------------------------------------------------------------------------

def test_admin_on_alias_registered() -> None:
    """Both 'admin only' and 'admin on' must be registered and point to the same handler."""
    bot = DummyBot()
    AdminCog(cast(Any, bot))

    assert "admin on" in bot.registered
    # Both keys are bound methods of the same underlying function.
    assert bot.registered["admin on"].__func__ is bot.registered["admin only"].__func__


def test_admin_on_alias_enables_mode(monkeypatch) -> None:
    """'admin on' must enable admin-only mode identically to 'admin only'."""
    monkeypatch.setattr(admin_module, "_allowed_ids", {42})
    monkeypatch.setattr(admin_module, "_admin_only", False)
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)
    monkeypatch.setattr("bot.cogs.admin.reload_allowed_users", lambda path=None: None)

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=42)

    # Call through the alias handler directly.
    asyncio.run(bot.registered["admin on"](cast(Any, msg), "admin on"))

    assert is_admin_only()
    assert "enabled" in msg.channel.sent[0][0].lower()


def test_admin_on_alias_denied_for_non_admin(monkeypatch) -> None:
    """'admin on' must deny a non-admin user the same way 'admin only' does."""
    monkeypatch.setattr(admin_module, "_allowed_ids", {999})
    monkeypatch.setattr(admin_module, "_admin_only", False)
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    bot = DummyBot()
    AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=123)  # NOT in allowed list

    asyncio.run(bot.registered["admin on"](cast(Any, msg), "admin on"))

    assert msg.channel.sent[0][0] == "⛔ You are not authorised to change admin settings."
    assert not is_admin_only()


# ---------------------------------------------------------------------------
# _parse_user_id
# ---------------------------------------------------------------------------

def test_parse_user_id_plain_integer() -> None:
    assert _parse_user_id("123456789") == 123456789


def test_parse_user_id_mention_format() -> None:
    assert _parse_user_id("<@123456789>") == 123456789


def test_parse_user_id_legacy_mention_format() -> None:
    assert _parse_user_id("<@!123456789>") == 123456789


def test_parse_user_id_with_whitespace() -> None:
    assert _parse_user_id("  42  ") == 42


def test_parse_user_id_invalid_returns_none() -> None:
    assert _parse_user_id("not_a_user") is None


def test_parse_user_id_empty_returns_none() -> None:
    assert _parse_user_id("") is None


# ---------------------------------------------------------------------------
# ban_user / unban_user / is_banned
# ---------------------------------------------------------------------------

def test_is_banned_false_initially(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_banned_ids", set())
    assert not is_banned(12345)


def test_ban_user_adds_to_banned_set(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_banned_ids", set())
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    ban_user(42)

    assert is_banned(42)


def test_ban_user_does_not_affect_others(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_banned_ids", set())
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    ban_user(42)

    assert not is_banned(99)


def test_unban_user_removes_from_banned_set(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_banned_ids", {42})
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    unban_user(42)

    assert not is_banned(42)


def test_unban_user_is_idempotent(monkeypatch) -> None:
    """Unbanning a user who is not banned must not raise."""
    monkeypatch.setattr(admin_module, "_banned_ids", set())
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    unban_user(99)  # 99 was never banned — must be silent

    assert not is_banned(99)


def test_ban_user_persists_state(monkeypatch, tmp_path) -> None:
    import json
    state_file = str(tmp_path / "state.json")
    monkeypatch.setattr(admin_module, "STATE_FILE", state_file)
    monkeypatch.setattr(admin_module, "_admin_only", False)
    monkeypatch.setattr(admin_module, "_banned_ids", set())

    ban_user(777)

    with open(state_file) as fh:
        data = json.load(fh)
    assert 777 in data["banned_ids"]


def test_unban_user_persists_state(monkeypatch, tmp_path) -> None:
    import json
    state_file = str(tmp_path / "state.json")
    monkeypatch.setattr(admin_module, "STATE_FILE", state_file)
    monkeypatch.setattr(admin_module, "_admin_only", False)
    monkeypatch.setattr(admin_module, "_banned_ids", {777})

    unban_user(777)

    with open(state_file) as fh:
        data = json.load(fh)
    assert 777 not in data["banned_ids"]


# ---------------------------------------------------------------------------
# Persistence — banned_ids round-trip
# ---------------------------------------------------------------------------

def test_save_state_includes_banned_ids(monkeypatch, tmp_path) -> None:
    import json
    state_file = str(tmp_path / "state.json")
    monkeypatch.setattr(admin_module, "STATE_FILE", state_file)
    monkeypatch.setattr(admin_module, "_admin_only", False)
    monkeypatch.setattr(admin_module, "_banned_ids", {10, 20, 30})

    admin_module._save_state()

    with open(state_file) as fh:
        data = json.load(fh)
    assert set(data["banned_ids"]) == {10, 20, 30}


def test_load_state_restores_banned_ids(monkeypatch, tmp_path) -> None:
    import json
    state_file = str(tmp_path / "state.json")
    (tmp_path / "state.json").write_text(
        json.dumps({"admin_only": False, "banned_ids": [10, 20, 30]})
    )
    monkeypatch.setattr(admin_module, "STATE_FILE", state_file)
    monkeypatch.setattr(admin_module, "_banned_ids", set())

    load_state()

    assert is_banned(10)
    assert is_banned(20)
    assert is_banned(30)
    assert not is_banned(99)


def test_load_state_missing_banned_ids_key_defaults_empty(monkeypatch, tmp_path) -> None:
    import json
    state_file = str(tmp_path / "state.json")
    (tmp_path / "state.json").write_text(json.dumps({"admin_only": False}))
    monkeypatch.setattr(admin_module, "STATE_FILE", state_file)
    monkeypatch.setattr(admin_module, "_banned_ids", {99})  # would be wrong if kept

    load_state()

    assert not is_banned(99)


# ---------------------------------------------------------------------------
# AdminCog — ban/unban command registration
# ---------------------------------------------------------------------------

def test_admin_cog_registers_ban_and_unban() -> None:
    bot = DummyBot()
    AdminCog(cast(Any, bot))

    assert "ban" in bot.registered
    assert "unban" in bot.registered


# ---------------------------------------------------------------------------
# AdminCog._ban — non-admin is denied
# ---------------------------------------------------------------------------

def test_ban_denied_for_non_admin(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {999})

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=123)  # NOT in allowed list

    asyncio.run(cog._ban(cast(Any, msg), "ban 456"))

    assert msg.channel.sent[0][0] == "⛔ You are not authorised to change admin settings."


# ---------------------------------------------------------------------------
# AdminCog._ban — admin bans a user
# ---------------------------------------------------------------------------

def test_ban_by_user_id(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {42})
    monkeypatch.setattr(admin_module, "_banned_ids", set())
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=42)

    asyncio.run(cog._ban(cast(Any, msg), "ban 555"))

    assert is_banned(555)
    assert "555" in msg.channel.sent[0][0]


def test_ban_by_mention(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {42})
    monkeypatch.setattr(admin_module, "_banned_ids", set())
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=42)

    asyncio.run(cog._ban(cast(Any, msg), "ban <@555>"))

    assert is_banned(555)


def test_ban_legacy_mention(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {42})
    monkeypatch.setattr(admin_module, "_banned_ids", set())
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=42)

    asyncio.run(cog._ban(cast(Any, msg), "ban <@!555>"))

    assert is_banned(555)


def test_ban_missing_target_sends_usage(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {42})

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=42)

    asyncio.run(cog._ban(cast(Any, msg), "ban"))

    assert "usage" in msg.channel.sent[0][0].lower()


def test_ban_invalid_target_sends_error(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {42})

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=42)

    asyncio.run(cog._ban(cast(Any, msg), "ban not_valid"))

    assert "parse" in msg.channel.sent[0][0].lower() or "id" in msg.channel.sent[0][0].lower()


# ---------------------------------------------------------------------------
# AdminCog._unban — non-admin is denied
# ---------------------------------------------------------------------------

def test_unban_denied_for_non_admin(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {999})

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=123)  # NOT in allowed list

    asyncio.run(cog._unban(cast(Any, msg), "unban 456"))

    assert msg.channel.sent[0][0] == "⛔ You are not authorised to change admin settings."


# ---------------------------------------------------------------------------
# AdminCog._unban — admin unbans a user
# ---------------------------------------------------------------------------

def test_unban_by_user_id(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {42})
    monkeypatch.setattr(admin_module, "_banned_ids", {555})
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=42)

    asyncio.run(cog._unban(cast(Any, msg), "unban 555"))

    assert not is_banned(555)
    assert "555" in msg.channel.sent[0][0]


def test_unban_by_mention(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {42})
    monkeypatch.setattr(admin_module, "_banned_ids", {555})
    monkeypatch.setattr(admin_module, "_save_state", lambda: None)

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=42)

    asyncio.run(cog._unban(cast(Any, msg), "unban <@555>"))

    assert not is_banned(555)


def test_unban_missing_target_sends_usage(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {42})

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=42)

    asyncio.run(cog._unban(cast(Any, msg), "unban"))

    assert "usage" in msg.channel.sent[0][0].lower()


def test_unban_invalid_target_sends_error(monkeypatch) -> None:
    monkeypatch.setattr(admin_module, "_allowed_ids", {42})

    bot = DummyBot()
    cog = AdminCog(cast(Any, bot))
    msg = DummyMessage(user_id=42)

    asyncio.run(cog._unban(cast(Any, msg), "unban not_valid"))

    assert "parse" in msg.channel.sent[0][0].lower() or "id" in msg.channel.sent[0][0].lower()


# ---------------------------------------------------------------------------
# Bot.on_message — ban gate blocks banned non-admin user
# ---------------------------------------------------------------------------

def test_on_message_blocked_when_banned(monkeypatch) -> None:
    from bot.client import Bot

    bot = Bot()
    handled: list[str] = []

    async def handler(message, command):
        handled.append(command)

    bot.register_command("hello", handler)

    channel = DummyChannel()

    monkeypatch.setattr("bot.client.get_command", lambda _: "hello")
    monkeypatch.setattr("bot.client.is_admin_only", lambda: False)
    monkeypatch.setattr("bot.client.is_allowed", lambda uid: False)
    monkeypatch.setattr("bot.client.is_banned", lambda uid: True)

    class _Author:
        bot = False
        id = 456

    class _Msg:
        content = "gemma hello"
        author = _Author()

    msg = _Msg()
    msg.channel = channel  # type: ignore[attr-defined]

    asyncio.run(bot.on_message(cast(Any, msg)))

    assert handled == []
    assert len(channel.sent) == 1
    assert "banned" in channel.sent[0][0].lower()


def test_on_message_ban_gate_bypassed_for_admin(monkeypatch) -> None:
    """Admins are never blocked by the ban gate, even if technically banned."""
    from bot.client import Bot

    bot = Bot()
    handled: list[str] = []

    async def handler(message, command):
        handled.append(command)

    bot.register_command("hello", handler)

    monkeypatch.setattr("bot.client.get_command", lambda _: "hello")
    monkeypatch.setattr("bot.client.is_admin_only", lambda: False)
    monkeypatch.setattr("bot.client.is_allowed", lambda uid: True)   # admin
    monkeypatch.setattr("bot.client.is_banned", lambda uid: True)    # also banned

    class _Author:
        bot = False
        id = 42

    class _Msg:
        content = "gemma hello"
        author = _Author()
        channel = DummyChannel()

    async def fake_process(m):
        pass

    bot.process_commands = fake_process  # type: ignore[assignment]

    asyncio.run(bot.on_message(cast(Any, _Msg())))

    assert handled == ["hello"]


def test_on_message_non_banned_user_passes_ban_gate(monkeypatch) -> None:
    from bot.client import Bot

    bot = Bot()
    handled: list[str] = []

    async def handler(message, command):
        handled.append(command)

    bot.register_command("hello", handler)

    monkeypatch.setattr("bot.client.get_command", lambda _: "hello")
    monkeypatch.setattr("bot.client.is_admin_only", lambda: False)
    monkeypatch.setattr("bot.client.is_allowed", lambda uid: False)
    monkeypatch.setattr("bot.client.is_banned", lambda uid: False)

    class _Author:
        bot = False
        id = 789

    class _Msg:
        content = "gemma hello"
        author = _Author()
        channel = DummyChannel()

    async def fake_process(m):
        pass

    bot.process_commands = fake_process  # type: ignore[assignment]

    asyncio.run(bot.on_message(cast(Any, _Msg())))

    assert handled == ["hello"]
