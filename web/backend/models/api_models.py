"""Pydantic request/response models for the Verdict API.

These are the API surface — intentionally thinner than the internal
verdict.models.schemas models. Keep in sync with src/types/api.ts.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class ConfigResponse(BaseModel):
    categories: list[str]
    attack_families: list[str]
    judge_models: list[str]
    default_judge_model: str


# ---------------------------------------------------------------------------
# Eval run
# ---------------------------------------------------------------------------


class EvalRunRequest(BaseModel):
    target: str = "simple_rag"
    categories: list[str] = Field(
        default=["correctness", "safety", "injection", "edge_case", "compliance"]
    )
    attack_mode: Literal["standard", "adaptive"] = "standard"
    enable_ci: bool = True
    enable_flakiness: bool = False
    judge_model: str = "claude-sonnet-4-6"
    num_per_category: int = Field(default=5, ge=1, le=20)
    custom_prompts: list[str] = Field(default_factory=list)
    custom_category: str = "correctness"


class CategoryStats(BaseModel):
    total: int
    passed: int
    failed: int
    pass_rate: float
    failure_modes: dict[str, int]
    critical_failures: list[str]


class EvalReport(BaseModel):
    run_id: str
    target_system: str
    total_tests: int
    pass_rate: float
    pass_rate_ci_low: float | None = None
    pass_rate_ci_high: float | None = None
    bootstrap_iterations: int | None = None
    category_breakdown: dict[str, CategoryStats]
    timestamp: str
    verdict_version: str | None = None
    cost_breakdown: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


class RunListItem(BaseModel):
    run_id: str
    target_system: str
    timestamp: str
    pass_rate: float
    total_tests: int
    label: str | None = None


class LabelRequest(BaseModel):
    label: str | None = None


# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------


class ComplianceRequest(BaseModel):
    run_id: str
    frameworks: list[Literal["hipaa", "nist"]] = ["hipaa", "nist"]


class ControlEvidence(BaseModel):
    source: str
    tests_run: int
    tests_passed: int
    pass_rate: float
    ci_low: float
    ci_high: float
    evidence_strength: str
    flakiness_flag: bool
    notable_failure_modes: list[str]


class ControlResult(BaseModel):
    id: str
    framework: str
    function: str
    title: str
    description: str
    reference: str
    overall_status: Literal["pass", "partial", "fail", "insufficient_data"]
    overall_pass_rate: float | None
    overall_ci_low: float | None
    overall_ci_high: float | None
    confidence: str
    flakiness_flag: bool
    evidence: list[ControlEvidence]


class ComplianceArtifactEvalRun(BaseModel):
    run_id: str
    target_system: str
    total_tests: int
    pass_rate: float
    timestamp: str


class ComplianceArtifact(BaseModel):
    artifact_id: str
    schema_version: str
    generated_at: str
    eval_run: ComplianceArtifactEvalRun
    controls: list[ControlResult]


class ComplianceResponse(BaseModel):
    artifact: ComplianceArtifact
    markdown: str


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


class CategoryDiff(BaseModel):
    category: str
    a_pass_rate: float | None
    b_pass_rate: float | None
    delta: float | None
    a_total: int
    b_total: int


class DiffRunRequest(BaseModel):
    model_a: str = "claude-haiku-4-5-20251001"
    model_b: str = "claude-sonnet-4-6"
    categories: list[str] = Field(
        default=["correctness", "safety", "injection", "edge_case", "compliance"]
    )
    num_per_category: int = Field(default=3, ge=1, le=10)
    judge_model: str = "claude-sonnet-4-6"


class PerPromptRow(BaseModel):
    prompt_id: str
    prompt_text: str
    category: str
    severity: str
    a_passed: bool
    b_passed: bool
    a_failure_mode: str | None
    b_failure_mode: str | None
    a_reasoning: str
    b_reasoning: str


class DiffRunResponse(BaseModel):
    run_id: str
    model_a: str
    model_b: str
    timestamp: str
    total_tests: int
    a_pass_rate: float
    b_pass_rate: float
    pass_rate_delta: float
    regression_count: int
    improvement_count: int
    unchanged: int
    categories: list[CategoryDiff]
    regressions: list[PerPromptRow]
    improvements: list[PerPromptRow]


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------


class ErrorResponse(BaseModel):
    detail: str
