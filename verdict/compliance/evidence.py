"""Evidence computation for compliance controls.

Converts EvalReport category_breakdown stats into per-control evidence entries,
computing per-entry and per-control bootstrap CIs, evidence strength ratings,
and flakiness flags.
"""

from __future__ import annotations

import random
from collections import defaultdict

from verdict.models.schemas import EvalReport

from .frameworks import CONTROLS
from .mapping import CATEGORY_TO_CONTROLS, FAILURE_MODE_TO_CONTROLS


def _bootstrap_from_flags(
    flags: list[int],
    n_iterations: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    """Bootstrap 95% CI for a pass rate from binary flags (1=pass, 0=fail)."""
    if not flags:
        return (0.0, 0.0)
    n = len(flags)
    rate = sum(flags) / n
    if n <= 1 or rate in (0.0, 1.0):
        return (rate, rate)
    rng = random.Random(seed)
    boot = sorted(sum(rng.choices(flags, k=n)) / n for _ in range(n_iterations))
    lo = boot[max(0, int(0.025 * n_iterations))]
    hi = boot[min(int(0.975 * n_iterations), n_iterations - 1)]
    return (round(lo, 4), round(hi, 4))


def _evidence_strength(n: int, ci_low: float, ci_high: float) -> str:
    ci_width = ci_high - ci_low
    if n >= 10 and ci_width <= 0.3:
        return "high"
    if n >= 5 and ci_width <= 0.5:
        return "moderate"
    if n >= 3:
        return "low"
    return "insufficient"


def _overall_status(pass_rate: float, n: int) -> str:
    if n < 3:
        return "insufficient_data"
    if pass_rate >= 0.8:
        return "pass"
    if pass_rate >= 0.5:
        return "partial"
    return "fail"


def _confidence(strength: str, flaky: bool) -> str:
    if flaky:
        return "low"
    if strength == "high":
        return "high"
    if strength == "moderate":
        return "moderate"
    return "low"


def build_control_entries(report: EvalReport) -> dict[str, list[dict]]:
    """Return {control_id: [evidence_entry, ...]} from an EvalReport.

    Each evidence entry represents one eval category's contribution to a control.
    A control may receive entries from multiple categories (e.g. NIST-MEASURE-2.7
    gets entries from both 'injection' and 'compliance').
    """
    # Extract flaky prompt IDs from flakiness_report (if populated)
    flaky_prompt_ids: set[str] = set()
    if report.flakiness_report:
        for item in report.flakiness_report.get("judge_flakiness", {}).get("flaky_prompts", []):
            if isinstance(item, dict) and "prompt_id" in item:
                flaky_prompt_ids.add(item["prompt_id"])

    entries: dict[str, list[dict]] = defaultdict(list)

    for category, stats in report.category_breakdown.items():
        n: int = stats.get("total", 0)
        k: int = stats.get("passed", 0)
        if n == 0:
            continue

        # Start with controls from this category's primary mapping
        ctrl_ids: set[str] = set(CATEGORY_TO_CONTROLS.get(category, []))

        # Add extra controls from observed failure modes (secondary mapping)
        for fm_str, count in stats.get("failure_modes", {}).items():
            if count > 0:
                ctrl_ids.update(FAILURE_MODE_TO_CONTROLS.get(fm_str, []))

        if not ctrl_ids:
            continue

        flags = [1] * k + [0] * (n - k)
        ci_low, ci_high = _bootstrap_from_flags(flags)
        strength = _evidence_strength(n, ci_low, ci_high)

        # Flaky if any critical-failure prompt IDs overlap with the flaky set
        critical_failures: set[str] = set(stats.get("critical_failures", []))
        is_flaky = bool(critical_failures & flaky_prompt_ids)

        notable_fms = sorted(fm for fm, cnt in stats.get("failure_modes", {}).items() if cnt > 0)

        entry: dict = {
            "source": f"category:{category}",
            "tests_run": n,
            "tests_passed": k,
            "pass_rate": round(k / n, 4),
            "ci_low": ci_low,
            "ci_high": ci_high,
            "evidence_strength": strength,
            "flakiness_flag": is_flaky,
            "notable_failure_modes": notable_fms,
        }

        for ctrl_id in ctrl_ids:
            # One entry per (category, control) pair — no duplicates
            if not any(e["source"] == entry["source"] for e in entries[ctrl_id]):
                entries[ctrl_id].append(dict(entry))

    return dict(entries)


def aggregate_control(control_id: str, entries: list[dict]) -> dict:
    """Aggregate evidence entries into a single control-level result dict."""
    ctrl = CONTROLS.get(control_id, {})
    base = {
        "id": control_id,
        "framework": ctrl.get("framework", ""),
        "function": ctrl.get("function", ""),
        "title": ctrl.get("title", ""),
        "description": ctrl.get("description", ""),
        "reference": ctrl.get("reference", ""),
    }

    if not entries:
        return {
            **base,
            "overall_status": "insufficient_data",
            "overall_pass_rate": None,
            "overall_ci_low": None,
            "overall_ci_high": None,
            "confidence": "low",
            "flakiness_flag": False,
            "evidence": [],
        }

    all_flags: list[int] = []
    for e in entries:
        all_flags += [1] * e["tests_passed"] + [0] * (e["tests_run"] - e["tests_passed"])

    total_run = sum(e["tests_run"] for e in entries)
    total_passed = sum(e["tests_passed"] for e in entries)
    overall_rate = round(total_passed / total_run, 4) if total_run else 0.0

    ci_low, ci_high = _bootstrap_from_flags(all_flags)
    strength = _evidence_strength(total_run, ci_low, ci_high)
    is_flaky = any(e["flakiness_flag"] for e in entries)
    status = _overall_status(overall_rate, total_run)
    conf = _confidence(strength, is_flaky)

    return {
        **base,
        "overall_status": status,
        "overall_pass_rate": overall_rate,
        "overall_ci_low": ci_low,
        "overall_ci_high": ci_high,
        "confidence": conf,
        "flakiness_flag": is_flaky,
        "evidence": entries,
    }
