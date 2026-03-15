# Contributing to PRTS Bot

New contributors begin here. This page provides a comprehensive guide on how to contribute to the PRTS repository.

You might find this useful as well: https://discord.com/developers/docs/intro

## Table of Contents

- [Project Overview](#project-overview)
- [Local Setup](#local-setup)
  - [Minimal .env Setup](#minimal-env-setup)
- [Run the App](#run-the-app)
- [Testing](#testing)
- [Code Standards](#code-standards)
  - [Code Standards: Config](#config-and-environment-variables)
  - [Code Standards: Logging](#logging)
  - [Code Standards: Error Handling](#error-handling)
  - [Code Standards: Module Scope](#keep-modules-focused)
- [Feature Contribution Patterns](#feature-contribution-patterns)
  - [Feature Patterns: Prefix Commands](#add-a-new-prefix-command)
  - [Feature Patterns: Tools](#add-a-new-tool)
  - [Feature Patterns: Calendar](#add-calendar-behavior)
- [Security and Safety Notes](#security-and-safety-notes)
- [Issues and Feature Requests](#issues-and-feature-requests)
  - [Issues: Reporting Bugs](#reporting-bugs)
  - [Issues: Suggesting Features](#suggesting-features)
- [Pull Request Checklist](#pull-request-checklist)
  - [PR Checklist: Before Opening](#before-opening-a-pr)
  - [PR Checklist: Review Readiness](#review-readiness)
- [Commit Message Guidance](#commit-message-guidance)

## Project Overview

PRTS is a Discord bot with:

- Prefix-based command routing in `bot/client.py`
- Cog-based features in `bot/cogs/`
- LLM + tool-calling flow in `bot/cogs/llm.py` and `tools/`
- Google Calendar integration via slash commands + tool calls
- OAuth callback server in `oauth_server.py`

## Local Setup

1. Create and activate a virtual environment.

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Create your env file.

```bash
cp .env.example .env
```

4. Fill required values in `.env` (Discord token, LLM settings, OAuth, Supabase).

### Minimal .env Setup

You only need to fill env vars for the features you are actively working on.

- Core bot startup: `DISCORD_TOKEN`, `BOT_PREFIX`
- Hosted LLM work: `LLM_API_KEY` (and optional `LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`)
- Google Calendar features: `CLIENT_ID`, `CLIENT_SECRET`, `OAUTH_BASE_URL`, `OAUTH_REDIRECT_URI`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- OAuth server work: `CLIENT_ID`, `CLIENT_SECRET`, `OAUTH_REDIRECT_URI`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`

### LLM Provider Setup (Groq vs Local)

Choose hosted or local LLM mode depending on your development workflow.

- Hosted (Groq/API): set `LLM_PROVIDER=groq` and `LLM_API_KEY=<your_key>`.
- Local (Ollama): set `LLM_PROVIDER=ollama` and run Ollama locally.
- Optional overrides for either mode: `LLM_MODEL`, `LLM_BASE_URL`, `LLM_REQUEST_TIMEOUT_SECONDS`.
- Default behavior:
  - If unset, provider defaults to `groq`.
  - `LLM_API_KEY` is required for hosted providers, not required for `ollama`.

## Run the App

- Bot:

```bash
python main.py
```

- OAuth server:

```bash
uvicorn oauth_server:app --reload
```

## Testing

Run tests:

```bash
pytest -q
```

If test collection fails with missing modules (e.g. `discord`), ensure your venv is active and dependencies are installed from `requirements.txt`.

For quick syntax checks on edited files:

```bash
python3 -m py_compile <file1.py> <file2.py>
```

## Code Standards

### 1) Configuration and Environment Variables

`settings.py` is the single source of truth for env-backed configuration.

- Do:
  - Add new env vars in `settings.py`
  - Read config from `settings.<VAR>` in all other modules
- Do not:
  - Call `os.getenv()` / `os.environ[...]` outside `settings.py`
  - Call `load_dotenv()` outside `settings.py`

This keeps config parsing/validation consistent and avoids startup-order bugs.

### 2) Logging

Use `utils.logger.log()` instead of `print()` for runtime logs.

### 3) Error Handling

- Catch specific exceptions where possible.
- Reserve broad `except Exception` for top-level boundaries where you convert to user-safe error messages.
- Include enough context in logs to debug failures.

### 4) Keep Modules Focused

Avoid adding more responsibilities to already large files (especially `bot/cogs/llm.py`, `bot/cogs/gcal.py`, and `tools/toolcalls/tool_registry.py`).

Prefer extracting helper modules/services when adding significant new logic.

## Feature Contribution Patterns

### Add a New Prefix Command

1. Implement handler in an appropriate cog under `bot/cogs/`.
2. Register with `bot.register_command("your command", self._handler)`.
3. Keep command parsing/validation in the cog, not in `bot/client.py`.
4. Add/extend tests under `tests/`.

### Add a New Tool

1. Implement function in `tools/toolcalls/`.
2. Add OpenAI-style tool definition dict.
3. Register in `tools/toolcalls/tool_registry.py`:
   - `TOOLS` mapping
   - `TOOL_DEFINITIONS` list
4. Add tests for normal path + failure path.
5. If user-visible behavior changes in LLM flow, update `utils/prompts.py` guidance as needed.

### Add Calendar Behavior

If touching Google Calendar behavior, make the change consistent across:

- Slash command path (`bot/cogs/gcal.py`)
- Tool-call path (`tools/toolcalls/tool_registry.py`)

When possible, extract shared logic instead of duplicating behavior.

## Security and Safety Notes

- Keep sandbox boundaries intact for code/terminal execution.
- Do not expose internal prompts/tool internals in user-facing responses.
- Preserve safety behavior for crisis and PR-sensitive handling.

## Issues and Feature Requests

Please use the GitHub **Issues** tab for bugs and feature requests.

### Reporting Bugs

- Apply the correct labels/tags.
- Use a clear, descriptive title.
- Include a detailed description.
- Bugs: include repro steps, expected vs actual behavior, and relevant logs/screenshots.

### Suggesting Features

- Features: include the use case and desired behavior.

## Pull Request Checklist

### Before Opening a PR

Before opening a PR:

1. Code builds and imports cleanly.
2. Tests pass locally (or explain why not).
3. New logic has tests or documented rationale for no tests.
4. No new direct env reads outside `settings.py`.
5. No debug prints left in runtime code.
6. README/docs updated if behavior or setup changed.

### Review Readiness

- Keep PR scope focused (avoid mixing unrelated refactors/features).
- Include a short summary of what changed and how it was verified.

## Commit Message Guidance

Use short imperative messages that describe the change clearly.

Examples:

- `centralize env config via settings for oauth and gcal`
- `add gcal reminder validation for negative values`
- `refactor llm tool-call notice redaction`
