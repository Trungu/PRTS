# bot/cogs/general.py — general-purpose commands.
from __future__ import annotations

import discord
from discord.ext import commands

from utils.prefix_handler import get_command
from utils.logger import log
from utils.command_registry import register

# Register every command this cog owns.
register("hello", "clear history")


class General(commands.Cog):
    """General commands available to all users."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Route messages that match the custom prefix to command handlers."""
        # Ignore the bot itself and other bots.
        if message.author.bot:
            return

        command = get_command(message.content)
        if command is None:
            return

        await self._dispatch(message, command)

    # ------------------------------------------------------------------
    # Internal dispatcher
    # ------------------------------------------------------------------

    async def _dispatch(self, message: discord.Message, command: str) -> None:
        """Match a stripped command string to the appropriate handler."""
        cmd = command.lower().strip()

        if cmd == "hello":
            await self._hello(message)
        elif cmd == "clear history":
            await self._clear_history(message)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _hello(self, message: discord.Message) -> None:
        await message.channel.send("Hello!")

    async def _clear_history(self, message: discord.Message) -> None:
        # TODO: implement history clearing
        pass


async def setup(bot: commands.Bot) -> None:
    """Entry point called by Bot.load_extension."""
    await bot.add_cog(General(bot))
