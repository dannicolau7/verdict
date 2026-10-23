"""Statistics for comparing pass rates between two runs (base vs head).

All functions are stdlib-only and deterministic (bootstrap takes a seed).

    wilson_interval(k, n)            95% (default) Wilson score interval for k/n.
    fisher_exact(a, b, c, d)         Two-sided Fisher's exact p-value for a 2x2 table.
    bootstrap_diff(base, head, ...)  Bootstrap p-value and CI for head_rate - base_rate.
"""

from __future__ import annotations

import math
import random
from statistics import NormalDist


def _z(confidence: float) -> float:
    return NormalDist().inv_cdf(1.0 - (1.0 - confidence) / 2.0)


def wilson_interval(k: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion.

    Unlike the normal approximation it stays inside [0, 1] and behaves sensibly
    at 0/n and n/n, which are common for eval cases.

    Returns (0.0, 1.0) when n == 0 (no information).
    """
    if n < 0 or k < 0 or k > n:
        raise ValueError(f"invalid proportion {k}/{n}")
    if n == 0:
        return (0.0, 1.0)
    z = _z(confidence)
    p = k / n
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, centre - half), min(1.0, centre + half))


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher's exact test p-value for the table [[a, b], [c, d]].

    Rows are the two groups (base, head); columns are (passed, failed).
    The p-value sums the probabilities of every table with the same margins that is
    no more likely than the observed one. Computed with exact integers.
    """
    if min(a, b, c, d) < 0:
        raise ValueError("table cells must be non-negative")
    r1, r2 = a + b, c + d
    c1 = a + c
    n = r1 + r2
    if n == 0:
        return 1.0
    lo, hi = max(0, c1 - r2), min(r1, c1)
    # P(x) = C(r1, x) * C(r2, c1 - x) / C(n, c1); compare numerators only.
    weights = {x: math.comb(r1, x) * math.comb(r2, c1 - x) for x in range(lo, hi + 1)}
    observed = weights[a]
    total = math.comb(n, c1)
    extreme = sum(w for w in weights.values() if w <= observed)
    return min(1.0, extreme / total)


def bootstrap_diff(
    base: list[bool],
    head: list[bool],
    iterations: int = 2000,
    confidence: float = 0.95,
    seed: int | None = 0,
) -> tuple[float, float, float]:
    """Bootstrap the difference in pass rate (head - base).

    Each side is resampled independently with replacement.

    Returns:
        (p_value, ci_low, ci_high) where p_value is the two-sided bootstrap
        p-value for "the difference is zero" (2 * the smaller tail mass at 0).
    """
    if not base or not head:
        return (1.0, 0.0, 0.0)
    rng = random.Random(seed)
    nb, nh = len(base), len(head)
    b_flags = [1 if x else 0 for x in base]
    h_flags = [1 if x else 0 for x in head]
    diffs: list[float] = []
    for _ in range(iterations):
        diffs.append(sum(rng.choices(h_flags, k=nh)) / nh - sum(rng.choices(b_flags, k=nb)) / nb)
    diffs.sort()
    le = sum(1 for x in diffs if x <= 0) / iterations
    ge = sum(1 for x in diffs if x >= 0) / iterations
    p = min(1.0, 2.0 * min(le, ge))
    alpha = 1.0 - confidence
    lo_idx = max(0, min(int((alpha / 2) * iterations), iterations - 1))
    hi_idx = max(0, min(int((1 - alpha / 2) * iterations) - 1, iterations - 1))
    return (p, diffs[lo_idx], diffs[hi_idx])
