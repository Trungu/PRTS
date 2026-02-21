# utils/admin.py — Admin-only mode: allowed-user list and mode state.
#
# State machine
# -------------
# When admin-only mode is ON, the bot's on_message dispatcher will reject
# any command from a user whose Discord ID is not listed in admin.txt.
# The mode can be toggled with the "admin only" / "admin off" commands,
# both of which are themselves gated behind the same allowed-user check.

from __future__ import annotations

import os

from utils.logger import log, LogLevel

# Absolute path to admin.txt, resolved relative to the project root.
ADMIN_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "admin.txt")

# ---------------------------------------------------------------------------
# Module-level state — single source of truth
# ---------------------------------------------------------------------------

_admin_only: bool = False
_allowed_ids: set[int] = set()


# ---------------------------------------------------------------------------
# Admin file helpers
# ---------------------------------------------------------------------------

def load_admin_file(path: str = ADMIN_FILE) -> set[int]:
    """Parse *path* and return the set of Discord user IDs it contains.

    Rules:
    - One entry per line.
    - Entries must be plain integers (Discord snowflake IDs).
    - Lines starting with ``#`` and blank lines are silently skipped.
    - Invalid (non-integer) entries are skipped with a WARNING log.
    - A missing file is handled gracefully (returns an empty set).
    """
    ids: set[int] = set()
    try:
        with open(path) as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    ids.add(int(line))
                except ValueError:
                    log(
                        f"[Admin] Skipping non-integer entry in admin file: {line!r}",
                        LogLevel.WARNING,
                    )
    except FileNotFoundError:
        log(
            f"[Admin] Admin file not found at {path!r}. "
            "No users will be permitted in admin-only mode.",
            LogLevel.WARNING,
        )
    return ids


def reload_allowed_users(path: str = ADMIN_FILE) -> None:
    """Reload the in-memory allowed-user set from *path*.

    Call this before enabling admin-only mode so the latest version of the
    file is always active.
    """
    global _allowed_ids
    _allowed_ids = load_admin_file(path)
    log(f"[Admin] Loaded {len(_allowed_ids)} allowed user(s) from admin file.")


def is_allowed(user_id: int) -> bool:
    """Return ``True`` if *user_id* is in the current allowed-user set."""
    return user_id in _allowed_ids


# ---------------------------------------------------------------------------
# Mode flag
# ---------------------------------------------------------------------------

def set_admin_only(enabled: bool) -> None:
    """Enable (``True``) or disable (``False``) admin-only mode."""
    global _admin_only
    _admin_only = enabled


def is_admin_only() -> bool:
    """Return ``True`` if admin-only mode is currently active."""
    return _admin_only


# ---------------------------------------------------------------------------
# Initialisation — load once at import time
# ---------------------------------------------------------------------------

# Populate the allowed-user set immediately so is_allowed() works before
# any "admin only" command is ever issued.
reload_allowed_users()
