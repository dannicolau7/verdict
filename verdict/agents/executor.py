"""Executor agent for the Verdict evaluation framework.

Design decision — the Executor is NOT LLM-bound:
    The three other agents (Generator, Judge, Reporter) use LLMs as their
    primary mechanism.  The Executor's job is orchestration: set up the
    adapter, run prompts concurrently, tear down cleanly.

    create_executor() returns a CrewAI Agent for D9 crew composition, but
    the actual work lives in the plain async function execute_test_suite().
    No LLM call happens inside execute_test_suite(); it delegates entirely
    to the TargetAdapter.

    This split keeps execution deterministic and reproducible — the same
    TestPrompt against the same adapter produces the same ExecutionResult
    (modulo latency).
"""

from __future__ import annotations

from verdict.adapters.base import TargetAdapter
from verdict.models.schemas import ExecutionResult, TestPrompt


# ---------------------------------------------------------------------------
# CrewAI Agent factory (used in D9 crew assembly)
# ---------------------------------------------------------------------------


def create_executor(model: str | None = None):  # -> crewai.Agent
    """Return a configured CrewAI Agent for the Executor role.

    Uses Haiku (cheapest/fastest model) at temperature 0.0 since no
    generative reasoning is required — just orchestration.

    Args:
        model: Anthropic model ID override.  Defaults to
               settings.default_executor_model (Haiku).
    """
    from crewai import Agent
    from langchain_anthropic import ChatAnthropic

    from verdict.config.settings import get_settings

    settings = get_settings()
    llm = ChatAnthropic(
        model=model or settings.default_executor_model,
        temperature=0.0,
        anthropic_api_key=settings.anthropic_api_key.get_secret_value(),
    )
    return Agent(
        role="Test Execution Coordinator",
        goal=(
            "Run test prompts against the target system with full fidelity, "
            "capturing every response and error without modifying prompts."
        ),
        backstory=(
            "You are a meticulous QA automation engineer.  Your only job is to "
            "faithfully relay each test prompt to the target system and record "
            "the raw response.  You never summarise, paraphrase, or modify prompts."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=2,
        max_rpm=20,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def execute_test_suite(
    prompts: list[TestPrompt],
    adapter: TargetAdapter,
) -> list[ExecutionResult]:
    """Execute a list of test prompts against a target adapter.

    This is NOT an LLM operation.  The CrewAI Agent wrapper (create_executor)
    exists so all four agents compose uniformly in D9's Crew, but the real
    work here is plain async Python: setup → batch execute → teardown.

    Order is preserved: results[i] corresponds to prompts[i].

    Args:
        prompts: Test prompts to execute.
        adapter: Any TargetAdapter implementation.

    Returns:
        list[ExecutionResult] in the same order as prompts.
        Errors from the adapter are captured in ExecutionResult.error —
        this function never raises.
    """
    await adapter.setup()
    try:
        results = await adapter.execute_batch(prompts)
    finally:
        await adapter.teardown()
    return results
