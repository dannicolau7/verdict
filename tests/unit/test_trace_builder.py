"""Unit tests for verdict.reports.trace_builder. No LLM calls."""

from __future__ import annotations

import uuid

import pytest

from verdict.models.trace_schemas import TraceEvalReport, TraceFailureMode, TraceJudgment
from verdict.reports.trace_builder import build_trace_eval_markdown, build_trace_eval_report

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _judgment(
    overall_passed: bool = True,
    overall_score: int | None = 4,
    failure_modes: list[TraceFailureMode] | None = None,
) -> TraceJudgment:
    return TraceJudgment(
        trace_id=str(uuid.uuid4()),
        overall_passed=overall_passed,
        overall_score=overall_score,
        reasoning="Test judgment: reasoning is sufficiently long for validation.",
        step_judgments=[],
        failure_modes=failure_modes or [],
        judge_model="claude-sonnet-4-6",
    )


# ---------------------------------------------------------------------------
# build_trace_eval_report
# ---------------------------------------------------------------------------

class TestBuildTraceEvalReport:
    def test_empty_judgments_returns_zero_report(self):
        report = build_trace_eval_report([], agent_name="agent", run_id="run-1")
        assert report.total_traces == 0
        assert report.pass_rate == 0.0
        assert report.trace_judgments == []

    def test_all_pass(self):
        judgments = [_judgment(True) for _ in range(5)]
        report = build_trace_eval_report(judgments, agent_name="agent", run_id="r")
        assert report.pass_rate == 1.0
        assert report.total_traces == 5

    def test_all_fail(self):
        judgments = [_judgment(False) for _ in range(4)]
        report = build_trace_eval_report(judgments, agent_name="agent", run_id="r")
        assert report.pass_rate == 0.0

    def test_mixed_pass_rate(self):
        judgments = [_judgment(True)] * 3 + [_judgment(False)] * 1
        report = build_trace_eval_report(judgments, agent_name="agent", run_id="r")
        assert report.pass_rate == pytest.approx(0.75)

    def test_failure_mode_counts_aggregated(self):
        judgments = [
            _judgment(False, failure_modes=[TraceFailureMode.wrong_tool_selected]),
            _judgment(False, failure_modes=[TraceFailureMode.wrong_tool_selected,
                                             TraceFailureMode.task_not_completed]),
            _judgment(True),
        ]
        report = build_trace_eval_report(judgments, agent_name="agent", run_id="r")
        assert report.failure_mode_counts["wrong_tool_selected"] == 2
        assert report.failure_mode_counts["task_not_completed"] == 1

    def test_bootstrap_ci_computed(self):
        judgments = [_judgment(True)] * 7 + [_judgment(False)] * 3
        report = build_trace_eval_report(
            judgments, agent_name="agent", run_id="r", bootstrap_iterations=500
        )
        assert report.pass_rate_ci_low is not None
        assert report.pass_rate_ci_high is not None
        assert 0.0 <= report.pass_rate_ci_low <= report.pass_rate_ci_high <= 1.0

    def test_bootstrap_disabled_when_zero(self):
        judgments = [_judgment(True) for _ in range(5)]
        report = build_trace_eval_report(
            judgments, agent_name="agent", run_id="r", bootstrap_iterations=0
        )
        assert report.pass_rate_ci_low is None
        assert report.pass_rate_ci_high is None
        assert report.bootstrap_iterations is None

    def test_run_id_auto_generated_when_none(self):
        report = build_trace_eval_report([], agent_name="agent")
        assert len(report.run_id) == 36  # UUID4


# ---------------------------------------------------------------------------
# build_trace_eval_markdown
# ---------------------------------------------------------------------------

class TestBuildTraceEvalMarkdown:
    def _report_with_data(self) -> TraceEvalReport:
        judgments = [
            _judgment(True, 5),
            _judgment(False, 2, [TraceFailureMode.task_not_completed]),
        ]
        return build_trace_eval_report(judgments, agent_name="test-agent", run_id="test-run")

    def test_contains_agent_name(self):
        report = self._report_with_data()
        md = build_trace_eval_markdown(report)
        assert "test-agent" in md

    def test_contains_pass_rate(self):
        report = self._report_with_data()
        md = build_trace_eval_markdown(report)
        assert "50.0%" in md or "50%" in md

    def test_contains_failure_mode(self):
        report = self._report_with_data()
        md = build_trace_eval_markdown(report)
        assert "task_not_completed" in md

    def test_contains_per_trace_section(self):
        report = self._report_with_data()
        md = build_trace_eval_markdown(report)
        assert "Per-Trace Results" in md

    def test_empty_report_renders_without_error(self):
        report = build_trace_eval_report([], agent_name="empty-agent", run_id="r")
        md = build_trace_eval_markdown(report)
        assert "empty-agent" in md
