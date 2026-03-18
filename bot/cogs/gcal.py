from __future__ import annotations

# DATABASE IMPORTS
from utils.gcal_db import create_connect_request, get_refresh_token
from utils.gcal_db import set_selected_calendars, get_selected_calendars
import asyncio
from typing import Awaitable, Callable

from datetime import datetime, timedelta, timezone
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# DISCORD IMPORTS
import discord
from discord import app_commands
from discord.http import Route
from discord.ext import commands
import settings

# CONFIG
OAUTH_BASE_URL = settings.OAUTH_BASE_URL
SCOPES = ["https://www.googleapis.com/auth/calendar"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
_FLAG_EPHEMERAL = 1 << 6
_FLAG_COMPONENTS_V2 = 1 << 15


class GCal(commands.GroupCog, group_name="gcal"):
    """Google Calendar commands (connect only, for now)."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @staticmethod
    def _require_google_oauth_client() -> tuple[str, str]:
        client_id = settings.CLIENT_ID
        client_secret = settings.CLIENT_SECRET
        if not client_id or not client_secret:
            raise RuntimeError("Google OAuth client is not configured.")
        return client_id, client_secret


    @staticmethod
    def _event_time_display(ev: dict) -> str:
        start = ev.get("start", {})
        dt = start.get("dateTime")
        if dt:
            parsed = datetime.fromisoformat(dt.replace("Z", "+00:00"))
            unix = int(parsed.timestamp())
            return f"<t:{unix}:f>  (<t:{unix}:R>)"

        # all-day
        d = start.get("date")
        if d:
            return f"All-day ({d})"

        return "Unknown time"

    @staticmethod
    def _single_line(text: str | None) -> str:
        if not text:
            return ""
        return " ".join(str(text).split())

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[: max(0, limit - 1)].rstrip() + "…"

    @staticmethod
    def _event_start_datetime(ev: dict) -> datetime | None:
        start = ev.get("start", {})
        raw = start.get("dateTime")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except Exception:
            return None

    def _build_upcoming_v2_components(
        self,
        *,
        owner_id: int,
        items: list[dict],
        range_mode: str,
        page: int,
        page_size: int = 6,
    ) -> list[dict]:
        total_pages = max(1, (len(items) + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))
        start = page * page_size
        end = start + page_size
        page_items = items[start:end]

        card_components: list[dict] = [
            {"type": 10, "content": "## 🗓️ Upcoming Events"},
            {
                "type": 10,
                "content": (
                    f"Schedule snapshot\n"
                    f"{len(items)} event(s) in "
                    f"{'today' if range_mode == 'today' else 'the next 24 hours'}."
                ),
            },
            {"type": 14, "divider": True, "spacing": 1},
        ]

        for i, ev in enumerate(page_items):
            title = self._truncate(self._single_line(str(ev.get("summary") or "Untitled")), 96)
            start_dt = self._event_start_datetime(ev)
            badge = ""
            if start_dt is not None:
                now = datetime.now(start_dt.tzinfo or timezone.utc)
                mins = int((start_dt - now).total_seconds() // 60)
                if 0 <= mins <= 15:
                    badge = " `Now`"
                elif 16 <= mins <= 60:
                    badge = " `Soon`"
            when = self._event_time_display(ev)
            location = self._truncate(self._single_line(ev.get("location")), 64)
            body = f"### {title}{badge}\n🕒 {when}"
            if location:
                body += f"\n📍 {location}"
            card_components.append({"type": 10, "content": body})
            if i < len(page_items) - 1:
                card_components.append({"type": 14, "divider": False, "spacing": 2})

        card_components.append({"type": 14, "divider": False, "spacing": 2})
        card_components.append(
            {
                "type": 10,
                "content": (
                    f"*Page {page + 1}/{total_pages} • "
                    f"{'Today' if range_mode == 'today' else 'Next 24h'}*"
                ),
            }
        )
        card_components.append({"type": 14, "divider": True, "spacing": 1})
        card_components.append(
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 2,
                        "label": "◀",
                        "custom_id": f"gcalv2:{owner_id}:prev:{range_mode}:{page}",
                        "disabled": page <= 0,
                    },
                    {
                        "type": 2,
                        "style": 1,
                        "label": "▶",
                        "custom_id": f"gcalv2:{owner_id}:next:{range_mode}:{page}",
                        "disabled": page >= (total_pages - 1),
                    },
                    {
                        "type": 2,
                        "style": 2,
                        "label": "Refresh",
                        "custom_id": f"gcalv2:{owner_id}:refresh:{range_mode}:{page}",
                    },
                    {
                        "type": 2,
                        "style": 3,
                        "label": "🗂️ Calendars",
                        "custom_id": f"gcalv2:{owner_id}:cal:{range_mode}:{page}",
                    },
                    {
                        "type": 2,
                        "style": 2,
                        "label": "⏱️ Next 24h" if range_mode == "today" else "📆 Today",
                        "custom_id": f"gcalv2:{owner_id}:toggle:{range_mode}:{page}",
                    },
                ],
            }
        )

        return [{"type": 17, "components": card_components}]

    async def _fetch_calendar_options_for_user(
        self, discord_user_id: int
    ) -> tuple[list[discord.SelectOption], dict[str, tuple[str, str]]]:
        rt = await asyncio.to_thread(get_refresh_token, discord_user_id)
        if not rt:
            raise RuntimeError("You are not connected. Run `/gcal connect` first.")

        client_id, client_secret = self._require_google_oauth_client()

        def fetch_calendar_options() -> tuple[list[discord.SelectOption], dict[str, tuple[str, str]]]:
            creds = Credentials(
                token=None,
                refresh_token=rt,
                token_uri=TOKEN_URI,
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES,
            )
            creds.refresh(Request())
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)

            items = service.calendarList().list().execute().get("items", [])

            def score(c: dict) -> tuple[int, int]:
                primary_rank = 0 if c.get("primary") else 1
                role = c.get("accessRole") or ""
                role_rank = 0 if role in ("owner", "writer") else 1
                return (primary_rank, role_rank)

            items.sort(key=score)

            options: list[discord.SelectOption] = []
            index_to_calendar: dict[str, tuple[str, str]] = {}
            i = 0
            for c in items:
                if i >= 5:
                    break

                cal_id = c.get("id")
                name = c.get("summary") or cal_id
                if not cal_id or not name:
                    continue

                idx = str(i)
                label = name[:100]
                desc = ("Primary" if c.get("primary") else (c.get("accessRole") or ""))[:100] or None
                options.append(discord.SelectOption(label=label, value=idx, description=desc))
                index_to_calendar[idx] = (cal_id, name)
                i += 1

            return options, index_to_calendar

        return await asyncio.to_thread(fetch_calendar_options)

    async def _fetch_upcoming_events(
        self, discord_user_id: int, *, range_mode: str = "next24h"
    ) -> list[dict]:
        rt = await asyncio.to_thread(get_refresh_token, discord_user_id)
        if not rt:
            raise RuntimeError("You are not connected. Run `/gcal connect` first.")

        selected = await asyncio.to_thread(get_selected_calendars, discord_user_id)
        calendar_ids = selected or ["primary"]
        client_id, client_secret = self._require_google_oauth_client()

        def fetch() -> list[dict]:
            creds = Credentials(
                token=None,
                refresh_token=rt,
                token_uri=TOKEN_URI,
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES,
            )
            creds.refresh(Request())
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)

            now_utc = datetime.now(timezone.utc)
            time_min = now_utc.isoformat().replace("+00:00", "Z")
            if range_mode == "today":
                now_local = datetime.now().astimezone()
                next_midnight_local = datetime.combine(
                    now_local.date() + timedelta(days=1),
                    datetime.min.time(),
                    tzinfo=now_local.tzinfo,
                )
                time_max_dt = next_midnight_local.astimezone(timezone.utc)
            else:
                time_max_dt = now_utc + timedelta(days=1)
            time_max = time_max_dt.isoformat().replace("+00:00", "Z")

            all_items: list[dict] = []
            for cal_id in calendar_ids:
                res = service.events().list(
                    calendarId=cal_id,
                    timeMin=time_min,
                    timeMax=time_max,
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=25,
                ).execute()
                all_items.extend(res.get("items", []))

            def start_key(ev: dict) -> str:
                start = ev.get("start", {})
                return start.get("dateTime") or start.get("date") or ""

            all_items.sort(key=start_key)
            return all_items[:48]

        return await asyncio.to_thread(fetch)

    @staticmethod
    def _parse_iso_datetime(raw: str) -> datetime:
        # Accept both "...Z" and full ISO-8601 offsets.
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Datetime must include a timezone offset, e.g. +00:00 or Z.")
        return parsed

    @staticmethod
    def _build_service(refresh_token: str):
        client_id, client_secret = GCal._require_google_oauth_client()
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri=TOKEN_URI,
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        creds.refresh(Request())
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    async def _get_service_for_user(self, discord_user_id: int):
        rt = await asyncio.to_thread(get_refresh_token, discord_user_id)
        if not rt:
            return None, "You are not connected. Run `/gcal connect` first."
        try:
            service = await asyncio.to_thread(self._build_service, rt)
            return service, None
        except Exception as e:
            return None, f"Failed to authenticate with Google Calendar: {e}"

    async def _resolve_default_calendar(self, discord_user_id: int) -> str:
        selected = await asyncio.to_thread(get_selected_calendars, discord_user_id)
        if selected:
            return selected[0]
        return "primary"

    @staticmethod
    def _with_prts_event_metadata(description: str | None) -> tuple[str, dict[str, str]]:
        """Return visible + private metadata that marks PRTS-created events.

        The marker in ``description`` gives human provenance directly in Google Calendar.
        ``extendedProperties.private`` stores machine-readable metadata for future
        automation (safe filtering of bot-created events, migration/versioning, and
        idempotent updates) without exposing extra internals to attendees.
        """
        marker = "[Added by PRTS bot]"
        base = (description or "").strip()
        if marker.lower() in base.lower():
            merged_description = base
        elif base:
            merged_description = f"{base}\n\n{marker}"
        else:
            merged_description = marker

        private_meta = {
            "prts_created": "true",
            "prts_source": "discord_bot",
            "prts_created_at_utc": datetime.now(timezone.utc).isoformat(),
        }
        return merged_description, private_meta


    @app_commands.command(name="connect", description="Connect your Google Calendar")
    async def connect(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        if not OAUTH_BASE_URL:
            await interaction.followup.send("OAuth server is not configured.", ephemeral=True)
            return

        # IMPORTANT: create + store connect_id in DB
        connect_id = await asyncio.to_thread(create_connect_request, interaction.user.id)

        link = f"Please connect your Google Calendar using this link: {OAUTH_BASE_URL.rstrip('/')}/auth?connect_id={connect_id}"
        await interaction.followup.send(link, ephemeral=True)


    @app_commands.command(name="add_event", description="Add a Google Calendar event")
    @app_commands.describe(
        title="Event title",
        start_iso="Start datetime ISO-8601 (e.g. 2026-03-03T15:00:00-06:00)",
        end_iso="End datetime ISO-8601 (e.g. 2026-03-03T16:00:00-06:00)",
        description="Optional description",
        location="Optional location",
        reminder_minutes="Optional reminder minutes before start (e.g. 10,60)",
        calendar_id="Optional calendar ID (defaults to first selected or primary)",
    )
    async def add_event(
        self,
        interaction: discord.Interaction,
        title: str,
        start_iso: str,
        end_iso: str,
        description: str | None = None,
        location: str | None = None,
        reminder_minutes: str | None = None,
        calendar_id: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            start_dt = self._parse_iso_datetime(start_iso)
            end_dt = self._parse_iso_datetime(end_iso)
            if end_dt <= start_dt:
                await interaction.followup.send("`end_iso` must be after `start_iso`.", ephemeral=True)
                return
        except ValueError as e:
            await interaction.followup.send(f"Invalid datetime: {e}", ephemeral=True)
            return

        reminder_overrides: list[dict] | None = None
        if reminder_minutes:
            try:
                mins = sorted(
                    {
                        int(v.strip())
                        for v in reminder_minutes.split(",")
                        if v.strip()
                    }
                )
            except ValueError:
                await interaction.followup.send(
                    "Invalid `reminder_minutes`. Use comma-separated integers like `10,60`.",
                    ephemeral=True,
                )
                return

            if not mins or any(m < 0 for m in mins):
                await interaction.followup.send(
                    "`reminder_minutes` must contain non-negative integers.",
                    ephemeral=True,
                )
                return

            reminder_overrides = [{"method": "popup", "minutes": m} for m in mins]

        service, auth_error = await self._get_service_for_user(interaction.user.id)
        if not service:
            await interaction.followup.send(auth_error, ephemeral=True)
            return

        target_calendar = calendar_id or await self._resolve_default_calendar(interaction.user.id)

        event_body = {
            "summary": title,
            "start": {"dateTime": start_dt.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
        }
        marked_description, private_meta = self._with_prts_event_metadata(description)
        event_body["description"] = marked_description
        event_body["extendedProperties"] = {"private": private_meta}
        if location:
            event_body["location"] = location
        if reminder_overrides is not None:
            event_body["reminders"] = {"useDefault": False, "overrides": reminder_overrides}

        def create_event():
            return service.events().insert(calendarId=target_calendar, body=event_body).execute()

        try:
            created = await asyncio.to_thread(create_event)
        except HttpError as e:
            status = getattr(e.resp, "status", "unknown")
            await interaction.followup.send(
                f"Google Calendar rejected the request ({status}). "
                "Reconnect with `/gcal connect` to grant write scope, then try again.",
                ephemeral=True,
            )
            return
        except Exception as e:
            await interaction.followup.send(f"Failed to create event: {e}", ephemeral=True)
            return

        event_id = created.get("id", "unknown")
        when = self._event_time_display(created)
        await interaction.followup.send(
            f"Created event ✅\nTitle: `{title}`\nWhen: {when}\nEvent ID: `{event_id}`\nCalendar: `{target_calendar}`",
            ephemeral=True,
        )


    @app_commands.command(name="remove_event", description="Delete a Google Calendar event by event ID")
    @app_commands.describe(
        event_id="Event ID to delete (shown by /gcal add_event)",
        calendar_id="Optional calendar ID (defaults to first selected or primary)",
    )
    async def remove_event(
        self,
        interaction: discord.Interaction,
        event_id: str,
        calendar_id: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        service, auth_error = await self._get_service_for_user(interaction.user.id)
        if not service:
            await interaction.followup.send(auth_error, ephemeral=True)
            return

        target_calendar = calendar_id or await self._resolve_default_calendar(interaction.user.id)

        def delete_event():
            return service.events().delete(calendarId=target_calendar, eventId=event_id).execute()

        try:
            await asyncio.to_thread(delete_event)
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            if status == 404:
                await interaction.followup.send(
                    f"No event found with ID `{event_id}` in `{target_calendar}`.",
                    ephemeral=True,
                )
                return
            await interaction.followup.send(
                f"Google Calendar rejected the request ({status or 'unknown'}). "
                "Reconnect with `/gcal connect` to grant write scope, then try again.",
                ephemeral=True,
            )
            return
        except Exception as e:
            await interaction.followup.send(f"Failed to remove event: {e}", ephemeral=True)
            return

        await interaction.followup.send(
            f"Deleted event ✅\nEvent ID: `{event_id}`\nCalendar: `{target_calendar}`",
            ephemeral=True,
        )


    @app_commands.command(name="set_reminder", description="Set pop-up reminder minutes for an event")
    @app_commands.describe(
        event_id="Event ID to update",
        reminder_minutes="Comma-separated minutes before event start (e.g. 10,30,60)",
        calendar_id="Optional calendar ID (defaults to first selected or primary)",
    )
    async def set_reminder(
        self,
        interaction: discord.Interaction,
        event_id: str,
        reminder_minutes: str,
        calendar_id: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        try:
            mins = sorted(
                {
                    int(v.strip())
                    for v in reminder_minutes.split(",")
                    if v.strip()
                }
            )
        except ValueError:
            await interaction.followup.send(
                "Invalid `reminder_minutes`. Use comma-separated integers like `10,60`.",
                ephemeral=True,
            )
            return

        if not mins or any(m < 0 for m in mins):
            await interaction.followup.send(
                "`reminder_minutes` must contain non-negative integers.",
                ephemeral=True,
            )
            return

        service, auth_error = await self._get_service_for_user(interaction.user.id)
        if not service:
            await interaction.followup.send(auth_error, ephemeral=True)
            return

        target_calendar = calendar_id or await self._resolve_default_calendar(interaction.user.id)
        reminder_payload = {
            "reminders": {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": m} for m in mins],
            }
        }

        def patch_event():
            return service.events().patch(
                calendarId=target_calendar,
                eventId=event_id,
                body=reminder_payload,
            ).execute()

        try:
            await asyncio.to_thread(patch_event)
        except HttpError as e:
            status = getattr(e.resp, "status", None)
            if status == 404:
                await interaction.followup.send(
                    f"No event found with ID `{event_id}` in `{target_calendar}`.",
                    ephemeral=True,
                )
                return
            await interaction.followup.send(
                f"Google Calendar rejected the request ({status or 'unknown'}). "
                "Reconnect with `/gcal connect` to grant write scope, then try again.",
                ephemeral=True,
            )
            return
        except Exception as e:
            await interaction.followup.send(f"Failed to set reminder: {e}", ephemeral=True)
            return

        mins_pretty = ", ".join(str(m) for m in mins)
        await interaction.followup.send(
            f"Reminder updated ✅\nEvent ID: `{event_id}`\nMinutes: `{mins_pretty}`\nCalendar: `{target_calendar}`",
            ephemeral=True,
        )


    @app_commands.command(name="calendars", description="Choose which calendars to use for reminders")
    async def calendars(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            options, index_to_calendar = await self._fetch_calendar_options_for_user(interaction.user.id)
        except Exception as e:
            await interaction.followup.send(f"Failed to load calendars: {e}", ephemeral=True)
            return

        if not options:
            await interaction.followup.send("No calendars found.", ephemeral=True)
            return
        
        # Show the select menu and display the options
        view = CalendarSelectView(
            owner_id=interaction.user.id,
            options=options,
            index_to_calendar=index_to_calendar,
            redirect_to_upcoming_after_save=True,
            fetch_events=self._fetch_upcoming_events,
            fetch_calendars=self._fetch_calendar_options_for_user,
            build_v2_components=self._build_upcoming_v2_components,
            render_time=self._event_time_display,
            location_formatter=lambda raw: self._truncate(self._single_line(raw), 64),
            redirect_range_mode="next24h",
            page_size=6,
        )

        await interaction.followup.send(
            "Pick calendars (showing up to 5):",
            view=view, 
            ephemeral=True
        )


    @app_commands.command(name="show", description="Show upcoming Google Calendar events")
    async def show(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        try:
            items = await self._fetch_upcoming_events(interaction.user.id, range_mode="next24h")
            if not items:
                await interaction.followup.send("Connected ✅ No events in the next 24 hours.", ephemeral=True)
                return
            payload = {
                "flags": _FLAG_EPHEMERAL | _FLAG_COMPONENTS_V2,
                "components": self._build_upcoming_v2_components(
                    owner_id=interaction.user.id,
                    items=items,
                    range_mode="next24h",
                    page=0,
                    page_size=6,
                ),
            }
            route = Route(
                "POST",
                "/webhooks/{webhook_id}/{webhook_token}",
                webhook_id=interaction.application_id,
                webhook_token=interaction.token,
            )
            await self.bot.http.request(route, json=payload)
        except Exception as e:
            await interaction.followup.send(f"Failed to show upcoming events: {e}", ephemeral=True)

        # await interaction.followup.send("\n".join(lines), ephemeral=True)


    @app_commands.command(name="status", description="Show Google Calendar connection/debug status")
    async def status(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)

        user_id = interaction.user.id
        rt = await asyncio.to_thread(get_refresh_token, user_id)
        selected = await asyncio.to_thread(get_selected_calendars, user_id)
        selected_display = ", ".join(selected) if selected else "primary (default)"

        if not rt:
            await interaction.followup.send(
                "\n".join(
                    [
                        "Google Calendar status:",
                        f"- discord_user_id: `{user_id}`",
                        "- refresh_token_in_db: `False`",
                        f"- selected_calendars: `{selected_display}`",
                        "- auth_check: `skipped (no token)`",
                    ]
                ),
                ephemeral=True,
            )
            return
        try:
            client_id, client_secret = self._require_google_oauth_client()
        except RuntimeError as e:
            await interaction.followup.send(str(e), ephemeral=True)
            return

        def auth_check() -> tuple[bool, str]:
            creds = Credentials(
                token=None,
                refresh_token=rt,
                token_uri=TOKEN_URI,
                client_id=client_id,
                client_secret=client_secret,
                scopes=SCOPES,
            )
            creds.refresh(Request())
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            primary = service.calendars().get(calendarId="primary").execute()
            summary = primary.get("summary", "primary")
            return True, f"ok (primary='{summary}')"

        try:
            ok, detail = await asyncio.to_thread(auth_check)
            auth_text = f"{ok} ({detail})"
        except Exception as e:
            auth_text = f"False ({e})"

        await interaction.followup.send(
            "\n".join(
                [
                    "Google Calendar status:",
                    f"- discord_user_id: `{user_id}`",
                    "- refresh_token_in_db: `True`",
                    f"- selected_calendars: `{selected_display}`",
                    f"- auth_check: `{auth_text}`",
                    f"- requested_scopes: `{', '.join(SCOPES)}`",
                ]
            ),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        data = getattr(interaction, "data", None) or {}
        custom_id = str(data.get("custom_id", "") or "")
        if not custom_id.startswith("gcalv2:"):
            return

        parts = custom_id.split(":")
        if len(parts) != 5:
            if not interaction.response.is_done():
                await interaction.response.send_message("Invalid UI action.", ephemeral=True)
            return

        _, owner_raw, action, range_mode, page_raw = parts
        try:
            owner_id = int(owner_raw)
            page = int(page_raw)
        except ValueError:
            if not interaction.response.is_done():
                await interaction.response.send_message("Invalid UI state.", ephemeral=True)
            return

        if interaction.user.id != owner_id:
            if not interaction.response.is_done():
                await interaction.response.send_message("This UI isn’t for you.", ephemeral=True)
            return

        if action == "cal":
            try:
                options, index_to_calendar = await self._fetch_calendar_options_for_user(interaction.user.id)
            except Exception as e:
                await interaction.response.send_message(f"Failed to load calendars: {e}", ephemeral=True)
                return
            if not options:
                await interaction.response.send_message("No calendars found.", ephemeral=True)
                return

            view = CalendarSelectView(
                owner_id=interaction.user.id,
                options=options,
                index_to_calendar=index_to_calendar,
                redirect_to_upcoming_after_save=True,
                fetch_events=self._fetch_upcoming_events,
                fetch_calendars=self._fetch_calendar_options_for_user,
                build_v2_components=self._build_upcoming_v2_components,
                render_time=self._event_time_display,
                location_formatter=lambda raw: self._truncate(self._single_line(raw), 64),
                redirect_range_mode=range_mode,
                page_size=6,
            )
            await interaction.response.send_message(
                "Pick calendars (showing up to 5):",
                view=view,
                ephemeral=True,
            )
            return

        if not interaction.response.is_done():
            await interaction.response.defer()

        target_range = range_mode
        if action == "today":
            target_range = "today"
        elif action == "next24":
            target_range = "next24h"
        elif action == "toggle":
            target_range = "today" if range_mode != "today" else "next24h"

        try:
            items = await self._fetch_upcoming_events(interaction.user.id, range_mode=target_range)
        except Exception as e:
            await interaction.followup.send(f"Failed to refresh events: {e}", ephemeral=True)
            return

        if not items:
            await interaction.followup.send("No events found for this range.", ephemeral=True)
            return

        total_pages = max(1, (len(items) + 6 - 1) // 6)
        if action == "prev":
            page = max(0, page - 1)
        elif action == "next":
            page = min(total_pages - 1, page + 1)
        elif action == "refresh":
            page = min(page, total_pages - 1)
        elif action in {"today", "next24", "toggle"}:
            page = 0

        components = self._build_upcoming_v2_components(
            owner_id=interaction.user.id,
            items=items,
            range_mode=target_range,
            page=page,
            page_size=6,
        )
        route = Route(
            "PATCH",
            "/webhooks/{webhook_id}/{webhook_token}/messages/{message_id}",
            webhook_id=interaction.application_id,
            webhook_token=interaction.token,
            message_id=interaction.message.id,  # type: ignore[arg-type]
        )
        try:
            await self.bot.http.request(route, json={"components": components})
        except Exception as e:
            await interaction.followup.send(f"Failed to update UI: {e}", ephemeral=True)


class CalendarSelect(discord.ui.Select):
    def __init__(self, options: list[discord.SelectOption], index_to_calendar: dict[str, tuple[str, str]]):
        # index_to_calendar maps "0" -> (calendar_id, calendar_name)
        self.index_to_calendar = index_to_calendar

        super().__init__(
            placeholder="Choose calendars for reminders (max 5 shown)",
            min_values=1,
            max_values=min(5, len(options)),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        # Only allow the user who opened the menu to interact
        view: CalendarSelectView = self.view  # type: ignore
        if interaction.user.id != view.owner_id:
            await interaction.response.send_message("This menu isn’t for you.", ephemeral=True)
            return

        chosen_ids: list[str] = []
        chosen_names: list[str] = []

        for idx in self.values:  # idx is "0".."4"
            cal_id, cal_name = self.index_to_calendar[idx]
            chosen_ids.append(cal_id)
            chosen_names.append(cal_name)

        # Save to DB (offload sync supabase call)
        await asyncio.to_thread(set_selected_calendars, interaction.user.id, chosen_ids)

        pretty = "\n".join(f"• {name}" for name in chosen_names)
        saved_text = f"Saved ✅ I’ll send reminders for:\n{pretty}"

        if view.redirect_to_upcoming_after_save and view.fetch_events is not None:
            await interaction.response.send_message(saved_text, ephemeral=True)
            try:
                items = await view.fetch_events(interaction.user.id, range_mode=view.redirect_range_mode)
            except Exception as e:
                await interaction.followup.send(
                    f"Failed to refresh upcoming events: {e}",
                    ephemeral=True,
                )
            else:
                if not items:
                    await interaction.followup.send(
                        "No events found for the selected range.",
                        ephemeral=True,
                    )
                else:
                    if view.build_v2_components is None:
                        await interaction.followup.send(
                            "Saved, but V2 renderer is unavailable.",
                            ephemeral=True,
                        )
                    else:
                        payload = {
                            "flags": _FLAG_EPHEMERAL | _FLAG_COMPONENTS_V2,
                            "components": view.build_v2_components(
                                owner_id=interaction.user.id,
                                items=items,
                                range_mode=view.redirect_range_mode,
                                page=0,
                                page_size=view.page_size,
                            ),
                        }
                        route = Route(
                            "POST",
                            "/webhooks/{webhook_id}/{webhook_token}",
                            webhook_id=interaction.application_id,
                            webhook_token=interaction.token,
                        )
                        try:
                            await interaction.client.http.request(route, json=payload)  # type: ignore[union-attr]
                        except Exception as e:
                            await interaction.followup.send(
                                f"Saved, but failed to render events card: {e}",
                                ephemeral=True,
                            )
        else:
            await interaction.response.send_message(saved_text, ephemeral=True)

        self.disabled = True
        view.stop()

        if interaction.message:
            try:
                await interaction.message.edit(view=view)
            except discord.NotFound:
                pass


class CalendarSelectView(discord.ui.View):
    def __init__(
        self,
        owner_id: int,
        options: list[discord.SelectOption],
        index_to_calendar: dict[str, tuple[str, str]],
        *,
        redirect_to_upcoming_after_save: bool = False,
        fetch_events: Callable[..., Awaitable[list[dict]]] | None = None,
        fetch_calendars: Callable[[int], Awaitable[tuple[list[discord.SelectOption], dict[str, tuple[str, str]]]]] | None = None,
        build_v2_components: Callable[..., list[dict]] | None = None,
        render_time=None,
        location_formatter=None,
        redirect_range_mode: str = "next24h",
        page_size: int = 6,
    ):
        super().__init__(timeout=120)
        self.owner_id = owner_id
        self.redirect_to_upcoming_after_save = redirect_to_upcoming_after_save
        self.fetch_events = fetch_events
        self.fetch_calendars = fetch_calendars
        self.build_v2_components = build_v2_components
        self.render_time = render_time
        self.location_formatter = location_formatter
        self.redirect_range_mode = redirect_range_mode
        self.page_size = page_size
        self.add_item(CalendarSelect(options, index_to_calendar))


class UpcomingEventsPagerView(discord.ui.View):
    def __init__(
        self,
        *,
        owner_id: int,
        items: list[dict],
        render_time,
        location_formatter,
        fetch_events: Callable[..., Awaitable[list[dict]]],
        fetch_calendars: Callable[[int], Awaitable[tuple[list[discord.SelectOption], dict[str, tuple[str, str]]]]],
        range_mode: str = "next24h",
        page_size: int = 6,
    ):
        super().__init__(timeout=300)
        self.owner_id = owner_id
        self.items = items
        self.render_time = render_time
        self.location_formatter = location_formatter
        self.fetch_events = fetch_events
        self.fetch_calendars = fetch_calendars
        self.range_mode = range_mode
        self.page_size = max(1, page_size)
        self.page_index = 0
        self._sync_buttons()

    def _page_count(self) -> int:
        return max(1, (len(self.items) + self.page_size - 1) // self.page_size)

    def _sync_buttons(self) -> None:
        total = self._page_count()
        self.prev_button.disabled = self.page_index <= 0
        self.next_button.disabled = self.page_index >= (total - 1)
        self.range_toggle_button.label = "⏱️ Next 24h" if self.range_mode == "today" else "📆 Today"

    def current_embed(self) -> discord.Embed:
        total = self._page_count()
        start = self.page_index * self.page_size
        end = start + self.page_size
        page_items = self.items[start:end]

        embed = discord.Embed(
            title="🗓️ Upcoming Events",
            description=(
                f"**Schedule Snapshot**\n"
                f"{len(self.items)} event(s) "
                f"in {'today' if self.range_mode == 'today' else 'the next 24 hours'}."
            ),
        )
        embed.set_footer(text=f"Page {self.page_index + 1}/{total}")

        for ev in page_items:
            title = str(ev.get("summary") or "Untitled")[:256]
            when = self.render_time(ev)
            location = self.location_formatter(ev.get("location"))

            details = f"🕒 {when}"
            if location:
                details += f"\n📍 {location}"
            # Keep a visual gap between events in dense lists.
            details += "\n\u200b"

            embed.add_field(name=title, value=details, inline=False)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This pager isn't for you.", ephemeral=True)
            return False
        return True

    async def _render(self, interaction: discord.Interaction) -> None:
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.current_embed(), view=self)

    async def _reload_items(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        try:
            self.items = await self.fetch_events(self.owner_id, range_mode=self.range_mode)
            self.page_index = 0
            self._sync_buttons()
            await interaction.edit_original_response(embed=self.current_embed(), view=self)
        except Exception as e:
            await interaction.followup.send(f"Failed to refresh events: {e}", ephemeral=True)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if self.page_index > 0:
            self.page_index -= 1
        await self._render(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if self.page_index < self._page_count() - 1:
            self.page_index += 1
        await self._render(interaction)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.secondary)
    async def refresh_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        await self._reload_items(interaction)

    @discord.ui.button(label="📆 Today", style=discord.ButtonStyle.secondary)
    async def range_toggle_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.range_mode = "today" if self.range_mode != "today" else "next24h"
        await self._reload_items(interaction)

    @discord.ui.button(label="🗂️ Calendars", style=discord.ButtonStyle.success)
    async def calendars_button(self, interaction: discord.Interaction, _button: discord.ui.Button):
        try:
            options, index_to_calendar = await self.fetch_calendars(self.owner_id)
        except Exception as e:
            await interaction.response.send_message(f"Failed to load calendars: {e}", ephemeral=True)
            return

        if not options:
            await interaction.response.send_message("No calendars found.", ephemeral=True)
            return

        view = CalendarSelectView(
            owner_id=self.owner_id,
            options=options,
            index_to_calendar=index_to_calendar,
            redirect_to_upcoming_after_save=True,
            fetch_events=self.fetch_events,
            fetch_calendars=self.fetch_calendars,
            render_time=self.render_time,
            location_formatter=self.location_formatter,
            redirect_range_mode=self.range_mode,
            page_size=self.page_size,
        )
        await interaction.response.send_message(
            "Pick calendars (showing up to 5):",
            view=view,
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(GCal(bot))
