# bot/cogs/admin.py — Admin-only mode commands and user ban management.
#
# Commands registered
# -------------------
#   admin only / admin on  — Enable admin-only mode (caller must be in admin.txt).
#   admin off              — Disable admin-only mode (caller must be in admin.txt).
#   ban <user>             — Ban a user from using the bot (admins only).
#   unban <user>           — Unban a previously banned user (admins only).
#
# All commands are gated behind the admin allowed-user list.

from __future__ import annotations

import re
from typing import cast

import discord
from discord.ext import commands

from bot.client import Bot
from utils.admin import (
    is_allowed,
    is_admin_only,
    reload_allowed_users,
    set_admin_only,
    ban_user,
    unban_user,
    is_banned,
)
from utils.logger import log, LogLevel


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------

def _parse_user_id(text: str) -> int | None:
    """Extract a Discord user ID from a raw mention or plain integer string.

    Accepts ``<@123456789>``, ``<@!123456789>`` (legacy mention), or a bare
    integer string.  Returns ``None`` if the text cannot be parsed.
    """
    text = text.strip()
    match = re.fullmatch(r"<@!?(\d+)>", text)
    if match:
        return int(match.group(1))
    try:
        return int(text)
    except ValueError:
        return None


class AdminCog(commands.Cog):
    """Commands for managing admin-only mode."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        bot.register_command("admin only", self._admin_only)
        bot.register_command("admin on",   self._admin_only)  # alias
        bot.register_command("admin off",  self._admin_off)
        bot.register_command("ban",        self._ban)
        bot.register_command("unban",      self._unban)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _deny(self, message: discord.Message) -> None:
        """Send a standardised 'not authorised' reply."""
        await message.channel.send("⛔ You are not authorised to change admin settings.")

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _admin_only(self, message: discord.Message, _command: str) -> None:
        """Enable admin-only mode.

        The caller must be listed in admin.txt.  The allowed-user list is
        reloaded from disk before locking down so any recent edits are picked
        up immediately.
        """
        if not is_allowed(message.author.id):
            await self._deny(message)
            return

        reload_allowed_users()   # Refresh the list before locking down.
        set_admin_only(True)
        await message.channel.send(
            "🔒 Admin-only mode **enabled**. Only admins may use the bot."
        )
        log(
            f"[Admin] Admin-only mode enabled by {message.author} (id={message.author.id})",
            LogLevel.INFO,
        )

    async def _admin_off(self, message: discord.Message, _command: str) -> None:
        """Disable admin-only mode.

        The caller must be listed in admin.txt.
        """
        if not is_allowed(message.author.id):
            await self._deny(message)
            return

        set_admin_only(False)
        await message.channel.send(
            "🔓 Admin-only mode **disabled**. All users may use the bot."
        )
        log(
            f"[Admin] Admin-only mode disabled by {message.author} (id={message.author.id})",
            LogLevel.INFO,
        )


    async def _ban(self, message: discord.Message, command: str) -> None:
        """Ban a user from using the bot.

        Only users listed in admin.txt may issue this command.  Accepts a
        Discord mention (``<@123456789>``) or a raw user-ID integer.
        """
        if not is_allowed(message.author.id):
            await self._deny(message)
            return

        parts = command.strip().split(None, 1)
        if len(parts) < 2:
            await message.channel.send("Usage: `ban <@user>` or `ban <user_id>`")
            return

        user_id = _parse_user_id(parts[1])
        if user_id is None:
            await message.channel.send("⚠️ Could not parse a user ID from that input.")
            return

        ban_user(user_id)
        await message.channel.send(
            f"🔨 User `{user_id}` has been banned from using the bot."
        )
        log(
            f"[Admin] User {user_id} banned by {message.author} (id={message.author.id})",
            LogLevel.INFO,
        )

    async def _unban(self, message: discord.Message, command: str) -> None:
        """Unban a previously banned user.

        Only users listed in admin.txt may issue this command.  Accepts a
        Discord mention (``<@123456789>``) or a raw user-ID integer.
        """
        if not is_allowed(message.author.id):
            await self._deny(message)
            return

        parts = command.strip().split(None, 1)
        if len(parts) < 2:
            await message.channel.send("Usage: `unban <@user>` or `unban <user_id>`")
            return

        user_id = _parse_user_id(parts[1])
        if user_id is None:
            await message.channel.send("⚠️ Could not parse a user ID from that input.")
            return

        unban_user(user_id)
        await message.channel.send(f"✅ User `{user_id}` has been unbanned.")
        log(
            f"[Admin] User {user_id} unbanned by {message.author} (id={message.author.id})",
            LogLevel.INFO,
        )


async def setup(bot: commands.Bot) -> None:
    """Entry point called by Bot.load_extension."""
    await bot.add_cog(AdminCog(cast(Bot, bot)))
