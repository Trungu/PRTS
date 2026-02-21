# bot/cogs/admin.py — Admin-only mode commands.
#
# Commands registered
# -------------------
#   admin only   — Enable admin-only mode (caller must be in admin.txt).
#   admin off    — Disable admin-only mode (caller must be in admin.txt).
#
# Both commands are always gated behind the admin allowed-user list,
# regardless of whether admin-only mode is currently active.

from __future__ import annotations

from typing import cast

import discord
from discord.ext import commands

from bot.client import Bot
from utils.admin import is_allowed, is_admin_only, reload_allowed_users, set_admin_only
from utils.logger import log, LogLevel


class AdminCog(commands.Cog):
    """Commands for managing admin-only mode."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        bot.register_command("admin only", self._admin_only)
        bot.register_command("admin off",  self._admin_off)

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


async def setup(bot: commands.Bot) -> None:
    """Entry point called by Bot.load_extension."""
    await bot.add_cog(AdminCog(cast(Bot, bot)))
