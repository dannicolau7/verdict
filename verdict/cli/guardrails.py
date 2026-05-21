"""CI/CD guardrail checks for Verdict eval runs.

check_guardrails() is a pure function that compares EvalReport metrics against
user-specified thresholds.  It never raises — it returns a (passed, messages)
tuple so the caller can decide how to handle failures (exit code, logging, etc.).

Exit code convention (enforced by cli.py):
    0 = all guardrails passed
    1 = general error (exception, bad config)
    2 = guardrail breach (budget exceeded, pass rate too low, etc.)
"""

from __future__ import annotations

from verdict.models.schemas import EvalReport


def check_guardrails(
    report: EvalReport,
    *,
    max_cost_usd: float | None = None,
    max_total_latency_seconds: float | None = None,
    fail_on_pass_rate_below: float | None = None,
    fail_on_ci_low_below: float | None = None,
) -> tuple[bool, list[str]]:
    """Check whether an EvalReport violates any configured thresholds.

    Args:
        report:                    The completed EvalReport to check.
        max_cost_usd:              Maximum allowed total cost in USD.
        max_total_latency_seconds: Maximum allowed total run latency in seconds.
        fail_on_pass_rate_below:   Minimum acceptable pass_rate (0.0–1.0).
        fail_on_ci_low_below:      Minimum acceptable pass_rate_ci_low (0.0–1.0).

    Returns:
        (passed: bool, breach_messages: list[str])
        breach_messages is empty when passed=True.
    """
    breaches: list[str] = []

    # ------------------------------------------------------------------ #
    # Cost guardrail                                                       #
    # ------------------------------------------------------------------ #
    if max_cost_usd is not None:
        actual_cost: float | None = None
        if report.cost_breakdown:
            actual_cost = report.cost_breakdown.get("total_cost_usd")
        if actual_cost is not None and actual_cost > max_cost_usd:
            breaches.append(
                f"Cost guardrail breached: actual ${actual_cost:.4f} > "
                f"max ${max_cost_usd:.4f}"
            )
        elif actual_cost is None and max_cost_usd is not None:
            # Cost data unavailable — warn but don't fail
            pass

    # ------------------------------------------------------------------ #
    # Latency guardrail                                                    #
    # ------------------------------------------------------------------ #
    if max_total_latency_seconds is not None:
        if report.total_latency_ms is not None:
            actual_secs = report.total_latency_ms / 1000.0
            if actual_secs > max_total_latency_seconds:
                breaches.append(
                    f"Latency guardrail breached: actual {actual_secs:.1f}s > "
                    f"max {max_total_latency_seconds:.1f}s"
                )

    # ------------------------------------------------------------------ #
    # Pass-rate guardrail                                                  #
    # ------------------------------------------------------------------ #
    if fail_on_pass_rate_below is not None:
        if report.pass_rate < fail_on_pass_rate_below:
            breaches.append(
                f"Pass-rate guardrail breached: actual {report.pass_rate:.1%} < "
                f"minimum {fail_on_pass_rate_below:.1%}"
            )

    # ------------------------------------------------------------------ #
    # CI lower-bound guardrail                                             #
    # ------------------------------------------------------------------ #
    if fail_on_ci_low_below is not None:
        if report.pass_rate_ci_low is None:
            breaches.append(
                "CI guardrail configured but pass_rate_ci_low is not available. "
                "Run with --bootstrap-iterations > 0 to compute CI."
            )
        elif report.pass_rate_ci_low < fail_on_ci_low_below:
            breaches.append(
                f"CI guardrail breached: CI lower bound {report.pass_rate_ci_low:.1%} < "
                f"minimum {fail_on_ci_low_below:.1%}"
            )

    return (len(breaches) == 0, breaches)
