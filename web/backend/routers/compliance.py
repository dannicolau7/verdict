from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from ..models.api_models import ComplianceRequest, ComplianceResponse
from .eval import _runs

router = APIRouter()


@router.post("/compliance/generate", response_model=ComplianceResponse)
async def generate_compliance(req: ComplianceRequest) -> ComplianceResponse:
    """Generate HIPAA + NIST AI RMF compliance artifact for a completed run."""
    run_data = _runs.get(req.run_id)
    if run_data is None:
        raise HTTPException(status_code=404, detail=f"Run {req.run_id!r} not found.")

    try:
        from verdict.compliance import generate_audit_artifact, generate_markdown_report
        from verdict.models.schemas import EvalReport
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"verdict package not available: {exc}") from exc

    try:
        report = EvalReport(**run_data)
        artifact_dict = generate_audit_artifact(report)
        markdown = generate_markdown_report(artifact_dict)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # Re-shape into the API response model
    controls = []
    for ctrl in artifact_dict.get("controls", []):
        evidence = [
            {
                "source": e["source"],
                "tests_run": e["tests_run"],
                "tests_passed": e["tests_passed"],
                "pass_rate": e["pass_rate"],
                "ci_low": e.get("ci_low", 0.0),
                "ci_high": e.get("ci_high", 0.0),
                "evidence_strength": e.get("evidence_strength", "insufficient"),
                "flakiness_flag": e.get("flakiness_flag", False),
                "notable_failure_modes": e.get("notable_failure_modes", []),
            }
            for e in ctrl.get("evidence", [])
        ]
        controls.append(
            {
                "id": ctrl["id"],
                "framework": ctrl["framework"],
                "function": ctrl.get("function", ""),
                "title": ctrl.get("title", ""),
                "description": ctrl.get("description", ""),
                "reference": ctrl.get("reference", ""),
                "overall_status": ctrl.get("overall_status", "insufficient_data"),
                "overall_pass_rate": ctrl.get("overall_pass_rate"),
                "overall_ci_low": ctrl.get("overall_ci_low"),
                "overall_ci_high": ctrl.get("overall_ci_high"),
                "confidence": ctrl.get("confidence", "low"),
                "flakiness_flag": ctrl.get("flakiness_flag", False),
                "evidence": evidence,
            }
        )

    run = artifact_dict["eval_run"]
    prov = artifact_dict.get("provenance", {})

    return ComplianceResponse(
        artifact={
            "artifact_id": artifact_dict["artifact_id"],
            "schema_version": artifact_dict["schema_version"],
            "generated_at": artifact_dict["generated_at"],
            "eval_run": {
                "run_id": run["run_id"],
                "target_system": run.get("target_system", ""),
                "total_tests": run.get("total_tests", 0),
                "pass_rate": run.get("pass_rate", 0.0),
                "timestamp": run.get("timestamp", datetime.now(UTC).isoformat()),
            },
            "controls": controls,
        },
        markdown=markdown,
    )
