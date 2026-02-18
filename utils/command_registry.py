# utils/command_registry.py — central registry of known bot commands.
#
# Each cog registers its own command prefixes here at import time.
# The LLM cog uses this to decide whether a message is a known command
# (and should be ignored by it) or a freeform prompt to send to the model.

from __future__ import annotations

_KNOWN: set[str] = set()


def register(*commands: str) -> None:
    """Register one or more command strings (lowercased) as known commands."""
    for cmd in commands:
        _KNOWN.add(cmd.lower().strip())


def is_known(command: str) -> bool:
    """Return True if the command (or its prefix) is a registered known command.

    Matches either an exact command (e.g. 'hello') or a known prefix
    followed by a space (e.g. 'clear history ...' when 'clear history' is registered).
    """
    cmd = command.lower().strip()
    if cmd in _KNOWN:
        return True
    # Also match multi-word commands that are prefixes of the incoming string
    # e.g. registered 'clear history' matches 'clear history all'
    return any(cmd.startswith(k + " ") for k in _KNOWN)
