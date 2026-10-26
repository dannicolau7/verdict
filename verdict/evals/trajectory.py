"""Deterministic trajectory checks: did the agent use its tools the right way?

check_trajectory() scores an agent's steps against an optional TrajectoryExpectation
and always runs degradation checks that need no expectation:

    Expectation checks (error when violated)
        tool_sequence    expected tools vs actual, by `match` (exact / in_order / unordered)
        forbidden_tool   a tool in forbidden_tools was called
        tool_args        no call of a tool had the expected arguments
        max_tool_calls / max_steps   too many calls or steps
        output_contains  final output lacks required text

    Degradation checks (always on)
        agent_error      the agent crashed                                   (error)
        empty_output     no final output                                     (error)
        unknown_tool     tool not in tools_available                         (error)
        error_swallowed  a tool failed and the final answer never says so    (error)
        empty_result     a tool returned nothing and the answer didn't say so (warning)
        repeated_call    same tool + arguments called 3+ times               (warning)

No LLM calls; cheap enough to run on every case of every run.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from verdict.models.trace_schemas import (
    TraceFailureMode,
    TraceStep,
    TrajectoryExpectation,
)

# A tool result that is itself an error. Conservative on purpose: words like "error"
# inside ordinary text don't count, only results that *are* errors.
_ERROR_RESULT = re.compile(
    r'^\s*(error|exception|traceback)\b|"error"\s*:|\bHTTP\s*[45]\d\d\b'
    r'|\bstatus(?:_code)?["\s:=]+[45]\d\d\b',
    re.IGNORECASE,
)
# Phrases showing the final answer admits a problem.
_ACKNOWLEDGES = re.compile(
    r"\b(sorry|unable|couldn'?t|could not|can'?t|cannot|error|failed|failure|unavailable|"
    r"try again|problem|issue|no results?|not find|didn'?t find|nothing (?:was )?found)\b",
    re.IGNORECASE,
)
_EMPTY_RESULTS = {"", "[]", "{}", "null", "none", '""'}
_REPEAT_LIMIT = 3


class TrajectoryFinding(BaseModel):
    check: str
    severity: Literal["error", "warning"]
    detail: str
    step_id: int | None = None
    failure_mode: TraceFailureMode | None = None


class TrajectoryResult(BaseModel):
    passed: bool = Field(description="No error-severity findings.")
    findings: list[TrajectoryFinding] = Field(default_factory=list)
    tool_sequence: list[str] = Field(default_factory=list)
    n_steps: int = 0
    n_tool_calls: int = 0
    tool_recall: float | None = Field(
        default=None, description="Share of expected tool calls that were made."
    )
    tool_precision: float | None = Field(
        default=None, description="Share of actual tool calls that were expected."
    )
    args_matched: int = 0
    args_expected: int = 0

    @property
    def errors(self) -> list[TrajectoryFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[TrajectoryFinding]:
        return [f for f in self.findings if f.severity == "warning"]


# ---------------------------------------------------------------------------
# Matching helpers
# ---------------------------------------------------------------------------


def _lcs(a: list[str], b: list[str]) -> int:
    prev = [0] * (len(b) + 1)
    for x in a:
        cur = [0]
        for j, y in enumerate(b):
            cur.append(prev[j] + 1 if x == y else max(prev[j + 1], cur[j]))
        prev = cur
    return prev[-1]


def _value_matches(expected: Any, actual: Any, present: bool) -> bool:
    if isinstance(expected, dict) and len(expected) == 1:
        (op, operand), = expected.items()
        if op == "$any":
            return present
        if op == "$contains":
            return present and str(operand).lower() in _as_text(actual).lower()
        if op == "$regex":
            return present and re.search(str(operand), _as_text(actual)) is not None
    return present and actual == expected


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)


def _call_matches(args: dict[str, Any] | None, expected: dict[str, Any]) -> bool:
    actual = args or {}
    return all(_value_matches(v, actual.get(k), k in actual) for k, v in expected.items())


def _short(seq: list[str]) -> str:
    return " → ".join(seq) if seq else "(no tool calls)"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def check_trajectory(
    steps: list[TraceStep],
    final_output: str | None,
    expectation: TrajectoryExpectation | None = None,
    *,
    tools_available: list[str] | None = None,
    agent_error: str | None = None,
) -> TrajectoryResult:
    findings: list[TrajectoryFinding] = []

    def add(check: str, severity: Literal["error", "warning"], detail: str,
            fm: TraceFailureMode | None = None, step_id: int | None = None) -> None:
        findings.append(TrajectoryFinding(
            check=check, severity=severity, detail=detail, failure_mode=fm, step_id=step_id
        ))

    calls = [s for s in steps if s.step_type == "tool_call" and s.tool_name]
    sequence = [s.tool_name for s in calls if s.tool_name]
    output = final_output
    if output is None:
        answers = [s.llm_output for s in steps if s.step_type == "final_answer" and s.llm_output]
        output = answers[-1] if answers else None
    acknowledged = bool(output and _ACKNOWLEDGES.search(output))

    # --- degradation checks ------------------------------------------------
    if agent_error:
        add("agent_error", "error", f"agent crashed: {agent_error}", TraceFailureMode.unhandled_error)
    if not output or not output.strip():
        add("empty_output", "error", "no final output", TraceFailureMode.task_not_completed)

    if tools_available:
        for s in calls:
            if s.tool_name not in tools_available:
                add("unknown_tool", "error", f"called `{s.tool_name}`, which is not an available tool",
                    TraceFailureMode.hallucinated_tool_call, s.step_id)

    def _failed(s: TraceStep) -> bool:
        return bool(s.error) or (s.tool_result is not None and _ERROR_RESULT.search(s.tool_result) is not None)

    def _empty(s: TraceStep) -> bool:
        return s.tool_result is not None and s.tool_result.strip().lower() in _EMPTY_RESULTS

    tool_steps = [s for s in steps if s.step_type in ("tool_call", "tool_result")]

    def _recovered(i: int) -> bool:
        """A later step of the same tool came back with a usable result."""
        tool = tool_steps[i].tool_name
        return any(
            t.tool_name == tool and t.tool_result is not None and not _failed(t) and not _empty(t)
            for t in tool_steps[i + 1 :]
        )

    for i, s in enumerate(tool_steps):
        result = s.tool_result
        failed = _failed(s)
        if (failed or _empty(s)) and (acknowledged or _recovered(i)):
            continue
        if failed:
            what = s.error or (result or "")[:80]
            add("error_swallowed", "error",
                f"`{s.tool_name or 'tool'}` failed ({what}) but the final answer doesn't say so",
                TraceFailureMode.error_not_propagated, s.step_id)
        elif _empty(s):
            add("empty_result", "warning",
                f"`{s.tool_name or 'tool'}` returned nothing, but the answer doesn't say so",
                None, s.step_id)

    repeats = Counter((s.tool_name, _as_text(s.tool_arguments or {})) for s in calls)
    for (tool, _), count in repeats.items():
        if count >= _REPEAT_LIMIT:
            add("repeated_call", "warning", f"`{tool}` called {count}× with the same arguments",
                TraceFailureMode.excessive_retries)

    # --- expectation checks ------------------------------------------------
    recall = precision = None
    args_matched = 0
    exp = expectation
    if exp is not None:
        if exp.tools is not None:
            expected = exp.tools
            if exp.match == "unordered":
                overlap = sum((Counter(expected) & Counter(sequence)).values())
                ok = overlap == len(expected)
            else:
                overlap = _lcs(expected, sequence)
                ok = sequence == expected if exp.match == "exact" else overlap == len(expected)
            recall = overlap / len(expected) if expected else 1.0
            precision = overlap / len(sequence) if sequence else (1.0 if not expected else 0.0)
            if not ok:
                add("tool_sequence", "error",
                    f"expected {_short(expected)} ({exp.match.replace('_', ' ')}), got {_short(sequence)}",
                    TraceFailureMode.wrong_tool_selected)

        for tool in exp.forbidden_tools:
            for s in calls:
                if s.tool_name == tool:
                    add("forbidden_tool", "error", f"called forbidden tool `{tool}`",
                        TraceFailureMode.wrong_tool_selected, s.step_id)

        for a in exp.args:
            tool_calls = [s for s in calls if s.tool_name == a.tool]
            if any(_call_matches(s.tool_arguments, a.args) for s in tool_calls):
                args_matched += 1
            elif not tool_calls:
                add("tool_args", "error", f"`{a.tool}` was never called, so its arguments "
                    f"{_as_text(a.args)} could not match", TraceFailureMode.invalid_tool_arguments)
            else:
                got = _as_text(tool_calls[0].tool_arguments or {})
                add("tool_args", "error", f"`{a.tool}` arguments {got} don't match {_as_text(a.args)}",
                    TraceFailureMode.invalid_tool_arguments, tool_calls[0].step_id)

        if exp.max_tool_calls is not None and len(calls) > exp.max_tool_calls:
            add("max_tool_calls", "error", f"{len(calls)} tool calls (max {exp.max_tool_calls})",
                TraceFailureMode.unnecessary_steps)
        if exp.max_steps is not None and len(steps) > exp.max_steps:
            add("max_steps", "error", f"{len(steps)} steps (max {exp.max_steps})",
                TraceFailureMode.unnecessary_steps)

        missing = [t for t in exp.output_contains if not output or t.lower() not in output.lower()]
        if missing:
            add("output_contains", "error", f"final output is missing {', '.join(repr(m) for m in missing)}",
                TraceFailureMode.task_not_completed)

    return TrajectoryResult(
        passed=not any(f.severity == "error" for f in findings),
        findings=findings,
        tool_sequence=sequence,
        n_steps=len(steps),
        n_tool_calls=len(calls),
        tool_recall=recall,
        tool_precision=precision,
        args_matched=args_matched,
        args_expected=len(exp.args) if exp else 0,
    )
