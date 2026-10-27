"""Verdict adapter for the support agent (`target: verdict_adapter.py:SupportAgent`).

Reports the agent's answer, every tool call as a trajectory step, token usage and an
estimated cost, so `verdict diff` can check tool use and compare cost between refs.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from verdict.adapters.base import TargetAdapter
from verdict.models.schemas import ExecutionResult
from verdict.models.trace_schemas import TraceStep

from support_agent.agent import DEFAULT_EFFORT, DEFAULT_MODEL, AgentRun, run_agent

# USD per 1M tokens, standard API rates. Only the models this demo is meant to run on.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}


def to_steps(run: AgentRun) -> list[TraceStep]:
    steps = []
    for i, s in enumerate(run.steps):
        if s["type"] == "tool_call":
            steps.append(TraceStep(step_id=i, step_type="tool_call", tool_name=s["tool"],
                                   tool_arguments=s["arguments"], tool_result=s["result"],
                                   error=s["error"]))
        else:
            steps.append(TraceStep(step_id=i, step_type="final_answer", llm_output=s["output"]))
    return steps


def cost_usd(run: AgentRun) -> float | None:
    price = PRICES.get(run.model)
    if price is None:
        return None
    return (run.input_tokens * price[0] + run.output_tokens * price[1]) / 1_000_000


class SupportAgent(TargetAdapter):
    def __init__(self, client: Any = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = client
        self._model = os.environ.get("DEMO_AGENT_MODEL", DEFAULT_MODEL)
        self._effort = os.environ.get("DEMO_AGENT_EFFORT", DEFAULT_EFFORT)

    @property
    def name(self) -> str:
        return "trailhead-support"

    @property
    def version(self) -> str:
        return f"{self._model}@{self._effort}"

    async def execute(self, prompt: str, prompt_id: str) -> ExecutionResult:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        run = await asyncio.to_thread(
            run_agent, prompt, client=self._client, model=self._model, effort=self._effort
        )
        result = self.make_result(
            prompt_id,
            run.answer,
            token_count=run.input_tokens + run.output_tokens,
            error=run.error,
            steps=to_steps(run),
        )
        result.token_usage = {
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "total_tokens": run.input_tokens + run.output_tokens,
        }
        result.estimated_cost_usd = cost_usd(run)
        result.model_used = run.model
        return result
