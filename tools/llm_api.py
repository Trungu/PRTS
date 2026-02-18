# tools/llm_api.py — thin wrapper around an OpenAI-compatible chat completions API.
#
# Supports:
#   • Simple string input  → chat("Say hello")
#   • Structured history   → chat([{"role": "user", "content": "..."}, ...])
#
# Valid message roles:
#   "system"    — sets the model's behaviour / persona (prepended automatically
#                 when a system_prompt kwarg is supplied to the simple string form)
#   "user"      — a message from the human
#   "assistant" — a previous reply from the model (for multi-turn history)
#   "tool"      — the result returned by a tool call

from __future__ import annotations

import requests
from typing import Literal, TypedDict

import settings

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

Role = Literal["system", "user", "assistant", "tool"]


class Message(TypedDict):
    """A single turn in a conversation."""
    role: Role
    content: str


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
_DEFAULT_MODEL    = "llama3-8b-8192"

# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------

def chat(
    messages: str | list[Message],
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    timeout: int = 30,
) -> str:
    """Send a chat request to an OpenAI-compatible API and return the reply text.

    Parameters
    ----------
    messages:
        Either a plain string (treated as a single ``user`` message) or a list
        of ``Message`` dicts with ``role`` and ``content`` keys.  Valid roles:
        ``"system"``, ``"user"``, ``"assistant"``, ``"tool"``.
    system_prompt:
        Convenience shortcut — when *messages* is a plain string, this text is
        prepended as a ``system`` message.  Ignored when *messages* is already
        a list (include the system message in the list yourself instead).
    model:
        Model identifier to request.  Falls back to ``LLM_MODEL`` env var, then
        to the built-in default.
    temperature:
        Sampling temperature (0 = deterministic, 2 = very random).
    max_tokens:
        Upper limit on reply length in tokens.
    timeout:
        HTTP request timeout in seconds.

    Returns
    -------
    str
        The model's reply text, stripped of leading/trailing whitespace.

    Raises
    ------
    requests.HTTPError
        When the API returns a non-2xx status code.
    ValueError
        When the response JSON is missing expected fields.
    """
    # --- Build the message list ------------------------------------------------
    if isinstance(messages, str):
        payload_messages: list[Message] = []
        if system_prompt:
            payload_messages.append({"role": "system", "content": system_prompt})
        payload_messages.append({"role": "user", "content": messages})
    else:
        payload_messages = list(messages)

    # --- Resolve configuration ------------------------------------------------
    base_url   = (settings.LLM_BASE_URL or _DEFAULT_BASE_URL).rstrip("/")
    model_name = model or settings.LLM_MODEL or _DEFAULT_MODEL

    url = f"{base_url}/chat/completions"

    headers = {
        "Authorization": f"Bearer {settings.LLM_API_KEY}",
        "Content-Type":  "application/json",
    }

    body = {
        "model":       model_name,
        "messages":    payload_messages,
        "temperature": temperature,
        "max_tokens":  max_tokens,
    }

    # --- HTTP request ---------------------------------------------------------
    response = requests.post(url, headers=headers, json=body, timeout=timeout)
    response.raise_for_status()

    data = response.json()

    try:
        return data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise ValueError(f"Unexpected API response shape: {data}") from exc
