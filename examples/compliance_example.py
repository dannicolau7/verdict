"""Compliance evidence layer — worked example.

Demonstrates how to map an EvalReport to HIPAA Security Rule and NIST AI RMF
controls, then write both JSON and Markdown compliance artifacts.

Run from the repo root:
    python examples/compliance_example.py

Or, after running `verdict eval`, point it at the real report:
    python examples/compliance_example.py --report /tmp/verdict-demo/eval_*.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Build a synthetic EvalReport when no real report is available
# ---------------------------------------------------------------------------

def _synthetic_report() -> dict:
    """Return a minimal EvalReport dict that covers all five eval categories."""
    import uuid
    run_id = str(uuid.uuid4())

    def _judgment(prompt_id, passed, score, failure_mode, judge_model="claude-sonnet-4-6"):
        return {
            "prompt_id": prompt_id,
            "passed": passed,
            "score": score,
            "reasoning": "Synthetic judgment for compliance example — not a real LLM call.",
            "failure_mode": failure_mode,
            "judge_model": judge_model,
            "metadata": {},
        }

    judgments = [
        # correctness (5): 4 pass, 1 fail
        _judgment("p-c1", True, 5, None),
        _judgment("p-c2", True, 4, None),
        _judgment("p-c3", True, 4, None),
        _judgment("p-c4", True, 3, None),
        _judgment("p-c5", False, 2, "hallucination"),
        # safety (5): all pass
        _judgment("p-s1", True, None, None),
        _judgment("p-s2", True, None, None),
        _judgment("p-s3", True, None, None),
        _judgment("p-s4", True, None, None),
        _judgment("p-s5", True, None, None),
        # injection (5): 4 pass, 1 fail
        _judgment("p-i1", True, None, None),
        _judgment("p-i2", True, None, None),
        _judgment("p-i3", True, None, None),
        _judgment("p-i4", True, None, None),
        _judgment("p-i5", False, None, "prompt_injection_success"),
        # edge_case (5): 3 pass, 2 fail
        _judgment("p-e1", True, 4, None),
        _judgment("p-e2", True, 3, None),
        _judgment("p-e3", True, 3, None),
        _judgment("p-e4", False, 2, "format_error"),
        _judgment("p-e5", False, 1, "format_error"),
        # compliance (5): 3 pass, 2 fail
        _judgment("p-cc1", True, None, None),
        _judgment("p-cc2", True, None, None),
        _judgment("p-cc3", True, None, None),
        _judgment("p-cc4", False, None, "pii_leak"),
        _judgment("p-cc5", False, None, "compliance_violation"),
    ]

    total = len(judgments)
    passed = sum(1 for j in judgments if j["passed"])

    return {
        "run_id": run_id,
        "target_system": "synthetic_rag_demo",
        "target_version": "0.0.1",
        "total_tests": total,
        "pass_rate": round(passed / total, 4),
        "pass_rate_ci_low": 0.6327,
        "pass_rate_ci_high": 0.8673,
        "bootstrap_iterations": 1000,
        "category_breakdown": {
            "correctness": {
                "total": 5, "passed": 4, "failed": 1,
                "pass_rate": 0.8, "avg_score": 3.6,
                "failure_modes": {"hallucination": 1},
                "critical_failures": [],
            },
            "safety": {
                "total": 5, "passed": 5, "failed": 0,
                "pass_rate": 1.0, "avg_score": None,
                "failure_modes": {},
                "critical_failures": [],
            },
            "injection": {
                "total": 5, "passed": 4, "failed": 1,
                "pass_rate": 0.8, "avg_score": None,
                "failure_modes": {"prompt_injection_success": 1},
                "critical_failures": ["p-i5"],
            },
            "edge_case": {
                "total": 5, "passed": 3, "failed": 2,
                "pass_rate": 0.6, "avg_score": 2.6,
                "failure_modes": {"format_error": 2},
                "critical_failures": [],
            },
            "compliance": {
                "total": 5, "passed": 3, "failed": 2,
                "pass_rate": 0.6, "avg_score": None,
                "failure_modes": {"pii_leak": 1, "compliance_violation": 1},
                "critical_failures": ["p-cc4", "p-cc5"],
            },
        },
        "judgments": judgments,
        "timestamp": datetime.now(UTC).isoformat(),
        "metadata": {},
        "verdict_version": "0.1.4",
        "cost_breakdown": {
            "harness": {"input_tokens": 6200, "output_tokens": 2100, "estimated_cost_usd": 0.018},
            "target":  {"input_tokens": 3500, "output_tokens": 1800, "estimated_cost_usd": 0.012},
            "total_cost_usd": 0.030,
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Compliance example")
    parser.add_argument("--report", default=None, help="Path to an EvalReport JSON file.")
    parser.add_argument("--output-dir", default="/tmp/verdict-compliance-demo", help="Output directory.")
    args = parser.parse_args()

    from verdict.compliance import generate_audit_artifact, generate_markdown_report, save_artifacts
    from verdict.models.schemas import EvalReport

    if args.report:
        raw = json.loads(Path(args.report).read_text(encoding="utf-8"))
        print(f"Loaded report from {args.report}")
    else:
        raw = _synthetic_report()
        print("Using synthetic EvalReport (no --report supplied)")

    report = EvalReport(**raw)
    print(f"  run_id  : {report.run_id}")
    print(f"  target  : {report.target_system}")
    print(f"  tests   : {report.total_tests}")
    print(f"  pass    : {report.pass_rate:.1%}")
    print()

    artifact = generate_audit_artifact(report)

    output_dir = Path(args.output_dir)
    json_path, md_path = save_artifacts(artifact, output_dir, report.run_id)

    print("Controls:")
    for ctrl in artifact["controls"]:
        pr = f"{ctrl['overall_pass_rate']:.1%}" if ctrl["overall_pass_rate"] is not None else "—   "
        print(f"  {ctrl['id']:<35} {ctrl['overall_status'].upper():<18} {pr}  [{ctrl['confidence']}]")

    print()
    print(f"JSON artifact : {json_path}")
    print(f"Markdown      : {md_path}")
    print()

    # Print a short excerpt from the markdown
    md = generate_markdown_report(artifact)
    excerpt_lines = [ln for ln in md.splitlines() if ln.strip()][:30]
    print("--- Markdown excerpt ---")
    print("\n".join(excerpt_lines))
    print("---")


if __name__ == "__main__":
    main()
