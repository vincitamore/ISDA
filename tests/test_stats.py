"""
Gate-statistics tests: known answers first, then the two rules.

The known-answer tests pin the arithmetic to hand-computed values so that a
formula change that alters a result fails. The remaining tests assert that a
threshold is read together with its detectability floor, and that constant
series are quarantined from the pairwise redundancy detectors.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from isda.kernel.stats import (  # noqa: E402
    null_floor, omega_squared, permutation_p, redundancy_findings, spearman,
)


# ---------- omega squared ----------

def test_omega_squared_known_answer():
    """Hand-computed: SSB=54, SSW=4, MSW=1 -> (54-1)/(54+4+1) = 53/59."""
    groups = {"a": [1.0, 2.0, 3.0], "b": [7.0, 8.0, 9.0]}
    assert omega_squared(groups) == pytest.approx(53 / 59)


def test_omega_squared_negative_bias_for_identical_groups():
    """Zero effect gives a small negative value, not zero: the unbiased
    estimator subtracts expected noise. Hand-computed: SSB=0, SSW=10, MSW=5/3
    -> -(k-1)*MSW / (SST+MSW) = -(5/3)/(35/3) = -1/7."""
    groups = {"a": [1.0, 2.0, 3.0, 4.0], "b": [1.0, 2.0, 3.0, 4.0]}
    assert omega_squared(groups) == pytest.approx(-1 / 7)


def test_omega_squared_may_be_negative():
    """ω² is reported as computed: a small negative value means an effect near
    zero, and clamping it would hide that the estimate overshot."""
    groups = {"a": [1.0, 5.0, 3.0], "b": [3.0, 1.0, 5.0], "c": [5.0, 3.0, 1.0]}
    assert omega_squared(groups) < 0


def test_omega_squared_refuses_degenerate_shapes():
    with pytest.raises(ValueError):
        omega_squared({"a": [1.0, 2.0]})


# ---------- permutation machinery ----------

def test_permutation_p_small_for_separated_groups():
    groups = {"a": [float(i) for i in range(10)],
              "b": [float(i + 100) for i in range(10)]}
    assert permutation_p(groups, n_perm=500, seed=1) < 0.01


def test_permutation_p_large_for_identical_groups():
    groups = {"a": [float(i) for i in range(10)],
              "b": [float(i) for i in range(10)]}
    assert permutation_p(groups, n_perm=500, seed=1) > 0.5


def test_null_floor_sits_below_a_real_effect_and_above_zero():
    groups = {"a": [float(i) for i in range(15)],
              "b": [float(i + 50) for i in range(15)],
              "c": [float(i + 100) for i in range(15)]}
    floor = null_floor(groups, q=0.99, n_perm=500, seed=1)
    assert 0.0 < floor < omega_squared(groups)


def test_permutation_results_are_deterministic_under_seed():
    groups = {"a": [1.0, 4.0, 2.0, 8.0], "b": [3.0, 9.0, 5.0, 7.0]}
    assert (permutation_p(groups, n_perm=200, seed=7)
            == permutation_p(groups, n_perm=200, seed=7))


# ---------- spearman ----------

def test_spearman_monotone_is_one():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert spearman(xs, [x ** 3 for x in xs]) == pytest.approx(1.0)
    assert spearman(xs, [-x for x in xs]) == pytest.approx(-1.0)


def test_spearman_handles_ties():
    assert abs(spearman([1.0, 1.0, 2.0, 3.0], [1.0, 2.0, 2.0, 3.0])) <= 1.0


def test_spearman_refuses_constant_series():
    with pytest.raises(ValueError):
        spearman([1.0, 1.0, 1.0], [1.0, 2.0, 3.0])


# ---------- redundancy detectors ----------

def test_exact_identity_detected():
    xs = [float(i) for i in range(12)]
    out = redundancy_findings({"a": xs, "b": list(xs)})
    assert any(f.kind == "exact" and f.measures == ("a", "b") for f in out)


def test_constant_ratio_detected():
    """A series that is a fixed multiple of another is one quantity under two names."""
    xs = [float(i + 1) for i in range(12)]
    out = redundancy_findings({"a": xs, "b": [x * 0.5476 for x in xs]})
    assert any(f.kind == "constant-ratio" for f in out)


def test_constant_difference_detected():
    """Additive identities evade the ratio detector: the count of adjacent
    sentence pairs always equals the count of sentences minus one, and the ratio
    between the two varies with the values."""
    xs = [float(i * 3) for i in range(12)]
    out = redundancy_findings({"a": xs, "b": [x + 5.0 for x in xs]})
    assert any(f.kind == "constant-difference" for f in out)


def test_rank_redundancy_detected_when_not_affine():
    xs = [float(i + 1) for i in range(12)]
    out = redundancy_findings({"a": xs, "b": [x ** 3 + i for i, x in enumerate(xs)]})
    assert any(f.kind == "rank" for f in out)


def test_constant_series_is_quarantined_not_paired():
    """A zero-variance series trivially satisfies ratio and difference constancy,
    so it is reported on its own and never paired with another series."""
    xs = [float(i) for i in range(12)]
    out = redundancy_findings({"a": xs, "flat": [4.0] * 12})
    assert any(f.kind == "constant" and f.measures == ("flat",) for f in out)
    assert not any(f.kind != "constant" and "flat" in f.measures for f in out)


def test_none_values_reduce_overlap_below_minimum():
    xs: list[float | None] = [float(i) for i in range(12)]
    ys: list[float | None] = list(xs)
    for i in range(0, 12, 2):
        ys[i] = None
    out = redundancy_findings({"a": xs, "b": ys}, min_overlap=10)
    assert out == []
