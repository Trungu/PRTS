# bot/client.py — Bot subclass with cog auto-loading and lifecycle hooks.
from __future__ import annotations

import os
import discord
from discord.ext import commands

from utils.logger import log, LogLevel


class Bot(commands.Bot):
    """Custom Bot subclass.

    Cogs are loaded automatically from the ``bot/cogs/`` directory.
    Any module inside that package that contains a top-level ``setup``
    coroutine will be loaded on startup.
    """

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            # commands.Bot requires a command_prefix, but we handle prefix
            # matching ourselves in the cogs, so use a no-op callable.
            command_prefix=commands.when_mentioned,
            intents=intents,
            help_command=None,  # disable the built-in help command
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def setup_hook(self) -> None:
        """Called automatically by discord.py before the bot connects.

        This is the right place to load cogs because it runs in the async
        context, and ``load_extension`` is a coroutine.
        """
        await self._load_cogs()

    async def _load_cogs(self) -> None:
        """Discover and load every cog module in ``bot/cogs/``."""
        cogs_dir = os.path.join(os.path.dirname(__file__), "cogs")

        for filename in sorted(os.listdir(cogs_dir)):
            if filename.startswith("_") or not filename.endswith(".py"):
                continue

            extension = f"bot.cogs.{filename[:-3]}"  # strip .py
            try:
                await self.load_extension(extension)
                log(f"Loaded cog: {extension}")
            except Exception as exc:  # noqa: BLE001
                log(f"Failed to load cog {extension}: {exc}", LogLevel.ERROR)

    async def on_ready(self) -> None:
        """Called once the bot has connected and all cogs are ready."""
        assert self.user is not None # self.user can theoretically be None before the connection is fully established
        log(f"Logged in as {self.user} (id: {self.user.id})")
        log("------")
