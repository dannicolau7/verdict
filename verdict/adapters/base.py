"""Pluggable adapter pattern for Verdict.

Design decision — Pattern A (execute returns ExecutionResult):
    Adapter authors implement ``execute()`` and return a full ``ExecutionResult``.
    The base class provides ``make_result()`` as a convenience factory so authors
    don't have to import or construct ExecutionResult directly.

    Rationale for Pattern A over Pattern B (execute returns str):
    - Adapters that can report token counts (e.g., direct Anthropic SDK callers)
      can populate ``token_count`` without needing extra out-of-band channels.
    - Adapters that need to populate custom metadata fields retain that ability.
    - The tradeoff is a tiny bit more boilerplate, fully offset by ``make_result()``.

    The base class still handles all of:
    - Automatic latency measurement via time.perf_counter()
    - Per-call timeout enforcement via asyncio.wait_for()
    - Exception capture (any exception → ExecutionResult.error, never a crash)
    - Concurrency limiting via asyncio.Semaphore from settings

Usage:
    class MyChatbotAdapter(TargetAdapter):
        @property
        def name(self) -> str:
            return "MyChatbot"

        @property
        def version(self) -> str:
            return "1.2.3"

        async def execute(self, prompt: str, prompt_id: str) -> ExecutionResult:
            response = await my_chatbot.send(prompt)
            return self.make_result(prompt_id, response.text, token_count=response.tokens)

    adapter = MyChatbotAdapter()
    await adapter.setup()
    results = await adapter.execute_batch(test_prompts)
    await adapter.teardown()
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from verdict.caching.backends import CacheBackend, FileSystemCacheBackend
from verdict.caching.cache import CacheMissError, CacheMode, compute_cache_key
from verdict.config.settings import get_settings
from verdict.models.schemas import ExecutionResult, TestPrompt

logger = logging.getLogger(__name__)


class TargetAdapter(ABC):
    """Abstract base class for any system Verdict can evaluate.

    To create an adapter for your AI system, subclass ``TargetAdapter`` and
    implement ``name``, ``version``, and ``execute()``. Optionally override
    ``setup()`` and ``teardown()`` for resource management.

    The base class handles concurrency limiting, per-call timing, timeout
    enforcement, exception capture, and optional response caching.

    Caching (v0.2.0):
        Pass cache_mode and optionally cache_dir to __init__ to enable caching.
        OFF (default) preserves v0.1.0 behavior exactly.

    Example:
        class MyChatbotAdapter(TargetAdapter):
            @property
            def name(self) -> str:
                return "MyChatbot"

            @property
            def version(self) -> str:
                return "1.2.3"

            async def execute(self, prompt: str, prompt_id: str) -> ExecutionResult:
                response = await my_chatbot.send(prompt)
                return self.make_result(prompt_id, response.text, token_count=response.tokens)
    """

    def __init__(
        self,
        *,
        cache_mode: CacheMode = CacheMode.OFF,
        cache_dir: str | None = None,
        _cache: CacheBackend | None = None,
    ) -> None:
        """Initialise adapter with optional caching configuration.

        Args:
            cache_mode: OFF (default) = no caching; RECORD = cache on miss;
                        REPLAY = cache-only (raises on miss); UPDATE = always overwrite.
            cache_dir:  Directory for the filesystem cache (default: .verdict_cache/).
                        Ignored when cache_mode is OFF.
            _cache:     Inject a custom CacheBackend (used in tests).
        """
        self._cache_mode = cache_mode
        self._cache: CacheBackend | None

        if _cache is not None:
            self._cache = _cache
        elif cache_mode != CacheMode.OFF:
            import os
            dir_path = cache_dir or os.environ.get("VERDICT_CACHE_DIR", ".verdict_cache")
            self._cache = FileSystemCacheBackend(cache_dir=dir_path, adapter_name=self.name)  # type: ignore[arg-type]
        else:
            self._cache = None

    # ------------------------------------------------------------------ #
    # Abstract interface — subclasses must implement these                 #
    # ------------------------------------------------------------------ #

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of the target system (e.g. 'MyChatbot')."""

    @property
    @abstractmethod
    def version(self) -> str:
        """Version string of the target system (e.g. '1.2.3')."""

    @abstractmethod
    async def execute(self, prompt: str, prompt_id: str) -> ExecutionResult:
        """Run a single prompt against the target system.

        Args:
            prompt:    The prompt text to send to the target system.
            prompt_id: The ID of the originating TestPrompt (for correlation).

        Returns:
            An ExecutionResult. Use ``self.make_result()`` for convenience.

        Note:
            Do NOT measure timing or catch exceptions here — the base class
            wraps this call in ``_safe_execute()`` which handles both.
        """

    # ------------------------------------------------------------------ #
    # Lifecycle hooks — default no-ops, override as needed                 #
    # ------------------------------------------------------------------ #

    async def setup(self) -> None:
        """Load resources, open connections, warm up the target system.

        Called once before ``execute_batch()``. Default implementation does nothing.
        """

    async def teardown(self) -> None:
        """Release resources and close connections.

        Called once after ``execute_batch()`` completes (including on error).
        Default implementation does nothing.
        """

    # ------------------------------------------------------------------ #
    # Batch execution — provided, not abstract                             #
    # ------------------------------------------------------------------ #

    async def execute_batch(self, prompts: list[TestPrompt]) -> list[ExecutionResult]:
        """Execute a list of TestPrompts concurrently against the target system.

        Concurrency is bounded by ``settings.max_concurrent_executions``.
        Results are returned in the same order as the input ``prompts`` list.
        All errors are captured inside the returned ExecutionResult objects —
        this method never raises.

        Args:
            prompts: List of TestPrompt objects to execute.

        Returns:
            List of ExecutionResult objects in the same order as ``prompts``.
        """
        settings = get_settings()
        semaphore = asyncio.Semaphore(settings.max_concurrent_executions)

        async def bounded(prompt: TestPrompt) -> ExecutionResult:
            async with semaphore:
                return await self._safe_execute(prompt)

        return list(await asyncio.gather(*[bounded(p) for p in prompts]))

    # ------------------------------------------------------------------ #
    # Internal helper                                                       #
    # ------------------------------------------------------------------ #

    @property
    def cache_stats(self) -> dict[str, int]:
        """Return cumulative cache stats, or zeros if caching is disabled."""
        if self._cache is not None:
            return self._cache.stats()
        return {"hits": 0, "misses": 0, "writes": 0}

    async def _safe_execute(self, prompt: TestPrompt) -> ExecutionResult:
        """Wrap execute() with caching, timing, timeout, and error capture.

        Adapter authors should never call this directly.  It is invoked by
        ``execute_batch()`` for every prompt.

        Cache behavior (v0.2.0):
          OFF:    bypass cache entirely (v0.1.0 behavior).
          RECORD: serve from cache on hit; execute + save on miss.
          REPLAY: serve from cache only; raise CacheMissError on miss.
          UPDATE: always execute + overwrite cache.

        Args:
            prompt: The TestPrompt to execute.

        Returns:
            ExecutionResult — always, never raises (except REPLAY mode miss).
        """
        settings = get_settings()

        # ---------------------------------------------------------------- #
        # Cache REPLAY / RECORD hit path                                    #
        # ---------------------------------------------------------------- #
        if self._cache is not None and self._cache_mode != CacheMode.OFF:
            key = compute_cache_key(self.name, self.version, prompt.prompt, prompt.id)

            if self._cache_mode == CacheMode.REPLAY:
                cached = self._cache.get(key)
                if cached is not None:
                    logger.debug("Cache HIT (REPLAY): %s", key[:16])
                    return cached
                raise CacheMissError(
                    f"REPLAY mode: no cache entry for prompt_id={prompt.id} "
                    f"(adapter={self.name}, key={key[:16]}…). "
                    "Run with --cache-mode record first."
                )

            if self._cache_mode == CacheMode.RECORD:
                cached = self._cache.get(key)
                if cached is not None:
                    logger.debug("Cache HIT (RECORD): %s", key[:16])
                    return cached

        # ---------------------------------------------------------------- #
        # Execute (live API call)                                           #
        # ---------------------------------------------------------------- #
        start = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                self.execute(prompt.prompt, prompt.id),
                timeout=settings.default_timeout_seconds,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            if result.latency_ms == 0.0:
                result.latency_ms = elapsed_ms
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            result = ExecutionResult(
                prompt_id=prompt.id,
                response="",
                latency_ms=elapsed_ms,
                error=f"{type(exc).__name__}: {exc}",
            )

        # ---------------------------------------------------------------- #
        # Cache RECORD / UPDATE write path                                  #
        # ---------------------------------------------------------------- #
        if (
            self._cache is not None
            and self._cache_mode in (CacheMode.RECORD, CacheMode.UPDATE)
            and result.error is None  # don't cache error responses
        ):
            key = compute_cache_key(self.name, self.version, prompt.prompt, prompt.id)
            self._cache.set(key, result)
            logger.debug("Cache WRITE (%s): %s", self._cache_mode.value, key[:16])

        return result

    # ------------------------------------------------------------------ #
    # Convenience factory                                                   #
    # ------------------------------------------------------------------ #

    def make_result(
        self,
        prompt_id: str,
        response: str,
        *,
        latency_ms: float = 0.0,
        token_count: int | None = None,
        error: str | None = None,
        **extra: Any,
    ) -> ExecutionResult:
        """Construct an ExecutionResult with sensible defaults.

        Adapter authors use this inside ``execute()`` to avoid importing or
        constructing ExecutionResult directly.

        Pass ``latency_ms=0.0`` (the default) when you don't have a precise
        measurement — ``_safe_execute()`` will overwrite it with the true
        wall-clock measurement automatically.

        Args:
            prompt_id:   ID of the originating TestPrompt.
            response:    Verbatim response text from the target system.
            latency_ms:  Optional latency override in ms (default 0.0 → auto).
            token_count: Total tokens consumed, if available.
            error:       Error message string, if the call failed.
            **extra:     Ignored (future-proofing; ExecutionResult uses extra="forbid").

        Returns:
            A fully constructed ExecutionResult.
        """
        return ExecutionResult(
            prompt_id=prompt_id,
            response=response,
            latency_ms=latency_ms,
            token_count=token_count,
            error=error,
        )
