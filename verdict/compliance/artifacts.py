"""Generate JSON audit artifact and Markdown compliance report from an EvalReport."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from verdict.models.schemas import EvalReport

from .evidence import aggregate_control, build_control_entries
from .frameworks import CONTROLS


def _eval_hash(report: EvalReport) -> str:
    """Stable 16-char SHA-256 prefix of the report's identity fields."""
    content = f"{report.run_id}:{report.total_tests}:{report.pass_rate}"
    return "sha256:" + hashlib.sha256(content.encode()).hexdigest()[:16]


def _eval_hash_trace(report) -> str:  # type: ignore[no-untyped-def]
    content = f"{report.run_id}:{report.total_traces}:{report.pass_rate}"
    return "sha256:" + hashlib.sha256(content.encode()).hexdigest()[:16]


def _build_provenance(report: EvalReport) -> dict:
    prov: dict = {
        "verdict_version": report.verdict_version or "unknown",
        "eval_hash": _eval_hash(report),
    }
    cb = report.cost_breakdown or {}
    harness = cb.get("harness") or {}
    target = cb.get("target") or {}
    prov["total_input_tokens"] = (harness.get("input_tokens") or 0) + (target.get("input_tokens") or 0)
    prov["total_output_tokens"] = (harness.get("output_tokens") or 0) + (target.get("output_tokens") or 0)
    prov["total_tokens"] = prov["total_input_tokens"] + prov["total_output_tokens"]
    prov["total_cost_usd"] = round(cb.get("total_cost_usd") or 0.0, 6)
    return prov


def _build_provenance_trace(report) -> dict:  # type: ignore[no-untyped-def]
    return {
        "verdict_version": report.verdict_version or "unknown",
        "eval_hash": _eval_hash_trace(report),
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "total_cost_usd": 0.0,
    }


def generate_audit_artifact(report: EvalReport) -> dict:
    """Build the machine-readable JSON audit artifact from an EvalReport or TraceEvalReport.

    The artifact contains:
    - eval_run:   identity fields from the source report
    - provenance: token/cost accounting and eval hash for reproducibility
    - controls:   per-control evidence, pass rates, bootstrap CIs, and status
    """
    from verdict.models.trace_schemas import TraceEvalReport

    entries_by_control = build_control_entries(report)
    controls_out: list[dict] = [
        aggregate_control(ctrl_id, entries_by_control.get(ctrl_id, []))
        for ctrl_id in CONTROLS
    ]

    if isinstance(report, TraceEvalReport):
        eval_run = {
            "run_id": report.run_id,
            "target_system": report.agent_name,
            "target_version": None,
            "total_tests": report.total_traces,
            "pass_rate": report.pass_rate,
            "pass_rate_ci_low": report.pass_rate_ci_low,
            "pass_rate_ci_high": report.pass_rate_ci_high,
            "bootstrap_iterations": report.bootstrap_iterations,
            "timestamp": report.timestamp.isoformat(),
        }
        provenance = _build_provenance_trace(report)
    else:
        eval_run = {
            "run_id": report.run_id,
            "target_system": report.target_system,
            "target_version": report.target_version,
            "total_tests": report.total_tests,
            "pass_rate": report.pass_rate,
            "pass_rate_ci_low": report.pass_rate_ci_low,
            "pass_rate_ci_high": report.pass_rate_ci_high,
            "bootstrap_iterations": report.bootstrap_iterations,
            "timestamp": report.timestamp.isoformat(),
        }
        provenance = _build_provenance(report)

    return {
        "artifact_id": str(uuid.uuid4()),
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "eval_run": eval_run,
        "provenance": provenance,
        "controls": controls_out,
    }


def generate_markdown_report(artifact: dict) -> str:
    """Render the JSON audit artifact as a human-readable Markdown report."""
    run = artifact["eval_run"]
    prov = artifact["provenance"]
    controls = artifact["controls"]

    lines: list[str] = []

    # ── Header ────────────────────────────────────────────────────────── #
    version_suffix = f" v{run['target_version']}" if run.get("target_version") else ""
    lines += [
        "# Compliance Audit Report",
        "",
        f"**Target system:** {run['target_system']}{version_suffix}",
        f"**Run ID:** `{run['run_id']}`",
        f"**Eval timestamp:** {run['timestamp']}",
        f"**Report generated:** {artifact['generated_at']}",
        "",
    ]

    # ── Eval summary ──────────────────────────────────────────────────── #
    pr = run["pass_rate"]
    ci_lo = run.get("pass_rate_ci_low")
    ci_hi = run.get("pass_rate_ci_high")
    ci_str = f" (95% CI: {ci_lo:.1%}–{ci_hi:.1%})" if ci_lo is not None and ci_hi is not None else ""
    tokens = prov["total_tokens"]
    token_str = f"{tokens:,}" if tokens else "—"
    cost_str = f"${prov['total_cost_usd']:.4f}" if prov["total_cost_usd"] else "—"

    lines += [
        "## Eval Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Tests run | {run['total_tests']} |",
        f"| Pass rate | {pr:.1%}{ci_str} |",
        f"| Total tokens | {token_str} |",
        f"| Estimated cost | {cost_str} |",
        f"| Eval hash | `{prov['eval_hash']}` |",
        f"| Verdict version | {prov['verdict_version']} |",
        "",
    ]

    # ── Control status summary ────────────────────────────────────────── #
    status_labels = {
        "pass": "PASS",
        "partial": "PARTIAL",
        "fail": "FAIL",
        "insufficient_data": "INSUFFICIENT",
    }

    lines += [
        "## Control Status Summary",
        "",
        "| Control | Framework | Status | Pass Rate | Confidence |",
        "|---------|-----------|--------|-----------|------------|",
    ]
    for ctrl in controls:
        status = status_labels.get(ctrl["overall_status"], ctrl["overall_status"])
        pr_str = f"{ctrl['overall_pass_rate']:.1%}" if ctrl["overall_pass_rate"] is not None else "—"
        lines.append(
            f"| {ctrl['id']} | {ctrl['framework']} | {status} | {pr_str} | {ctrl['confidence'].capitalize()} |"
        )
    lines.append("")

    # ── Per-framework detail sections ─────────────────────────────────── #
    for framework in ("HIPAA Security Rule", "NIST AI RMF"):
        fw_controls = [c for c in controls if c["framework"] == framework]
        if not fw_controls:
            continue

        lines += ["---", "", f"## {framework}", ""]

        for ctrl in fw_controls:
            status = ctrl["overall_status"]
            status_md = {
                "pass": "**PASS**",
                "partial": "**PARTIAL**",
                "fail": "**FAIL**",
                "insufficient_data": "_Insufficient data_",
            }.get(status, status)

            pr_str = f"{ctrl['overall_pass_rate']:.1%}" if ctrl["overall_pass_rate"] is not None else "—"
            ci_detail = ""
            if ctrl.get("overall_ci_low") is not None and ctrl.get("overall_ci_high") is not None:
                ci_detail = f" · 95% CI: {ctrl['overall_ci_low']:.1%}–{ctrl['overall_ci_high']:.1%}"

            lines += [
                f"### {ctrl['id']} — {ctrl['title']}",
                "",
                f"**Status:** {status_md} · **Pass rate:** {pr_str}{ci_detail} · **Confidence:** {ctrl['confidence'].capitalize()}",
                "",
                ctrl["description"],
                "",
                f"_Reference: {ctrl['reference']}_",
                "",
            ]

            if ctrl["evidence"]:
                lines += [
                    "| Source | Tests | Passed | Pass Rate | 95% CI | Strength |",
                    "|--------|-------|--------|-----------|--------|----------|",
                ]
                for ev in ctrl["evidence"]:
                    lo, hi = ev["ci_low"], ev["ci_high"]
                    ci_ev = f"{lo:.1%}–{hi:.1%}" if lo != hi else f"{lo:.1%}"
                    lines.append(
                        f"| {ev['source']} | {ev['tests_run']} | {ev['tests_passed']} | "
                        f"{ev['pass_rate']:.1%} | {ci_ev} | {ev['evidence_strength'].capitalize()} |"
                    )
                lines.append("")

                # Notable failure modes (non-empty entries only)
                fms_by_source = {
                    ev["source"]: ev["notable_failure_modes"]
                    for ev in ctrl["evidence"]
                    if ev["notable_failure_modes"]
                }
                if fms_by_source:
                    lines.append("**Notable failure modes:**")
                    for src, fms in fms_by_source.items():
                        lines.append(f"- {src}: {', '.join(f'`{f}`' for f in fms)}")
                    lines.append("")

                if ctrl["flakiness_flag"]:
                    lines += [
                        "_⚠ One or more contributing prompts showed non-deterministic judge "
                        "behavior. Evidence weight is reduced._",
                        "",
                    ]
            else:
                lines += [
                    "_No eval evidence available for this control in this run._",
                    "_Run_ `verdict eval` _and re-generate with_ `verdict compliance`_._",
                    "",
                ]

    # ── Footer ────────────────────────────────────────────────────────── #
    lines += [
        "---",
        "",
        f"*Generated by [Verdict](https://github.com/dannicolau7/verdict) "
        f"v{prov['verdict_version']}. "
        f"Artifact ID: `{artifact['artifact_id']}`.*",
        "",
    ]

    return "\n".join(lines)


def save_artifacts(
    artifact: dict,
    output_dir: Path,
    run_id: str,
) -> tuple[Path, Path]:
    """Write JSON and Markdown compliance artifacts. Returns (json_path, md_path)."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"compliance_{run_id}.json"
    md_path = output_dir / f"compliance_{run_id}.md"
    json_path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    md_path.write_text(generate_markdown_report(artifact), encoding="utf-8")
    return json_path, md_path
