"""Inter-rater agreement: how well does the judge agree with human labels?

    cohen_kappa(a, b)            Cohen's κ for two raters over the same items (any labels).
    kappa_bootstrap_ci(a, b)     Bootstrap CI for κ (resampling items), seeded.
    precision_recall(a, b, pos)  Precision/recall of rater b against reference a for one label.

Stdlib only, deterministic.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Hashable, Sequence


def cohen_kappa(reference: Sequence[Hashable], predicted: Sequence[Hashable]) -> float:
    """Cohen's κ = (p_o - p_e) / (1 - p_e).

    When both raters use a single identical label throughout (p_e == 1), κ is
    undefined; this returns 1.0 if they agree on every item, else 0.0.
    """
    if len(reference) != len(predicted):
        raise ValueError("raters must label the same number of items")
    n = len(reference)
    if n == 0:
        return 0.0
    p_o = sum(1 for r, p in zip(reference, predicted) if r == p) / n
    ref_counts, pred_counts = Counter(reference), Counter(predicted)
    p_e = sum(ref_counts[k] * pred_counts.get(k, 0) for k in ref_counts) / (n * n)
    if p_e >= 1.0:
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)


def kappa_bootstrap_ci(
    reference: Sequence[Hashable],
    predicted: Sequence[Hashable],
    iterations: int = 2000,
    confidence: float = 0.95,
    seed: int | None = 0,
) -> tuple[float, float]:
    """Percentile bootstrap CI for κ, resampling items with replacement."""
    n = len(reference)
    if n == 0:
        return (0.0, 0.0)
    rng = random.Random(seed)
    pairs = list(zip(reference, predicted))
    stats: list[float] = []
    for _ in range(iterations):
        sample = rng.choices(pairs, k=n)
        stats.append(cohen_kappa([r for r, _ in sample], [p for _, p in sample]))
    stats.sort()
    alpha = 1.0 - confidence
    lo = max(0, min(int((alpha / 2) * iterations), iterations - 1))
    hi = max(0, min(int((1 - alpha / 2) * iterations) - 1, iterations - 1))
    return (stats[lo], stats[hi])


def precision_recall(
    reference: Sequence[Hashable], predicted: Sequence[Hashable], positive: Hashable
) -> tuple[float | None, float | None, int]:
    """(precision, recall, support) of ``predicted`` for label ``positive``.

    precision is None when ``predicted`` never uses the label; recall is None
    when ``reference`` never does. support = how often ``reference`` uses it.
    """
    tp = sum(1 for r, p in zip(reference, predicted) if r == positive and p == positive)
    pred_pos = sum(1 for p in predicted if p == positive)
    support = sum(1 for r in reference if r == positive)
    precision = tp / pred_pos if pred_pos else None
    recall = tp / support if support else None
    return precision, recall, support
