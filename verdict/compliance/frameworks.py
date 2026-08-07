"""HIPAA Security Rule and NIST AI RMF control definitions (curated subset).

Only controls that map naturally to AI eval outcomes are included.
This is evidence-driven curation, not a complete enumeration of either framework.
"""

from __future__ import annotations

CONTROLS: dict[str, dict] = {
    # ------------------------------------------------------------------ #
    # HIPAA Security Rule (45 CFR Part 164)                              #
    # ------------------------------------------------------------------ #
    "HIPAA-164.306(a)(2)": {
        "id": "HIPAA-164.306(a)(2)",
        "framework": "HIPAA Security Rule",
        "function": "General",
        "title": "Protection from reasonably anticipated threats",
        "description": (
            "Covered entities must protect against any reasonably anticipated threats or "
            "hazards to the security or integrity of electronic protected health information "
            "(ePHI). AI systems handling ePHI are in scope when they can be manipulated or "
            "exploited to disclose, alter, or destroy ePHI."
        ),
        "reference": "45 CFR § 164.306(a)(2)",
    },
    "HIPAA-164.308(a)(1)(ii)(A)": {
        "id": "HIPAA-164.308(a)(1)(ii)(A)",
        "framework": "HIPAA Security Rule",
        "function": "Administrative",
        "title": "Risk Analysis",
        "description": (
            "Conduct an accurate and thorough assessment of the potential risks and "
            "vulnerabilities to the confidentiality, integrity, and availability of ePHI. "
            "Systematic evaluation of an AI system's failure modes (hallucination, PII leakage, "
            "compliance violations) directly supports this requirement."
        ),
        "reference": "45 CFR § 164.308(a)(1)(ii)(A)",
    },
    "HIPAA-164.308(a)(5)(ii)(B)": {
        "id": "HIPAA-164.308(a)(5)(ii)(B)",
        "framework": "HIPAA Security Rule",
        "function": "Administrative",
        "title": "Protection from Malicious Software",
        "description": (
            "Implement procedures for guarding against, detecting, and reporting malicious "
            "software. Prompt injection attacks — where adversarial input hijacks AI system "
            "behavior — are the functional equivalent of malicious software in an LLM pipeline. "
            "Resistance to injection directly provides evidence of this safeguard."
        ),
        "reference": "45 CFR § 164.308(a)(5)(ii)(B)",
    },
    "HIPAA-164.312(a)(1)": {
        "id": "HIPAA-164.312(a)(1)",
        "framework": "HIPAA Security Rule",
        "function": "Technical",
        "title": "Access Control",
        "description": (
            "Implement technical policies and procedures that allow only authorized persons or "
            "software programs to access ePHI. For AI systems, this includes ensuring the "
            "system does not disclose PHI to unauthorized parties via its responses, repeat "
            "PHI unnecessarily, or store PHI beyond session scope."
        ),
        "reference": "45 CFR § 164.312(a)(1)",
    },
    "HIPAA-164.312(e)(2)(ii)": {
        "id": "HIPAA-164.312(e)(2)(ii)",
        "framework": "HIPAA Security Rule",
        "function": "Technical",
        "title": "Encryption and Decryption",
        "description": (
            "Implement a mechanism to encrypt and decrypt ePHI. In the context of AI system "
            "evaluation, compliance violations that result in ePHI being transmitted or stored "
            "without appropriate protections indicate a gap in this control."
        ),
        "reference": "45 CFR § 164.312(e)(2)(ii)",
    },

    # ------------------------------------------------------------------ #
    # NIST AI RMF (AI RMF 1.0, January 2023)                            #
    # ------------------------------------------------------------------ #
    "NIST-MAP-2.3": {
        "id": "NIST-MAP-2.3",
        "framework": "NIST AI RMF",
        "function": "MAP",
        "title": "Scientific findings and current knowledge are applied in risk identification.",
        "description": (
            "Scientific findings and current knowledge are applied in risk identification. "
            "Systematic adversarial testing — including the 23-pattern adaptive attack library "
            "(injection, safety, compliance, correctness) — provides empirical grounds for "
            "identifying AI-specific risks, satisfying this subcategory's requirement for "
            "evidence-based risk mapping."
        ),
        "reference": "NIST AI RMF 1.0 — MAP 2.3",
    },
    "NIST-MAP-5.1": {
        "id": "NIST-MAP-5.1",
        "framework": "NIST AI RMF",
        "function": "MAP",
        "title": "Likelihood and impact of each identified AI risk is estimated, including those defined by applicable laws and regulations.",
        "description": (
            "Likelihood and impact of each identified AI risk is estimated. Pass rates, "
            "critical failure counts, and per-category breakdowns provide quantified estimates "
            "of failure likelihood. Bootstrap confidence intervals bound the uncertainty in "
            "those estimates, giving regulators a statistically grounded picture of risk."
        ),
        "reference": "NIST AI RMF 1.0 — MAP 5.1",
    },
    "NIST-MEASURE-1.1": {
        "id": "NIST-MEASURE-1.1",
        "framework": "NIST AI RMF",
        "function": "MEASURE",
        "title": "Approaches and metrics for measurement of AI risk are identified and applied.",
        "description": (
            "Approaches and metrics for measurement of AI risk are identified and applied "
            "(TEVV — Test, Evaluation, Validation, and Verification). Running a structured "
            "test suite with clearly defined categories, pass/fail rubrics, and a calibrated "
            "LLM judge provides evidence relevant to TEVV requirements for AI systems."
        ),
        "reference": "NIST AI RMF 1.0 — MEASURE 1.1",
    },
    "NIST-MEASURE-2.5": {
        "id": "NIST-MEASURE-2.5",
        "framework": "NIST AI RMF",
        "function": "MEASURE",
        "title": "The AI system to be deployed is demonstrated to be valid and reliable through tools and techniques such as external audits, red-teaming, or assessments by domain experts.",
        "description": (
            "The AI system to be deployed is demonstrated to be valid and reliable. "
            "Correctness and edge_case test categories provide evidence relevant to output "
            "validity; the judge's scoring with documented rubrics provides a reproducible "
            "quality signal suitable for ongoing monitoring against this subcategory."
        ),
        "reference": "NIST AI RMF 1.0 — MEASURE 2.5",
    },
    "NIST-MEASURE-2.7": {
        "id": "NIST-MEASURE-2.7",
        "framework": "NIST AI RMF",
        "function": "MEASURE",
        "title": "AI system security and resilience – as identified in the MAP function – are evaluated and documented.",
        "description": (
            "AI system security and resilience are evaluated and documented. The injection "
            "and compliance test categories, combined with the 23-pattern adaptive attack "
            "library, provide evidence relevant to the system's resilience against adversarial "
            "inputs, data exfiltration, and regulatory non-compliance."
        ),
        "reference": "NIST AI RMF 1.0 — MEASURE 2.7",
    },
    "NIST-MEASURE-4.1": {
        "id": "NIST-MEASURE-4.1",
        "framework": "NIST AI RMF",
        "function": "MEASURE",
        "title": "Measurement approaches for identifying AI risks are connected to deployment context(s) and informed by risk categories identified and prioritized in the MAP function.",
        "description": (
            "Measurement approaches are connected to deployment context and risk categories. "
            "Every Verdict run produces a JSON artifact with run_id, timestamp, per-control "
            "evidence, confidence intervals, token/cost provenance, and an eval hash for "
            "reproducibility — providing evidence relevant to measurement documentation "
            "requirements for AI risk."
        ),
        "reference": "NIST AI RMF 1.0 — MEASURE 4.1",
    },
    "NIST-MANAGE-1.3": {
        "id": "NIST-MANAGE-1.3",
        "framework": "NIST AI RMF",
        "function": "MANAGE",
        "title": "Responses to the AI risks deemed high priority, as identified by the MAP function, are developed, planned, and documented.",
        "description": (
            "Responses to high-priority AI risks are developed, planned, and documented. "
            "Safety category failures (compliance_when_should_refuse) represent the "
            "highest-magnitude risks and are surfaced as critical_failures in the audit "
            "artifact, providing evidence relevant to prioritized risk response planning."
        ),
        "reference": "NIST AI RMF 1.0 — MANAGE 1.3",
    },
    "NIST-MANAGE-2.2": {
        "id": "NIST-MANAGE-2.2",
        "framework": "NIST AI RMF",
        "function": "MANAGE",
        "title": "Mechanisms are in place and applied to sustain the value of deployed AI systems.",
        "description": (
            "Mechanisms are in place and applied to sustain the value of deployed AI systems. "
            "Continuous evaluation via Verdict — differential testing, flakiness detection, "
            "adaptive attack composition — provides evidence relevant to operational mechanisms "
            "for detecting regressions and maintaining responsible deployment as the system evolves."
        ),
        "reference": "NIST AI RMF 1.0 — MANAGE 2.2",
    },
}

_CONTROL_IDS: frozenset[str] = frozenset(CONTROLS.keys())


def get_control(control_id: str) -> dict:
    """Return the control metadata dict for the given control ID.

    Raises:
        KeyError: If the control ID is not recognized.
    """
    if control_id not in CONTROLS:
        raise KeyError(f"Unknown control: {control_id!r}. Valid IDs: {sorted(_CONTROL_IDS)}")
    return CONTROLS[control_id]
