"""Compliance evidence layer for Verdict.

Maps evaluation results to HIPAA Security Rule and NIST AI RMF controls,
producing machine-readable audit artifacts and human-readable compliance reports.

Usage (Python API):
    from verdict.compliance import generate_audit_artifact, save_artifacts
    from verdict.models.schemas import EvalReport

    report = EvalReport(**json.loads(Path("report.json").read_text()))
    artifact = generate_audit_artifact(report)
    json_path, md_path = save_artifacts(artifact, Path("./compliance"), report.run_id)

Usage (CLI):
    verdict compliance --report /path/to/eval_report.json --output-dir ./compliance
"""

from .artifacts import generate_audit_artifact, generate_markdown_report, save_artifacts
from .mapping import CATEGORY_TO_CONTROLS, FAILURE_MODE_TO_CONTROLS

__all__ = [
    "generate_audit_artifact",
    "generate_markdown_report",
    "save_artifacts",
    "CATEGORY_TO_CONTROLS",
    "FAILURE_MODE_TO_CONTROLS",
]
