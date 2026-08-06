"""Unit tests for verdict.models.trace_schemas. No LLM calls."""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from verdict.models.trace_schemas import (
    AgentTrace,
    StepJudgment,
    TraceEvalReport,
    TraceFailureMode,
    TraceJudgment,
    TraceStep,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _step(step_id: int = 0, step_type: str = "tool_call", **kw) -> TraceStep:
    return TraceStep(step_id=step_id, step_type=step_type, **kw)


def _trace(**kw) -> AgentTrace:
    base = dict(
        agent_name="test-agent",
        task="Do something.",
        expected_behavior="Do it correctly.",
        steps=[_step(0, "llm_call"), _step(1, "final_answer")],
    )
    base.update(kw)
    return AgentTrace(**base)


def _step_judgment(step_id: int = 0, passed: bool = True, **kw) -> StepJudgment:
    return StepJudgment(
        step_id=step_id,
        passed=passed,
        reasoning="This step was evaluated correctly in the test.",
        **kw,
    )


def _trace_judgment(trace_id: str | None = None, overall_passed: bool = True, **kw) -> TraceJudgment:
    return TraceJudgment(
        trace_id=trace_id or str(uuid.uuid4()),
        overall_passed=overall_passed,
        reasoning="Overall trace was evaluated correctly in the test suite.",
        judge_model="claude-sonnet-4-6",
        **kw,
    )


# ---------------------------------------------------------------------------
# TraceFailureMode
# ---------------------------------------------------------------------------

class TestTraceFailureMode:
    def test_all_ten_modes_defined(self):
        assert len(TraceFailureMode) == 10

    def test_str_values_match_names(self):
        for mode in TraceFailureMode:
            assert mode.value == mode.name

    def test_is_str_enum(self):
        assert isinstance(TraceFailureMode.other, str)
        assert TraceFailureMode.other == "other"

    def test_all_expected_values_present(self):
        expected = {
            "wrong_tool_selected", "invalid_tool_arguments", "unhandled_error",
            "premature_termination", "unnecessary_steps", "task_not_completed",
            "hallucinated_tool_call", "error_not_propagated", "excessive_retries", "other",
        }
        assert {m.value for m in TraceFailureMode} == expected


# ---------------------------------------------------------------------------
# TraceStep
# ---------------------------------------------------------------------------

class TestTraceStep:
    def test_minimal_step(self):
        step = _step(0, "observation")
        assert step.step_id == 0
        assert step.step_type == "observation"
        assert step.tool_name is None

    def test_tool_call_step(self):
        step = TraceStep(
            step_id=1,
            step_type="tool_call",
            tool_name="web_search",
            tool_arguments={"query": "RAG papers"},
        )
        assert step.tool_name == "web_search"
        assert step.tool_arguments == {"query": "RAG papers"}

    def test_invalid_step_type_rejected(self):
        with pytest.raises(ValidationError):
            TraceStep(step_id=0, step_type="invalid_type")

    def test_negative_latency_rejected(self):
        with pytest.raises(ValidationError):
            TraceStep(step_id=0, step_type="llm_call", latency_ms=-1.0)

    def test_metadata_defaults_empty(self):
        step = _step(0)
        assert step.metadata == {}


# ---------------------------------------------------------------------------
# AgentTrace
# ---------------------------------------------------------------------------

class TestAgentTrace:
    def test_trace_id_auto_generated(self):
        trace = _trace()
        assert len(trace.trace_id) == 36  # UUID4 format

    def test_custom_trace_id(self):
        tid = str(uuid.uuid4())
        trace = _trace(trace_id=tid)
        assert trace.trace_id == tid

    def test_tools_available_defaults_empty(self):
        trace = _trace()
        assert trace.tools_available == []

    def test_timestamp_defaults_to_utc(self):
        trace = _trace()
        assert trace.timestamp.tzinfo is not None

    def test_steps_must_be_provided(self):
        with pytest.raises((ValidationError, TypeError)):
            AgentTrace(agent_name="a", task="t", expected_behavior="e")

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            AgentTrace(
                agent_name="a", task="t", expected_behavior="e",
                steps=[_step(0)], nonexistent_field="x",
            )


# ---------------------------------------------------------------------------
# StepJudgment
# ---------------------------------------------------------------------------

class TestStepJudgment:
    def test_valid_step_judgment(self):
        sj = _step_judgment(0, True)
        assert sj.passed is True
        assert sj.failure_mode is None

    def test_score_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            StepJudgment(
                step_id=0, passed=True,
                reasoning="Valid reasoning that is long enough to pass.",
                score=6,
            )

    def test_reasoning_too_short_rejected(self):
        with pytest.raises(ValidationError):
            StepJudgment(step_id=0, passed=True, reasoning="too short")

    def test_failure_mode_accepted(self):
        sj = StepJudgment(
            step_id=1, passed=False,
            reasoning="The wrong tool was selected for this step.",
            failure_mode=TraceFailureMode.wrong_tool_selected,
        )
        assert sj.failure_mode == TraceFailureMode.wrong_tool_selected


# ---------------------------------------------------------------------------
# TraceJudgment
# ---------------------------------------------------------------------------

class TestTraceJudgment:
    def test_valid_trace_judgment(self):
        tj = _trace_judgment()
        assert tj.overall_passed is True
        assert tj.failure_modes == []
        assert tj.step_judgments == []

    def test_overall_score_range_enforced(self):
        with pytest.raises(ValidationError):
            TraceJudgment(
                trace_id=str(uuid.uuid4()),
                overall_passed=True,
                overall_score=0,
                reasoning="Valid reasoning that is long enough.",
                judge_model="claude-sonnet-4-6",
            )

    def test_reasoning_too_short_rejected(self):
        with pytest.raises(ValidationError):
            TraceJudgment(
                trace_id=str(uuid.uuid4()),
                overall_passed=True,
                reasoning="too short",
                judge_model="claude-sonnet-4-6",
            )

    def test_failure_modes_list(self):
        tj = _trace_judgment(
            overall_passed=False,
            failure_modes=[TraceFailureMode.unhandled_error, TraceFailureMode.task_not_completed],
        )
        assert len(tj.failure_modes) == 2


# ---------------------------------------------------------------------------
# TraceEvalReport
# ---------------------------------------------------------------------------

class TestTraceEvalReport:
    def test_minimal_report(self):
        report = TraceEvalReport(
            run_id=str(uuid.uuid4()),
            agent_name="test-agent",
            total_traces=2,
            pass_rate=0.5,
        )
        assert report.pass_rate == 0.5
        assert report.trace_judgments == []

    def test_pass_rate_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            TraceEvalReport(
                run_id=str(uuid.uuid4()),
                agent_name="a",
                total_traces=1,
                pass_rate=1.5,
            )

    def test_timestamp_defaults_utc(self):
        r = TraceEvalReport(
            run_id=str(uuid.uuid4()), agent_name="a", total_traces=0, pass_rate=0.0
        )
        assert r.timestamp.tzinfo is not None

    def test_failure_mode_counts_defaults_empty(self):
        r = TraceEvalReport(
            run_id=str(uuid.uuid4()), agent_name="a", total_traces=0, pass_rate=0.0
        )
        assert r.failure_mode_counts == {}

    def test_ci_bounds_accepted(self):
        r = TraceEvalReport(
            run_id=str(uuid.uuid4()),
            agent_name="a",
            total_traces=10,
            pass_rate=0.8,
            pass_rate_ci_low=0.6,
            pass_rate_ci_high=0.95,
            bootstrap_iterations=1000,
        )
        assert r.pass_rate_ci_low == 0.6
