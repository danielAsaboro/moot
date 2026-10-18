"""The eval harness arithmetic, tested on its own: no database."""
import pytest

from moot.stats import nearest_rank, timing_summary, wilson, wilson_upper


def test_wilson_matches_known_values():
    assert wilson_upper(0, 20) == pytest.approx(0.1192, abs=1e-3)   # "0 false allows of 20" still allows ~12%
    lo, hi = wilson(2, 6)
    assert (round(lo, 3), round(hi, 3)) == (0.097, 0.700)
    assert wilson(0, 0) == (0.0, 1.0)
    lo, hi = wilson(10, 10)
    assert hi == 1.0 and lo < 1.0


def test_nearest_rank_does_not_interpolate():
    xs = [5, 1, 4, 2, 3]
    assert nearest_rank(xs, 50) == 3 and nearest_rank(xs, 95) == 5 and nearest_rank(xs, 1) == 1
    assert nearest_rank(list(range(1, 101)), 95) == 95
    with pytest.raises(ValueError):
        nearest_rank([], 50)


def test_timing_summary_drops_warmup_and_keeps_cold_apart():
    s = timing_summary([100.0, 1.0, 2.0, 3.0], warmup=1, cold_ms=250.0)
    assert s == dict(n=3, warmup=1, p50=2.0, p95=3.0, max=3.0, cold=250.0)
    assert timing_summary([1.0], cold_ms=None)["cold"] is None   # not measured is reported as such, never invented
    with pytest.raises(ValueError):
        timing_summary([1.0], warmup=1)
