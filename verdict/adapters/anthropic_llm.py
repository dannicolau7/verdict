"""AnthropicLLMAdapter — evaluate a Claude model directly as the system under test.

Uses the Anthropic Messages API to send each test prompt as a bare user message
and return the assistant text.  Intended for red-teaming / benchmarking Claude
models themselves (injection resistance, compliance, etc.).

Usage (CLI)::

    verdict eval --target anthropic_llm --categories injection compliance \\
                 --num-per-category 5 --judge-model claude-haiku-4-5-20251001

Usage (Python)::

    from verdict.adapters.anthropic_llm import AnthropicLLMAdapter
    from verdict.agents.executor import execute_test_suite

    adapter = AnthropicLLMAdapter(model="claude-haiku-4-5-20251001")
    results = await execute_test_suite(prompts, adapter)
"""

from __future__ import annotations

import anthropic

from verdict.adapters.base import TargetAdapter
from verdict.config.settings import get_settings
from verdict.models.schemas import ExecutionResult


class AnthropicLLMAdapter(TargetAdapter):
    """Sends each test prompt to a Claude model and returns the text response.

    Args:
        model:       Claude model ID (default: settings.default_executor_model).
        max_tokens:  Max tokens in the response (default: 1024).
        system:      Optional system prompt to prepend (default: none).
        **kwargs:    Passed to TargetAdapter (cache_mode, cache_dir, etc.).
    """

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int = 1024,
        system: str | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        settings = get_settings()
        self._model = model or settings.default_executor_model
        self._max_tokens = max_tokens
        self._system = system
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )

    @property
    def name(self) -> str:
        return "AnthropicLLM"

    @property
    def version(self) -> str:
        return self._model

    async def execute(self, prompt: str, prompt_id: str) -> ExecutionResult:
        msg_kwargs: dict = dict(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        if self._system:
            msg_kwargs["system"] = self._system

        import asyncio
        response = await asyncio.to_thread(self._client.messages.create, **msg_kwargs)
        text: str = response.content[0].text  # type: ignore[index]
        tokens = (response.usage.input_tokens + response.usage.output_tokens
                  if response.usage else None)
        return self.make_result(prompt_id, text, token_count=tokens)
