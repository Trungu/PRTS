# bot/cogs/general.py — general-purpose commands.
from __future__ import annotations

from typing import cast

import discord
from discord import app_commands
from discord.http import Route
from discord.ext import commands

from bot.client import Bot
from utils.logger import log, LogLevel


class General(commands.Cog):
    """General commands available to all users."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

        # Register every command this cog owns directly with the bot dispatcher.
        # The bot will route matching messages here; no manual command_registry
        # call is needed, and the LLM cog can never accidentally steal these.
        bot.register_command("hello",         self._hello)
        bot.register_command("clear history", self._clear_history)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _hello(self, message: discord.Message, _command: str) -> None:
        await message.channel.send("Hello!")

    async def _clear_history(self, message: discord.Message, _command: str) -> None:
        await message.channel.send("Clearing history is not implemented")

    @app_commands.command(name="ui_demo", description="Send a Components V2 demo card")
    async def ui_demo(self, interaction: discord.Interaction) -> None:
        """Demo command for Discord Components V2 container-style cards."""
        await interaction.response.defer(ephemeral=True)

        payload = {
            "flags": (1 << 15) | (1 << 6),  # IS_COMPONENTS_V2 | EPHEMERAL
            "components": [
                {
                    "type": 17,  # Container
                    "components": [
                        {
                            "type": 10,  # Text Display
                            "content": "## UI Kit V2 Demo",
                        },
                        {
                            "type": 10,  # Text Display
                            "content": (
                                "This is a **Components V2** container card rendered by PRTS.\n"
                                "Use this to validate whether your client + bot path supports V2 layout components."
                            ),
                        },
                        {
                            "type": 14,  # Separator
                            "divider": True,
                            "spacing": 1,
                        },
                        {
                            "type": 1,  # Action Row
                            "components": [
                                {
                                    "type": 2,  # Button
                                    "style": 5,  # Link
                                    "label": "Discord Components Docs",
                                    "url": "https://docs.discord.com/developers/components/overview",
                                }
                            ],
                        },
                    ],
                }
            ],
        }

        route = Route(
            "POST",
            "/webhooks/{webhook_id}/{webhook_token}",
            webhook_id=interaction.application_id,
            webhook_token=interaction.token,
        )
        try:
            await self.bot.http.request(route, json=payload)
        except Exception as exc:
            log(f"[UI Demo] Failed to send Components V2 payload: {exc}", LogLevel.ERROR)
            await interaction.followup.send(
                "Failed to send a Components V2 demo card. "
                "Your current library/runtime path may not support this payload yet.",
                ephemeral=True,
            )


async def setup(bot: commands.Bot) -> None:
    """Entry point called by Bot.load_extension."""
    await bot.add_cog(General(cast(Bot, bot)))
