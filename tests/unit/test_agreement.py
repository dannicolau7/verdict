import pytest

from verdict.stats.agreement import cohen_kappa, kappa_bootstrap_ci, precision_recall


def test_kappa_textbook_example():
    # 50 items: 20 yes/yes, 5 yes/no, 10 no/yes, 15 no/no -> p_o=0.7, p_e=0.5, kappa=0.4
    ref = ["y"] * 25 + ["n"] * 25
    pred = ["y"] * 20 + ["n"] * 5 + ["y"] * 10 + ["n"] * 15
    assert cohen_kappa(ref, pred) == pytest.approx(0.4)


def test_kappa_small_binary_and_multiclass():
    assert cohen_kappa([1, 1, 0, 0], [1, 0, 0, 0]) == pytest.approx(0.5)
    assert cohen_kappa(list("abca"), list("abba")) == pytest.approx(0.6)


def test_kappa_perfect_chance_and_degenerate():
    assert cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == 1.0
    assert cohen_kappa([1, 0, 1, 0], [0, 1, 0, 1]) == pytest.approx(-1.0)
    assert cohen_kappa([1, 1, 1], [1, 1, 1]) == 1.0  # single class, full agreement
    assert cohen_kappa([], []) == 0.0
    with pytest.raises(ValueError):
        cohen_kappa([1], [1, 0])


def test_kappa_ci_contains_point_and_is_seeded():
    ref = [1] * 30 + [0] * 30
    pred = [1] * 25 + [0] * 5 + [0] * 25 + [1] * 5
    lo, hi = kappa_bootstrap_ci(ref, pred, seed=3)
    assert lo <= cohen_kappa(ref, pred) <= hi
    assert (lo, hi) == kappa_bootstrap_ci(ref, pred, seed=3)


def test_precision_recall():
    ref = ["fail", "fail", "pass", "pass", "fail"]
    pred = ["fail", "pass", "fail", "pass", "fail"]
    p, r, support = precision_recall(ref, pred, "fail")
    assert (p, r, support) == (pytest.approx(2 / 3), pytest.approx(2 / 3), 3)
    assert precision_recall(["pass"], ["pass"], "fail") == (None, None, 0)
