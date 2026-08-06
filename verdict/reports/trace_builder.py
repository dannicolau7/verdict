"""Deterministic TraceEvalReport builder.

All arithmetic is computed here. No LLM involved. Mirrors reports/builder.py.
"""

from __future__ import annotations

import random
import uuid
from collections import defaultdict
from typing import Any

from verdict.models.trace_schemas import TraceEvalReport, TraceJudgment


def _bootstrap_ci(
    flags: list[int],
    n_iterations: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    """Bootstrap 95% CI for a pass rate from binary flags."""
    if not flags:
        return (0.0, 0.0)
    n = len(flags)
    rate = sum(flags) / n
    if n <= 1 or rate in (0.0, 1.0):
        return (rate, rate)
    rng = random.Random(seed)
    boot = sorted(sum(rng.choices(flags, k=n)) / n for _ in range(n_iterations))
    lo = boot[max(0, int(0.025 * n_iterations))]
    hi = boot[min(int(0.975 * n_iterations), n_iterations - 1)]
    return (round(lo, 4), round(hi, 4))


def build_trace_eval_report(
    judgments: list[TraceJudgment],
    agent_name: str,
    run_id: str | None = None,
    bootstrap_iterations: int = 1000,
    metadata: dict[str, Any] | None = None,
) -> TraceEvalReport:
    """Compute a fully-populated TraceEvalReport from raw TraceJudgments.

    Args:
        judgments:            All TraceJudgment objects for this run.
        agent_name:           Name of the agent under evaluation.
        run_id:               Unique identifier for this run (auto-generated if None).
        bootstrap_iterations: Bootstrap resamples for CI (0 = disable).
        metadata:             Optional extra data for the run.

    Returns:
        A fully-populated TraceEvalReport.
    """
    if run_id is None:
        run_id = str(uuid.uuid4())

    total = len(judgments)
    if total == 0:
        return TraceEvalReport(
            run_id=run_id,
            agent_name=agent_name,
            total_traces=0,
            pass_rate=0.0,
            trace_judgments=[],
            failure_mode_counts={},
            metadata=metadata or {},
        )

    passed_count = sum(1 for j in judgments if j.overall_passed)
    pass_rate = round(passed_count / total, 4)

    # Failure mode frequency (across all traces)
    fm_counts: dict[str, int] = defaultdict(int)
    for j in judgments:
        for fm in j.failure_modes:
            fm_counts[fm.value] += 1

    # Bootstrap CI
    ci_low: float | None = None
    ci_high: float | None = None
    if bootstrap_iterations > 0:
        flags = [1 if j.overall_passed else 0 for j in judgments]
        ci_low, ci_high = _bootstrap_ci(flags, n_iterations=bootstrap_iterations)

    try:
        from importlib.metadata import version
        verdict_ver: str | None = version("verdict-eval")
    except Exception:
        verdict_ver = None

    return TraceEvalReport(
        run_id=run_id,
        agent_name=agent_name,
        total_traces=total,
        pass_rate=pass_rate,
        trace_judgments=judgments,
        failure_mode_counts=dict(fm_counts),
        pass_rate_ci_low=ci_low,
        pass_rate_ci_high=ci_high,
        bootstrap_iterations=bootstrap_iterations if bootstrap_iterations > 0 else None,
        metadata=metadata or {},
        verdict_version=verdict_ver,
    )


def build_trace_eval_markdown(report: TraceEvalReport) -> str:
    """Render a TraceEvalReport as a human-readable markdown document."""
    lines: list[str] = []
    lines.append(f"# Trace Eval Report — {report.agent_name}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Run ID | `{report.run_id}` |")
    lines.append(f"| Agent | {report.agent_name} |")
    lines.append(f"| Total Traces | {report.total_traces} |")
    ci_str = ""
    if report.pass_rate_ci_low is not None:
        ci_str = f" (95% CI: {report.pass_rate_ci_low:.1%}–{report.pass_rate_ci_high:.1%})"
    lines.append(f"| Pass Rate | {report.pass_rate:.1%}{ci_str} |")
    lines.append(f"| Timestamp | {report.timestamp.isoformat()} |")
    if report.verdict_version:
        lines.append(f"| Verdict Version | {report.verdict_version} |")
    lines.append("")

    if report.failure_mode_counts:
        lines.append("## Failure Mode Breakdown")
        lines.append("")
        lines.append("| Failure Mode | Count |")
        lines.append("|--------------|-------|")
        for fm, count in sorted(report.failure_mode_counts.items(), key=lambda x: -x[1]):
            lines.append(f"| {fm} | {count} |")
        lines.append("")

    lines.append("## Per-Trace Results")
    lines.append("")
    lines.append("| Trace ID | Passed | Score | Failure Modes |")
    lines.append("|----------|--------|-------|---------------|")
    for j in report.trace_judgments:
        status = "✅" if j.overall_passed else "❌"
        score_str = str(j.overall_score) if j.overall_score is not None else "—"
        fms = ", ".join(fm.value for fm in j.failure_modes) or "—"
        lines.append(f"| `{j.trace_id[:8]}…` | {status} | {score_str} | {fms} |")
    lines.append("")

    lines.append("## Trace Reasoning")
    lines.append("")
    for j in report.trace_judgments:
        status = "PASS" if j.overall_passed else "FAIL"
        lines.append(f"### `{j.trace_id[:16]}…` — {status}")
        lines.append("")
        lines.append(j.reasoning)
        if j.step_judgments:
            lines.append("")
            lines.append("**Step judgments:**")
            for sj in j.step_judgments:
                sj_status = "✅" if sj.passed else "❌"
                fm_part = f" ({sj.failure_mode})" if sj.failure_mode else ""
                lines.append(f"- Step {sj.step_id} {sj_status}{fm_part}: {sj.reasoning}")
        lines.append("")

    return "\n".join(lines)
