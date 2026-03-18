import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncio
import json
import logging
from typing import cast
from datetime import datetime, timezone

from bot.client import Bot
from tools.llm_api import chat
from utils.todo_db import add_tasks, get_pending_tasks, complete_task, get_tasks_to_ping, update_last_pinged

log = logging.getLogger("todolist")

class TodoList(commands.Cog):
    """ADHD-friendly to-do list manager."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.ping_tasks_loop.start()

    def cog_unload(self):
        self.ping_tasks_loop.cancel()

    @app_commands.command(name="todo_start", description="Start using the ADHD-friendly to-do list (DMs you)")
    async def todo_start(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            user = interaction.user
            dm_channel = await user.create_dm()

            embed = discord.Embed(
                title="🧠 Welcome to your ADHD-friendly To-Do List!",
                description=(
                    "I've set up a private space for you to dump your tasks.\n\n"
                    "**How to use:**\n"
                    "1. Use `/dump <tasks>` anywhere, or just talk to me here in DMs to brain-dump your tasks. "
                    "I'll organize them by importance and estimate how long they'll take.\n"
                    "2. Use `/list` to see your organized tasks.\n"
                    "3. If you forget about them, I'll gently remind you later!\n\n"
                    "Go ahead and try `/dump I need to do laundry, finish the presentation, and reply to Bob's email.`"
                ),
                color=discord.Color.green()
            )
            await dm_channel.send(embed=embed)
            await interaction.followup.send("I've sent you a DM to get started!", ephemeral=True)
        except discord.Forbidden:
            await interaction.followup.send("I couldn't send you a DM. Please check your privacy settings.", ephemeral=True)

    @app_commands.command(name="dump", description="Brain-dump tasks. I will organize them for you!")
    @app_commands.describe(
        tasks="A messy list of things you need to do",
        visibility="Should others see this? (True for public accountability, False for private. Default: False)"
    )
    async def dump(self, interaction: discord.Interaction, tasks: str, visibility: bool = False) -> None:
        # If visibility is False, make the response ephemeral
        await interaction.response.defer(ephemeral=not visibility)

        system_prompt = (
            "You are an ADHD-friendly task organizer assistant. The user will provide a messy, unstructured "
            "brain dump of things they need to do. Your job is to parse this into a structured JSON list of distinct tasks. "
            "For each task, infer a clean title, an optional brief description or breakdown, a priority/importance level "
            "from 1 (lowest) to 5 (highest, most urgent/important), and an estimated duration in minutes.\n\n"
            "Respond ONLY with valid JSON matching this schema:\n"
            "[\n"
            "  {\n"
            '    "title": "String",\n'
            '    "description": "String (optional breakdown or tips)",\n'
            '    "importance": Integer (1-5),\n'
            '    "duration_minutes": Integer (estimated minutes, e.g., 15)\n'
            "  }\n"
            "]"
        )

        try:
            # Use the LLM to parse the tasks
            response = await asyncio.to_thread(
                chat,
                messages=tasks,
                system_prompt=system_prompt,
                temperature=0.3, # Low temp for structured output
                max_tokens=1024,
                enable_tools=False
            )

            # Clean up potential markdown formatting around JSON
            clean_response = response.strip()
            if clean_response.startswith("```json"):
                clean_response = clean_response[7:]
            if clean_response.startswith("```"):
                clean_response = clean_response[3:]
            if clean_response.endswith("```"):
                clean_response = clean_response[:-3]

            parsed_tasks = json.loads(clean_response)

            if not isinstance(parsed_tasks, list) or not parsed_tasks:
                raise ValueError("LLM did not return a valid list of tasks.")

            # Save to DB
            await asyncio.to_thread(add_tasks, interaction.user.id, parsed_tasks)

            # Respond
            count = len(parsed_tasks)
            await interaction.followup.send(f"✅ Successfully processed and organized {count} task(s)! Use `/list` to view them.", ephemeral=not visibility)

        except Exception as e:
            log.error(f"Failed to process dump: {e}")
            await interaction.followup.send(f"❌ Sorry, I had trouble parsing your tasks. Please try again in a different format.", ephemeral=not visibility)

    @app_commands.command(name="list", description="View your organized to-do list")
    @app_commands.describe(
        visibility="Should others see your list? (True for public accountability, False for private. Default: False)"
    )
    async def list_tasks(self, interaction: discord.Interaction, visibility: bool = False) -> None:
        await interaction.response.defer(ephemeral=not visibility)

        pending_tasks = await asyncio.to_thread(get_pending_tasks, interaction.user.id)

        if not pending_tasks:
            await interaction.followup.send("🎉 Your to-do list is completely empty! Great job!", ephemeral=not visibility)
            return

        embed = discord.Embed(
            title=f"📝 To-Do List for {interaction.user.display_name}",
            description="Here are your pending tasks, ordered by importance:",
            color=discord.Color.blue()
        )

        # Display top 10 tasks to avoid hitting Discord embed limits
        for i, task in enumerate(pending_tasks[:10]):
            importance_stars = "⭐" * task['importance']
            duration = f"{task['duration_minutes']} min" if task['duration_minutes'] else "Unknown time"

            title_text = f"**{task['title']}** ({duration}) - {importance_stars}"
            desc_text = task['description'] if task['description'] else "No description"

            embed.add_field(name=title_text, value=desc_text, inline=False)

        if len(pending_tasks) > 10:
            embed.set_footer(text=f"...and {len(pending_tasks) - 10} more tasks.")

        view = TaskCompletionView(pending_tasks[:5]) # Show completion buttons for top 5
        await interaction.followup.send(embed=embed, view=view, ephemeral=not visibility)

    @tasks.loop(hours=2) # Check every 2 hours
    async def ping_tasks_loop(self):
        """Background loop to ping users about old pending tasks."""
        try:
            tasks_to_ping = await asyncio.to_thread(get_tasks_to_ping, hours_since_creation=24, hours_since_last_ping=24)

            # Group tasks by user
            users_to_ping = {}
            for task in tasks_to_ping:
                user_id = task["user_id"]
                if user_id not in users_to_ping:
                    users_to_ping[user_id] = []
                users_to_ping[user_id].append(task)

            for user_id, tasks in users_to_ping.items():
                try:
                    user = await self.bot.fetch_user(user_id)
                    if user:
                        dm_channel = await user.create_dm()

                        count = len(tasks)
                        task_list_str = "\n".join([f"- **{t['title']}**" for t in tasks[:3]])
                        if count > 3:
                            task_list_str += f"\n...and {count - 3} more."

                        embed = discord.Embed(
                            title="⏰ Friendly check-in on your tasks!",
                            description=f"Hey there! I noticed you have some tasks pending for over 24 hours:\n\n{task_list_str}\n\nHave you made any progress? You can use `/list` to view all your tasks.",
                            color=discord.Color.orange()
                        )
                        await dm_channel.send(embed=embed)

                        # Update last_pinged_at
                        for t in tasks:
                            await asyncio.to_thread(update_last_pinged, t["id"])

                except Exception as e:
                    log.error(f"Failed to ping user {user_id}: {e}")

        except Exception as e:
            log.error(f"Error in ping_tasks_loop: {e}")

    @ping_tasks_loop.before_loop
    async def before_ping_tasks_loop(self):
        await self.bot.wait_until_ready()

class TaskCompletionView(discord.ui.View):
    def __init__(self, tasks: list):
        super().__init__(timeout=None) # Don't timeout, let users click later

        # Create a button for each task
        for i, task in enumerate(tasks):
            # Pass the task_id into the button creation
            self.add_item(CompleteTaskButton(task['id'], task['title'], row=i//3)) # Max 3 per row

class CompleteTaskButton(discord.ui.Button):
    def __init__(self, task_id: int, title: str, row: int):
        label_text = title[:20] + "..." if len(title) > 20 else title
        super().__init__(style=discord.ButtonStyle.success, label=f"✓ {label_text}", custom_id=f"complete_task_{task_id}", row=row)
        self.task_id = task_id

    async def callback(self, interaction: discord.Interaction):
        try:
            # Mark complete in DB
            await asyncio.to_thread(complete_task, self.task_id, interaction.user.id)

            # Disable the button and update it
            self.disabled = True
            self.style = discord.ButtonStyle.secondary
            self.label = f"Completed"

            await interaction.response.edit_message(view=self.view)
            await interaction.followup.send(f"Great job completing a task!", ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(f"Error completing task: {e}", ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TodoList(bot))
