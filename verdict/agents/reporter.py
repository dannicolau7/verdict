"""Reporter agent for the Verdict evaluation framework.

Architecture:
    Step 1 (deterministic): build_eval_report() computes all metrics in Python.
    Step 2 (LLM):           Reporter LLM writes prose around the pre-computed data.
    Step 3 (verification):  A post-generation check compares percentages in the
                            generated markdown against the EvalReport.  Mismatches
                            trigger one regeneration with explicit numbers injected.

    This separation means every number in the report is auditable — readers can
    open {run_id}.json and verify the math without trusting the LLM.

Output files:
    reports/{run_id}.json  — EvalReport serialized (source of truth)
    reports/{run_id}.md    — LLM-generated narrative report
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any

import anthropic

from verdict.agents.prompts.reporter_prompt import REPORT_TEMPLATE, SYSTEM_PROMPT
from verdict.config.settings import get_settings
from verdict.models.schemas import EvalReport, Judgment, TestPrompt
from verdict.reports.builder import build_eval_report

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CrewAI Agent factory (used in D9 crew assembly)
# ---------------------------------------------------------------------------


def create_reporter(model: str | None = None):  # -> crewai.Agent
    """Return a configured CrewAI Agent for the Reporter role.

    Uses Sonnet at temperature 0.3 — creative enough for varied prose but
    constrained enough to stay on-topic.

    Args:
        model: Anthropic model ID override.  Defaults to
               settings.default_reporter_model.
    """
    from crewai import Agent
    from langchain_anthropic import ChatAnthropic

    settings = get_settings()
    llm = ChatAnthropic(
        model=model or settings.default_reporter_model,
        temperature=0.3,
        anthropic_api_key=settings.anthropic_api_key.get_secret_value(),
    )
    return Agent(
        role="Evaluation Report Writer",
        goal=(
            "Produce clear, accurate evaluation reports that help engineering teams "
            "understand AI system failures and prioritize remediation."
        ),
        backstory=(
            "You are a technical writer who specialises in AI safety evaluation reports. "
            "You lead with the most important finding, cite specific evidence, and make "
            "every recommendation actionable.  You never fabricate metrics — you work "
            "only from pre-computed data provided to you."
        ),
        llm=llm,
        allow_delegation=False,
        verbose=False,
        max_iter=2,
        max_rpm=5,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_metrics_block(report: EvalReport) -> str:
    """Format the pre-computed metrics as a readable block for the LLM prompt."""
    lines = [
        f"Total tests: {report.total_tests}",
        f"Overall pass rate: {report.pass_rate * 100:.1f}%",
        f"Passed: {sum(1 for j in report.judgments if j.passed)}",
        f"Failed: {sum(1 for j in report.judgments if not j.passed)}",
        "",
        "Per-category breakdown:",
    ]
    for cat, data in report.category_breakdown.items():
        lines.append(
            f"  {cat}: {data['passed']}/{data['total']} passed "
            f"({data['pass_rate'] * 100:.1f}%), "
            f"critical failures: {len(data.get('critical_failures', []))}"
        )
        if data.get("avg_score") is not None:
            lines.append(f"    average score: {data['avg_score']:.2f}/5")
        if data.get("failure_modes"):
            lines.append(f"    failure modes: {data['failure_modes']}")
    return "\n".join(lines)


def _format_critical_failures(
    report: EvalReport, prompt_map: dict[str, TestPrompt]
) -> str:
    """Format critical failure details for the LLM prompt."""
    failures = []
    for j in report.judgments:
        p = prompt_map.get(j.prompt_id)
        if p and p.severity == "critical" and not j.passed:
            response_excerpt = (
                j.metadata.get("response_excerpt", "")
                or "[response not available]"
            )
            failures.append(
                f"ID: {j.prompt_id}\n"
                f"Category: {p.category}\n"
                f"Prompt: {p.prompt}\n"
                f"Failure mode: {j.failure_mode.value if j.failure_mode else 'other'}\n"
                f"Judge reasoning: {j.reasoning}\n"
            )
    if not failures:
        return "No critical failures in this run."
    return "\n---\n".join(failures)


def _format_judgments_summary(
    report: EvalReport, prompt_map: dict[str, TestPrompt]
) -> str:
    """Format a terse summary of all judgments for the LLM prompt."""
    lines = []
    for j in report.judgments:
        p = prompt_map.get(j.prompt_id)
        cat = p.category if p else "unknown"
        sev = p.severity if p else "unknown"
        result = "PASS" if j.passed else f"FAIL({j.failure_mode.value if j.failure_mode else 'other'})"
        score_str = f" score={j.score}" if j.score is not None else ""
        lines.append(f"  [{cat}/{sev}] {result}{score_str} — {j.reasoning[:80]}…")
    return "\n".join(lines)


def _extract_percentages(markdown: str) -> list[float]:
    """Extract all percentage values from a markdown string."""
    return [float(m) for m in re.findall(r"(\d+(?:\.\d+)?)\s*%", markdown)]


def _verify_markdown_metrics(markdown: str, report: EvalReport) -> bool:
    """Check that key percentages in the markdown match the EvalReport.

    Returns True if metrics look consistent, False if a mismatch is found.
    Uses ±1.0 tolerance to handle rounding differences.
    """
    overall_pct = round(report.pass_rate * 100, 1)
    # Check if the overall pass rate percentage appears (allow ±1.0)
    found_percentages = _extract_percentages(markdown)
    if not found_percentages:
        logger.warning("No percentages found in generated markdown.")
        return True  # Can't verify, proceed
    closest = min(found_percentages, key=lambda x: abs(x - overall_pct))
    if abs(closest - overall_pct) > 1.0:
        logger.warning(
            "Percentage mismatch: report says %.1f%% but markdown closest value is %.1f%%",
            overall_pct,
            closest,
        )
        return False
    return True


def _call_reporter(
    client: anthropic.Anthropic,
    model: str,
    report: EvalReport,
    prompt_map: dict[str, TestPrompt],
    force_numbers: bool = False,
) -> str:
    """Call the Reporter LLM and return the generated markdown."""
    metrics_block = _format_metrics_block(report)
    critical_failures_block = _format_critical_failures(report, prompt_map)
    judgments_summary = _format_judgments_summary(report, prompt_map)

    # Collect all critical failure IDs for the template
    all_critical_ids: list[str] = []
    for data in report.category_breakdown.values():
        all_critical_ids.extend(data.get("critical_failures", []))
    critical_ids_str = (
        f"({', '.join(all_critical_ids[:5])}{'…' if len(all_critical_ids) > 5 else ''})"
        if all_critical_ids
        else ""
    )

    extra_instruction = ""
    if force_numbers:
        extra_instruction = (
            f"\n\nCRITICAL: Use EXACTLY {report.pass_rate * 100:.1f}% as the overall "
            f"pass rate. Do not round or change this number."
        )

    user_prompt = REPORT_TEMPLATE.format(
        metrics_block=metrics_block + extra_instruction,
        critical_failures_block=critical_failures_block,
        judgments_summary=judgments_summary,
        target_name=report.target_system,
        run_id=report.run_id,
        timestamp=report.timestamp.strftime("%Y-%m-%d %H:%M UTC"),
        total_tests=report.total_tests,
        pass_rate_pct=f"{report.pass_rate * 100:.1f}",
        critical_failure_count=len(all_critical_ids),
        critical_failure_ids=critical_ids_str,
        num_categories=len(report.category_breakdown),
    )

    message = client.messages.create(
        model=model,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text  # type: ignore[index]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_report(
    judgments: list[Judgment],
    prompts: list[TestPrompt],
    target_name: str,
    run_id: str | None = None,
    output_dir: Path | None = None,
    model: str | None = None,
    target_version: str | None = None,
    metadata: dict[str, Any] | None = None,
    bootstrap_iterations: int = 1000,
) -> tuple[Path, Path]:
    """Generate a JSON + markdown evaluation report.

    Flow:
        1. Compute EvalReport deterministically (no LLM).
        2. Save {run_id}.json.
        3. Call Reporter LLM to write the markdown narrative.
        4. Verify percentages in the markdown match the EvalReport.
           If they don't, regenerate once with explicit numbers.
        5. Save {run_id}.md.
        6. Return (json_path, md_path).

    Args:
        judgments:      All Judgment objects for this run.
        prompts:        All TestPrompt objects for this run.
        target_name:    Name of the adapter/system under test.
        run_id:         Unique run ID. Generated if not provided.
        output_dir:     Directory for output files. Defaults to settings.reports_dir.
        model:          Anthropic model ID override.
        target_version: Optional version string from the adapter.
        metadata:       Optional extra data for the EvalReport.

    Returns:
        (json_path, md_path) — paths to the saved files.

    Raises:
        ValueError: If judgments is empty.
    """
    settings = get_settings()
    resolved_model = model or settings.default_reporter_model
    resolved_run_id = run_id or uuid.uuid4().hex[:8]
    resolved_output_dir = output_dir or settings.reports_dir
    resolved_output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Step 1: Cost attribution (R6) — extract judge tokens from metadata  #
    # ------------------------------------------------------------------ #
    from verdict.costs.calculator import compute_run_costs
    from verdict.observability.token_tracker import TokenTracker

    tracker = TokenTracker()
    # Collect target tokens from execution_results if present in metadata
    exec_results = (metadata or {}).get("execution_results", [])
    tracker.absorb_execution_results(exec_results)
    # Collect judge tokens from judgment metadata
    for j in judgments:
        tu = j.metadata.get("_token_usage")
        jm = j.metadata.get("_model") or j.judge_model
        if tu:
            tracker.record_from_usage("judge", jm, tu)

    flat = tracker.get_flat_counts()
    target_execution_results = list(exec_results)
    cost_breakdown = compute_run_costs(
        execution_results=target_execution_results,
        harness_token_counts={k: v for k, v in flat.items() if k != "target"},
        harness_models={"judge": settings.default_judge_model},
    )

    # ------------------------------------------------------------------ #
    # Step 2: Deterministic report                                        #
    # ------------------------------------------------------------------ #
    # Remove execution_results from metadata before storing (too large)
    clean_metadata = {k: v for k, v in (metadata or {}).items() if k != "execution_results"}
    report = build_eval_report(
        judgments=judgments,
        prompts=prompts,
        target_name=target_name,
        run_id=resolved_run_id,
        target_version=target_version,
        metadata=clean_metadata,
        bootstrap_iterations=bootstrap_iterations,
    )
    report.cost_breakdown = cost_breakdown

    prompt_map: dict[str, TestPrompt] = {p.id: p for p in prompts}

    # ------------------------------------------------------------------ #
    # Step 3: Save JSON                                                   #
    # ------------------------------------------------------------------ #
    json_path = resolved_output_dir / f"{resolved_run_id}.json"
    json_path.write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )
    logger.info("EvalReport saved to %s", json_path)

    # ------------------------------------------------------------------ #
    # Step 4: LLM prose generation                                        #
    # ------------------------------------------------------------------ #
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
    markdown = _call_reporter(client, resolved_model, report, prompt_map)

    # ------------------------------------------------------------------ #
    # Step 5: Verify metrics; regenerate if mismatch                     #
    # ------------------------------------------------------------------ #
    if not _verify_markdown_metrics(markdown, report):
        logger.warning(
            "Metric mismatch detected in generated markdown — regenerating with explicit numbers."
        )
        markdown = _call_reporter(
            client, resolved_model, report, prompt_map, force_numbers=True
        )
        if not _verify_markdown_metrics(markdown, report):
            logger.warning(
                "Metric mismatch persists after regeneration. Proceeding anyway — "
                "the JSON report (%s) remains the authoritative source.",
                json_path,
            )

    # ------------------------------------------------------------------ #
    # Step 6: Save markdown                                               #
    # ------------------------------------------------------------------ #
    md_path = resolved_output_dir / f"{resolved_run_id}.md"
    md_path.write_text(markdown, encoding="utf-8")
    logger.info("Markdown report saved to %s", md_path)

    return json_path, md_path
