"""Render a DiffResult as a PR comment (Markdown) and as JSON.

Comment order: verdict line, gate breaches, regressions, failing cases, summary table,
then every case in a collapsed <details>. Tables stay narrow so they read on a phone.
The first line is a hidden marker so a CI action can find and update its own comment.
"""

from __future__ import annotations

import json

from verdict.ci.diff import CaseDiff, DiffResult, SideStats

COMMENT_MARKER = "<!-- verdict-diff -->"
_MAX_ROWS = 15


def _cell(text: str, limit: int = 60) -> str:
    text = " ".join(text.split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _rate(s: SideStats) -> str:
    return f"{s.pass_rate:.0%} ({s.ci_low:.0%}–{s.ci_high:.0%})"


def _runs(s: SideStats) -> str:
    return f"{s.passed}/{s.n}"


def _p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def _pts(delta: float) -> str:
    return f"{delta * 100:+.1f} pts"


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{x:+.1%}"


def render_markdown(result: DiffResult) -> str:
    refs = f"`{result.base_ref}` {result.base_sha[:7]} → `{result.head_ref}` {result.head_sha[:7]}"
    lines = [COMMENT_MARKER]

    if result.status == "skipped":
        lines += [
            "### ⏭️ Verdict: skipped",
            "",
            f"{refs} · no files matching the `watch` globs changed.",
        ]
        return "\n".join(lines) + "\n"

    assert result.suite is not None
    suite = result.suite
    method = "Fisher's exact" if result.stats_method == "fisher" else "bootstrap"
    if not result.gate.passed:
        head = "### ❌ Verdict: regression detected"
    elif result.regressions:
        head = "### ⚠️ Verdict: gate passed, some cases regressed"
    else:
        head = "### ✅ Verdict: no regression"
    lines += [
        head,
        "",
        f"{refs}  ",
        f"{result.n_cases} cases × {result.runs} runs · pass rate "
        f"**{suite.base.pass_rate:.1%} → {suite.head.pass_rate:.1%}** "
        f"({_pts(suite.delta)}, p={_p(suite.p_value)}, {method})",
        "",
    ]

    breaches = result.gate.breaches
    if breaches:
        lines += ["**Gate breached**", ""]
        lines += [f"- ❌ {c.detail}" for c in breaches]
        lines.append("")

    regs = result.regressions
    if regs:
        lines += [f"#### Regressions ({len(regs)})", "", "| Case | Base | Head | p |", "|---|---|---|---|"]
        for c in sorted(regs, key=lambda c: (c.delta, c.p_value))[:_MAX_ROWS]:
            lines.append(f"| `{_cell(c.case_id, 40)}` | {_runs(c.base)} | {_runs(c.head)} | {_p(c.p_value)} |")
        lines.append("")

    failing = sorted(result.failing_on_head, key=lambda c: (c.head.pass_rate, c.case_id))
    if failing:
        lines += [
            f"#### Failing on head ({len(failing)})",
            "",
            "| Case | Head | Why (sample) |",
            "|---|---|---|",
        ]
        for c in failing[:_MAX_ROWS]:
            why = _cell(c.head_failures[0]) if c.head_failures else "—"
            lines.append(f"| `{_cell(c.case_id, 40)}` | {_runs(c.head)} | {why} |")
        if len(failing) > _MAX_ROWS:
            lines.append(f"| … | | {len(failing) - _MAX_ROWS} more in the JSON report |")
        lines.append("")

    lines += [
        "#### Summary",
        "",
        "| | Base | Head | Δ |",
        "|---|---|---|---|",
        f"| Pass rate (95% CI) | {_rate(suite.base)} | {_rate(suite.head)} | {_pts(suite.delta)} |",
    ]
    if suite.base.mean_cost_usd is not None and suite.head.mean_cost_usd is not None:
        lines.append(
            f"| Cost / run | ${suite.base.mean_cost_usd:.4f} | ${suite.head.mean_cost_usd:.4f} "
            f"| {_pct(suite.cost_delta_pct)} |"
        )
    if suite.base.mean_latency_ms is not None and suite.head.mean_latency_ms is not None:
        lines.append(
            f"| Latency / run | {suite.base.mean_latency_ms:.0f} ms "
            f"| {suite.head.mean_latency_ms:.0f} ms | {_pct(suite.latency_delta_pct)} |"
        )
    if suite.base.errors or suite.head.errors:
        lines.append(f"| Errors | {suite.base.errors} | {suite.head.errors} | |")
    lines.append("")

    passed_checks = [c for c in result.gate.checks if not c.breached]
    if passed_checks:
        lines += [f"✅ {c.detail}  " for c in passed_checks]
        lines.append("")

    lines += [
        f"<details><summary>All cases ({len(result.cases)})</summary>",
        "",
        "| Case | Base | Head | p | |",
        "|---|---|---|---|---|",
    ]
    lines += [_case_row(c) for c in result.cases]
    lines += ["", "</details>"]
    return "\n".join(lines) + "\n"


def _case_row(c: CaseDiff) -> str:
    mark = {"regressed": "🔻", "improved": "🔺", "unchanged": ""}[c.status]
    return (
        f"| `{_cell(c.case_id, 40)}` | {_runs(c.base)} | {_runs(c.head)} | {_p(c.p_value)} | {mark} |"
    )


def render_json(result: DiffResult) -> str:
    data = result.model_dump(mode="json")
    data["gate"]["breaches"] = [c.name for c in result.gate.breaches]
    return json.dumps(data, indent=2)
