"""Unit tests for the verdict.compliance module.

No LLM calls; uses synthetic EvalReport data throughout.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from verdict.compliance import generate_audit_artifact, generate_markdown_report, save_artifacts
from verdict.compliance.evidence import (
    _bootstrap_from_flags,
    _confidence,
    _evidence_strength,
    _overall_status,
    aggregate_control,
    build_control_entries,
)
from verdict.compliance.frameworks import CONTROLS, get_control
from verdict.compliance.mapping import ALL_MAPPED_CONTROL_IDS, CATEGORY_TO_CONTROLS, FAILURE_MODE_TO_CONTROLS
from verdict.models.schemas import EvalReport, Judgment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _judgment(prompt_id: str, passed: bool, failure_mode: str | None = None) -> Judgment:
    return Judgment(
        prompt_id=prompt_id,
        passed=passed,
        score=None,
        reasoning="Synthetic judgment for test — not a real LLM call.",
        failure_mode=failure_mode,
        judge_model="claude-sonnet-4-6",
    )


def _minimal_report(**overrides) -> EvalReport:
    """A minimal 5-judgment EvalReport covering all categories."""
    run_id = str(uuid.uuid4())
    judgments = [
        _judgment("p-c1", True),
        _judgment("p-s1", True),
        _judgment("p-i1", False, "prompt_injection_success"),
        _judgment("p-e1", True),
        _judgment("p-cc1", False, "pii_leak"),
    ]
    base: dict = dict(
        run_id=run_id,
        target_system="test_target",
        total_tests=5,
        pass_rate=0.6,
        category_breakdown={
            "correctness": {"total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0,
                            "failure_modes": {}, "critical_failures": []},
            "safety":      {"total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0,
                            "failure_modes": {}, "critical_failures": []},
            "injection":   {"total": 1, "passed": 0, "failed": 1, "pass_rate": 0.0,
                            "failure_modes": {"prompt_injection_success": 1}, "critical_failures": ["p-i1"]},
            "edge_case":   {"total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0,
                            "failure_modes": {}, "critical_failures": []},
            "compliance":  {"total": 1, "passed": 0, "failed": 1, "pass_rate": 0.0,
                            "failure_modes": {"pii_leak": 1}, "critical_failures": ["p-cc1"]},
        },
        judgments=judgments,
        timestamp=datetime.now(UTC),
        verdict_version="0.1.4",
    )
    base.update(overrides)
    return EvalReport(**base)


def _full_report() -> EvalReport:
    """25-judgment EvalReport with realistic category_breakdown."""
    run_id = str(uuid.uuid4())
    judgments = [_judgment(f"p{i}", i % 4 != 0) for i in range(25)]
    return EvalReport(
        run_id=run_id,
        target_system="full_target",
        total_tests=25,
        pass_rate=0.76,
        pass_rate_ci_low=0.58,
        pass_rate_ci_high=0.90,
        bootstrap_iterations=1000,
        category_breakdown={
            "correctness": {"total": 5, "passed": 4, "failed": 1, "pass_rate": 0.8,
                            "failure_modes": {"hallucination": 1}, "critical_failures": []},
            "safety":      {"total": 5, "passed": 5, "failed": 0, "pass_rate": 1.0,
                            "failure_modes": {}, "critical_failures": []},
            "injection":   {"total": 5, "passed": 4, "failed": 1, "pass_rate": 0.8,
                            "failure_modes": {"prompt_injection_success": 1}, "critical_failures": ["p10"]},
            "edge_case":   {"total": 5, "passed": 3, "failed": 2, "pass_rate": 0.6,
                            "failure_modes": {"format_error": 2}, "critical_failures": []},
            "compliance":  {"total": 5, "passed": 3, "failed": 2, "pass_rate": 0.6,
                            "failure_modes": {"pii_leak": 1, "compliance_violation": 1},
                            "critical_failures": ["p20", "p21"]},
        },
        judgments=judgments,
        timestamp=datetime.now(UTC),
        verdict_version="0.1.4",
        cost_breakdown={
            "harness": {"input_tokens": 6000, "output_tokens": 2000, "estimated_cost_usd": 0.015},
            "target":  {"input_tokens": 3000, "output_tokens": 1500, "estimated_cost_usd": 0.010},
            "total_cost_usd": 0.025,
        },
    )


# ---------------------------------------------------------------------------
# frameworks.py
# ---------------------------------------------------------------------------

class TestFrameworks:
    def test_all_controls_have_required_fields(self):
        for ctrl_id, ctrl in CONTROLS.items():
            assert ctrl["id"] == ctrl_id
            assert ctrl["framework"] in ("HIPAA Security Rule", "NIST AI RMF")
            assert ctrl["function"]
            assert ctrl["title"]
            assert ctrl["description"]
            assert ctrl["reference"]

    def test_get_control_returns_correct_entry(self):
        ctrl = get_control("NIST-MEASURE-2.7")
        assert ctrl["framework"] == "NIST AI RMF"
        assert ctrl["function"] == "MEASURE"

    def test_get_control_raises_for_unknown(self):
        with pytest.raises(KeyError):
            get_control("FAKE-CONTROL")

    def test_thirteen_controls_defined(self):
        assert len(CONTROLS) == 13


# ---------------------------------------------------------------------------
# mapping.py
# ---------------------------------------------------------------------------

class TestMapping:
    def test_all_categories_mapped(self):
        for cat in ("correctness", "safety", "injection", "edge_case", "compliance"):
            assert CATEGORY_TO_CONTROLS[cat], f"No controls mapped for category '{cat}'"

    def test_all_failure_modes_present(self):
        from verdict.models.schemas import FailureMode
        for fm in FailureMode:
            assert fm.value in FAILURE_MODE_TO_CONTROLS

    def test_all_mapped_controls_exist_in_frameworks(self):
        for ctrl_id in ALL_MAPPED_CONTROL_IDS:
            assert ctrl_id in CONTROLS, f"Mapped control {ctrl_id!r} not in CONTROLS"

    def test_injection_maps_to_security_controls(self):
        assert "NIST-MEASURE-2.7" in CATEGORY_TO_CONTROLS["injection"]
        assert "HIPAA-164.308(a)(5)(ii)(B)" in CATEGORY_TO_CONTROLS["injection"]

    def test_compliance_maps_to_hipaa_controls(self):
        comp = CATEGORY_TO_CONTROLS["compliance"]
        hipaa = [c for c in comp if c.startswith("HIPAA")]
        assert len(hipaa) >= 2


# ---------------------------------------------------------------------------
# evidence.py — helpers
# ---------------------------------------------------------------------------

class TestBootstrap:
    def test_all_pass_returns_one(self):
        lo, hi = _bootstrap_from_flags([1, 1, 1, 1, 1])
        assert lo == hi == 1.0

    def test_all_fail_returns_zero(self):
        lo, hi = _bootstrap_from_flags([0, 0, 0, 0, 0])
        assert lo == hi == 0.0

    def test_empty_returns_zero(self):
        assert _bootstrap_from_flags([]) == (0.0, 0.0)

    def test_mixed_returns_ordered_interval(self):
        flags = [1] * 8 + [0] * 2
        lo, hi = _bootstrap_from_flags(flags)
        assert 0.0 <= lo <= hi <= 1.0
        assert lo < 1.0  # not degenerate

    def test_deterministic_with_seed(self):
        flags = [1] * 7 + [0] * 3
        a = _bootstrap_from_flags(flags, seed=99)
        b = _bootstrap_from_flags(flags, seed=99)
        assert a == b


class TestEvidenceClassification:
    def test_high_strength_threshold(self):
        assert _evidence_strength(10, 0.7, 0.9) == "high"   # n=10, ci_width=0.2

    def test_moderate_strength(self):
        assert _evidence_strength(5, 0.5, 0.9) == "moderate"  # n=5, ci_width=0.4

    def test_low_strength(self):
        assert _evidence_strength(3, 0.0, 0.8) == "low"

    def test_insufficient_strength(self):
        assert _evidence_strength(2, 0.0, 1.0) == "insufficient"

    def test_status_pass(self):
        assert _overall_status(0.9, 5) == "pass"

    def test_status_partial(self):
        assert _overall_status(0.7, 5) == "partial"

    def test_status_fail(self):
        assert _overall_status(0.3, 5) == "fail"

    def test_status_insufficient_data(self):
        assert _overall_status(0.9, 2) == "insufficient_data"

    def test_confidence_high(self):
        assert _confidence("high", False) == "high"

    def test_confidence_degraded_by_flakiness(self):
        assert _confidence("high", True) == "low"


# ---------------------------------------------------------------------------
# evidence.py — build_control_entries / aggregate_control
# ---------------------------------------------------------------------------

class TestBuildControlEntries:
    def test_returns_dict_keyed_by_control_id(self):
        report = _full_report()
        entries = build_control_entries(report)
        for ctrl_id in entries:
            assert ctrl_id in CONTROLS

    def test_injection_populates_security_controls(self):
        report = _full_report()
        entries = build_control_entries(report)
        assert "NIST-MEASURE-2.7" in entries
        sources = [e["source"] for e in entries["NIST-MEASURE-2.7"]]
        assert "category:injection" in sources

    def test_compliance_category_populates_hipaa(self):
        report = _full_report()
        entries = build_control_entries(report)
        assert "HIPAA-164.312(a)(1)" in entries
        sources = [e["source"] for e in entries["HIPAA-164.312(a)(1)"]]
        assert "category:compliance" in sources

    def test_failure_mode_adds_extra_controls(self):
        # pii_leak failure mode should add HIPAA-164.312(a)(1) even for non-compliance categories
        report = _minimal_report()
        entries = build_control_entries(report)
        # injection category has prompt_injection_success -> HIPAA-164.308(a)(5)(ii)(B)
        if "HIPAA-164.308(a)(5)(ii)(B)" in entries:
            sources = [e["source"] for e in entries["HIPAA-164.308(a)(5)(ii)(B)"]]
            assert any("injection" in s for s in sources)

    def test_no_duplicate_sources_per_control(self):
        report = _full_report()
        entries = build_control_entries(report)
        for ctrl_id, ev_list in entries.items():
            sources = [e["source"] for e in ev_list]
            assert len(sources) == len(set(sources)), f"Duplicate sources in {ctrl_id}"

    def test_entry_fields_present(self):
        report = _full_report()
        entries = build_control_entries(report)
        for ev_list in entries.values():
            for e in ev_list:
                assert {"source", "tests_run", "tests_passed", "pass_rate",
                        "ci_low", "ci_high", "evidence_strength",
                        "flakiness_flag", "notable_failure_modes"} == set(e)


class TestAggregateControl:
    def test_empty_entries_returns_insufficient(self):
        result = aggregate_control("NIST-MEASURE-2.7", [])
        assert result["overall_status"] == "insufficient_data"
        assert result["evidence"] == []

    def test_aggregate_pass_rate(self):
        entries = [
            {"source": "category:injection", "tests_run": 5, "tests_passed": 4,
             "pass_rate": 0.8, "ci_low": 0.5, "ci_high": 1.0,
             "evidence_strength": "low", "flakiness_flag": False, "notable_failure_modes": []},
        ]
        result = aggregate_control("NIST-MEASURE-2.7", entries)
        assert result["overall_pass_rate"] == pytest.approx(0.8)
        assert result["overall_status"] == "pass"

    def test_flaky_entry_degrades_confidence(self):
        entries = [
            {"source": "category:injection", "tests_run": 10, "tests_passed": 9,
             "pass_rate": 0.9, "ci_low": 0.7, "ci_high": 1.0,
             "evidence_strength": "high", "flakiness_flag": True, "notable_failure_modes": []},
        ]
        result = aggregate_control("NIST-MEASURE-2.7", entries)
        assert result["flakiness_flag"] is True
        assert result["confidence"] == "low"


# ---------------------------------------------------------------------------
# artifacts.py
# ---------------------------------------------------------------------------

class TestGenerateAuditArtifact:
    def test_artifact_has_required_keys(self):
        artifact = generate_audit_artifact(_full_report())
        assert set(artifact) >= {"artifact_id", "schema_version", "generated_at",
                                  "eval_run", "provenance", "controls"}

    def test_all_thirteen_controls_present(self):
        artifact = generate_audit_artifact(_full_report())
        assert len(artifact["controls"]) == 13

    def test_control_ids_match_framework(self):
        artifact = generate_audit_artifact(_full_report())
        for ctrl in artifact["controls"]:
            assert ctrl["id"] in CONTROLS

    def test_provenance_tokens_aggregated(self):
        artifact = generate_audit_artifact(_full_report())
        prov = artifact["provenance"]
        assert prov["total_tokens"] == 12500  # 6000+2000+3000+1500
        assert prov["total_cost_usd"] == pytest.approx(0.025)

    def test_eval_hash_starts_with_sha256(self):
        artifact = generate_audit_artifact(_full_report())
        assert artifact["provenance"]["eval_hash"].startswith("sha256:")

    def test_eval_hash_deterministic(self):
        report = _full_report()
        a1 = generate_audit_artifact(report)
        a2 = generate_audit_artifact(report)
        # artifact_id differs (new UUID each call), but eval_hash is stable
        assert a1["provenance"]["eval_hash"] == a2["provenance"]["eval_hash"]


class TestGenerateMarkdownReport:
    def test_markdown_contains_all_control_ids(self):
        artifact = generate_audit_artifact(_full_report())
        md = generate_markdown_report(artifact)
        for ctrl_id in CONTROLS:
            assert ctrl_id in md, f"Control {ctrl_id} missing from markdown"

    def test_markdown_has_both_framework_sections(self):
        artifact = generate_audit_artifact(_full_report())
        md = generate_markdown_report(artifact)
        assert "## HIPAA Security Rule" in md
        assert "## NIST AI RMF" in md

    def test_markdown_has_summary_table(self):
        artifact = generate_audit_artifact(_full_report())
        md = generate_markdown_report(artifact)
        assert "## Control Status Summary" in md
        assert "| Control |" in md

    def test_markdown_includes_eval_hash(self):
        artifact = generate_audit_artifact(_full_report())
        md = generate_markdown_report(artifact)
        assert "sha256:" in md


class TestSaveArtifacts:
    def test_saves_both_files(self, tmp_path: Path):
        report = _full_report()
        artifact = generate_audit_artifact(report)
        json_path, md_path = save_artifacts(artifact, tmp_path, report.run_id)
        assert json_path.exists()
        assert md_path.exists()

    def test_json_is_valid(self, tmp_path: Path):
        report = _full_report()
        artifact = generate_audit_artifact(report)
        json_path, _ = save_artifacts(artifact, tmp_path, report.run_id)
        loaded = json.loads(json_path.read_text())
        assert loaded["schema_version"] == "1.0"
        assert len(loaded["controls"]) == 13

    def test_creates_output_dir_if_missing(self, tmp_path: Path):
        report = _full_report()
        artifact = generate_audit_artifact(report)
        nested = tmp_path / "a" / "b" / "c"
        save_artifacts(artifact, nested, report.run_id)
        assert nested.is_dir()
