"""Verdict CLI — evaluation infrastructure for AI agents.

Commands:
    verdict eval       Run a full evaluation against a target adapter.
    verdict diff       Compare two adapter versions on the same test suite.
    verdict flakiness  Analyze historical run variance for a target system.

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
@click.option("--target", required=True, help="Adapter spec: 'simple_rag' or 'path/to/file.py:ClassName'")
@click.option("--num-per-category", default=5, show_default=True, help="Prompts per category.")
@click.option("--categories", multiple=True, help="Specific categories (repeat flag for multiple).")
@click.option("--output-dir", type=click.Path(), default=None, help="Report output directory.")
@click.option("--run-id", default=None, help="Custom run ID.")
@click.option("--model", default=None, help="Override LLM model for all agents.")
# R3 — bootstrap CI
@click.option("--bootstrap-iterations", default=1000, show_default=True,
              help="Bootstrap CI iterations (0 to disable).")
# R5 — guardrails
@click.option("--max-cost-usd", type=float, default=None,
              help="Fail if total cost exceeds this USD amount.")
@click.option("--max-total-latency-seconds", type=float, default=None,
              help="Fail if total run latency exceeds this in seconds.")
@click.option("--fail-on-pass-rate-below", type=float, default=None,
              help="Fail if pass_rate < threshold (0.0–1.0).")
@click.option("--fail-on-ci-low-below", type=float, default=None,
              help="Fail if CI lower bound < threshold. Requires --bootstrap-iterations > 0.")
# R4 — caching
@click.option("--cache-mode", type=click.Choice(["off", "record", "replay", "update"]),
              default="off", show_default=True, help="Response caching mode.")
@click.option("--cache-dir", type=click.Path(), default=".verdict_cache",
              show_default=True, help="Directory for cache files.")
# R9 — adaptive probes
@click.option("--adaptive", is_flag=True, default=False,
              help="Run adaptive follow-up probes based on initial responses.")
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
    from verdict.agents.executor import execute_test_suite
    from verdict.agents.judge import judge_results
    from verdict.agents.reporter import generate_report
    from verdict.agents.test_generator import generate_test_suite
    from verdict.caching.cache import CacheMode as CM
    from verdict.cli_utils.guardrails import check_guardrails

    cache_mode_enum = CM(cache_mode)
    adapter = _load_adapter(target, cache_mode=cache_mode_enum, cache_dir=cache_dir)
    cat_list = list(categories) if categories else None

    console.rule("[bold blue]Verdict Evaluation")
    console.print(f"  Target:    [cyan]{target}[/cyan]")
    console.print(f"  Prompts:   {num_per_category} per category")
    console.print(f"  Cache:     {cache_mode}")

    # 1. Generate
    console.print("\n[bold]Generating test prompts…[/bold]")
    prompts = generate_test_suite(
        num_per_category=num_per_category,
        categories=cat_list,
        model=model,
    )
    console.print(f"  [green]✓[/green] {len(prompts)} prompts generated.")

    # 2. Execute
    console.print("\n[bold]Executing against target…[/bold]")
    results = asyncio.run(execute_test_suite(prompts, adapter))
    errors = sum(1 for r in results if r.error)
    console.print(f"  [green]✓[/green] {len(results)} responses received ({errors} errors).")

    # 2b. Adaptive follow-up probes (R9, optional)
    if adaptive:
        from verdict.agents.adaptive_generator import AdaptiveTestGenerator

        console.print("\n[bold]Generating adaptive follow-up probes…[/bold]")
        gen = AdaptiveTestGenerator()
        adaptive_prompts = []
        for result in results:
            probe = gen.next_probe(result)
            if probe is not None:
                adaptive_prompts.append(probe)

        if adaptive_prompts:
            console.print(f"  [cyan]→[/cyan] {len(adaptive_prompts)} adaptive probes queued.")
            adaptive_results = asyncio.run(execute_test_suite(adaptive_prompts, adapter))
            prompts = list(prompts) + adaptive_prompts
            results = list(results) + adaptive_results
            console.print("  [green]✓[/green] Adaptive probes executed.")
        else:
            console.print("  [yellow]No adaptive probes selected (pattern library exhausted or empty).[/yellow]")

    # 3. Judge
    console.print("\n[bold]Judging results…[/bold]")
    judgments = judge_results(prompts, results, judge_models=[model] if model else None)
    passed = sum(1 for j in judgments if j.passed)
    console.print(f"  [green]✓[/green] {passed}/{len(judgments)} passed.")

    # 4. Report
    console.print("\n[bold]Generating report…[/bold]")
    out_path = Path(output_dir) if output_dir else None
    json_path, md_path = generate_report(
        judgments=judgments,
        prompts=prompts,
        target_name=getattr(adapter, "name", target),
        run_id=run_id,
        output_dir=out_path,
        model=model,
        target_version=getattr(adapter, "version", None),
        metadata={"execution_results": results},
        bootstrap_iterations=bootstrap_iterations,
    )
    console.print(f"  [green]✓[/green] JSON: {json_path}")
    console.print(f"  [green]✓[/green] Markdown: {md_path}")

    # 5. Cache stats
    stats = adapter.cache_stats
    if stats["hits"] + stats["misses"] + stats["writes"] > 0:
        console.print(
            f"\n  Cache: {stats['hits']} hits, {stats['misses']} misses, {stats['writes']} writes"
        )

    # 6. Guardrails
    # Load the EvalReport to get CI values
    import json as _json
    report_data = _json.loads(json_path.read_text())
    from verdict.models.schemas import EvalReport
    report = EvalReport(**report_data)

    passed_all, breaches = check_guardrails(
        report,
        max_cost_usd=max_cost_usd,
        max_total_latency_seconds=max_total_latency_seconds,
        fail_on_pass_rate_below=fail_on_pass_rate_below,
        fail_on_ci_low_below=fail_on_ci_low_below,
    )
    if not passed_all:
        console.print("\n[bold red]Guardrail breaches:[/bold red]")
        for msg in breaches:
            console.print(f"  [red]✗[/red] {msg}")
        console.print(
            "\n[yellow]Report saved. Exiting with code 2 (guardrail breach).[/yellow]"
        )
        sys.exit(2)
    else:
        ci_str = ""
        if report.pass_rate_ci_low is not None:
            ci_str = f" (95% CI: {report.pass_rate_ci_low:.1%}–{report.pass_rate_ci_high:.1%})"
        console.print(
            f"\n[bold green]✓ Evaluation complete.[/bold green] "
            f"Pass rate: {report.pass_rate:.1%}{ci_str}"
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
@click.option("--cache-mode", type=click.Choice(["off", "record", "replay", "update"]),
              default="off", show_default=True)
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
@click.option("--target", required=True, help="Target system name (matches EvalReport.target_system).")
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


if __name__ == "__main__":
    main()
