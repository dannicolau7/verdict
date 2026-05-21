"""End-to-end evaluation of SimpleRAGAdapter using Verdict Phase 2 agents.

Usage:
    python examples/eval_simple_rag.py

This script exercises D5 (generate) and D6 (execute) and prints a summary
table to the terminal using Rich.  D7 (judge) and D8 (report) are not
included here — see the Phase 2 smoke test in the project docs for the
full pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from rich.console import Console
from rich.table import Table

from verdict.adapters.simple_rag import SimpleRAGAdapter
from verdict.agents.executor import execute_test_suite
from verdict.agents.test_generator import generate_test_suite

logging.basicConfig(level=logging.WARNING)  # suppress verbose LLM logs in demo
console = Console()


async def _run() -> None:
    console.rule("[bold blue]Verdict — SimpleRAG Evaluation")

    # ------------------------------------------------------------------ #
    # Step 1: Generate 10 test prompts (2 per category)                  #
    # ------------------------------------------------------------------ #
    console.print("\n[bold]Step 1:[/bold] Generating 10 test prompts (2 per category)…")
    prompts = generate_test_suite(num_per_category=2)
    console.print(f"  [green]✓[/green] Generated {len(prompts)} prompts.")

    if not prompts:
        console.print("[red]No prompts generated — check your ANTHROPIC_API_KEY.[/red]")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # Step 2: Execute against SimpleRAGAdapter                           #
    # ------------------------------------------------------------------ #
    console.print("\n[bold]Step 2:[/bold] Executing prompts against SimpleRAGAdapter…")
    adapter = SimpleRAGAdapter()
    results = await execute_test_suite(prompts, adapter)
    console.print(f"  [green]✓[/green] Received {len(results)} responses.")

    # ------------------------------------------------------------------ #
    # Step 3: Print summary table                                        #
    # ------------------------------------------------------------------ #
    console.print("\n[bold]Step 3:[/bold] Results summary\n")

    # Build prompt_id -> prompt lookup for display
    prompt_map = {p.id: p for p in prompts}

    table = Table(
        title="SimpleRAG Evaluation Results",
        show_lines=True,
        header_style="bold cyan",
    )
    table.add_column("#", style="dim", width=3)
    table.add_column("Category", width=12)
    table.add_column("Severity", width=9)
    table.add_column("Prompt (truncated)", width=38)
    table.add_column("Response (truncated)", width=38)
    table.add_column("Latency", width=9)
    table.add_column("Error?", width=7)

    for i, result in enumerate(results, start=1):
        p = prompt_map.get(result.prompt_id)
        category = p.category if p else "?"
        severity = p.severity if p else "?"
        prompt_text = (p.prompt[:35] + "…") if p and len(p.prompt) > 35 else (p.prompt if p else "?")
        resp_text = (result.response[:35] + "…") if len(result.response) > 35 else result.response
        latency = f"{result.latency_ms:.0f}ms"
        has_error = "[red]yes[/red]" if result.error else "[green]no[/green]"

        severity_color = {
            "low": "green",
            "medium": "yellow",
            "high": "orange1",
            "critical": "red",
        }.get(severity, "white")

        table.add_row(
            str(i),
            category,
            f"[{severity_color}]{severity}[/{severity_color}]",
            prompt_text,
            resp_text,
            latency,
            has_error,
        )

    console.print(table)

    # Error summary
    errors = [r for r in results if r.error]
    if errors:
        console.print(f"\n[yellow]⚠[/yellow]  {len(errors)} execution(s) returned errors:")
        for r in errors:
            console.print(f"   prompt_id={r.prompt_id[:8]}… error={r.error}")
    else:
        console.print("\n[green]✓[/green]  All executions completed without errors.")

    total_tokens = sum(r.token_count or 0 for r in results)
    console.print(f"\n[dim]Total tokens consumed: {total_tokens}[/dim]")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
