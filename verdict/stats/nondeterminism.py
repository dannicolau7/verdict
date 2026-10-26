"""Statistics for non-deterministic agents: capability, consistency and power.

    pass_at_k(n, c, k)       P(at least one of k tries passes), unbiased from c passes in n runs.
    pass_hat_k(n, c, k)      P(all k tries pass) — "pass^k", consistency.
    is_flaky(n, c)           Both passes and failures were observed.
    runs_needed(p, drop)     Observations per side to detect a pass-rate drop (two-proportion test).
    min_detectable_drop(p, n)  Smallest drop detectable with n observations per side.

pass@k follows Chen et al. 2021 (HumanEval); pass^k follows Yao et al. 2024 (τ-bench).
The power calculations use the normal approximation to a two-sided two-proportion test;
Fisher's exact test is slightly more conservative, so treat results as a lower bound.
Stdlib only.
"""

from __future__ import annotations

import math
from statistics import NormalDist


def _check(n: int, c: int, k: int) -> None:
    if not (0 <= c <= n) or k < 1:
        raise ValueError(f"need 0 <= c <= n and k >= 1, got n={n}, c={c}, k={k}")
    if k > n:
        raise ValueError(f"k={k} exceeds the number of runs n={n}")


def pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased estimate of P(at least one of k samples passes): 1 - C(n-c, k) / C(n, k)."""
    _check(n, c, k)
    if n - c < k:
        return 1.0
    return 1.0 - math.comb(n - c, k) / math.comb(n, k)


def pass_hat_k(n: int, c: int, k: int) -> float:
    """Unbiased estimate of P(all k samples pass): C(c, k) / C(n, k)."""
    _check(n, c, k)
    return math.comb(c, k) / math.comb(n, k)


def is_flaky(n: int, c: int) -> bool:
    """A case is flaky when the same input both passed and failed."""
    return 0 < c < n


def _z(x: float) -> float:
    return NormalDist().inv_cdf(x)


def runs_needed(
    baseline: float, drop: float, alpha: float = 0.05, power: float = 0.8
) -> int:
    """Observations per side to detect ``baseline -> baseline - drop`` (two-sided test).

    An observation is one judged run of one case, so divide by the number of cases
    to get runs per case.
    """
    if not 0.0 < baseline <= 1.0:
        raise ValueError("baseline must be in (0, 1]")
    if not 0.0 < drop <= baseline:
        raise ValueError("drop must be in (0, baseline]")
    if not 0.0 < alpha < 1.0 or not 0.0 < power < 1.0:
        raise ValueError("alpha and power must be in (0, 1)")
    p1, p2 = baseline, baseline - drop
    p_bar = (p1 + p2) / 2
    z_a, z_b = _z(1 - alpha / 2), _z(power)
    num = z_a * math.sqrt(2 * p_bar * (1 - p_bar)) + z_b * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    return math.ceil((num / drop) ** 2)


def min_detectable_drop(
    baseline: float, n: int, alpha: float = 0.05, power: float = 0.8
) -> float | None:
    """Smallest drop from ``baseline`` detectable with ``n`` observations per side.

    Returns None when even a drop to 0% would not be detectable (n too small) or the
    baseline is 0.
    """
    if n < 1 or baseline <= 0.0:
        return None
    if runs_needed(baseline, baseline, alpha, power) > n:
        return None
    lo, hi = 0.0, baseline
    for _ in range(60):  # bisection; runs_needed decreases as the drop grows
        mid = (lo + hi) / 2
        if mid > 0 and runs_needed(baseline, mid, alpha, power) <= n:
            hi = mid
        else:
            lo = mid
    return hi
