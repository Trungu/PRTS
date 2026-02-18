# bot/cogs/llm.py — LLM chat command.
from __future__ import annotations

import asyncio
import discord
from discord.ext import commands

from utils.prefix_handler import get_command
from utils.logger import log, LogLevel
from utils.prompts import SYSTEM_PROMPT
from utils.command_registry import is_known
from tools.llm_api import chat


class LLM(commands.Cog):
    """Commands that interact with the language model."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Route messages that match the custom prefix to LLM handlers."""
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
        cmd = command.strip()

        # If the command matches any registered cog command, leave it alone.
        if is_known(cmd):
            return

        # Everything else is treated as a freeform LLM prompt.
        await self._ask(message, cmd)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _ask(self, message: discord.Message, prompt: str) -> None:
        """Send *prompt* to the LLM and reply with the response."""
        log(
            f"[LLM] Prompt from {message.author} (#{message.channel}) "
            f"| {len(prompt)} chars: {prompt!r}"
        )

        async with message.channel.typing():
            try:
                # chat() is synchronous (uses requests), so run it off the
                # event loop to avoid blocking Discord's async machinery.
                loop = asyncio.get_running_loop()
                log(f"[LLM] Sending request to API...", LogLevel.DEBUG)
                reply = await loop.run_in_executor(
                    None,
                    lambda: chat(prompt, system_prompt=SYSTEM_PROMPT),
                )
                log(
                    f"[LLM] Response received for {message.author} "
                    f"| {len(reply)} chars"
                )
            except Exception as exc:
                log(
                    f"[LLM] API error for {message.author} "
                    f"| prompt: {prompt!r} | {type(exc).__name__}: {exc}",
                    LogLevel.ERROR,
                )
                await message.channel.send(
                    f"⚠️ The LLM returned an error: `{exc}`"
                )
                return

        # Discord messages cap at 2000 chars — split if needed.
        chunks = [reply[i:i+2000] for i in range(0, len(reply), 2000)]
        if len(chunks) > 1:
            log(f"[LLM] Reply split into {len(chunks)} chunks for {message.author}", LogLevel.DEBUG)
        for chunk in chunks:
            await message.channel.send(chunk)


async def setup(bot: commands.Bot) -> None:
    """Entry point called by Bot.load_extension."""
    await bot.add_cog(LLM(bot))
