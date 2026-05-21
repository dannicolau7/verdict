"""Pydantic v2 schemas for the Verdict evaluation framework.

Data flow:
    TestPrompt -> (executor) -> ExecutionResult -> (judge) -> Judgment -> (reporter) -> EvalReport

- TestPrompt:      A single adversarial or compliance test case to run against the target system.
- ExecutionResult: The raw response from the target system for a given TestPrompt.
- Judgment:        The judge's verdict on one ExecutionResult (score, pass/fail, reasoning).
- EvalReport:      Aggregated report across all Judgments for a single evaluation run.
- DiffReport:      Comparison of two adapter versions run against the same test suite (v0.2.0+).

v0.2.0 additions (all Optional with None defaults — fully backward-compatible):
    ExecutionResult: token_usage, estimated_cost_usd, model_used
    EvalReport:      pass_rate_ci_low/high, bootstrap_iterations, cost_breakdown,
                     total_latency_ms, cache_stats, flakiness_report, verdict_version
    DiffReport:      new model for differential testing
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FailureMode(StrEnum):
    """Taxonomy of ways an agent can fail an evaluation."""

    hallucination = "hallucination"
    refusal_when_should_comply = "refusal_when_should_comply"
    compliance_when_should_refuse = "compliance_when_should_refuse"
    prompt_injection_success = "prompt_injection_success"
    pii_leak = "pii_leak"
    compliance_violation = "compliance_violation"
    format_error = "format_error"
    latency_breach = "latency_breach"
    other = "other"


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TestPrompt(BaseModel):
    """A single test case to be executed against the target agent system.

    Attributes:
        id:                UUID4 string uniquely identifying this test case.
        prompt:            The actual text sent to the target system.
        category:          Broad category this test belongs to.
        severity:          Estimated impact if the agent fails this test.
        expected_behavior: Human-readable description of what a correct response looks like.
        metadata:          Arbitrary extra data (source references, OWASP IDs, etc.).
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid", frozen=False)

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID4 string uniquely identifying this test case.",
    )
    prompt: str = Field(..., description="The actual prompt text sent to the target system.")
    category: Literal["correctness", "safety", "injection", "edge_case", "compliance"] = Field(
        ..., description="Test category."
    )
    severity: Literal["low", "medium", "high", "critical"] = Field(
        ..., description="Severity if the agent fails this test."
    )
    expected_behavior: str = Field(
        ..., description="What a correct agent response looks like."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary extra data (OWASP IDs, source refs, etc.).",
    )


class ExecutionResult(BaseModel):
    """The raw output from running one TestPrompt against the target system.

    Attributes:
        prompt_id:   Foreign key to the TestPrompt that produced this result.
        response:    The verbatim response returned by the target system.
        latency_ms:  Wall-clock time in milliseconds for the full round-trip.
        token_count: Total tokens consumed (prompt + completion), if available.
        error:       Populated when the adapter raised an exception; None on success.
        timestamp:   UTC datetime when the execution completed.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid", frozen=False)

    prompt_id: str = Field(..., description="ID of the TestPrompt that was executed.")
    response: str = Field(..., description="Verbatim response from the target system.")
    latency_ms: float = Field(..., description="Round-trip latency in milliseconds.")
    token_count: int | None = Field(
        default=None, description="Total tokens consumed, if reported by the adapter."
    )
    error: str | None = Field(
        default=None,
        description="Exception message if the adapter raised; None on success.",
    )
    timestamp: datetime = Field(
        default_factory=_utcnow, description="UTC datetime when execution completed."
    )

    # ------------------------------------------------------------------ #
    # v0.2.0 fields (all Optional — backward-compatible)                  #
    # ------------------------------------------------------------------ #

    token_usage: dict[str, int] | None = Field(
        default=None,
        description=(
            "Per-call token counts for the target system. "
            "Standard shape: {'input_tokens': N, 'output_tokens': N, 'total_tokens': N}. "
            "When populated, supersedes the legacy token_count field."
        ),
    )
    estimated_cost_usd: float | None = Field(
        default=None,
        ge=0.0,
        description="Estimated USD cost of this single target call, derived from token_usage and model pricing.",
    )
    model_used: str | None = Field(
        default=None,
        description="Actual model string the adapter used (e.g., 'claude-sonnet-4-6'). Useful when adapters select models dynamically.",
    )

    @field_validator("latency_ms")
    @classmethod
    def latency_must_be_non_negative(cls, v: float) -> float:
        """Reject negative latency values."""
        if v < 0:
            raise ValueError(f"latency_ms must be >= 0, got {v}")
        return v


class Judgment(BaseModel):
    """The judge's verdict on a single ExecutionResult.

    Attributes:
        prompt_id:    Foreign key to the TestPrompt being judged.
        score:        Graded score 1-5 for rubric-based categories; None for binary categories.
        passed:       Binary verdict — always populated regardless of scoring mode.
        reasoning:    Non-empty explanation of the judgment (min 20 chars after strip).
        failure_mode: Categorized failure type if passed=False; None if passed=True.
        judge_model:  Identifier of the model that produced this judgment.
        metadata:     Extra data such as multi-judge agreement scores.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid", frozen=False)

    prompt_id: str = Field(..., description="ID of the TestPrompt being judged.")
    score: int | None = Field(
        default=None,
        description="Graded score 1-5 for rubric-based categories; None for binary categories.",
    )
    passed: bool = Field(..., description="Binary pass/fail verdict.")
    reasoning: str = Field(
        ..., description="Explanation of the judgment (min 20 characters)."
    )
    failure_mode: FailureMode | None = Field(
        default=None,
        description="Failure category when passed=False; None when passed=True.",
    )
    judge_model: str = Field(
        ..., description="Model identifier that produced this judgment."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Extra data such as multi-judge agreement scores.",
    )

    @field_validator("score")
    @classmethod
    def score_must_be_in_range(cls, v: int | None) -> int | None:
        """Score must be between 1 and 5 inclusive when provided."""
        if v is not None and not (1 <= v <= 5):
            raise ValueError(f"score must be between 1 and 5, got {v}")
        return v

    @field_validator("reasoning")
    @classmethod
    def reasoning_must_be_non_empty(cls, v: str) -> str:
        """Strip whitespace and reject empty or too-short reasoning."""
        v = v.strip()
        if len(v) < 20:
            raise ValueError(
                f"reasoning must be at least 20 characters after stripping whitespace, got {len(v)}"
            )
        return v


class EvalReport(BaseModel):
    """Aggregated report for a complete evaluation run.

    Attributes:
        run_id:             Unique identifier for this eval run.
        target_system:      Adapter name identifying the system under test.
        target_version:     Optional version string from the adapter.
        total_tests:        Number of tests run; must equal len(judgments).
        pass_rate:          Fraction of passing judgments (0.0 to 1.0).
        category_breakdown: Per-category metrics dict (keys are category names).
        judgments:          All individual Judgment objects for this run.
        timestamp:          UTC datetime when the report was generated.
        metadata:           Arbitrary extra data for this run.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid", frozen=False)

    run_id: str = Field(..., description="Unique identifier for this evaluation run.")
    target_system: str = Field(
        ..., description="Adapter name identifying the system under test."
    )
    target_version: str | None = Field(
        default=None, description="Optional version string from the adapter."
    )
    total_tests: int = Field(
        ..., description="Total number of tests run; must equal len(judgments)."
    )
    pass_rate: float = Field(..., description="Fraction of passing judgments (0.0–1.0).")
    category_breakdown: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-category metrics (pass_rate, count, failures, etc.).",
    )
    judgments: list[Judgment] = Field(
        default_factory=list, description="All individual Judgment objects for this run."
    )
    timestamp: datetime = Field(
        default_factory=_utcnow, description="UTC datetime when the report was generated."
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary extra data for this run."
    )

    # ------------------------------------------------------------------ #
    # v0.2.0 fields (all Optional — backward-compatible)                  #
    # ------------------------------------------------------------------ #

    pass_rate_ci_low: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Lower bound of 95% CI from bootstrap resampling (v0.2.0+).",
    )
    pass_rate_ci_high: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Upper bound of 95% CI from bootstrap resampling (v0.2.0+).",
    )
    bootstrap_iterations: int | None = Field(
        default=None, ge=0,
        description="Number of bootstrap iterations used to compute CI (v0.2.0+).",
    )
    cost_breakdown: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Cost accounting split by source (v0.2.0+). "
            "Shape: {'harness': {'input_tokens': N, 'output_tokens': N, 'estimated_cost_usd': X}, "
            "'target': {'input_tokens': N, 'output_tokens': N, 'estimated_cost_usd': X}, "
            "'total_cost_usd': X}."
        ),
    )
    total_latency_ms: float | None = Field(
        default=None, ge=0.0,
        description="Sum of latency_ms across all executions in this run (v0.2.0+).",
    )
    cache_stats: dict[str, int] | None = Field(
        default=None,
        description="Cache hit/miss/write counts (v0.2.0+). Shape: {'hits': N, 'misses': N, 'writes': N}.",
    )
    flakiness_report: dict[str, Any] | None = Field(
        default=None,
        description="Variance analysis across historical runs (v0.2.0+). Populated by analysis.flakiness module.",
    )
    verdict_version: str | None = Field(
        default=None,
        description="The Verdict library version that produced this report. Useful for audit trails (v0.2.0+).",
    )

    @field_validator("pass_rate")
    @classmethod
    def pass_rate_must_be_fraction(cls, v: float) -> float:
        """pass_rate must be between 0.0 and 1.0 inclusive."""
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"pass_rate must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("total_tests")
    @classmethod
    def total_tests_must_be_non_negative(cls, v: int) -> int:
        """total_tests must be >= 0."""
        if v < 0:
            raise ValueError(f"total_tests must be >= 0, got {v}")
        return v

    @model_validator(mode="after")
    def total_tests_matches_judgments(self) -> EvalReport:
        """total_tests must equal the number of Judgment objects."""
        if self.total_tests != len(self.judgments):
            raise ValueError(
                f"total_tests ({self.total_tests}) must equal len(judgments) ({len(self.judgments)})"
            )
        return self

    @model_validator(mode="after")
    def ci_bounds_must_be_ordered(self) -> EvalReport:
        """If both CI bounds are set, low must be <= high."""
        lo, hi = self.pass_rate_ci_low, self.pass_rate_ci_high
        if lo is not None and hi is not None and lo > hi:
            raise ValueError(
                f"pass_rate_ci_low ({lo}) must be <= pass_rate_ci_high ({hi})"
            )
        return self

    @model_validator(mode="after")
    def cost_breakdown_shape(self) -> EvalReport:
        """If cost_breakdown is set, harness and target must have estimated_cost_usd."""
        cb = self.cost_breakdown
        if cb is None:
            return self
        for key in ("harness", "target"):
            if key in cb:
                entry = cb[key]
                if not isinstance(entry, dict) or not isinstance(
                    entry.get("estimated_cost_usd"), (int, float)
                ):
                    raise ValueError(
                        f"cost_breakdown['{key}'] must be a dict with numeric 'estimated_cost_usd'"
                    )
        return self


# ---------------------------------------------------------------------------
# v0.2.0 — DiffReport
# ---------------------------------------------------------------------------


class DiffReport(BaseModel):
    """Comparison of two adapter versions run against the same test suite (v0.2.0+).

    Produced by `verdict diff --target-a ... --target-b ...`.
    Saved as reports/diff_{run_id}.json.
    """

    model_config = ConfigDict(validate_assignment=True, extra="forbid", frozen=False)

    run_id: str = Field(..., description="Unique identifier for this diff run.")
    target_a_name: str = Field(..., description="Name of adapter A.")
    target_a_version: str = Field(..., description="Version of adapter A.")
    target_b_name: str = Field(..., description="Name of adapter B.")
    target_b_version: str = Field(..., description="Version of adapter B.")
    total_tests: int = Field(..., description="Total prompts in the shared test suite.")
    a_pass_rate: float = Field(..., ge=0.0, le=1.0, description="Pass rate for adapter A.")
    b_pass_rate: float = Field(..., ge=0.0, le=1.0, description="Pass rate for adapter B.")
    pass_rate_delta: float = Field(..., description="b_pass_rate - a_pass_rate.")
    regressions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Prompts where A passed but B failed.",
    )
    improvements: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Prompts where A failed but B passed.",
    )
    unchanged: int = Field(
        ..., description="Prompts where both adapters agreed (both pass or both fail)."
    )
    per_judgment: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Full per-prompt comparison data.",
    )
    timestamp: datetime = Field(
        default_factory=_utcnow, description="UTC datetime when the diff ran."
    )
