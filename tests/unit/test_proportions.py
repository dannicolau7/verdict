"""Reference values cross-checked against scipy.stats / statsmodels."""

import pytest

from verdict.stats.proportions import bootstrap_diff, fisher_exact, wilson_interval


class TestWilson:
    def test_known_value(self):
        lo, hi = wilson_interval(8, 10)
        assert lo == pytest.approx(0.4902, abs=1e-4)
        assert hi == pytest.approx(0.9433, abs=1e-4)

    def test_all_pass_stays_in_bounds(self):
        lo, hi = wilson_interval(10, 10)
        assert hi == 1.0
        assert lo == pytest.approx(0.7225, abs=1e-4)

    def test_zero_of_n(self):
        lo, hi = wilson_interval(0, 20)
        assert lo == 0.0
        assert 0.0 < hi < 0.2

    def test_empty(self):
        assert wilson_interval(0, 0) == (0.0, 1.0)

    def test_invalid(self):
        with pytest.raises(ValueError):
            wilson_interval(5, 3)


class TestFisher:
    @pytest.mark.parametrize(
        "table,expected",
        [
            ((10, 0, 4, 6), 0.010836),
            ((3, 1, 1, 3), 0.485714),
            ((8, 2, 1, 5), 0.034965),
            ((5, 5, 5, 5), 1.0),
        ],
    )
    def test_matches_scipy(self, table, expected):
        assert fisher_exact(*table) == pytest.approx(expected, abs=1e-5)

    def test_symmetric_in_direction(self):
        assert fisher_exact(10, 0, 4, 6) == pytest.approx(fisher_exact(4, 6, 10, 0))

    def test_degenerate(self):
        assert fisher_exact(0, 0, 0, 0) == 1.0
        assert fisher_exact(10, 0, 10, 0) == 1.0


class TestBootstrapDiff:
    def test_identical_sides(self):
        p, lo, hi = bootstrap_diff([True] * 10, [True] * 10)
        assert (p, lo, hi) == (1.0, 0.0, 0.0)

    def test_clear_drop_is_significant(self):
        p, lo, hi = bootstrap_diff([True] * 95 + [False] * 5, [True] * 60 + [False] * 40)
        assert p < 0.01
        assert hi < 0

    def test_deterministic_with_seed(self):
        a, b = [True, False] * 20, [True, True, False] * 13
        assert bootstrap_diff(a, b, seed=7) == bootstrap_diff(a, b, seed=7)
