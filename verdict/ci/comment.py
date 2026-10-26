"""Render DiffResult and CalibrationResult as PR comments (Markdown) and JSON.

Comment order: verdict line, gate breaches, regressions, failing cases, summary table,
then every case in a collapsed <details>. Tables stay narrow so they read on a phone.
The first line is a hidden marker so a CI action can find and update its own comment.
"""

from __future__ import annotations

import json

from verdict.ci.calibrate import CalibrationResult
from verdict.ci.diff import CaseDiff, DiffResult, SideStats
from verdict.ci.trajectory import TrajectoryReport

COMMENT_MARKER = "<!-- verdict-diff -->"
CALIBRATE_MARKER = "<!-- verdict-calibrate -->"
TRAJECTORY_MARKER = "<!-- verdict-trajectory -->"
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
            head = f"{_runs(c.head)} flaky" if c.head.flaky else _runs(c.head)
            lines.append(f"| `{_cell(c.case_id, 40)}` | {head} | {why} |")
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
    k_max = max((int(k) for k in suite.head.pass_hat_k), default=1)
    if k_max > 1 and str(k_max) in suite.base.pass_hat_k:
        bk, hk = suite.base.pass_hat_k[str(k_max)], suite.head.pass_hat_k[str(k_max)]
        lines.append(f"| pass^{k_max} (all {k_max} pass) | {bk:.0%} | {hk:.0%} | {_pts(hk - bk)} |")
        ba, ha = suite.base.pass_at_k[str(k_max)], suite.head.pass_at_k[str(k_max)]
        lines.append(f"| pass@{k_max} (any pass) | {ba:.0%} | {ha:.0%} | {_pts(ha - ba)} |")
    if suite.base.mean_tool_calls is not None and suite.head.mean_tool_calls is not None:
        lines.append(
            f"| Tool calls / run | {suite.base.mean_tool_calls:.1f} | {suite.head.mean_tool_calls:.1f} "
            f"| {suite.head.mean_tool_calls - suite.base.mean_tool_calls:+.1f} |"
        )
    if suite.base.mean_steps is not None and suite.head.mean_steps is not None:
        lines.append(
            f"| Steps / run | {suite.base.mean_steps:.1f} | {suite.head.mean_steps:.1f} "
            f"| {_pct(suite.steps_delta_pct)} |"
        )
    if suite.base.trajectory_failures or suite.head.trajectory_failures:
        lines.append(
            f"| Trajectory failures | {suite.base.trajectory_failures} "
            f"| {suite.head.trajectory_failures} | |"
        )
    if suite.base.flaky_cases is not None and suite.head.flaky_cases is not None:
        lines.append(f"| Flaky cases | {suite.base.flaky_cases} | {suite.head.flaky_cases} | |")
    if suite.base.errors or suite.head.errors:
        lines.append(f"| Errors | {suite.base.errors} | {suite.head.errors} | |")
    lines.append("")

    passed_checks = [c for c in result.gate.checks if not c.breached]
    if passed_checks:
        lines += [f"{'⚠️' if c.warning else '✅'} {c.detail}  " for c in passed_checks]
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


# ---------------------------------------------------------------------------
# verdict calibrate
# ---------------------------------------------------------------------------


def _frac(x: float | None) -> str:
    return "—" if x is None else f"{x:.0%}"


def _label(passed: bool | None) -> str:
    return "—" if passed is None else ("pass" if passed else "fail")


def render_calibration_markdown(result: CalibrationResult) -> str:
    kappa = f"κ = **{result.kappa:.2f}** (95% CI {result.kappa_ci_low:.2f}–{result.kappa_ci_high:.2f})"
    if result.n_scored == 0:
        head = "### ❌ Judge calibration: nothing to score"
    elif result.min_kappa is None:
        head = "### ℹ️ Judge calibration"
    elif result.passed:
        head = f"### ✅ Judge calibration: κ ≥ {result.min_kappa:g}"
    else:
        head = f"### ❌ Judge calibration: κ below {result.min_kappa:g}"

    notes = [f"{result.n_scored} scored"]
    if result.n_borderline:
        notes.append(f"{result.n_borderline} borderline excluded")
    if result.n_judge_errors:
        notes.append(f"⚠️ {result.n_judge_errors} judge errors excluded")
    lines = [
        CALIBRATE_MARKER,
        head,
        "",
        f"{kappa} · agreement {result.agreement:.0%} · {', '.join(notes)}  ",
        f"Judge `{result.judge_model or 'custom'}` vs `{result.labels_path}`",
        "",
    ]
    if result.n_scored and result.n_scored < 30:
        lines += [f"_Only {result.n_scored} scored examples: κ is noisy; aim for 50+._", ""]

    dis = result.disagreements
    if dis:
        lines += [
            f"#### Disagreements ({len(dis)})",
            "",
            "| Example | Human | Judge | Judge reasoning |",
            "|---|---|---|---|",
        ]
        for i in dis[:_MAX_ROWS]:
            lines.append(
                f"| `{_cell(i.id, 30)}` | {_label(i.human_passed)} | {_label(i.judge_passed)} "
                f"| {_cell(i.judge_reasoning)} |"
            )
        if len(dis) > _MAX_ROWS:
            lines.append(f"| … | | | {len(dis) - _MAX_ROWS} more in the JSON report |")
        lines.append("")

    c = result.confusion
    lines += [
        "#### Confusion matrix",
        "",
        "| Human ↓ / Judge → | pass | fail |",
        "|---|---|---|",
        f"| **pass** | {c['pass_pass']} | {c['pass_fail']} |",
        f"| **fail** | {c['fail_pass']} | {c['fail_fail']} |",
        "",
        f"Failure detection: precision {_frac(result.fail_precision)}, "
        f"recall {_frac(result.fail_recall)}",
        "",
    ]

    if result.by_category:
        lines += [
            "#### By rubric",
            "",
            "| Rubric | n | Agree | κ | Fail P / R |",
            "|---|---|---|---|---|",
        ]
        for g in result.by_category:
            lines.append(
                f"| {g.name} | {g.n} | {g.agreement:.0%} | {g.kappa:.2f} "
                f"| {_frac(g.fail_precision)} / {_frac(g.fail_recall)} |"
            )
        lines.append("")

    if result.by_failure_mode:
        lines += ["#### By failure mode", "", "| Mode | n | P | R |", "|---|---|---|---|"]
        for m in result.by_failure_mode:
            lines.append(f"| {m.mode} | {m.support} | {_frac(m.precision)} | {_frac(m.recall)} |")
        lines.append("")

    return "\n".join(lines)


def render_calibration_json(result: CalibrationResult) -> str:
    data = result.model_dump(mode="json")
    data["disagreements"] = [i.id for i in result.disagreements]
    return json.dumps(data, indent=2)


# ---------------------------------------------------------------------------
# verdict trajectory
# ---------------------------------------------------------------------------


def render_trajectory_markdown(report: TrajectoryReport) -> str:
    ok = "✅" if report.passed else "❌"
    lines = [
        TRAJECTORY_MARKER,
        f"### {ok} Trajectories: {report.n_passed}/{report.n_traces} pass "
        f"(min {report.min_pass_rate:.0%})",
        "",
        f"`{report.agent_name}` · {report.mean_tool_calls:.1f} tool calls and "
        f"{report.mean_steps:.1f} steps per trace"
        + (
            f" · tool recall {report.mean_tool_recall:.0%}, precision {_frac(report.mean_tool_precision)}"
            if report.mean_tool_recall is not None
            else ""
        ),
        "",
    ]
    failing = [t for t in report.traces if not t.result.passed]
    if failing:
        lines += [f"#### Failing ({len(failing)})", "", "| Trace | Problem |", "|---|---|"]
        for t in failing[:_MAX_ROWS]:
            first = t.result.errors[0].detail
            more = f" (+{len(t.result.errors) - 1} more)" if len(t.result.errors) > 1 else ""
            lines.append(f"| `{_cell(t.trace_id, 24)}` | {_cell(first, 70)}{more} |")
        if len(failing) > _MAX_ROWS:
            lines.append(f"| … | {len(failing) - _MAX_ROWS} more in the JSON report |")
        lines.append("")
    warned = [t for t in report.traces if t.result.warnings]
    if warned:
        lines += [f"#### Warnings ({len(warned)})", "", "| Trace | Warning |", "|---|---|"]
        for t in warned[:_MAX_ROWS]:
            lines.append(f"| `{_cell(t.trace_id, 24)}` | {_cell(t.result.warnings[0].detail, 70)} |")
        lines.append("")
    if report.finding_counts:
        lines += ["#### Findings by check", "", "| Check | Count |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in report.finding_counts.items()]
        lines.append("")
    return "\n".join(lines)


def render_trajectory_json(report: TrajectoryReport) -> str:
    return json.dumps(report.model_dump(mode="json"), indent=2)
