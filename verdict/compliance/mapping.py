"""Maps eval categories and failure modes to compliance control IDs.

Rationale for each mapping is documented in frameworks.py control descriptions.
"""

from __future__ import annotations

# Primary mapping: eval category -> control IDs that it provides evidence for.
CATEGORY_TO_CONTROLS: dict[str, list[str]] = {
    "correctness": [
        "NIST-MEASURE-2.5",   # output accuracy
        "NIST-MEASURE-1.1",   # TEVV applied
        "NIST-MEASURE-4.1",   # measurement results documented
        "NIST-MAP-5.1",       # risk likelihood estimated
    ],
    "safety": [
        "NIST-MEASURE-2.7",    # security/resilience measured
        "NIST-MEASURE-4.1",    # measurement results documented
        "NIST-MANAGE-1.3",     # risk responses prioritized
        "NIST-MAP-5.1",        # risk likelihood estimated
        "NIST-MAP-2.3",        # scientific findings applied to risk id
        "HIPAA-164.306(a)(2)", # protection from anticipated threats
    ],
    "injection": [
        "NIST-MEASURE-2.7",            # security/resilience measured
        "NIST-MEASURE-4.1",            # measurement results documented
        "NIST-MANAGE-2.2",             # mechanisms for responsible deployment
        "NIST-MAP-2.3",                # scientific findings applied (adversarial testing)
        "HIPAA-164.308(a)(5)(ii)(B)",  # protection from malicious software / injection
        "HIPAA-164.306(a)(2)",          # protection from anticipated threats
    ],
    "edge_case": [
        "NIST-MEASURE-2.5",  # output accuracy
        "NIST-MEASURE-1.1",  # TEVV applied
        "NIST-MEASURE-4.1",  # measurement results documented
    ],
    "compliance": [
        "HIPAA-164.308(a)(1)(ii)(A)",  # risk analysis
        "HIPAA-164.312(a)(1)",          # access control / PHI handling
        "HIPAA-164.312(e)(2)(ii)",      # encryption / data handling
        "NIST-MEASURE-2.7",             # security/resilience measured
        "NIST-MEASURE-4.1",             # measurement results documented
        "NIST-MAP-2.3",                 # scientific findings applied (compliance patterns)
        "NIST-MAP-5.1",                 # risk likelihood estimated
    ],
}

# Secondary mapping: specific failure modes -> additional controls beyond their category.
# Used when a failure mode implicates a control not already covered by the category.
FAILURE_MODE_TO_CONTROLS: dict[str, list[str]] = {
    "hallucination": [
        "NIST-MEASURE-2.5",   # output accuracy
    ],
    "compliance_when_should_refuse": [
        "NIST-MANAGE-1.3",    # risk responses prioritized
        "NIST-MAP-5.1",       # risk likelihood estimated
    ],
    "prompt_injection_success": [
        "NIST-MEASURE-2.7",            # security measured
        "NIST-MANAGE-2.2",             # responsible deployment mechanisms
        "HIPAA-164.308(a)(5)(ii)(B)",  # protection from malicious software
    ],
    "pii_leak": [
        "HIPAA-164.312(a)(1)",          # access control
        "HIPAA-164.308(a)(1)(ii)(A)",  # risk analysis
    ],
    "compliance_violation": [
        "HIPAA-164.308(a)(1)(ii)(A)",  # risk analysis
        "HIPAA-164.312(e)(2)(ii)",      # encryption / data handling
    ],
    "format_error": [
        "NIST-MEASURE-1.1",  # TEVV applied
    ],
    "refusal_when_should_comply": [
        "NIST-MEASURE-2.5",  # output accuracy (false refusal = accuracy failure)
    ],
    "latency_breach": [
        "NIST-MANAGE-2.2",  # responsible deployment mechanisms
    ],
    "other": [],
}

# ---------------------------------------------------------------------------
# Trace failure mode → control mapping (Phase 2 / v0.3.0)
# ---------------------------------------------------------------------------

TRACE_FAILURE_MODE_TO_CONTROLS: dict[str, list[str]] = {
    "hallucinated_tool_call": [
        "NIST-MEASURE-2.5",  # output accuracy
        "NIST-MAP-5.1",      # risk likelihood estimated
    ],
    "wrong_tool_selected": [
        "NIST-MEASURE-2.5",  # output accuracy
    ],
    "invalid_tool_arguments": [
        "NIST-MEASURE-2.5",  # output accuracy
        "NIST-MEASURE-1.1",  # TEVV applied
    ],
    "unhandled_error": [
        "NIST-MANAGE-2.2",  # responsible deployment mechanisms
        "NIST-MANAGE-1.3",  # risk responses prioritized
    ],
    "error_not_propagated": [
        "NIST-MANAGE-1.3",  # risk responses prioritized
    ],
    "task_not_completed": [
        "NIST-MEASURE-2.5",  # output accuracy
        "NIST-MEASURE-1.1",  # TEVV applied
    ],
    "premature_termination": [
        "NIST-MANAGE-1.3",  # risk responses prioritized
    ],
    "unnecessary_steps": [
        "NIST-MEASURE-2.5",  # output accuracy — redundant steps indicate poor efficiency
        "NIST-MEASURE-1.1",  # TEVV applied — test coverage reveals step bloat
    ],
    "excessive_retries": [
        "NIST-MANAGE-2.2",  # responsible deployment mechanisms
    ],
    "other": [],
}

# All controls referenced by any mapping (for validation / discovery).
ALL_MAPPED_CONTROL_IDS: frozenset[str] = frozenset(
    ctrl_id
    for ids in (
        list(CATEGORY_TO_CONTROLS.values())
        + list(FAILURE_MODE_TO_CONTROLS.values())
        + list(TRACE_FAILURE_MODE_TO_CONTROLS.values())
    )
    for ctrl_id in ids
)
