"""Deterministic EvalReport builder.

Design:
    All arithmetic in Verdict reports is computed here in plain Python.
    The LLM Reporter (reporter.py) receives pre-computed figures and writes
    only prose and tables — it never recalculates.

    This separation means every number in a markdown report is traceable to
    the raw EvalReport JSON, which is traceable to individual Judgment objects.
    This audit trail is required for any compliance review citing Verdict output.

Raises:
    ValueError: if judgments is empty (can't build a meaningful report).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from verdict.models.schemas import EvalReport, Judgment, TestPrompt


def build_eval_report(
    judgments: list[Judgment],
    prompts: list[TestPrompt],
    target_name: str,
    run_id: str,
    target_version: str | None = None,
    metadata: dict[str, Any] | None = None,
    bootstrap_iterations: int = 1000,
) -> EvalReport:
    """Compute a fully-populated EvalReport from raw judgments.

    All metrics are computed by this function.  No LLM is involved.

    Args:
        judgments:      All Judgment objects for this run.
        prompts:        All TestPrompt objects (used to enrich category_breakdown).
        target_name:          Name of the adapter/system under test.
        run_id:               Unique identifier for this run.
        target_version:       Optional version string from the adapter.
        metadata:             Optional arbitrary extra data for the run.
        bootstrap_iterations: Number of bootstrap resamples for CI (0 = disable).

    Returns:
        A fully-populated EvalReport Pydantic model.

    Raises:
        ValueError: If judgments is empty.
    """
    if not judgments:
        raise ValueError(
            "Cannot build EvalReport with zero judgments. "
            "Run the evaluation pipeline first."
        )

    # ------------------------------------------------------------------ #
    # Build prompt_id -> TestPrompt lookup                                #
    # ------------------------------------------------------------------ #
    prompt_map: dict[str, TestPrompt] = {p.id: p for p in prompts}

    # ------------------------------------------------------------------ #
    # Top-level metrics                                                    #
    # ------------------------------------------------------------------ #
    total = len(judgments)
    passed_count = sum(1 for j in judgments if j.passed)
    pass_rate = passed_count / total

    # ------------------------------------------------------------------ #
    # Per-category breakdown                                              #
    # ------------------------------------------------------------------ #
    # Group judgments by category (via prompt_map)
    by_category: dict[str, list[Judgment]] = defaultdict(list)
    for j in judgments:
        p = prompt_map.get(j.prompt_id)
        category = p.category if p else "unknown"
        by_category[category].append(j)

    category_breakdown: dict[str, dict[str, Any]] = {}
    for cat, cat_judgments in by_category.items():
        cat_total = len(cat_judgments)
        cat_passed = sum(1 for j in cat_judgments if j.passed)
        cat_pass_rate = cat_passed / cat_total if cat_total > 0 else 0.0

        # Failure mode frequency
        failure_modes: dict[str, int] = defaultdict(int)
        for j in cat_judgments:
            if j.failure_mode is not None:
                failure_modes[j.failure_mode.value] += 1

        # Average score (for graded categories)
        scores = [j.score for j in cat_judgments if j.score is not None]
        avg_score = sum(scores) / len(scores) if scores else None

        # Critical failures (severity=critical prompts that failed)
        critical_failures = []
        for j in cat_judgments:
            p = prompt_map.get(j.prompt_id)
            if p and p.severity == "critical" and not j.passed:
                critical_failures.append(j.prompt_id)

        category_breakdown[cat] = {
            "total": cat_total,
            "passed": cat_passed,
            "failed": cat_total - cat_passed,
            "pass_rate": round(cat_pass_rate, 4),
            "avg_score": round(avg_score, 2) if avg_score is not None else None,
            "failure_modes": dict(failure_modes),
            "critical_failures": critical_failures,
        }

    # ------------------------------------------------------------------ #
    # Bootstrap CI (v0.2.0)                                               #
    # ------------------------------------------------------------------ #
    ci_low: float | None = None
    ci_high: float | None = None
    if bootstrap_iterations > 0:
        from verdict.stats.bootstrap import bootstrap_pass_rate_ci
        ci_low, ci_high = bootstrap_pass_rate_ci(judgments, n_iterations=bootstrap_iterations)

    # ------------------------------------------------------------------ #
    # Total latency (v0.2.0)                                              #
    # ------------------------------------------------------------------ #
    # Judgments don't carry latency; caller can set total_latency_ms post-build.
    # We set it here only when building from a source that provides it via metadata.
    total_latency_ms: float | None = None
    if metadata and "execution_results" in metadata:
        # Convenience: if caller passed raw execution_results in metadata,
        # compute latency here and remove from metadata to keep report clean.
        exec_results = metadata.pop("execution_results", [])
        total_latency_ms = sum(r.latency_ms for r in exec_results)

    # ------------------------------------------------------------------ #
    # Assemble report                                                      #
    # ------------------------------------------------------------------ #
    return EvalReport(
        run_id=run_id,
        target_system=target_name,
        target_version=target_version,
        total_tests=total,
        pass_rate=round(pass_rate, 4),
        pass_rate_ci_low=ci_low,
        pass_rate_ci_high=ci_high,
        bootstrap_iterations=bootstrap_iterations if bootstrap_iterations > 0 else None,
        category_breakdown=category_breakdown,
        judgments=judgments,
        total_latency_ms=total_latency_ms,
        metadata=metadata or {},
    )
