"""Token usage tracker for attributing LLM costs between harness and target.

TokenTracker is passed through the eval pipeline so each agent can record
its token usage.  At the end of a run, get_summary() returns per-source
totals that feed into EvalReport.cost_breakdown.

Thread safety:
    Uses threading.Lock so the tracker is safe to use from multiple threads
    (e.g., concurrent judge calls).

Sources:
    "generator" — Test Generator agent
    "executor"  — Executor agent (usually 0 unless it makes LLM calls)
    "judge"     — Judge agent
    "reporter"  — Reporter agent
    "target"    — The system being evaluated (populated from ExecutionResult.token_usage)
"""

from __future__ import annotations

import threading
from collections import defaultdict


class TokenTracker:
    """Accumulates token counts split by source and model."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # {source: {model: {"input_tokens": int, "output_tokens": int}}}
        self._counts: dict[str, dict[str, dict[str, int]]] = defaultdict(
            lambda: defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0})
        )

    def record_call(
        self,
        source: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record token usage for one LLM call.

        Args:
            source:        One of 'generator', 'executor', 'judge', 'reporter', 'target'.
            model:         Model identifier string.
            input_tokens:  Number of input (prompt) tokens.
            output_tokens: Number of output (completion) tokens.
        """
        with self._lock:
            bucket = self._counts[source][model]
            bucket["input_tokens"] += input_tokens
            bucket["output_tokens"] += output_tokens

    def record_from_usage(
        self,
        source: str,
        model: str,
        usage: dict[str, int] | None,
    ) -> None:
        """Convenience wrapper that accepts a token_usage dict (or None).

        Does nothing if usage is None or missing expected keys.
        """
        if not usage:
            return
        self.record_call(
            source=source,
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
        )

    def get_summary(self) -> dict:
        """Return per-source, per-model token totals.

        Shape:
            {
              "generator": {
                "claude-sonnet-4-6": {"input_tokens": N, "output_tokens": N}
              },
              ...
              "_totals": {
                "generator": {"input_tokens": N, "output_tokens": N},
                ...
              }
            }
        """
        with self._lock:
            result: dict = {}
            totals: dict[str, dict[str, int]] = {}

            for source, models in self._counts.items():
                result[source] = {}
                src_in, src_out = 0, 0
                for model, counts in models.items():
                    result[source][model] = dict(counts)
                    src_in += counts["input_tokens"]
                    src_out += counts["output_tokens"]
                totals[source] = {"input_tokens": src_in, "output_tokens": src_out}

            result["_totals"] = totals
            return result

    def get_flat_counts(self) -> dict[str, dict[str, int]]:
        """Return total counts per source (no per-model breakdown).

        Suitable for passing as harness_token_counts to compute_run_costs().
        """
        summary = self.get_summary()
        return summary.get("_totals", {})

    def reset(self) -> None:
        """Clear all accumulated counts (useful between runs in tests)."""
        with self._lock:
            self._counts.clear()

    def absorb_execution_results(
        self,
        results: list,  # list[ExecutionResult]
    ) -> None:
        """Record target token usage from a list of ExecutionResult objects."""
        for r in results:
            if r.token_usage and r.model_used:
                self.record_from_usage("target", r.model_used, r.token_usage)
