"""Pydantic v2 schemas for agent-trace evaluation (Phase 2 / v0.3.0).

Data flow:
    AgentTrace -> (trace_judge) -> TraceJudgment -> (trace_builder) -> TraceEvalReport

- AgentTrace:      A recorded step-by-step execution log from an agent run.
- TraceStep:       One node in the execution trace (LLM call, tool call, etc.).
- StepJudgment:    The judge's verdict on a single TraceStep.
- TraceJudgment:   Full verdict on one AgentTrace (per-step + overall).
- TraceEvalReport: Aggregated report across all TraceJudgments for a run.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TraceFailureMode(StrEnum):
    """Taxonomy of ways an agent trace can fail evaluation."""

    wrong_tool_selected = "wrong_tool_selected"
    invalid_tool_arguments = "invalid_tool_arguments"
    unhandled_error = "unhandled_error"
    premature_termination = "premature_termination"
    unnecessary_steps = "unnecessary_steps"
    task_not_completed = "task_not_completed"
    hallucinated_tool_call = "hallucinated_tool_call"
    error_not_propagated = "error_not_propagated"
    excessive_retries = "excessive_retries"
    other = "other"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TraceStep(BaseModel):
    """One step in an agent execution trace."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid", frozen=False)

    step_id: int = Field(..., description="Zero-based index of this step in the trace.")
    step_type: Literal[
        "llm_call", "tool_call", "tool_result", "observation", "final_answer"
    ] = Field(..., description="Type of step.")
    tool_name: str | None = Field(
        default=None, description="Tool invoked (for tool_call steps)."
    )
    tool_arguments: dict[str, Any] | None = Field(
        default=None, description="Arguments passed to the tool."
    )
    tool_result: str | None = Field(
        default=None, description="Raw result returned by the tool."
    )
    llm_input: str | None = Field(
        default=None,
        description="Prompt or context passed to the LLM (for llm_call steps).",
    )
    llm_output: str | None = Field(
        default=None,
        description="Raw output from the LLM (for llm_call and final_answer steps).",
    )
    latency_ms: float | None = Field(
        default=None, ge=0.0, description="Wall-clock time for this step in milliseconds."
    )
    error: str | None = Field(
        default=None, description="Exception message if this step raised an error."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTrace(BaseModel):
    """A recorded step-by-step execution log from an agent run."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid", frozen=False)

    trace_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID4 string uniquely identifying this trace.",
    )
    agent_name: str = Field(..., description="Identifier for the agent under evaluation.")
    task: str = Field(..., description="The original goal given to the agent.")
    expected_behavior: str = Field(
        ...,
        description="Human-readable description of what correct execution looks like.",
    )
    tools_available: list[str] = Field(
        default_factory=list,
        description="Names of tools the agent had access to.",
    )
    steps: list[TraceStep] = Field(..., description="Ordered list of execution steps.")
    final_output: str | None = Field(
        default=None, description="The agent's final answer or output."
    )
    total_latency_ms: float | None = Field(
        default=None, ge=0.0, description="Total wall-clock time for the full trace."
    )
    error: str | None = Field(
        default=None, description="Top-level error if the agent crashed."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(
        default_factory=_utcnow,
        description="UTC datetime when the trace was recorded.",
    )


class StepJudgment(BaseModel):
    """The judge's verdict on a single TraceStep."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid", frozen=False)

    step_id: int = Field(..., description="ID of the step being judged.")
    passed: bool = Field(..., description="Binary pass/fail verdict for this step.")
    score: int | None = Field(
        default=None, description="Graded score 1-5; None for binary-only steps."
    )
    reasoning: str = Field(
        ..., description="Explanation of the step judgment (min 20 chars)."
    )
    failure_mode: TraceFailureMode | None = Field(
        default=None, description="Failure category when passed=False."
    )

    @field_validator("score")
    @classmethod
    def score_in_range(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 5):
            raise ValueError(f"score must be 1-5, got {v}")
        return v

    @field_validator("reasoning")
    @classmethod
    def reasoning_non_empty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 20:
            raise ValueError(f"reasoning must be >= 20 chars, got {len(v)}")
        return v


class TraceJudgment(BaseModel):
    """Full judge verdict on one AgentTrace (per-step + overall)."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid", frozen=False)

    trace_id: str = Field(..., description="ID of the AgentTrace being judged.")
    overall_passed: bool = Field(
        ..., description="Holistic pass/fail for the full trace."
    )
    overall_score: int | None = Field(
        default=None, description="Holistic score 1-5 for the trace."
    )
    reasoning: str = Field(
        ...,
        description="Overall reasoning for the trace verdict (min 20 chars).",
    )
    step_judgments: list[StepJudgment] = Field(
        default_factory=list, description="Per-step verdicts."
    )
    failure_modes: list[TraceFailureMode] = Field(
        default_factory=list,
        description="All failure modes observed across steps (deduplicated).",
    )
    judge_model: str = Field(
        ..., description="Model identifier that produced this judgment."
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("overall_score")
    @classmethod
    def score_in_range(cls, v: int | None) -> int | None:
        if v is not None and not (1 <= v <= 5):
            raise ValueError(f"overall_score must be 1-5, got {v}")
        return v

    @field_validator("reasoning")
    @classmethod
    def reasoning_non_empty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 20:
            raise ValueError(f"reasoning must be >= 20 chars, got {len(v)}")
        return v


class TraceEvalReport(BaseModel):
    """Aggregated report across all TraceJudgments for a run."""

    model_config = ConfigDict(validate_assignment=True, extra="forbid", frozen=False)

    run_id: str = Field(..., description="Unique identifier for this trace eval run.")
    agent_name: str = Field(..., description="Name of the agent under evaluation.")
    total_traces: int = Field(..., ge=0, description="Number of traces evaluated.")
    pass_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Fraction of passing traces."
    )
    trace_judgments: list[TraceJudgment] = Field(
        default_factory=list, description="All individual TraceJudgment objects."
    )
    failure_mode_counts: dict[str, int] = Field(
        default_factory=dict,
        description="Frequency of each TraceFailureMode across all traces.",
    )
    pass_rate_ci_low: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Lower bound of 95% CI from bootstrap resampling.",
    )
    pass_rate_ci_high: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Upper bound of 95% CI from bootstrap resampling.",
    )
    bootstrap_iterations: int | None = Field(
        default=None,
        ge=0,
        description="Number of bootstrap iterations used to compute CI.",
    )
    timestamp: datetime = Field(
        default_factory=_utcnow,
        description="UTC datetime when the report was generated.",
    )
    metadata: dict[str, Any] = Field(default_factory=dict)
    verdict_version: str | None = Field(
        default=None,
        description="The Verdict library version that produced this report.",
    )
