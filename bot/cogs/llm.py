# bot/cogs/llm.py — LLM chat command with agentic tool-call support.
from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import suppress

import discord
from discord.ext import commands

from utils.logger import log, LogLevel
from utils.prompts import SYSTEM_PROMPT
from tools.llm_api import chat, MAX_TOOL_CALLS
from tools.toolcalls.code_runner import get_manager as _get_sandbox_manager
import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _silent_flags() -> discord.MessageFlags:
    """Return MessageFlags with suppress_notifications set."""
    flags = discord.MessageFlags()
    flags.suppress_notifications = True
    return flags


def _should_silent_all() -> bool:
    return settings.GLOBAL_SILENT


def _should_silent_toolcall() -> bool:
    return settings.GLOBAL_SILENT or settings.TOOLCALL_SILENT


_DISCORD_MAX = 2000


def _split_smart(text: str, limit: int = _DISCORD_MAX) -> list[str]:
    """Split *text* at natural language boundaries so each chunk ≤ *limit* chars.

    Break priority (highest first):
      1. Paragraph break (\n\n)
      2. Line break (\n)
      3. Sentence-ending punctuation followed by a space (.  !  ?)
      4. Any space (word boundary)
      5. Hard cut at *limit* as a last resort.
    """
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    while len(text) > limit:
        window = text[:limit]
        cut = -1
        for sep in ("\n\n", "\n", ". ", "! ", "? ", " "):
            pos = window.rfind(sep)
            if pos > 0:
                cut = pos + len(sep)
                break
        if cut <= 0:
            cut = limit  # absolute fallback — never exceeds limit
        chunks.append(text[:cut])
        text = text[cut:]

    if text:
        chunks.append(text)
    return chunks


def _split_hard(text: str, limit: int = _DISCORD_MAX) -> list[str]:
    """Hard-split *text* into chunks of at most *limit* chars (no crash safety net)."""
    return [text[i : i + limit] for i in range(0, len(text), limit)]


async def _send(channel: discord.abc.Messageable, content: str, *, force_silent: bool = False) -> None:
    """Send *content* to *channel*, applying silent flags when configured."""
    if _should_silent_all() or force_silent:
        await channel.send(content, silent=True)
    else:
        await channel.send(content)


class LLM(commands.Cog):
    """Commands that interact with the language model."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

        # Register as the catch-all fallback — only receives messages that no
        # other cog handler claimed, so it can never swallow a known command.
        bot.set_llm_handler(self._ask)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _ask(self, message: discord.Message, prompt: str) -> None:
        """Send *prompt* to the LLM and reply with the response."""
        log(
            f"[LLM] Prompt from {message.author} (#{message.channel}) "
            f"| {len(prompt)} chars: {prompt!r}"
        )

        loop = asyncio.get_running_loop()

        # ── Discord attachment → sandbox upload ───────────────────────────────
        # If the message has file attachments, upload each one to /workspace
        # before the LLM call so the model can reference them immediately.
        full_prompt = prompt
        if message.attachments:
            uploaded: list[str] = []
            try:
                mgr = await loop.run_in_executor(None, _get_sandbox_manager)
                for att in message.attachments:
                    try:
                        file_bytes = await att.read()
                        dest = f"{mgr.work_dir}/{att.filename}"
                        ok = await loop.run_in_executor(
                            None, mgr.copy_to_container, file_bytes, dest
                        )
                        if ok:
                            uploaded.append(att.filename)
                            log(
                                f"[LLM] Attachment '{att.filename}' "
                                f"({len(file_bytes)} bytes) uploaded to sandbox"
                            )
                        else:
                            log(
                                f"[LLM] Failed to upload attachment '{att.filename}'",
                                LogLevel.ERROR,
                            )
                    except Exception as exc:
                        log(
                            f"[LLM] Error uploading '{att.filename}': {exc}",
                            LogLevel.ERROR,
                        )
            except Exception as exc:
                log(
                    f"[LLM] Sandbox unavailable for attachment upload: {exc}",
                    LogLevel.ERROR,
                )

            if uploaded:
                names = ", ".join(f"'{n}'" for n in uploaded)
                full_prompt = (
                    f"[System: The following files were uploaded to /workspace "
                    f"and are ready to use: {names}]\n\n{prompt}"
                )

        def on_tool_call(tool_name: str, args: dict, result: str) -> None:
            """Called from the worker thread each time the LLM uses a tool."""
            log(f"[LLM] Tool call: {tool_name}({args}) → {result!r}", LogLevel.DEBUG)

            # ── File download: detect [__discord_file__=<path>] tag ───────────
            # get_workspace_file embeds this tag so the cog can send the file
            # to Discord while the LLM sees a clean human-readable message.
            file_match = re.search(r"\[__discord_file__=([^\]]+)\]", result)
            if file_match:
                local_path   = file_match.group(1)
                display_name = args.get("filename", os.path.basename(local_path))
                clean_result = re.sub(
                    r"\s*\[__discord_file__=[^\]]+\]", "", result
                ).strip()

                async def _send_file() -> None:
                    try:
                        disc_file = discord.File(
                            local_path,
                            filename=os.path.basename(local_path),
                        )
                        kwargs: dict = {
                            "content": f"📁 `{display_name}`",
                            "file":    disc_file,
                        }
                        if _should_silent_all() or _should_silent_toolcall():
                            kwargs["silent"] = True
                        await message.channel.send(**kwargs)
                    except Exception as exc:
                        log(
                            f"[LLM] Failed to send file '{local_path}' "
                            f"to Discord: {exc}",
                            LogLevel.ERROR,
                        )
                    finally:
                        with suppress(OSError):
                            os.remove(local_path)

                asyncio.run_coroutine_threadsafe(_send_file(), loop)

                # Also show the human-readable confirmation as a tool notice.
                args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
                notice = f"📁 **{tool_name}**({args_str}) → {clean_result}"
                asyncio.run_coroutine_threadsafe(
                    _send(
                        message.channel, notice,
                        force_silent=_should_silent_toolcall(),
                    ),
                    loop,
                )
                return

            # ── Normal tool-call notice ───────────────────────────────────────
            args_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
            notice = f"🔧 **{tool_name}**({args_str}) → `{result}`"
            asyncio.run_coroutine_threadsafe(
                _send(
                    message.channel, notice,
                    force_silent=_should_silent_toolcall(),
                ),
                loop,
            )

        async with message.channel.typing():
            try:
                log(f"[LLM] Sending request to API (tool calls enabled, max={MAX_TOOL_CALLS})…", LogLevel.DEBUG)
                reply = await loop.run_in_executor(
                    None,
                    lambda: chat(
                        full_prompt,
                        system_prompt=SYSTEM_PROMPT,
                        on_tool_call=on_tool_call,
                    ),
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
                await _send(message.channel, f"⚠️ The LLM returned an error: `{exc}`")
                return

        # Discord messages cap at 2000 chars — split if needed.
        if settings.SMART_CUTOFF:
            chunks = _split_smart(reply)
        else:
            chunks = _split_hard(reply)
        if len(chunks) > 1:
            log(
                f"[LLM] Reply split into {len(chunks)} chunks for {message.author} "
                f"({'smart' if settings.SMART_CUTOFF else 'hard'} cutoff)",
                LogLevel.DEBUG,
            )
        for chunk in chunks:
            await _send(message.channel, chunk)


async def setup(bot: commands.Bot) -> None:
    """Entry point called by Bot.load_extension."""
    await bot.add_cog(LLM(bot))
