"""The support agent: one customer message in, an answer and its tool trajectory out.

A manual Claude tool-use loop (not the SDK tool runner) so every tool call can be
recorded as a step for Verdict's trajectory checks.

Configuration (environment):
    DEMO_AGENT_MODEL    default claude-opus-5-5
    DEMO_AGENT_EFFORT   default low (support chat does well at low effort)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from support_agent.tools import ROOT, ToolBox, load_data, load_tool_definitions

DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "low"
MAX_TURNS = 8


@dataclass
class AgentRun:
    answer: str
    steps: list[dict[str, Any]] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = DEFAULT_MODEL
    stop_reason: str | None = None
    error: str | None = None


def system_prompt(today: str | None = None) -> str:
    text = (ROOT / "prompts" / "system.md").read_text(encoding="utf-8")
    return text.replace("{today}", today or load_data()["today"])


def _text(content: list[Any]) -> str:
    """Text blocks only: thinking blocks can come first on current models."""
    return "".join(
        b.text for b in content if getattr(b, "type", None) == "text" and isinstance(b.text, str)
    )


def run_agent(
    message: str,
    *,
    client: Any = None,
    model: str | None = None,
    effort: str | None = None,
    toolbox: ToolBox | None = None,
) -> AgentRun:
    if client is None:
        import anthropic

        client = anthropic.Anthropic()
    model = model or os.environ.get("DEMO_AGENT_MODEL", DEFAULT_MODEL)
    effort = effort or os.environ.get("DEMO_AGENT_EFFORT", DEFAULT_EFFORT)
    toolbox = toolbox or ToolBox()
    tools = load_tool_definitions()
    system = system_prompt()

    run = AgentRun(answer="", model=model)
    messages: list[dict[str, Any]] = [{"role": "user", "content": message}]
    for _ in range(MAX_TURNS):
        response = client.messages.create(
            model=model,
            max_tokens=16000,
            system=system,
            tools=tools,
            messages=messages,
            output_config={"effort": effort},
        )
        run.input_tokens += response.usage.input_tokens
        run.output_tokens += response.usage.output_tokens
        run.stop_reason = response.stop_reason

        if response.stop_reason == "refusal":
            run.error = "model refused the request"
            return run

        tool_uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_uses:
            run.answer = _text(response.content)
            run.steps.append({"type": "final_answer", "output": run.answer})
            return run

        # Keep the whole assistant turn (thinking blocks included) in the history.
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in tool_uses:
            result, is_error = toolbox.call(block.name, dict(block.input))
            run.steps.append({
                "type": "tool_call",
                "tool": block.name,
                "arguments": dict(block.input),
                "result": result,
                "error": result if is_error else None,
            })
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
                **({"is_error": True} if is_error else {}),
            })
        messages.append({"role": "user", "content": results})

    run.error = f"no final answer after {MAX_TURNS} turns"
    return run
