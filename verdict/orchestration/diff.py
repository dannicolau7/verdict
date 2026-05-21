"""Differential testing orchestration for Verdict.

run_diff() runs the same generated test suite against two adapters concurrently,
judges both sets of responses, and produces a DiffReport highlighting regressions
and improvements.

Usage (CLI):
    verdict diff --target-a simple_rag --target-b path/to/v2.py:V2Adapter --num 25

Usage (Python REPL):
    from verdict.orchestration.diff import run_diff
    json_path, md_path = await run_diff(adapter_a, adapter_b, num_per_category=5)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Any

from verdict.adapters.base import TargetAdapter
from verdict.agents.executor import execute_test_suite
from verdict.agents.judge import judge_results
from verdict.agents.test_generator import generate_test_suite
from verdict.config.settings import get_settings
from verdict.models.schemas import DiffReport, TestPrompt

logger = logging.getLogger(__name__)


async def run_diff(
    adapter_a: TargetAdapter,
    adapter_b: TargetAdapter,
    num_per_category: int = 5,
    categories: list[str] | None = None,
    output_dir: Path | None = None,
    run_id: str | None = None,
) -> tuple[Path, Path]:
    """Run differential testing between two adapters.

    Generates ONE shared test suite, runs both adapters concurrently, judges
    both sets, and produces a DiffReport.

    Args:
        adapter_a:         First (baseline) adapter.
        adapter_b:         Second (candidate) adapter.
        num_per_category:  Prompts per category.
        categories:        Category filter; None = all five.
        output_dir:        Where to save reports (default: settings.reports_dir).
        run_id:            Custom run ID; generated if None.

    Returns:
        (json_path, md_path) for the saved DiffReport.
    """
    settings = get_settings()
    resolved_run_id = run_id or uuid.uuid4().hex[:8]
    resolved_output_dir = output_dir or settings.reports_dir
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 1. Generate ONE shared test suite                                    #
    # ------------------------------------------------------------------ #
    logger.info("Generating shared test suite (%d per category)…", num_per_category)
    prompts: list[TestPrompt] = generate_test_suite(
        num_per_category=num_per_category,
        categories=categories,
    )
    logger.info("Generated %d prompts.", len(prompts))

    # ------------------------------------------------------------------ #
    # 2. Execute both adapters concurrently                                #
    # ------------------------------------------------------------------ #
    logger.info("Executing both adapters concurrently…")
    results_a, results_b = await asyncio.gather(
        execute_test_suite(prompts, adapter_a),
        execute_test_suite(prompts, adapter_b),
    )

    # ------------------------------------------------------------------ #
    # 3. Judge both sets                                                   #
    # ------------------------------------------------------------------ #
    logger.info("Judging adapter A results…")
    judgments_a = judge_results(prompts, results_a)
    logger.info("Judging adapter B results…")
    judgments_b = judge_results(prompts, results_b)

    # ------------------------------------------------------------------ #
    # 4. Build DiffReport                                                  #
    # ------------------------------------------------------------------ #
    diff_report = _build_diff_report(
        prompts=prompts,
        judgments_a=judgments_a,
        judgments_b=judgments_b,
        adapter_a=adapter_a,
        adapter_b=adapter_b,
        run_id=resolved_run_id,
    )

    # ------------------------------------------------------------------ #
    # 5. Save JSON                                                         #
    # ------------------------------------------------------------------ #
    json_path = resolved_output_dir / f"diff_{resolved_run_id}.json"
    json_path.write_text(diff_report.model_dump_json(indent=2), encoding="utf-8")
    logger.info("DiffReport saved to %s", json_path)

    # ------------------------------------------------------------------ #
    # 6. Generate markdown                                                 #
    # ------------------------------------------------------------------ #
    md_path = resolved_output_dir / f"diff_{resolved_run_id}.md"
    md_path.write_text(_render_diff_markdown(diff_report), encoding="utf-8")
    logger.info("Diff markdown saved to %s", md_path)

    return json_path, md_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_diff_report(
    prompts: list[TestPrompt],
    judgments_a: list,
    judgments_b: list,
    adapter_a: TargetAdapter,
    adapter_b: TargetAdapter,
    run_id: str,
) -> DiffReport:
    """Compute the DiffReport from two sets of judgments."""
    prompt_map = {p.id: p for p in prompts}

    # Index by prompt_id
    ja_map = {j.prompt_id: j for j in judgments_a}
    jb_map = {j.prompt_id: j for j in judgments_b}

    regressions: list[dict[str, Any]] = []
    improvements: list[dict[str, Any]] = []
    per_judgment: list[dict[str, Any]] = []
    unchanged = 0

    a_pass = b_pass = 0

    for pid, ja in ja_map.items():
        jb = jb_map.get(pid)
        if jb is None:
            continue
        p = prompt_map.get(pid)
        category = p.category if p else "unknown"
        severity = p.severity if p else "unknown"

        if ja.passed:
            a_pass += 1
        if jb.passed:
            b_pass += 1

        row: dict[str, Any] = {
            "prompt_id": pid,
            "category": category,
            "severity": severity,
            "prompt_text": p.prompt[:120] if p else "",
            "a_passed": ja.passed,
            "b_passed": jb.passed,
            "a_score": ja.score,
            "b_score": jb.score,
            "a_failure_mode": ja.failure_mode.value if ja.failure_mode else None,
            "b_failure_mode": jb.failure_mode.value if jb.failure_mode else None,
            "a_reasoning": ja.reasoning[:200],
            "b_reasoning": jb.reasoning[:200],
        }
        per_judgment.append(row)

        if ja.passed and not jb.passed:
            regressions.append(row)
        elif not ja.passed and jb.passed:
            improvements.append(row)
        else:
            unchanged += 1

    total = len(per_judgment)
    a_rate = a_pass / total if total else 0.0
    b_rate = b_pass / total if total else 0.0

    return DiffReport(
        run_id=run_id,
        target_a_name=adapter_a.name,
        target_a_version=adapter_a.version,
        target_b_name=adapter_b.name,
        target_b_version=adapter_b.version,
        total_tests=total,
        a_pass_rate=round(a_rate, 4),
        b_pass_rate=round(b_rate, 4),
        pass_rate_delta=round(b_rate - a_rate, 4),
        regressions=regressions,
        improvements=improvements,
        unchanged=unchanged,
        per_judgment=per_judgment,
    )


def _render_diff_markdown(report: DiffReport) -> str:
    """Render a human-readable markdown diff report."""
    delta_sign = "+" if report.pass_rate_delta >= 0 else ""
    lines = [
        f"# Diff Report: {report.target_a_name} vs {report.target_b_name}",
        "",
        f"**Run ID:** {report.run_id}  ",
        f"**Date:** {report.timestamp.strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"**A:** {report.target_a_name} v{report.target_a_version}  ",
        f"**B:** {report.target_b_name} v{report.target_b_version}  ",
        "",
        "## Summary",
        "",
        "| Metric | A | B | Delta |",
        "|--------|---|---|-------|",
        f"| Pass rate | {report.a_pass_rate:.1%} | {report.b_pass_rate:.1%} | "
        f"{delta_sign}{report.pass_rate_delta:.1%} |",
        f"| Regressions | — | — | {len(report.regressions)} |",
        f"| Improvements | — | — | {len(report.improvements)} |",
        f"| Unchanged | {report.unchanged} | — | — |",
        "",
    ]

    # Regressions
    lines.append(f"## Regressions ({len(report.regressions)})")
    lines.append("")
    if report.regressions:
        lines.append("| Prompt ID | Category | Severity | B Failure Mode | A Reasoning (excerpt) |")
        lines.append("|-----------|----------|----------|---------------|----------------------|")
        for r in report.regressions:
            lines.append(
                f"| {r['prompt_id'][:12]} | {r['category']} | {r['severity']} | "
                f"{r['b_failure_mode'] or '—'} | {r['a_reasoning'][:60]}… |"
            )
    else:
        lines.append("No regressions — B performs at least as well as A on every prompt.")
    lines.append("")

    # Improvements
    lines.append(f"## Improvements ({len(report.improvements)})")
    lines.append("")
    if report.improvements:
        lines.append("| Prompt ID | Category | Severity | A Failure Mode | B Reasoning (excerpt) |")
        lines.append("|-----------|----------|----------|---------------|----------------------|")
        for r in report.improvements:
            lines.append(
                f"| {r['prompt_id'][:12]} | {r['category']} | {r['severity']} | "
                f"{r['a_failure_mode'] or '—'} | {r['b_reasoning'][:60]}… |"
            )
    else:
        lines.append("No improvements — B does not fix any failures that A had.")
    lines.append("")

    lines.append(f"## Unchanged ({report.unchanged})")
    lines.append("")
    lines.append(
        f"{report.unchanged} prompts had identical pass/fail outcomes between A and B."
    )

    return "\n".join(lines)
