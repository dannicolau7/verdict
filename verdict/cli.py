"""Verdict CLI — evaluation infrastructure for AI agents.

Commands:
    verdict eval        Run a full evaluation against a target adapter.
    verdict diff        Compare two adapter versions on the same test suite.
    verdict flakiness   Analyze historical run variance for a target system.
    verdict compliance  Map an eval report to HIPAA + NIST AI RMF controls.

Adapter spec format:
    Built-in shorthand:  simple_rag  (maps to verdict.adapters.simple_rag.SimpleRAGAdapter)
    External file:       path/to/adapter.py:ClassName
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Adapter loader
# ---------------------------------------------------------------------------


def _load_adapter(spec: str, **kwargs: Any):
    """Load a TargetAdapter from a spec string.

    Spec formats:
        "simple_rag"                     -> built-in SimpleRAGAdapter
        "echo"                           -> built-in EchoAdapter (tests only)
        "path/to/adapter.py:ClassName"  -> load from file
    """
    from verdict.adapters.base import TargetAdapter

    BUILTINS = {
        "simple_rag": ("verdict.adapters.simple_rag", "SimpleRAGAdapter"),
    }

    if spec in BUILTINS:
        module_path, class_name = BUILTINS[spec]
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
    elif ":" in spec:
        file_path, class_name = spec.rsplit(":", 1)
        file_path = str(Path(file_path).resolve())
        mod_spec = importlib.util.spec_from_file_location("_verdict_adapter", file_path)
        if mod_spec is None or mod_spec.loader is None:
            raise click.ClickException(f"Cannot load adapter from {file_path!r}")
        mod = importlib.util.module_from_spec(mod_spec)
        mod_spec.loader.exec_module(mod)  # type: ignore[union-attr]
        cls = getattr(mod, class_name)
    else:
        raise click.ClickException(
            f"Unknown adapter spec {spec!r}. "
            "Use a built-in name (e.g., 'simple_rag') or 'path/to/file.py:ClassName'."
        )

    if not issubclass(cls, TargetAdapter):
        raise click.ClickException(f"{cls} is not a TargetAdapter subclass.")

    return cls(**kwargs)


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging.")
def main(debug: bool) -> None:
    """Verdict: evaluation infrastructure for AI agents."""
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


# ---------------------------------------------------------------------------
# verdict eval
# ---------------------------------------------------------------------------


@main.command("eval")
@click.option(
    "--target", required=True, help="Adapter spec: 'simple_rag' or 'path/to/file.py:ClassName'"
)
@click.option("--num-per-category", default=5, show_default=True, help="Prompts per category.")
@click.option("--categories", multiple=True, help="Specific categories (repeat flag for multiple).")
@click.option("--output-dir", type=click.Path(), default=None, help="Report output directory.")
@click.option("--run-id", default=None, help="Custom run ID.")
@click.option("--model", default=None, help="Override LLM model for all agents.")
# R3 — bootstrap CI
@click.option(
    "--bootstrap-iterations",
    default=1000,
    show_default=True,
    help="Bootstrap CI iterations (0 to disable).",
)
# R5 — guardrails
@click.option(
    "--max-cost-usd", type=float, default=None, help="Fail if total cost exceeds this USD amount."
)
@click.option(
    "--max-total-latency-seconds",
    type=float,
    default=None,
    help="Fail if total run latency exceeds this in seconds.",
)
@click.option(
    "--fail-on-pass-rate-below",
    type=float,
    default=None,
    help="Fail if pass_rate < threshold (0.0–1.0).",
)
@click.option(
    "--fail-on-ci-low-below",
    type=float,
    default=None,
    help="Fail if CI lower bound < threshold. Requires --bootstrap-iterations > 0.",
)
# R4 — caching
@click.option(
    "--cache-mode",
    type=click.Choice(["off", "record", "replay", "update"]),
    default="off",
    show_default=True,
    help="Response caching mode.",
)
@click.option(
    "--cache-dir",
    type=click.Path(),
    default=".verdict_cache",
    show_default=True,
    help="Directory for cache files.",
)
# R9 — adaptive probes
@click.option(
    "--adaptive",
    is_flag=True,
    default=False,
    help="Run adaptive follow-up probes based on initial responses.",
)
def eval_cmd(
    target: str,
    num_per_category: int,
    categories: tuple,
    output_dir: str | None,
    run_id: str | None,
    model: str | None,
    bootstrap_iterations: int,
    max_cost_usd: float | None,
    max_total_latency_seconds: float | None,
    fail_on_pass_rate_below: float | None,
    fail_on_ci_low_below: float | None,
    cache_mode: str,
    cache_dir: str,
    adaptive: bool,
) -> None:
    """Run a full evaluation against a target adapter."""
    from verdict.caching.cache import CacheMode as CM
    from verdict.cli_utils.guardrails import check_guardrails
    from verdict.crews.eval_crew import EvalCrew

    cache_mode_enum = CM(cache_mode)
    adapter = _load_adapter(target, cache_mode=cache_mode_enum, cache_dir=cache_dir)
    cat_list = list(categories) if categories else None

    console.rule("[bold blue]Verdict Evaluation")
    console.print(f"  Target:    [cyan]{target}[/cyan]")
    console.print(f"  Prompts:   {num_per_category} per category")
    console.print(f"  Cache:     {cache_mode}")

    _STAGE_HEADERS = {
        "generate": "\n[bold]Generating test prompts…[/bold]",
        "execute": "\n[bold]Executing against target…[/bold]",
        "adaptive": "\n[bold]Generating adaptive follow-up probes…[/bold]",
        "judge": "\n[bold]Judging results…[/bold]",
        "report": "\n[bold]Generating report…[/bold]",
    }
    _current_stage: list[str] = []

    def _on_progress(stage: str, detail: str) -> None:
        if not _current_stage or _current_stage[-1] != stage:
            _current_stage.clear()
            _current_stage.append(stage)
            if stage in _STAGE_HEADERS:
                console.print(_STAGE_HEADERS[stage])
        console.print(f"  [green]✓[/green] {detail}")

    crew = EvalCrew(
        adapter=adapter,
        num_per_category=num_per_category,
        categories=cat_list,
        model=model,
        run_id=run_id,
        output_dir=Path(output_dir) if output_dir else None,
        bootstrap_iterations=bootstrap_iterations,
        adaptive=adaptive,
    )
    ev = crew.kickoff(on_progress=_on_progress)

    # Cache stats
    stats = adapter.cache_stats
    if stats["hits"] + stats["misses"] + stats["writes"] > 0:
        console.print(
            f"\n  Cache: {stats['hits']} hits, {stats['misses']} misses, {stats['writes']} writes"
        )

    # Guardrails
    passed_all, breaches = check_guardrails(
        ev.report,
        max_cost_usd=max_cost_usd,
        max_total_latency_seconds=max_total_latency_seconds,
        fail_on_pass_rate_below=fail_on_pass_rate_below,
        fail_on_ci_low_below=fail_on_ci_low_below,
    )
    if not passed_all:
        console.print("\n[bold red]Guardrail breaches:[/bold red]")
        for msg in breaches:
            console.print(f"  [red]✗[/red] {msg}")
        console.print("\n[yellow]Report saved. Exiting with code 2 (guardrail breach).[/yellow]")
        sys.exit(2)
    else:
        ci_str = ""
        if ev.report.pass_rate_ci_low is not None:
            ci_str = (
                f" (95% CI: {ev.report.pass_rate_ci_low:.1%}–{ev.report.pass_rate_ci_high:.1%})"
            )
        console.print(
            f"\n[bold green]✓ Evaluation complete.[/bold green] "
            f"Pass rate: {ev.report.pass_rate:.1%}{ci_str}"
        )


# ---------------------------------------------------------------------------
# verdict diff
# ---------------------------------------------------------------------------


@main.command("diff")
@click.option("--target-a", required=True, help="Adapter A spec.")
@click.option("--target-b", required=True, help="Adapter B spec.")
@click.option("--num", default=5, show_default=True, help="Prompts per category.")
@click.option("--categories", multiple=True)
@click.option("--output-dir", type=click.Path(), default=None)
@click.option("--run-id", default=None)
@click.option(
    "--cache-mode",
    type=click.Choice(["off", "record", "replay", "update"]),
    default="off",
    show_default=True,
)
@click.option("--cache-dir", type=click.Path(), default=".verdict_cache", show_default=True)
def diff_cmd(
    target_a: str,
    target_b: str,
    num: int,
    categories: tuple,
    output_dir: str | None,
    run_id: str | None,
    cache_mode: str,
    cache_dir: str,
) -> None:
    """Compare two adapter versions against the same test suite."""
    from verdict.caching.cache import CacheMode as CM
    from verdict.orchestration.diff import run_diff

    cm = CM(cache_mode)
    adapter_a = _load_adapter(target_a, cache_mode=cm, cache_dir=cache_dir)
    adapter_b = _load_adapter(target_b, cache_mode=cm, cache_dir=cache_dir)
    cat_list = list(categories) if categories else None
    out_path = Path(output_dir) if output_dir else None

    console.rule("[bold blue]Verdict Diff")
    json_path, md_path = asyncio.run(
        run_diff(
            adapter_a=adapter_a,
            adapter_b=adapter_b,
            num_per_category=num,
            categories=cat_list,
            output_dir=out_path,
            run_id=run_id,
        )
    )
    console.print(f"[green]✓[/green] JSON: {json_path}")
    console.print(f"[green]✓[/green] Markdown: {md_path}")


# ---------------------------------------------------------------------------
# verdict flakiness
# ---------------------------------------------------------------------------


@main.command("flakiness")
@click.option(
    "--target", required=True, help="Target system name (matches EvalReport.target_system)."
)
@click.option("--min-runs", default=3, show_default=True, help="Minimum historical runs required.")
@click.option("--reports-dir", type=click.Path(), default="./reports", show_default=True)
@click.option("--output", type=click.Path(), default=None, help="Save flakiness JSON to file.")
def flakiness_cmd(
    target: str,
    min_runs: int,
    reports_dir: str,
    output: str | None,
) -> None:
    """Analyze historical run variance for a target system."""
    import json as _json

    from verdict.analysis.flakiness import analyze_flakiness

    report_path = Path(reports_dir)
    result = analyze_flakiness(report_path, target_system=target, min_runs=min_runs)

    if result is None:
        console.print(
            f"[yellow]Not enough historical runs for {target!r} "
            f"(need at least {min_runs}).[/yellow]"
        )
        return

    if output:
        Path(output).write_text(_json.dumps(result, indent=2), encoding="utf-8")
        console.print(f"[green]✓[/green] Flakiness report saved to {output}")

    # Print summary table
    table = Table(title=f"Flakiness Analysis: {target}", header_style="bold cyan")
    table.add_column("Prompt ID", width=20)
    table.add_column("Category", width=12)
    table.add_column("Disagree Rate", width=14)
    table.add_column("N Runs", width=7)

    for item in result.get("judge_flakiness", {}).get("flaky_prompts", []):
        table.add_row(
            item["prompt_id"][:18],
            item.get("category", "?"),
            f"{item['disagreement_rate']:.1%}",
            str(item["n_runs"]),
        )

    console.print(table)
    console.print(
        f"\nOverall judge consistency: "
        f"{result.get('judge_flakiness', {}).get('overall_judge_consistency', 'N/A')}"
    )


@main.command("compliance")
@click.option(
    "--report",
    required=True,
    type=click.Path(exists=True),
    help="Path to an EvalReport JSON file produced by `verdict eval`.",
)
@click.option(
    "--output-dir",
    type=click.Path(),
    default="./compliance",
    show_default=True,
    help="Directory where compliance artifacts are written.",
)
def compliance_cmd(report: str, output_dir: str) -> None:
    """Map an eval report to HIPAA Security Rule and NIST AI RMF controls.

    Reads the JSON report at --report and produces two files in --output-dir:

    \b
      compliance_{run_id}.json  machine-readable audit artifact
      compliance_{run_id}.md    human-readable control-by-control report

    Accepts both EvalReport (from `verdict eval`) and TraceEvalReport
    (from `verdict trace-eval`).
    """
    import json as _json

    from verdict.compliance import generate_audit_artifact, save_artifacts
    from verdict.models.schemas import EvalReport
    from verdict.models.trace_schemas import TraceEvalReport

    raw = _json.loads(Path(report).read_text(encoding="utf-8"))

    eval_report: EvalReport | TraceEvalReport
    try:
        eval_report = EvalReport(**raw)
        is_trace = False
    except Exception:
        try:
            eval_report = TraceEvalReport(**raw)
            is_trace = True
        except Exception as exc:
            console.print(f"[red]Failed to load report as EvalReport or TraceEvalReport:[/red] {exc}")
            raise SystemExit(1) from exc

    if is_trace:
        assert isinstance(eval_report, TraceEvalReport)
        console.print(
            f"[bold]Mapping[/bold] {eval_report.total_traces} trace judgments to compliance controls…"
        )
    else:
        assert isinstance(eval_report, EvalReport)
        console.print(f"[bold]Mapping[/bold] {eval_report.total_tests} judgments to compliance controls…")

    artifact = generate_audit_artifact(eval_report)
    run_id_val = eval_report.run_id
    json_path, md_path = save_artifacts(artifact, Path(output_dir), run_id_val)

    # Summary table
    controls = artifact["controls"]
    statuses = [c["overall_status"] for c in controls]
    n_pass = statuses.count("pass")
    n_partial = statuses.count("partial")
    n_fail = statuses.count("fail")
    n_insuf = statuses.count("insufficient_data")

    table = Table(title="Compliance Control Summary", header_style="bold cyan")
    table.add_column("Control", width=30)
    table.add_column("Framework", width=22)
    table.add_column("Status", width=14)
    table.add_column("Pass Rate", width=10)
    table.add_column("Confidence", width=11)

    status_colors = {"pass": "green", "partial": "yellow", "fail": "red", "insufficient_data": "dim"}
    for ctrl in controls:
        color = status_colors.get(ctrl["overall_status"], "white")
        pr_str = f"{ctrl['overall_pass_rate']:.1%}" if ctrl["overall_pass_rate"] is not None else "—"
        table.add_row(
            ctrl["id"],
            ctrl["framework"],
            f"[{color}]{ctrl['overall_status'].upper()}[/{color}]",
            pr_str,
            ctrl["confidence"].capitalize(),
        )

    console.print(table)
    console.print(
        f"\n[bold]Results:[/bold] "
        f"[green]{n_pass} pass[/green]  "
        f"[yellow]{n_partial} partial[/yellow]  "
        f"[red]{n_fail} fail[/red]  "
        f"[dim]{n_insuf} insufficient[/dim]"
    )
    console.print(f"\n[green]✓[/green] JSON artifact → {json_path}")
    console.print(f"[green]✓[/green] Markdown report → {md_path}")


@main.command("trace-eval")
@click.option(
    "--trace",
    "trace_path",
    type=click.Path(),
    default=None,
    help="Path to a single AgentTrace JSON file.",
)
@click.option(
    "--traces-dir",
    type=click.Path(),
    default=None,
    help="Directory containing AgentTrace JSON files.",
)
@click.option(
    "--agent-name",
    default=None,
    help="Agent name override (inferred from traces if omitted).",
)
@click.option(
    "--judge-model",
    default=None,
    help="Override judge model for trace evaluation.",
)
@click.option(
    "--output-dir",
    type=click.Path(),
    default="./trace_reports",
    show_default=True,
    help="Directory where trace eval reports are written.",
)
@click.option("--run-id", default=None, help="Custom run identifier.")
def trace_eval_cmd(
    trace_path: str | None,
    traces_dir: str | None,
    agent_name: str | None,
    judge_model: str | None,
    output_dir: str,
    run_id: str | None,
) -> None:
    """Evaluate agent execution traces against expected behavior.

    Load Verdict-native AgentTrace JSON files, judge each trace with the
    trace judge LLM, and produce a TraceEvalReport.

    \b
    Examples:
        verdict trace-eval --trace my_trace.json
        verdict trace-eval --traces-dir ./traces/ --output-dir ./reports
    """
    import json as _json

    from verdict.adapters.trace_ingestor import load_traces
    from verdict.agents.trace_judge import judge_traces
    from verdict.reports.trace_builder import build_trace_eval_markdown, build_trace_eval_report

    if trace_path is None and traces_dir is None:
        raise click.UsageError("Provide either --trace or --traces-dir.")
    if trace_path is not None and traces_dir is not None:
        raise click.UsageError("--trace and --traces-dir are mutually exclusive.")

    source = Path(trace_path) if trace_path else Path(traces_dir)  # type: ignore[arg-type]

    console.rule("[bold blue]Verdict Trace Eval")
    console.print(f"  Source: [cyan]{source}[/cyan]")

    try:
        traces = load_traces(source)
    except (FileNotFoundError, ValueError) as exc:
        console.print(f"[red]Failed to load traces:[/red] {exc}")
        raise SystemExit(1) from exc

    resolved_agent = agent_name or (traces[0].agent_name if traces else "unknown")
    console.print(f"  Agent:  [cyan]{resolved_agent}[/cyan]")
    console.print(f"  Traces: {len(traces)}\n")

    console.print("[bold]Judging traces…[/bold]")
    models = [judge_model] if judge_model else None
    judgments = judge_traces(traces, judge_models=models)

    for j, trace in zip(judgments, traces):
        status = "[green]PASS[/green]" if j.overall_passed else "[red]FAIL[/red]"
        fms = ", ".join(fm.value for fm in j.failure_modes) if j.failure_modes else "—"
        console.print(f"  {status}  {trace.trace_id[:16]}…  {fms}")

    report = build_trace_eval_report(
        judgments,
        agent_name=resolved_agent,
        run_id=run_id,
    )

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"trace_eval_{report.run_id[:8]}.json"
    md_path = out_dir / f"trace_eval_{report.run_id[:8]}.md"

    json_path.write_text(
        _json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    md_path.write_text(build_trace_eval_markdown(report), encoding="utf-8")

    # Summary table
    table = Table(title="Trace Eval Summary", header_style="bold cyan")
    table.add_column("Trace ID", width=20)
    table.add_column("Passed", width=8)
    table.add_column("Score", width=7)
    table.add_column("Failure Modes", width=35)

    for j in report.trace_judgments:
        color = "green" if j.overall_passed else "red"
        status_str = f"[{color}]{'YES' if j.overall_passed else 'NO'}[/{color}]"
        score_str = str(j.overall_score) if j.overall_score is not None else "—"
        fms = ", ".join(fm.value for fm in j.failure_modes)[:33] or "—"
        table.add_row(j.trace_id[:18] + "…", status_str, score_str, fms)

    console.print(table)

    ci_str = ""
    if report.pass_rate_ci_low is not None:
        ci_str = f" (95% CI: {report.pass_rate_ci_low:.1%}–{report.pass_rate_ci_high:.1%})"
    console.print(
        f"\n[bold]Pass rate:[/bold] {report.pass_rate:.1%}{ci_str}"
        f"  ({sum(1 for j in judgments if j.overall_passed)}/{report.total_traces} passing)"
    )
    console.print(f"\n[green]✓[/green] JSON report → {json_path}")
    console.print(f"[green]✓[/green] Markdown report → {md_path}")


if __name__ == "__main__":
    main()
