"""Small helpers for reading Claude API responses.

Current Claude models think by default, so a response's first content block can be a
thinking block rather than the answer. Read text by block type, never by position.
"""

from __future__ import annotations

from typing import Any

_NON_TEXT = {"thinking", "redacted_thinking", "tool_use", "server_tool_use"}


def message_text(message: Any) -> str:
    """Concatenate the text blocks of a Messages API response."""
    parts: list[str] = []
    for block in getattr(message, "content", None) or []:
        if getattr(block, "type", None) in _NON_TEXT:
            continue
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)
