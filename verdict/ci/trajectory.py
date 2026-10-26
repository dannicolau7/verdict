"""`verdict trajectory`: deterministic trajectory checks over recorded AgentTraces.

Runs verdict.evals.trajectory.check_trajectory on each trace, against the trace's own
`expected_trajectory` when it has one, and aggregates pass rate, step counts, tool
recall/precision and finding counts. No LLM calls.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from verdict.ci.diff import _verdict_version
from verdict.evals.trajectory import TrajectoryResult, check_trajectory
from verdict.models.trace_schemas import AgentTrace


class TraceTrajectory(BaseModel):
    trace_id: str
    task: str
    has_expectation: bool
    result: TrajectoryResult


class TrajectoryReport(BaseModel):
    agent_name: str
    n_traces: int
    n_passed: int
    pass_rate: float
    mean_steps: float
    mean_tool_calls: float
    mean_tool_recall: float | None = None
    mean_tool_precision: float | None = None
    finding_counts: dict[str, int] = Field(default_factory=dict)
    traces: list[TraceTrajectory]
    min_pass_rate: float
    passed: bool
    verdict_version: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


def _mean(xs: list[float]) -> float | None:
    return sum(xs) / len(xs) if xs else None


def evaluate_traces(traces: list[AgentTrace], min_pass_rate: float = 1.0) -> TrajectoryReport:
    items = [
        TraceTrajectory(
            trace_id=t.trace_id,
            task=t.task,
            has_expectation=t.expected_trajectory is not None,
            result=check_trajectory(
                t.steps,
                t.final_output,
                t.expected_trajectory,
                tools_available=t.tools_available,
                agent_error=t.error,
            ),
        )
        for t in traces
    ]
    n = len(items)
    n_passed = sum(1 for i in items if i.result.passed)
    rate = n_passed / n if n else 0.0
    return TrajectoryReport(
        agent_name=traces[0].agent_name if traces else "unknown",
        n_traces=n,
        n_passed=n_passed,
        pass_rate=rate,
        mean_steps=_mean([i.result.n_steps for i in items]) or 0.0,
        mean_tool_calls=_mean([i.result.n_tool_calls for i in items]) or 0.0,
        mean_tool_recall=_mean([i.result.tool_recall for i in items if i.result.tool_recall is not None]),
        mean_tool_precision=_mean(
            [i.result.tool_precision for i in items if i.result.tool_precision is not None]
        ),
        finding_counts=dict(Counter(f.check for i in items for f in i.result.findings).most_common()),
        traces=items,
        min_pass_rate=min_pass_rate,
        passed=bool(n) and rate >= min_pass_rate,
        verdict_version=_verdict_version(),
    )
