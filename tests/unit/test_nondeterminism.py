import math

import pytest

from verdict.stats.nondeterminism import (
    is_flaky,
    min_detectable_drop,
    pass_at_k,
    pass_hat_k,
    runs_needed,
)


def test_pass_at_k_matches_closed_form():
    # n=10, c=3, k=2: 1 - C(7,2)/C(10,2) = 1 - 21/45
    assert pass_at_k(10, 3, 2) == pytest.approx(1 - 21 / 45)
    assert pass_at_k(10, 0, 5) == 0.0
    assert pass_at_k(10, 8, 3) == 1.0  # fewer than k failures -> some sample must pass
    assert pass_at_k(10, 4, 1) == pytest.approx(0.4)  # pass@1 is the pass rate


def test_pass_hat_k():
    # n=10, c=8, k=3: C(8,3)/C(10,3) = 56/120
    assert pass_hat_k(10, 8, 3) == pytest.approx(56 / 120)
    assert pass_hat_k(10, 10, 10) == 1.0
    assert pass_hat_k(10, 9, 10) == 0.0
    assert pass_hat_k(10, 4, 1) == pytest.approx(0.4)


def test_pass_hat_k_is_unbiased_for_p_to_the_k():
    # E[C(c,k)/C(n,k)] over c ~ Binomial(n, p) equals p**k
    n, k, p = 8, 3, 0.7
    expected = sum(
        math.comb(n, c) * p**c * (1 - p) ** (n - c) * pass_hat_k(n, c, k) for c in range(n + 1)
    )
    assert expected == pytest.approx(p**k)


def test_k_validation():
    with pytest.raises(ValueError, match="exceeds"):
        pass_at_k(5, 2, 6)
    with pytest.raises(ValueError):
        pass_hat_k(5, 6, 1)


def test_is_flaky():
    assert is_flaky(10, 5) and not is_flaky(10, 0) and not is_flaky(10, 10)


@pytest.mark.parametrize(
    "baseline,drop,expected",
    [(0.9, 0.05, 686), (0.5, 0.1, 388), (0.9, 0.2, 62)],
)
def test_runs_needed_reference_values(baseline, drop, expected):
    # Two-sided two-proportion z-test, alpha=0.05, power=0.8, pooled variance under H0,
    # no continuity correction (values recomputed by hand from the formula).
    assert abs(runs_needed(baseline, drop) - expected) <= 1


def test_runs_needed_validation():
    with pytest.raises(ValueError):
        runs_needed(0.9, 0.0)
    with pytest.raises(ValueError):
        runs_needed(0.9, 0.95)
    with pytest.raises(ValueError):
        runs_needed(0.9, 0.05, power=1.0)


def test_min_detectable_drop_round_trips():
    n = runs_needed(0.9, 0.05)
    mdd = min_detectable_drop(0.9, n)
    assert mdd is not None and mdd <= 0.05 + 1e-9
    assert min_detectable_drop(0.9, n // 2) > 0.05
    assert min_detectable_drop(0.9, 2) is None
    assert min_detectable_drop(0.0, 1000) is None
