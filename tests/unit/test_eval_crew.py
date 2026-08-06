"""Unit tests for EvalCrew (D9) — no LLM calls, all external I/O mocked."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from verdict.crews.eval_crew import EvalCrew, EvalCrewResult
from verdict.models.schemas import (
    EvalReport,
    ExecutionResult,
    FailureMode,
    Judgment,
    TestPrompt,
)

# ---------------------------------------------------------------------------
# Minimal fixtures
# ---------------------------------------------------------------------------


def _make_prompt(prompt_id: str = "p1", category: str = "correctness") -> TestPrompt:
    return TestPrompt(
        id=prompt_id,
        prompt="What is 2+2?",
        category=category,  # type: ignore[arg-type]
        severity="low",
        expected_behavior="Returns 4",
    )


def _make_result(prompt_id: str = "p1") -> ExecutionResult:
    return ExecutionResult(
        prompt_id=prompt_id,
        response="4",
        latency_ms=100.0,
        error=None,
    )


def _make_judgment(prompt_id: str = "p1", passed: bool = True) -> Judgment:
    return Judgment(
        prompt_id=prompt_id,
        passed=passed,
        score=5,
        reasoning="Correct answer provided." if passed else "Hallucination detected in response.",
        failure_mode=None if passed else FailureMode.hallucination,
        judge_model="claude-sonnet-4-6",
    )


def _make_report(run_id: str = "test001") -> EvalReport:
    j = _make_judgment()
    return EvalReport(
        run_id=run_id,
        target_system="mock-adapter",
        total_tests=1,
        pass_rate=1.0,
        judgments=[j],
        category_breakdown={"correctness": {"total": 1, "passed": 1, "pass_rate": 1.0}},
    )


class _MockAdapter:
    """Minimal TargetAdapter stand-in that never calls a real service."""

    name = "mock-adapter"
    version = "0.0.0"
    cache_stats = {"hits": 0, "misses": 0, "writes": 0}

    async def setup(self) -> None:  # noqa: D401
        pass

    async def teardown(self) -> None:
        pass

    async def execute_batch(self, prompts):
        return [_make_result(p.id) for p in prompts]


# ---------------------------------------------------------------------------
# EvalCrewResult tests
# ---------------------------------------------------------------------------


class TestEvalCrewResult:
    def _build(self, passed_count: int = 2, total: int = 3) -> EvalCrewResult:
        prompts = [_make_prompt(f"p{i}") for i in range(total)]
        results = [_make_result(f"p{i}") for i in range(total)]
        judgments = [_make_judgment(f"p{i}", passed=i < passed_count) for i in range(total)]
        report = _make_report()
        return EvalCrewResult(
            json_path=Path("/tmp/r.json"),
            md_path=Path("/tmp/r.md"),
            prompts=prompts,
            results=results,
            judgments=judgments,
            report=report,
        )

    def test_pass_rate_delegates_to_report(self):
        ev = self._build()
        assert ev.pass_rate == ev.report.pass_rate

    def test_passed_count(self):
        ev = self._build(passed_count=2, total=3)
        assert ev.passed == 2

    def test_failed_count(self):
        ev = self._build(passed_count=2, total=3)
        assert ev.failed == 1

    def test_error_count_zero_when_no_errors(self):
        ev = self._build()
        assert ev.error_count == 0

    def test_error_count_counts_errored_results(self):
        prompts = [_make_prompt("p1")]
        results = [ExecutionResult(prompt_id="p1", response="", latency_ms=0.0, error="timeout")]
        judgments = [_make_judgment("p1", passed=False)]
        ev = EvalCrewResult(
            json_path=Path("/tmp/r.json"),
            md_path=Path("/tmp/r.md"),
            prompts=prompts,
            results=results,
            judgments=judgments,
            report=_make_report(),
        )
        assert ev.error_count == 1


# ---------------------------------------------------------------------------
# EvalCrew instantiation tests — crewai import is lazy, so these run without
# crewai installed as long as we patch create_* factories.
# ---------------------------------------------------------------------------


def _mock_agent(role: str) -> MagicMock:
    agent = MagicMock()
    agent.role = role
    return agent


@pytest.fixture()
def patched_factories():
    """Patch all four create_* factories to avoid crewai import."""
    with (
        patch(
            "verdict.crews.eval_crew.create_test_generator",
            return_value=_mock_agent("TestGenerator"),
        ),
        patch(
            "verdict.crews.eval_crew.create_executor",
            return_value=_mock_agent("Executor"),
        ),
        patch(
            "verdict.crews.eval_crew.create_judge",
            return_value=_mock_agent("Judge"),
        ),
        patch(
            "verdict.crews.eval_crew.create_reporter",
            return_value=_mock_agent("Reporter"),
        ),
    ):
        yield


class TestEvalCrewInit:
    def test_four_agents_assigned(self, patched_factories):
        crew = EvalCrew(adapter=_MockAdapter())
        assert crew.generator_agent.role == "TestGenerator"
        assert crew.executor_agent.role == "Executor"
        assert crew.judge_agent.role == "Judge"
        assert crew.reporter_agent.role == "Reporter"

    def test_defaults(self, patched_factories):
        crew = EvalCrew(adapter=_MockAdapter())
        assert crew.num_per_category == 5
        assert crew.categories is None
        assert crew.model is None
        assert crew.adaptive is False
        assert crew.bootstrap_iterations == 1000
        assert crew.metadata == {}

    def test_custom_params(self, patched_factories):
        adapter = _MockAdapter()
        crew = EvalCrew(
            adapter=adapter,
            num_per_category=2,
            categories=["safety"],
            model="claude-haiku-4-5-20251001",
            run_id="myrun",
            bootstrap_iterations=0,
            adaptive=True,
            metadata={"env": "ci"},
        )
        assert crew.num_per_category == 2
        assert crew.categories == ["safety"]
        assert crew.model == "claude-haiku-4-5-20251001"
        assert crew.run_id == "myrun"
        assert crew.bootstrap_iterations == 0
        assert crew.adaptive is True
        assert crew.metadata == {"env": "ci"}


# ---------------------------------------------------------------------------
# EvalCrew.kickoff() tests — pipeline functions are patched; no LLM calls.
# ---------------------------------------------------------------------------


@pytest.fixture()
def crew_with_mocked_pipeline(tmp_path, patched_factories):
    """EvalCrew whose four standalone-function calls are fully patched."""
    prompt = _make_prompt()
    result = _make_result()
    judgment = _make_judgment()
    report = _make_report()

    json_path = tmp_path / "test001.json"
    md_path = tmp_path / "test001.md"
    json_path.write_text(report.model_dump_json())
    md_path.write_text("# Report")

    crew = EvalCrew(adapter=_MockAdapter(), output_dir=tmp_path)

    with (
        patch.object(crew, "_stage_generate", return_value=[prompt]) as mock_gen,
        patch.object(crew, "_stage_execute", return_value=[result]) as mock_exec,
        patch.object(crew, "_stage_judge", return_value=[judgment]) as mock_judge,
        patch.object(crew, "_stage_report", return_value=(json_path, md_path)) as mock_report,
    ):
        yield (
            crew,
            {
                "generate": mock_gen,
                "execute": mock_exec,
                "judge": mock_judge,
                "report": mock_report,
                "prompt": prompt,
                "result": result,
                "judgment": judgment,
                "json_path": json_path,
                "md_path": md_path,
            },
        )


class TestEvalCrewKickoff:
    def test_returns_eval_crew_result(self, crew_with_mocked_pipeline):
        crew, mocks = crew_with_mocked_pipeline
        ev = crew.kickoff()
        assert isinstance(ev, EvalCrewResult)

    def test_result_contains_correct_paths(self, crew_with_mocked_pipeline):
        crew, mocks = crew_with_mocked_pipeline
        ev = crew.kickoff()
        assert ev.json_path == mocks["json_path"]
        assert ev.md_path == mocks["md_path"]

    def test_all_four_stages_called(self, crew_with_mocked_pipeline):
        crew, mocks = crew_with_mocked_pipeline
        crew.kickoff()
        mocks["generate"].assert_called_once()
        mocks["execute"].assert_called_once()
        mocks["judge"].assert_called_once()
        mocks["report"].assert_called_once()

    def test_execute_receives_generate_output(self, crew_with_mocked_pipeline):
        crew, mocks = crew_with_mocked_pipeline
        crew.kickoff()
        call_args = mocks["execute"].call_args[0]
        assert call_args[0] == [mocks["prompt"]]

    def test_judge_receives_execute_output(self, crew_with_mocked_pipeline):
        crew, mocks = crew_with_mocked_pipeline
        crew.kickoff()
        # _stage_judge is called with positional args: (prompts, results)
        args, _ = mocks["judge"].call_args
        assert args[1] == [mocks["result"]]

    def test_on_progress_callback_called(self, crew_with_mocked_pipeline):
        crew, _ = crew_with_mocked_pipeline
        received: list[tuple[str, str]] = []
        crew.kickoff(on_progress=lambda s, d: received.append((s, d)))
        stages = {s for s, _ in received}
        assert "generate" in stages
        assert "execute" in stages
        assert "judge" in stages
        assert "report" in stages

    def test_adaptive_stage_skipped_by_default(self, crew_with_mocked_pipeline):
        crew, _ = crew_with_mocked_pipeline
        with patch.object(crew, "_stage_adaptive", wraps=crew._stage_adaptive) as mock_adaptive:
            crew.kickoff()
            mock_adaptive.assert_not_called()

    def test_adaptive_stage_called_when_enabled(self, tmp_path, patched_factories):
        prompt = _make_prompt()
        result = _make_result()
        judgment = _make_judgment()
        report = _make_report()

        json_path = tmp_path / "test001.json"
        md_path = tmp_path / "test001.md"
        json_path.write_text(report.model_dump_json())
        md_path.write_text("# Report")

        crew = EvalCrew(adapter=_MockAdapter(), output_dir=tmp_path, adaptive=True)

        with (
            patch.object(crew, "_stage_generate", return_value=[prompt]),
            patch.object(crew, "_stage_execute", return_value=[result]),
            patch.object(
                crew,
                "_stage_adaptive",
                return_value=([prompt], [result]),
            ) as mock_adaptive,
            patch.object(crew, "_stage_judge", return_value=[judgment]),
            patch.object(crew, "_stage_report", return_value=(json_path, md_path)),
        ):
            crew.kickoff()
            mock_adaptive.assert_called_once()

    def test_result_report_loaded_from_json(self, crew_with_mocked_pipeline):
        crew, mocks = crew_with_mocked_pipeline
        ev = crew.kickoff()
        assert isinstance(ev.report, EvalReport)
        assert ev.report.run_id == "test001"


# ---------------------------------------------------------------------------
# crews package __init__ exports
# ---------------------------------------------------------------------------


def test_package_exports():
    from verdict.crews import EvalCrew as _EC
    from verdict.crews import EvalCrewResult as _ECR

    assert _EC is EvalCrew
    assert _ECR is EvalCrewResult
