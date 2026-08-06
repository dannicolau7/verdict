"""EvalCrew — orchestrates the four Verdict agents in a sequential pipeline (D9).

Why this is not Crew.kickoff():
    CrewAI's Crew.kickoff() routes context between tasks as LLM-generated text.
    Our pipeline passes typed Python objects (TestPrompt → ExecutionResult →
    Judgment → EvalReport).  Coercing those through LLM serialisation would add
    nondeterminism and cost without benefit.

    Instead, EvalCrew instantiates the four CrewAI Agent objects (so all agent
    config lives in one place) and drives them through the existing standalone
    functions, which call the Anthropic SDK directly.  The deterministic Reporter
    math is fully preserved.

Usage:
    from verdict.crews.eval_crew import EvalCrew
    from verdict.adapters.simple_rag import SimpleRAGAdapter

    crew = EvalCrew(adapter=SimpleRAGAdapter(), num_per_category=5)
    result = crew.kickoff()
    print(result.json_path, result.pass_rate)
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from verdict.adapters.base import TargetAdapter
from verdict.agents.executor import create_executor, execute_test_suite
from verdict.agents.judge import create_judge, judge_results
from verdict.agents.reporter import create_reporter, generate_report
from verdict.agents.test_generator import create_test_generator, generate_test_suite
from verdict.models.schemas import EvalReport, ExecutionResult, Judgment, TestPrompt

logger = logging.getLogger(__name__)


@dataclass
class EvalCrewResult:
    """Structured return value from EvalCrew.kickoff()."""

    json_path: Path
    md_path: Path
    prompts: list[TestPrompt]
    results: list[ExecutionResult]
    judgments: list[Judgment]
    report: EvalReport

    @property
    def pass_rate(self) -> float:
        return self.report.pass_rate

    @property
    def passed(self) -> int:
        return sum(1 for j in self.judgments if j.passed)

    @property
    def failed(self) -> int:
        return sum(1 for j in self.judgments if not j.passed)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.error)


class EvalCrew:
    """Orchestrates the four Verdict agents as a sequential evaluation pipeline.

    The four CrewAI Agent objects are instantiated in __init__; the pipeline
    is driven by the standalone functions in verdict.agents.*.  This keeps
    agent configuration centralised while preserving the typed data contracts
    between stages.

    Args:
        adapter:               TargetAdapter to evaluate.
        num_per_category:      Prompts per evaluation category.
        categories:            Subset of category names (None → all five).
        model:                 Anthropic model ID applied to all LLM agents.
        judge_models:          Override judge models for multi-judge consensus.
        run_id:                Custom run ID; auto-generated if omitted.
        output_dir:            Report output directory; defaults to settings.reports_dir.
        bootstrap_iterations:  Bootstrap CI iterations (0 to disable).
        adaptive:              Run adaptive follow-up probes after initial execution.
        metadata:              Extra key/value pairs stored in the EvalReport.
    """

    def __init__(
        self,
        adapter: TargetAdapter,
        num_per_category: int = 5,
        categories: list[str] | None = None,
        model: str | None = None,
        judge_models: list[str] | None = None,
        run_id: str | None = None,
        output_dir: Path | None = None,
        bootstrap_iterations: int = 1000,
        adaptive: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.adapter = adapter
        self.num_per_category = num_per_category
        self.categories = categories
        self.model = model
        self.judge_models = judge_models
        self.run_id = run_id
        self.output_dir = output_dir
        self.bootstrap_iterations = bootstrap_iterations
        self.adaptive = adaptive
        self.metadata: dict[str, Any] = metadata or {}

        # Instantiate all four CrewAI Agent objects up front so agent config
        # is centralised here rather than scattered across the CLI.
        self.generator_agent = create_test_generator(model=model)
        self.executor_agent = create_executor(model=model)
        self.judge_agent = create_judge(model=model)
        self.reporter_agent = create_reporter(model=model)

        logger.debug(
            "EvalCrew assembled: [%s] [%s] [%s] [%s]",
            self.generator_agent.role,
            self.executor_agent.role,
            self.judge_agent.role,
            self.reporter_agent.role,
        )

    # ------------------------------------------------------------------
    # Pipeline stages — each delegates to its standalone function
    # ------------------------------------------------------------------

    def _stage_generate(self) -> list[TestPrompt]:
        return generate_test_suite(
            num_per_category=self.num_per_category,
            categories=self.categories,
            model=self.model,
        )

    def _stage_execute(self, prompts: list[TestPrompt]) -> list[ExecutionResult]:
        return asyncio.run(execute_test_suite(prompts, self.adapter))

    def _stage_adaptive(
        self,
        prompts: list[TestPrompt],
        results: list[ExecutionResult],
    ) -> tuple[list[TestPrompt], list[ExecutionResult]]:
        from verdict.agents.adaptive_generator import AdaptiveTestGenerator

        gen = AdaptiveTestGenerator()
        extra_prompts = [
            probe for result in results if (probe := gen.next_probe(result)) is not None
        ]
        if not extra_prompts:
            return prompts, results
        extra_results = asyncio.run(execute_test_suite(extra_prompts, self.adapter))
        return list(prompts) + extra_prompts, list(results) + extra_results

    def _stage_judge(
        self,
        prompts: list[TestPrompt],
        results: list[ExecutionResult],
    ) -> list[Judgment]:
        resolved = self.judge_models or ([self.model] if self.model else None)
        return judge_results(prompts=prompts, results=results, judge_models=resolved)

    def _stage_report(
        self,
        judgments: list[Judgment],
        prompts: list[TestPrompt],
        results: list[ExecutionResult],
    ) -> tuple[Path, Path]:
        return generate_report(
            judgments=judgments,
            prompts=prompts,
            target_name=getattr(self.adapter, "name", type(self.adapter).__name__),
            run_id=self.run_id,
            output_dir=self.output_dir,
            model=self.model,
            target_version=getattr(self.adapter, "version", None),
            metadata={**self.metadata, "execution_results": results},
            bootstrap_iterations=self.bootstrap_iterations,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def kickoff(
        self,
        on_progress: Callable[[str, str], None] | None = None,
    ) -> EvalCrewResult:
        """Run the full evaluation pipeline and return a structured result.

        Stages (in order):
            generate  — TestGenerator agent produces adversarial prompts
            execute   — Executor agent runs prompts against the adapter
            adaptive  — (if adaptive=True) follow-up probes from AdaptiveTestGenerator
            judge     — Judge agent evaluates every response
            report    — Reporter agent writes JSON + markdown

        Args:
            on_progress: Optional callback called at each stage transition as
                         (stage_name, human_readable_detail).  The CLI uses this
                         to print Rich console messages without coupling EvalCrew
                         to a specific output mechanism.

        Returns:
            EvalCrewResult with typed data from every stage plus the final EvalReport.
        """

        def _notify(stage: str, detail: str) -> None:
            logger.info("[%s] %s", stage, detail)
            if on_progress is not None:
                on_progress(stage, detail)

        # 1. Generate
        _notify("generate", f"Generating {self.num_per_category} prompts per category…")
        prompts = self._stage_generate()
        _notify("generate", f"{len(prompts)} prompts generated.")

        # 2. Execute
        _notify("execute", f"Executing {len(prompts)} prompts against target…")
        results = self._stage_execute(prompts)
        errors = sum(1 for r in results if r.error)
        _notify("execute", f"{len(results)} responses received ({errors} errors).")

        # 3. Adaptive probes (optional)
        if self.adaptive:
            _notify("adaptive", "Generating adaptive follow-up probes…")
            prompts, results = self._stage_adaptive(prompts, results)
            _notify("adaptive", f"{len(prompts)} total prompts after adaptive extension.")

        # 4. Judge
        _notify("judge", f"Judging {len(results)} results…")
        judgments = self._stage_judge(prompts, results)
        passed = sum(1 for j in judgments if j.passed)
        _notify("judge", f"{passed}/{len(judgments)} passed.")

        # 5. Report
        _notify("report", "Generating report…")
        json_path, md_path = self._stage_report(judgments, prompts, results)
        _notify("report", f"JSON: {json_path}  Markdown: {md_path}")

        report = EvalReport(**json.loads(json_path.read_text(encoding="utf-8")))

        logger.info(
            "EvalCrew complete — pass rate: %.1f%% (%d/%d), run_id: %s",
            report.pass_rate * 100,
            passed,
            len(judgments),
            report.run_id,
        )

        return EvalCrewResult(
            json_path=json_path,
            md_path=md_path,
            prompts=prompts,
            results=results,
            judgments=judgments,
            report=report,
        )
