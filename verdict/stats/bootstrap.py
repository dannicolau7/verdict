"""Bootstrap confidence interval computation for Verdict pass rates.

Algorithm: standard non-parametric bootstrap with replacement.
    1. Resample n_iterations times (with replacement) from the judgments list.
    2. Compute pass_rate for each resample.
    3. Return the (alpha/2) and (1 - alpha/2) percentiles as the CI bounds.

No external dependencies — uses stdlib random and statistics modules only.
Deterministic when seed is provided.
"""

from __future__ import annotations

import random

from verdict.models.schemas import Judgment


def bootstrap_pass_rate_ci(
    judgments: list[Judgment],
    n_iterations: int = 1000,
    confidence: float = 0.95,
    seed: int | None = None,
) -> tuple[float, float]:
    """Compute a bootstrap confidence interval for the pass rate.

    Args:
        judgments:    List of Judgment objects for the run.
        n_iterations: Number of bootstrap resamples.  Use 0 to skip (returns
                      the empirical rate as both bounds).
        confidence:   Desired confidence level (e.g., 0.95 for 95% CI).
        seed:         Random seed for reproducibility.  None = non-deterministic.

    Returns:
        (ci_low, ci_high) as floats in [0.0, 1.0].

    Edge cases:
        - Empty judgments:       returns (0.0, 0.0)
        - Single judgment:       returns (rate, rate)
        - All pass / all fail:   returns (rate, rate) — no variance to resample
        - n_iterations == 0:     returns (rate, rate)
    """
    if not judgments:
        return (0.0, 0.0)

    n = len(judgments)
    pass_flags = [1 if j.passed else 0 for j in judgments]
    empirical_rate = sum(pass_flags) / n

    # Short-circuit cases with no variance
    if n_iterations == 0 or n == 1 or empirical_rate in (0.0, 1.0):
        return (empirical_rate, empirical_rate)

    rng = random.Random(seed)

    boot_rates: list[float] = []
    for _ in range(n_iterations):
        sample = rng.choices(pass_flags, k=n)
        boot_rates.append(sum(sample) / n)

    boot_rates.sort()

    alpha = 1.0 - confidence
    lo_idx = int((alpha / 2) * n_iterations)
    hi_idx = int((1.0 - alpha / 2) * n_iterations) - 1
    # Clamp indices to valid range
    lo_idx = max(0, min(lo_idx, n_iterations - 1))
    hi_idx = max(0, min(hi_idx, n_iterations - 1))

    return (round(boot_rates[lo_idx], 4), round(boot_rates[hi_idx], 4))
