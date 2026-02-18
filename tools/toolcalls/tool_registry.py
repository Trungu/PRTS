# tools/toolcalls/tool_registry.py — single source of truth for all agent tools.
#
# HOW TO ADD A NEW TOOL
# ---------------------
# 1. Create a file in tools/toolcalls/  (e.g. tools/toolcalls/web_search.py)
# 2. Define a callable with the tool's logic.
# 3. Define a TOOL_DEFINITION dict in that file (OpenAI function-calling format).
# 4. Import both here and add an entry to TOOLS and TOOL_DEFINITIONS below.
#
# The agentic loop in llm_api.py reads TOOL_DEFINITIONS and TOOLS automatically.

from __future__ import annotations

from tools.toolcalls.calculator import calculator, TOOL_DEFINITION as _CALC_DEF

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Maps tool name → callable(arguments_dict) → str
TOOLS: dict[str, callable] = {
    "calculator": lambda args: calculator(args["expression"]),
}

# List of OpenAI-style tool definitions sent with every API request.
TOOL_DEFINITIONS: list[dict] = [
    _CALC_DEF,
]
