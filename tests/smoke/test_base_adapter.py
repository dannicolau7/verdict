"""Smoke tests for TargetAdapter base class."""

import asyncio
import os

import pytest

os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-smoke-test")

from verdict.adapters.base import TargetAdapter  # noqa: E402
from verdict.models.schemas import ExecutionResult, TestPrompt  # noqa: E402


def _make_prompt(text: str = "Hello") -> TestPrompt:
    return TestPrompt(
        prompt=text,
        category="correctness",
        severity="low",
        expected_behavior="Any response.",
    )


# ---------------------------------------------------------------------------
# Echo adapter — echoes the prompt back as the response
# ---------------------------------------------------------------------------


class EchoAdapter(TargetAdapter):
    @property
    def name(self) -> str:
        return "EchoAdapter"

    @property
    def version(self) -> str:
        return "0.0.1"

    async def execute(self, prompt: str, prompt_id: str) -> ExecutionResult:
        return self.make_result(prompt_id, response=f"ECHO: {prompt}")


# ---------------------------------------------------------------------------
# Failing adapter — always raises ValueError
# ---------------------------------------------------------------------------


class FailingAdapter(TargetAdapter):
    @property
    def name(self) -> str:
        return "FailingAdapter"

    @property
    def version(self) -> str:
        return "0.0.1"

    async def execute(self, prompt: str, prompt_id: str) -> ExecutionResult:
        raise ValueError("intentional failure for testing")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_echo_adapter_batch() -> None:
    prompts = [_make_prompt(f"prompt {i}") for i in range(3)]
    adapter = EchoAdapter()
    results = asyncio.run(adapter.execute_batch(prompts))

    assert len(results) == 3
    for i, (result, prompt) in enumerate(zip(results, prompts)):
        assert result.prompt_id == prompt.id, f"result[{i}] prompt_id mismatch"
        assert result.error is None, f"result[{i}] has unexpected error: {result.error}"
        assert result.latency_ms > 0, f"result[{i}] latency_ms should be > 0"
        assert result.response == f"ECHO: prompt {i}"


def test_failing_adapter_batch_no_crash() -> None:
    prompts = [_make_prompt(f"prompt {i}") for i in range(3)]
    adapter = FailingAdapter()
    results = asyncio.run(adapter.execute_batch(prompts))

    assert len(results) == 3
    for i, result in enumerate(results):
        assert result.error is not None, f"result[{i}] should have an error"
        assert "ValueError" in result.error, f"result[{i}] error should name the exception"
        assert "intentional failure" in result.error
        assert result.response == ""
        assert result.latency_ms >= 0


def test_echo_adapter_result_ordering() -> None:
    """Results must come back in the same order as the input prompts."""
    prompts = [_make_prompt(str(i)) for i in range(10)]
    adapter = EchoAdapter()
    results = asyncio.run(adapter.execute_batch(prompts))

    for prompt, result in zip(prompts, results):
        assert result.prompt_id == prompt.id


def test_make_result_defaults() -> None:
    adapter = EchoAdapter()
    result = adapter.make_result("pid-1", "hello")
    assert result.prompt_id == "pid-1"
    assert result.response == "hello"
    assert result.latency_ms == 0.0
    assert result.token_count is None
    assert result.error is None
