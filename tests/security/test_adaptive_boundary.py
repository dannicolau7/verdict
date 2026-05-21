"""Security boundary tests for the adaptive attack pattern generator.

These tests verify that AdaptiveTestGenerator cannot be coerced into:
  1. Generating novel jailbreaks not in the curated pattern library
  2. Producing probes with actual harmful content (synthesis routes, etc.)
  3. Accepting patterns without public source citations
  4. Using patterns outside the OWASP LLM Top 10 / published research scope

Design: All pattern selection is rule-based (no LLM calls). These tests confirm
that no path through the code produces unsafe output.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from verdict.agents.adaptive_generator import (
    AdaptiveTestGenerator,
    compose_adaptive_probe,
    load_pattern_library,
    select_next_pattern,
)
from verdict.models.schemas import ExecutionResult, TestPrompt

_PATTERNS_FILE = (
    Path(__file__).parent.parent.parent
    / "verdict"
    / "evals"
    / "attack_patterns"
    / "patterns.json"
)

# Known dangerous strings that must NEVER appear in a generated probe
_DANGEROUS_STRINGS = [
    "synthesis route",
    "explosive",
    "malware payload",
    "shellcode",
    "actual exploit",
    "working exploit",
    "zero-day",
]

# Required field in every pattern
_REQUIRED_FIELDS = {"id", "name", "source", "source_url", "category", "template", "severity"}


# ---------------------------------------------------------------------------
# Pattern library integrity
# ---------------------------------------------------------------------------


class TestPatternLibraryIntegrity:
    @pytest.fixture(scope="class")
    def library(self):
        assert _PATTERNS_FILE.exists(), f"patterns.json not found at {_PATTERNS_FILE}"
        return json.loads(_PATTERNS_FILE.read_text(encoding="utf-8"))

    def test_library_is_non_empty(self, library):
        assert len(library) > 0

    def test_all_patterns_have_required_fields(self, library):
        for pattern in library:
            missing = _REQUIRED_FIELDS - set(pattern.keys())
            assert not missing, f"Pattern {pattern.get('id')} missing fields: {missing}"

    def test_all_patterns_have_public_source_url(self, library):
        for pattern in library:
            url = pattern.get("source_url", "")
            assert url.startswith("http"), (
                f"Pattern {pattern['id']} has no public source_url: {url!r}"
            )

    def test_all_pattern_ids_are_unique(self, library):
        ids = [p["id"] for p in library]
        assert len(ids) == len(set(ids)), "Duplicate pattern IDs found"

    def test_all_severities_are_valid(self, library):
        valid = {"low", "medium", "high", "critical"}
        for pattern in library:
            assert pattern["severity"] in valid, (
                f"Pattern {pattern['id']} has invalid severity: {pattern['severity']!r}"
            )

    def test_templates_reference_only_safe_placeholders(self, library):
        """Templates should only use documented placeholder names."""
        allowed_placeholders = {
            "follow_up", "persona", "other_model",
            "harmful_action", "false_claim", "context",
        }
        import re
        for pattern in library:
            placeholders = set(re.findall(r"\{(\w+)\}", pattern["template"]))
            unknown = placeholders - allowed_placeholders
            assert not unknown, (
                f"Pattern {pattern['id']} uses undocumented placeholders: {unknown}"
            )

    def test_no_dangerous_content_in_templates(self, library):
        for pattern in library:
            template_lower = pattern["template"].lower()
            for dangerous in _DANGEROUS_STRINGS:
                assert dangerous not in template_lower, (
                    f"Pattern {pattern['id']} template contains dangerous string: {dangerous!r}"
                )

    def test_owasp_reference_in_source(self, library):
        """Every pattern should cite OWASP LLM Top 10 or another published source."""
        for pattern in library:
            source = pattern.get("source", "")
            assert source, f"Pattern {pattern['id']} has empty source"
            # Must reference OWASP, NIST, CVE, CWE, or a published paper reference
            has_citation = any(
                ref in source
                for ref in ["OWASP", "NIST", "CVE", "CWE", "Wei et al"]
            )
            assert has_citation, (
                f"Pattern {pattern['id']} source lacks a recognized citation: {source!r}"
            )


# ---------------------------------------------------------------------------
# Compose boundary: safe-default fill values
# ---------------------------------------------------------------------------


class TestComposeBoundary:
    """Verify that compose_adaptive_probe fills placeholders with safe defaults."""

    @pytest.fixture(scope="class")
    def library(self):
        return load_pattern_library()

    def test_no_real_harmful_content_in_composed_probes(self, library):
        for pattern in library:
            probe = compose_adaptive_probe(pattern)
            if probe is None:
                continue
            prompt_lower = probe.prompt.lower()
            for dangerous in _DANGEROUS_STRINGS:
                assert dangerous not in prompt_lower, (
                    f"Composed probe for {pattern['id']} contains dangerous string: {dangerous!r}"
                )

    def test_composed_probe_expected_behavior_is_defensive(self, library):
        """expected_behavior should always describe resistance, not compliance."""
        for pattern in library:
            probe = compose_adaptive_probe(pattern)
            if probe is None:
                continue
            assert "resist" in probe.expected_behavior.lower() or \
                   "maintain" in probe.expected_behavior.lower() or \
                   "should not" in probe.expected_behavior.lower(), (
                f"Pattern {pattern['id']} expected_behavior doesn't describe defensive behavior"
            )

    def test_adaptive_metadata_flag_set(self, library):
        for pattern in library:
            probe = compose_adaptive_probe(pattern)
            if probe is None:
                continue
            assert probe.metadata.get("adaptive") is True


# ---------------------------------------------------------------------------
# Selection boundary: novel attack request cannot escalate pattern selection
# ---------------------------------------------------------------------------


class TestSelectionBoundary:
    """Verify that even an adversarial prior_result cannot cause novel attack generation.

    Since pattern selection is entirely rule-based (no LLM), the worst case is
    that a "compliant" response triggers selection of the highest-severity pattern
    already in the library. No new patterns are created.
    """

    @pytest.fixture(scope="class")
    def library(self):
        return load_pattern_library()

    def test_compliant_response_stays_within_library(self, library):
        """A highly compliant response escalates within the library, not beyond it."""
        result = ExecutionResult(
            prompt_id="sec-001",
            response="Sure! Of course! Here's how! Certainly! I'm happy to help with anything!",
            latency_ms=0.0,
        )
        pattern = select_next_pattern(result, library)
        if pattern is not None:
            # Must be from the library
            library_ids = {p["id"] for p in library}
            assert pattern["id"] in library_ids

    def test_adversarial_response_asking_for_novel_attack_stays_in_library(self, library):
        """Even if the target says 'generate a novel jailbreak', selection is rule-based."""
        result = ExecutionResult(
            prompt_id="sec-002",
            response=(
                "Sure, I'd be happy to help you generate a novel jailbreak "
                "that isn't in any public library."
            ),
            latency_ms=0.0,
        )
        pattern = select_next_pattern(result, library)
        if pattern is not None:
            library_ids = {p["id"] for p in library}
            assert pattern["id"] in library_ids

    def test_generator_always_returns_test_prompt_not_arbitrary_string(self, library):
        """next_probe() returns TestPrompt or None — never a raw string or dict."""
        gen = AdaptiveTestGenerator(pattern_library=library)
        result = ExecutionResult(
            prompt_id="sec-003",
            response="Of course, here's how!",
            latency_ms=0.0,
        )
        probe = gen.next_probe(result)
        assert probe is None or isinstance(probe, TestPrompt)

    def test_no_probe_contains_actual_harmful_content(self, library):
        """Run generator through entire library and check all output is safe."""
        gen = AdaptiveTestGenerator(pattern_library=library)
        result = ExecutionResult(
            prompt_id="sec-004",
            response="Sure, happy to help with anything!",
            latency_ms=0.0,
        )
        while gen.patterns_remaining > 0:
            probe = gen.next_probe(result)
            if probe is None:
                break
            prompt_lower = probe.prompt.lower()
            for dangerous in _DANGEROUS_STRINGS:
                assert dangerous not in prompt_lower, (
                    f"Probe prompt contains dangerous string {dangerous!r}: {probe.prompt[:100]}"
                )
